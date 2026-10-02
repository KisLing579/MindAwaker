"""
任务管理系统
支持：取消任务、持久化进度、WebSocket 实时推送
"""
import asyncio
import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any, AsyncGenerator
import uuid

from app.configs.logging_config import get_logger
from app.service.pipeline_manager import getPipelineManager

logger = get_logger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class TaskInfo:
    """任务信息"""
    id: str
    project_id: str
    type: str  # "video", "audio", "image", "text"
    status: TaskStatus
    progress: int = 0
    stage: str = ""
    message: str = ""
    pipeline_status: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    result: Optional[Dict] = None
    error: Optional[str] = None


class TaskDatabase:
    """SQLite 持久化存储"""

    def __init__(self, db_path: str = "app/assets/projects/tasks.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER DEFAULT 0,
                    stage TEXT DEFAULT '',
                    message TEXT DEFAULT '',
                    pipeline_status TEXT DEFAULT '',
                    created_at TEXT DEFAULT '',
                    updated_at TEXT DEFAULT '',
                    result TEXT,
                    error TEXT
                )
            """)
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "pipeline_status" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN pipeline_status TEXT DEFAULT ''")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_project_id ON tasks(project_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)
            """)

    def save_task(self, task: TaskInfo):
        """保存或更新任务"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tasks
                (id, project_id, type, status, progress, stage, message, pipeline_status, created_at, updated_at, result, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id, task.project_id, task.type, task.status,
                task.progress, task.stage, task.message, task.pipeline_status,
                task.created_at, task.updated_at,
                json.dumps(task.result) if task.result else None,
                task.error
            ))

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row:
                return self._row_to_task(row)
        return None

    def get_project_tasks(self, project_id: str) -> List[TaskInfo]:
        """获取项目的所有任务"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,)
            ).fetchall()
            return [self._row_to_task(r) for r in rows]

    def get_running_tasks(self) -> List[TaskInfo]:
        """获取所有运行中的任务"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ?", (TaskStatus.RUNNING,)
            ).fetchall()
            return [self._row_to_task(r) for r in rows]

    def get_unfinished_tasks(self) -> List[TaskInfo]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status IN (?, ?)",
                (TaskStatus.PENDING, TaskStatus.RUNNING),
            ).fetchall()
            return [self._row_to_task(r) for r in rows]

    def _row_to_task(self, row) -> TaskInfo:
        """数据库行转 TaskInfo"""
        return TaskInfo(
            id=row[0],
            project_id=row[1],
            type=row[2],
            status=TaskStatus(row[3]),
            progress=row[4],
            stage=row[5],
            message=row[6],
            pipeline_status=row[7] or "",
            created_at=row[8],
            updated_at=row[9],
            result=json.loads(row[10]) if row[10] else None,
            error=row[11]
        )


class TaskManager:
    """
    任务管理器
    - 支持创建、取消、查询任务
    - SQLite 持久化
    - WebSocket 实时推送
    """

    def __init__(self, db_path: str = "app/assets/projects/tasks.db"):
        self.db = TaskDatabase(db_path)
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._cancel_events: Dict[str, asyncio.Event] = {}
        self._progress_callbacks: Dict[str, List[Callable]] = {}
        self._lock = asyncio.Lock()

    def recover_interrupted_tasks(self):
        """Run once at startup, before accepting jobs (single-worker service)."""
        message = "服务已重启，上次任务已中断；已保存的素材保留，请重新生成"
        interrupted = self.db.get_unfinished_tasks()
        project_ids = set()
        for task in interrupted:
            if task.id in self._running_tasks:
                continue
            task.status = TaskStatus.ERROR
            task.error = task.stage = task.message = message
            task.pipeline_status = "error"
            task.updated_at = datetime.now().isoformat()
            self.db.save_task(task)
            project_ids.add(task.project_id)
        for project_id in project_ids:
            try:
                from app.service.pipeline_manager import TASKS
                manager = getPipelineManager()
                manager._ensure_project_loaded(project_id)
                task_data = TASKS[project_id]
                task_data.pop("stop_requested", None)
                task_data.update(status="error", stage=message, error=message)
                if isinstance(task_data.get("story_review"), dict):
                    task_data["story_review"]["error"] = message
                manager.save_project(project_id)
            except Exception:
                # A missing/unwritable project must not leave its DB task busy.
                logger.exception("Failed to save interrupted project %s", project_id)
        if project_ids:
            logger.warning("Recovered interrupted tasks for %s projects", len(project_ids))

    async def create_task(
        self,
        project_id: str,
        task_type: str,
        job_func: Callable,
        *args,
        **kwargs
    ) -> str:
        """
        创建新任务
        Args:
            project_id: 项目ID
            task_type: 任务类型 (video/audio/image/text)
            job_func: 实际执行的异步函数
            *args, **kwargs: 传递给 job_func 的参数
        Returns:
            task_id: 任务唯一标识
        """
        task_id = str(uuid.uuid4())
        from app.service.pipeline_manager import TASKS
        TASKS.setdefault(project_id, {}).pop("stop_requested", None)

        # 创建任务信息
        task_info = TaskInfo(
            id=task_id,
            project_id=project_id,
            type=task_type,
            status=TaskStatus.PENDING
        )
        self.db.save_task(task_info)

        # 创建取消事件
        cancel_event = asyncio.Event()
        self._cancel_events[task_id] = cancel_event

        loop = asyncio.get_running_loop()

        def progress_cb(progress_data: Dict):
            future = asyncio.run_coroutine_threadsafe(
                self._update_progress(task_id, progress_data),
                loop,
            )
            future.add_done_callback(
                lambda completed: logger.error(
                    f"Task {task_id}: Progress callback failed: {completed.exception()}"
                ) if completed.exception() else None
            )

        # 包装任务函数
        async def _wrapped_job():
            try:
                logger.info(f"Task {task_id}: Starting execution")
                # 更新状态为运行中
                await self._update_status(task_id, TaskStatus.RUNNING)

                # 执行实际任务，传入取消事件和进度回调
                result = await job_func(
                    *args,
                    project_id=project_id,
                    cancel_event=cancel_event,
                    progress_cb=progress_cb,
                    **kwargs
                )

                if cancel_event.is_set() or (isinstance(result, dict) and result.get("status") == "cancelled"):
                    logger.info(f"Task {task_id}: Cancelled by user")
                    self._save_stopped_project(project_id)
                    await self._update_status(task_id, TaskStatus.CANCELLED)
                elif isinstance(result, dict) and result.get("status") == "error":
                    logger.info(f"Task {task_id}: Reported error result")
                    await self._fail_task(task_id, result.get("error") or "Unknown error", result=result)
                else:
                    logger.info(f"Task {task_id}: Completed successfully")
                    await self._complete_task(task_id, result)

            except asyncio.CancelledError:
                logger.info(f"Task {task_id}: Cancelled")
                self._save_stopped_project(project_id)
                await self._update_status(task_id, TaskStatus.CANCELLED)
            except Exception as e:
                if cancel_event.is_set():
                    self._save_stopped_project(project_id)
                    await self._update_status(task_id, TaskStatus.CANCELLED)
                    return
                logger.error(f"Task {task_id}: Failed with error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await self._fail_task(task_id, str(e))
            finally:
                # 清理
                logger.info(f"Task {task_id}: Cleaning up")
                async with self._lock:
                    self._running_tasks.pop(task_id, None)
                    self._cancel_events.pop(task_id, None)
                    self._progress_callbacks.pop(task_id, None)

        # 启动异步任务
        asyncio_task = asyncio.create_task(_wrapped_job())
        async with self._lock:
            self._running_tasks[task_id] = asyncio_task

        return task_id

    def _save_stopped_project(self, project_id):
        from app.service.pipeline_manager import TASKS
        task = TASKS.setdefault(project_id, {})
        task.update(status="cancelled", stage="已停止，项目已保存")
        try:
            getPipelineManager().save_project(project_id)
        except Exception:
            logger.exception("Failed to save stopped project %s", project_id)

    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        Args:
            task_id: 任务ID
        Returns:
            是否成功取消
        """
        async with self._lock:
            if task_id in self._running_tasks and task_id in self._cancel_events:
                info = self.db.get_task(task_id)
                if not info or info.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
                    return False
                self._cancel_events[task_id].set()
                from app.service.pipeline_manager import TASKS
                TASKS.setdefault(info.project_id, {})["stop_requested"] = True
            else:
                return False

        try:
            getPipelineManager().save_project(info.project_id)
        except Exception:
            logger.exception("Failed to save cancellation request for %s", info.project_id)
        # Notification also takes _lock; never await it while holding the lock.
        await self._update_progress(task_id, {"stage": "正在停止，等待当前调用结束", "message": "正在停止，等待当前调用结束"})
        # Keep the worker tracked until it exits; cancelling an await cannot
        # terminate its Python thread.
        return True

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        return self.db.get_task(task_id)

    async def get_project_tasks(self, project_id: str) -> List[TaskInfo]:
        """获取项目的所有任务"""
        return self.db.get_project_tasks(project_id)

    async def subscribe_progress(self, task_id: str) -> AsyncGenerator[Dict, None]:
        """
        订阅任务进度（WebSocket 用）
        这是一个异步生成器，会持续产出进度更新
        """
        # 注册回调
        queue: asyncio.Queue = asyncio.Queue()

        async def _callback(data: Dict):
            await queue.put(data)

        async with self._lock:
            if task_id not in self._progress_callbacks:
                self._progress_callbacks[task_id] = []
            self._progress_callbacks[task_id].append(_callback)

        try:
            # 先发送当前状态
            task = self.db.get_task(task_id)
            if task:
                logger.info(f"subscribe_progress: Initial status for task {task_id}: {task.status}, progress: {task.progress}")
                yield self._task_to_dict(task)
            else:
                logger.warning(f"subscribe_progress: Task {task_id} not found in database")

            # 持续监听更新
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=1.0)
                    logger.info(f"subscribe_progress: Got update for task {task_id}: status={data.get('status')}, progress={data.get('progress')}")
                    yield data

                    # 如果任务已结束，停止监听
                    if data.get("status") in [
                        TaskStatus.COMPLETED,
                        TaskStatus.CANCELLED,
                        TaskStatus.ERROR
                    ]:
                        logger.info(f"subscribe_progress: Task {task_id} reached terminal state, stopping")
                        break
                except asyncio.TimeoutError:
                    # 检查任务是否还存在
                    logger.debug(f"subscribe_progress: Timeout waiting for task {task_id}, checking status")
                    if task_id not in self._running_tasks:
                        task = self.db.get_task(task_id)
                        if task:
                            logger.info(f"subscribe_progress: Task {task_id} not running, yielding final status: {task.status}")
                            yield self._task_to_dict(task)
                        else:
                            logger.warning(f"subscribe_progress: Task {task_id} not found after timeout")
                        break
        finally:
            # 取消注册
            async with self._lock:
                if task_id in self._progress_callbacks:
                    callbacks = self._progress_callbacks[task_id]
                    if _callback in callbacks:
                        callbacks.remove(_callback)
                        logger.info(f"subscribe_progress: Unregistered callback for task {task_id}")

    async def _update_progress(self, task_id: str, progress_data: Dict):
        """更新任务进度"""
        task = self.db.get_task(task_id)
        if not task or task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return

        # 更新字段
        if "progress" in progress_data:
            task.progress = progress_data["progress"]
        if "stage" in progress_data:
            task.stage = progress_data["stage"]
        if "message" in progress_data:
            task.message = progress_data["message"]
        if "pipeline_status" in progress_data:
            task.pipeline_status = progress_data["pipeline_status"] or ""
        elif "status" in progress_data and progress_data["status"] not in TaskStatus._value2member_map_:
            task.pipeline_status = progress_data["status"] or ""
        task.updated_at = datetime.now().isoformat()

        # 保存到数据库
        self.db.save_task(task)

        # 通知所有订阅者
        await self._notify_subscribers(task_id, self._task_to_dict(task))

    async def _update_status(self, task_id: str, status: TaskStatus):
        """更新任务状态"""
        task = self.db.get_task(task_id)
        if task:
            task.status = status
            task.updated_at = datetime.now().isoformat()
            self.db.save_task(task)
            await self._notify_subscribers(task_id, self._task_to_dict(task))

    async def _complete_task(self, task_id: str, result: Dict):
        """标记任务完成"""
        task = self.db.get_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.progress = 100
            task.result = result
            task.updated_at = datetime.now().isoformat()
            self.db.save_task(task)
            await self._notify_subscribers(task_id, self._task_to_dict(task))

    async def _fail_task(self, task_id: str, error: str, result: Optional[Dict] = None):
        """标记任务失败"""
        task = self.db.get_task(task_id)
        if task:
            task.status = TaskStatus.ERROR
            task.error = error
            task.stage = task.message = error
            task.pipeline_status = "error"
            task.updated_at = datetime.now().isoformat()
            # Persist the terminal state before optional project/snapshot work.
            self.db.save_task(task)
            if result is not None and isinstance(result, dict):
                task.result = result
            if task.type == "video":
                try:
                    pipeline_manager = getPipelineManager()
                    pipeline_manager._ensure_project_loaded(task.project_id)
                    from app.service.pipeline_manager import TASKS
                    TASKS[task.project_id].update(status="error", stage=error, error=error)
                    if task.result is None:
                        task.result = {
                            "project_id": task.project_id,
                            "recoverable": True,
                            "snapshot": pipeline_manager.get_project_snapshot(task.project_id),
                        }
                    pipeline_manager.save_project(task.project_id)
                except Exception as save_error:
                    logger.error(f"Task {task_id}: failed to persist project after error: {save_error}")
            self.db.save_task(task)
            await self._notify_subscribers(task_id, self._task_to_dict(task))


    async def _notify_subscribers(self, task_id: str, data: Dict):
        """通知所有订阅者"""
        async with self._lock:
            callbacks = list(self._progress_callbacks.get(task_id, []))
        for callback in callbacks:
            try:
                await callback(data)
            except Exception:
                pass  # 忽略通知失败

    def _task_to_dict(self, task: TaskInfo) -> Dict:
        """TaskInfo 转字典"""
        return {
            "id": task.id,
            "project_id": task.project_id,
            "type": task.type,
            "status": task.status,
            "progress": task.progress,
            "stage": task.stage,
            "message": task.message,
            "pipeline_status": task.pipeline_status,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "result": task.result,
            "error": task.error
        }


# 全局任务管理器实例
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """获取任务管理器单例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
