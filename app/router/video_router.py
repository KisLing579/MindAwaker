"""
视频生成路由 - 支持取消、WebSocket 实时进度
"""
import asyncio
from typing import Callable
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from app.model.video_schema import VideoRequest
from app.service.task_manager import get_task_manager, TaskStatus
from app.configs.logging_config import get_logger
from app.service.pipeline_manager import getPipelineManager

router = APIRouter()
logger = get_logger(__name__)

# 获取 PipelineManager 实例
pipeline_manager = getPipelineManager()

async def generate_video_with_pipeline(project_id: str, config: dict, cancel_event: asyncio.Event, progress_cb: Callable[[dict], None]):
    """包装函数，调用 pipeline_manager 的异步视频生成方法"""
    return await pipeline_manager.async_generate_video(
        project_id=project_id,
        config=config,
        cancel_event=cancel_event,
        progress_cb=progress_cb
    )


async def rebuild_video_with_pipeline(project_id: str, cancel_event: asyncio.Event, progress_cb: Callable[[dict], None]):
    """包装函数，调用 pipeline_manager 的异步视频重建方法"""
    return await pipeline_manager.async_rebuild_video(
        project_id=project_id,
        cancel_event=cancel_event,
        progress_cb=progress_cb,
    )


async def rebuild_dirty_clips_with_pipeline(project_id: str, cancel_event: asyncio.Event, progress_cb: Callable[[dict], None]):
    """包装函数，调用 pipeline_manager 的异步脏片段重建方法"""
    return await pipeline_manager.async_rebuild_dirty_clips(
        project_id=project_id,
        cancel_event=cancel_event,
        progress_cb=progress_cb,
    )


async def concat_clips_with_pipeline(project_id: str, cancel_event: asyncio.Event, progress_cb: Callable[[dict], None]):
    """包装函数，调用 pipeline_manager 的异步片段拼接方法"""
    return await pipeline_manager.async_concat_video_clips(
        project_id=project_id,
        cancel_event=cancel_event,
        progress_cb=progress_cb,
    )


@router.post("/compose")
async def create_video_task(request: VideoRequest, project_id: str = ""):
    """
    创建视频生成任务

    输入：
        - theme: 文案主题
        - text_model_name: 文本模型
        - text_api_key: API Key
        - style: 写作风格
        - image_model_name: 图像模型
        - image_api_key: 图像API Key
        - audio_model_name: 音频模型
        - audio_api_key: 音频API Key
        - voice: 音色
        - n: 图像数量
        - size: 图像尺寸

    输出：
        - task_id: 任务ID (用于查询进度和取消)
        - status: 任务状态
        - project_id: 项目ID
    """
    task_manager = get_task_manager()

    # 如果没有项目ID，创建一个临时项目
    if not project_id:
        from app.service.pipeline_manager import getPipelineManager
        pipeline_manager = getPipelineManager()
        project_id = pipeline_manager.create_project(name="video_task", target="video")


    # 创建配置字典
    config = {
        "theme": request.theme,
        "style": request.style,
        "language": request.language,
        "text_model_name": request.text_model_name,
        "text_api_key": request.text_api_key,
        "image_model_name": request.image_model_name,
        "image_api_key": request.image_api_key,
        "audio_model_name": request.audio_model_name,
        "audio_api_key": request.audio_api_key,
        "voice": request.voice,
        "article": request.article,
        "n": request.n,
        "size": request.size,
        "with_media_prompts": request.with_media_prompts,
        "media_prompt_style": request.media_prompt_style,
    }
    print("article======>",config["article"])
    # 创建异步任务
    task_id = await task_manager.create_task(
        project_id=project_id,
        task_type="video",
        job_func=generate_video_with_pipeline,
        config=config
    )

    return {
        "task_id": task_id,
        "project_id": project_id,
        "status": "started",
        "message": "视频生成任务已启动，请通过 WebSocket 或轮询接口获取进度"
    }


@router.post("/cancel/{task_id}")
async def cancel_video_task(task_id: str):
    """
    取消视频生成任务

    输入：
        - task_id: 任务ID

    输出：
        - cancelled: 是否成功取消
        - task_id: 任务ID
    """
    task_manager = get_task_manager()

    # 获取任务信息
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 只有运行中的任务可以取消
    if task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
        return {
            "cancelled": False,
            "task_id": task_id,
            "message": f"任务状态为 {task.status}，无法取消"
        }

    # 执行取消
    success = await task_manager.cancel_task(task_id)

    return {
        "cancelled": success,
        "task_id": task_id,
        "message": "已保存项目，正在停止当前操作" if success else "停止失败"
    }


@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """
    获取任务状态

    输入：
        - task_id: 任务ID

    输出：
        - 完整任务信息，包括进度、状态、结果等
    """
    task_manager = get_task_manager()
    task = await task_manager.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "task_id": task.id,
        "project_id": task.project_id,
        "type": task.type,
        "status": task.status,
        "pipeline_status": task.pipeline_status,
        "progress": task.progress,
        "stage": task.stage,
        "message": task.message,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "result": task.result,
        "error": task.error,
        "done": task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.ERROR]
    }


@router.get("/project/{project_id}/tasks")
async def get_project_tasks(project_id: str):
    """
    获取项目的所有任务

    输入：
        - project_id: 项目ID

    输出：
        - tasks: 任务列表
    """
    task_manager = get_task_manager()
    tasks = await task_manager.get_project_tasks(project_id)

    return {
        "project_id": project_id,
        "tasks": [
            {
                "task_id": t.id,
                "type": t.type,
                "status": t.status,
                "pipeline_status": t.pipeline_status,
                "progress": t.progress,
                "stage": t.stage,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in tasks
        ]
    }


@router.websocket("/ws/{task_id}")
async def task_websocket(websocket: WebSocket, task_id: str):
    """
    WebSocket 实时获取任务进度

    连接后，服务器会实时推送：
        - 进度更新 (progress)
        - 阶段更新 (stage)
        - 状态更新 (status)
        - 最终结果 (result) 或错误 (error)

    当任务完成、取消或出错时，连接会自动关闭
    """
    await websocket.accept()
    task_manager = get_task_manager()

    # 先检查任务是否存在
    task = await task_manager.get_task(task_id)
    if not task:
        await websocket.send_json({"error": "Task not found", "task_id": task_id})
        await websocket.close()
        return

    logger.info(f"WebSocket connected for task {task_id}, current status: {task.status}")

    try:
        # 订阅进度更新
        async for data in task_manager.subscribe_progress(task_id):
            logger.info(f"Sending progress update for task {task_id}: status={data.get('status')}, progress={data.get('progress')}")
            await websocket.send_json(data)

            # 如果任务已结束，关闭连接
            if data.get("status") in [
                TaskStatus.COMPLETED,
                TaskStatus.CANCELLED,
                TaskStatus.ERROR
            ]:
                logger.info(f"Task {task_id} reached terminal state {data.get('status')}, closing WebSocket")
                await websocket.close()
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task {task_id}")
    except Exception as e:
        logger.error(f"WebSocket error for task {task_id}: {e}")
        await websocket.send_json({"error": str(e)})
        await websocket.close()
