"""Project-scoped story review API, with optimistic revisions and stage locks."""
from contextlib import contextmanager
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.model.video_schema import VideoRequest
from app.service.pipeline_manager import getPipelineManager, TASKS
from app.service.task_manager import get_task_manager
from app.service.story_review import (ReviewConflict, project_lock, manager_for, read_review,
                                      save_review, compile_review, stage_job)

router = APIRouter()


class ChapterRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    source_text: str = Field(min_length=1, max_length=2000000)
    mode: Literal["generate", "review"] = "generate"


@router.get("/{project_id}/chapters")
def list_chapters(project_id: str):
    try:
        manager = manager_for(project_id)
        project = manager.projects[project_id]
        return {"chapters": project.get("chapters") or [{"id": "original", "title": "原始章节"}],
                "active_chapter": project.get("active_chapter") or "original"}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.get("/{project_id}/scene-studio")
def scene_studio_project(project_id: str):
    try:
        manager = manager_for(project_id)
        return {"project_path": str(manager._project_dir(project_id).resolve())}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/{project_id}/chapters")
async def append_chapter(project_id: str, request: ChapterRequest):
    from app.service.story_chapters import create_chapter
    try:
        with editing(project_id):
            project = create_chapter(manager_for(project_id), project_id, request.title, request.source_text)
        if request.mode == "review":
            return {"project_id": project_id, "loaded": True, "project": project}
        # One task owns the lock through analysis, missing media and composition.
        started = await start_stage(project_id, StageRequest(
            revision=project["task_data"]["story_review"]["revision"], stage="pipeline"))
        return {"project_id": project_id, "loaded": True, "project": project,
                "task_id": started["task_id"]}
    except ReviewConflict as exc:
        raise HTTPException(409, str(exc))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/{project_id}/chapters/{chapter_id}/load")
def load_chapter(project_id: str, chapter_id: str):
    from app.service.story_chapters import select_chapter
    try:
        with editing(project_id):
            project = select_chapter(manager_for(project_id), project_id, chapter_id)
        return {"project_id": project_id, "loaded": True, "project": project}
    except ReviewConflict as exc:
        raise HTTPException(409, str(exc))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


class EditRequest(BaseModel):
    revision: int
    source_text: str
    items: dict
    scenes: list = Field(default_factory=list)
    style_tokens: str


class StageRequest(BaseModel):
    revision: int
    stage: Literal["items", "scenes", "shots", "media", "images", "audio", "redraw", "clip", "compose", "pipeline"]
    shot_id: Optional[str] = None


class SelectionRequest(BaseModel):
    revision: int
    shot_id: str
    history_index: int


class ClipConfigRequest(BaseModel):
    clip_mode: Literal["static", "jimeng"] = "static"
    clip_video_prompt: str = Field("", max_length=800)


@router.put("/{project_id}/clip-config")
def update_clip_config(project_id: str, request: ClipConfigRequest):
    try:
        with editing(project_id):
            manager = manager_for(project_id)
            config = manager._normalize_config_for_save(manager.projects[project_id]["config"])
            changed = any(config.get(key, "static" if key == "clip_mode" else "") != value
                          for key, value in request.model_dump().items())
            config.update(request.model_dump())
            manager.update_config(project_id, config)
            if changed:
                clips = manager._sync_clips_from_assets(project_id)
                manager._mark_clips_dirty(project_id, list(range(len(clips))))
                TASKS[project_id].pop("video_path", None)
            manager.save_project(project_id)
        return {"project": manager.get_project_snapshot(project_id)}
    except ReviewConflict as exc:
        raise HTTPException(409, str(exc))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


def idle(project_id):
    if any(t.status in ("pending", "running") for t in get_task_manager().db.get_project_tasks(project_id)):
        raise ReviewConflict("项目有正在运行的任务，请等待完成后再编辑")


@contextmanager
def editing(project_id):
    lock = project_lock(project_id)
    if not lock.acquire(blocking=False):
        raise ReviewConflict("当前项目正在生成或保存，请稍后重试")
    try:
        idle(project_id)
        yield
    finally:
        lock.release()


@router.post("/start")
def start_review(request: VideoRequest):
    if request.style != "story" or not (request.article or "").strip():
        raise HTTPException(400, "分阶段编辑需要故事模式和故事原文")
    manager = getPipelineManager()
    project_id = manager.create_project("story_review", "video")
    manager.update_config(project_id, request.model_dump())
    document = read_review(project_id)
    save_review(project_id, document, 0)
    return {"project_id": project_id}


@router.get("/{project_id}")
def get_review(project_id: str):
    try:
        manager = manager_for(project_id)
        document = read_review(project_id)
        tasks = get_task_manager().db.get_project_tasks(project_id)
        active = next((t for t in tasks if t.status in ("pending", "running")), None)
        return {"document": document, "project": manager.get_project_snapshot(project_id),
                "busy": project_lock(project_id).locked() or active is not None,
                "task_id": active.id if active else None}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc))


@router.put("/{project_id}")
def update_review(project_id: str, request: EditRequest):
    try:
        with editing(project_id):
            document = save_review(project_id, request.model_dump(), request.revision)
        return {"document": document}
    except ReviewConflict as exc:
        raise HTTPException(409, str(exc))
    except (ValueError, KeyError, TypeError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/{project_id}/preview")
def preview_review(project_id: str, request: EditRequest):
    try:
        manager_for(project_id)
        return {"segments": compile_review(request.model_dump())["segments"]}
    except (ValueError, KeyError, TypeError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/{project_id}/stage")
async def start_stage(project_id: str, request: StageRequest):
    acquired = False
    try:
        lock = project_lock(project_id)
        acquired = lock.acquire(blocking=False)
        if not acquired:
            raise ReviewConflict("当前项目正在运行，请等待完成")
        idle(project_id)
        document = read_review(project_id)
        if document["revision"] != request.revision:
            raise ReviewConflict("内容已更新，请重新加载")
        task_id = await get_task_manager().create_task(project_id=project_id, task_type="video", job_func=stage_job,
                                                     stage=request.stage, shot_id=request.shot_id)
        acquired = False  # The job owns the lock through completion/cancellation.
        return {"task_id": task_id, "project_id": project_id}
    except ReviewConflict as exc:
        raise HTTPException(409, str(exc))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))
    finally:
        if acquired:
            lock.release()


@router.post("/{project_id}/selection")
def select_image(project_id: str, request: SelectionRequest):
    try:
        with editing(project_id):
            manager = manager_for(project_id)
            document = read_review(project_id)
            if document["revision"] != request.revision:
                raise ReviewConflict("内容已更新，请重新加载")
            segments = compile_review(document)["segments"]
            index = next((i for i, s in enumerate(segments) if s["shot_id"] == request.shot_id), None)
            if index is None:
                raise ValueError("找不到分镜")
            if request.history_index < 0:
                raise ValueError("无效的历史版本")
            candidate = TASKS[project_id]["image_redraw_history"][index][request.history_index]
            manager.apply_redraw_selection(project_id, image_selected_history={str(index): request.history_index})
            # Applying an old image does not replace the edited structured plan.
            TASKS[project_id]["images_configs"] = []
            manager._restore_story_inputs(project_id, segments)
            # Submission is explicit acceptance, including an older candidate.
            document["dirty_images"] = [i for i in document["dirty_images"] if i != index]
            document["revision"] += 1
            TASKS[project_id]["story_review"] = document
            manager.save_project(project_id)
        return {"document": document}
    except ReviewConflict as exc:
        raise HTTPException(409, str(exc))
    except (ValueError, IndexError, KeyError, TypeError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))
