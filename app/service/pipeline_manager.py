from app.configs.credentials import clear_legacy_credentials
import time, os, ffmpeg
import asyncio
import logging
from time import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

# 从环境变量读取 HF 缓存路径，使用默认值
# def setup_hf_env():
#     """设置 HuggingFace 环境变量"""
    # # 默认缓存路径 (项目根目录下的 cache 文件夹)
    # default_cache = Path(__file__).parent.parent.parent / "cache" / "huggingface"
    # default_cache.mkdir(parents=True, exist_ok=True)

    # os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    # os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    # os.environ.setdefault("HF_HOME", str(default_cache))
    # os.environ.setdefault("HF_HUB_CACHE", str(default_cache))
    # os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(default_cache))
    # os.environ.setdefault("TRANSFORMERS_CACHE", str(default_cache))


# setup_hf_env()
import json
import re
from pathlib import Path
from uuid import uuid4
from typing import Dict, Any, Callable, List, Optional

from app.service.dependencies import (
    get_text_service,
    get_audio_service,
    get_image_service,
    get_subtitle_service,
)
from app.service.story_pipeline import run_story_pipeline
from app.model.story_visual_schema import StoryVisualSession, ShotRenderPrompt, ShotRenderRequest
from app.utils.config_loader import get_default_language
from app.utils.language_utils import resolve_language
# import torch

import subprocess
import shlex


class Project:
    id: str  # project_id
    name: str
    target: str  # "text" | "audio" | "image" | "video" | "custom"
    # status: str           # "draft" | "in_progress" | "completed"
    config: dict  # 选用的模型、风格等
    created_at: time
    updated_at: time


textGenerationService = get_text_service()
imageGenerationService = get_image_service()
audioGenerationService = get_audio_service()
sub = get_subtitle_service()
# storyPromptPipeline = get_story_prompt_pipeline()
targets = ["text", "audio", "image", "video", "custom"]
all_status = [
    "draft",
    "in_text_progress",
    "in_building_characters",
    "in_building_scenes",
    "in_audio_progress",
    "in_image_progress",
    "in_video_progress",
    "in_video_rebuild",
    "in_video_concat",
    "completed",
    "error",
    "block",
]


TASKS = {}  # 简单用内存字典保存进度，生产可换为 Redis 等
SETTINGS = {}
PROGRESS_CALLBACKS = {}  # project_id -> progress callback function
logger = logging.getLogger(__name__)


def register_progress_callback(project_id: str, callback):
    """注册进度回调函数，当 update_progress 被调用时触发"""
    PROGRESS_CALLBACKS[project_id] = callback


def unregister_progress_callback(project_id: str):
    """注销进度回调函数"""
    PROGRESS_CALLBACKS.pop(project_id, None)


def update_progress(project_id: str, percent: int, stage: str):
    print("percent:", percent, ", stage:", stage)
    TASKS[project_id]["percent"] = percent
    TASKS[project_id]["stage"] = stage
    pipeline_status = TASKS[project_id].get("status", "")

    # 调用进度回调（如果已注册）
    if project_id in PROGRESS_CALLBACKS:
        try:
            PROGRESS_CALLBACKS[project_id](
                {
                    "project_id": project_id,
                    "progress": percent,
                    "percent": percent,
                    "stage": stage,
                    "message": stage,
                    "pipeline_status": pipeline_status,
                }
            )
        except Exception as e:
            print(f"进度回调调用失败: {e}")


def emit_progress_status(project_id: str, status: str, stage: Optional[str] = None, percent: Optional[int] = None):
    set_progress_status(project_id=project_id, status=status)
    payload = {
        "project_id": project_id,
        "pipeline_status": TASKS[project_id].get("status", ""),
        "progress": TASKS[project_id].get("percent", 0),
        "percent": TASKS[project_id].get("percent", 0),
        "stage": TASKS[project_id].get("stage", ""),
        "message": TASKS[project_id].get("stage", ""),
    }
    if percent is not None:
        TASKS[project_id]["percent"] = percent
        payload["progress"] = percent
        payload["percent"] = percent
    if stage is not None:
        TASKS[project_id]["stage"] = stage
        payload["stage"] = stage
        payload["message"] = stage

    if project_id in PROGRESS_CALLBACKS:
        try:
            PROGRESS_CALLBACKS[project_id](payload)
        except Exception as e:
            print(f"状态回调调用失败: {e}")




def set_progress_data(project_id: str, key: str, data: Any):
    TASKS[project_id][key] = data


def set_progress_data_with_index(project_id: str, key: str, index: int, data: Any):
    # if index < len(TASKS[project_id][key]):
    TASKS[project_id][key][index] = data


def get_progress_data(project_id: str, key: str):
    return TASKS[project_id].get(key)


def get_progress_data_len(project_id: str, key: str):
    return len(TASKS[project_id].get(key))


def get_progress_data_with_index(project_id: str, key: str, index: int):
    if index < len(TASKS[project_id][key]):
        return TASKS[project_id][key][index]


def set_progress_status(project_id: str, status: str):
    if status not in all_status:
        status = "unknown status"
    TASKS[project_id]["status"] = status


def get_progress_status(project_id: str):
    return TASKS[project_id].get("status")


def update_audio_task_config(project_id: str, config: dict, index: int):
    TASKS[project_id]["audios_configs"][index] = config


def update_image_task_config(project_id: str, config: dict, index: int):
    TASKS[project_id]["images_configs"][index] = config


def update_text_task_config(project_id: str, config: dict):
    TASKS[project_id]["text_config"] = config


class PipelineManager:
    REDRAW_HISTORY_LIMIT = 4

    def __init__(self, base_dir: str = "app/assets/projects"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self.projects: Dict[str, Dict[str, Any]] = {}  # 也可以只存 meta，把详细的放文件里

    def _normalize_config_for_save(self, config: Any):
        if config is None:
            return None
        if isinstance(config, dict):
            return config
        if hasattr(config, "model_dump"):
            return config.model_dump()
        if hasattr(config, "dict"):
            return config.dict()
        return config

    def _get_project_language(self, project_id: str, text: str = "", requested_language: Optional[str] = None) -> str:
        project = self.projects.get(project_id, {})
        config = project.get("config") or {}
        default_language = get_default_language()
        if isinstance(config, dict):
            configured_language = config.get("language") or config.get("default_language")
        else:
            configured_language = getattr(config, "language", None) or getattr(config, "default_language", None)
        return resolve_language(text=text, requested_language=requested_language or configured_language, default_language=default_language)

    def _get_config_value(self, config: Any, key: str, default: Any = ""):
        if isinstance(config, dict):
            value = config.get(key, default)
        else:
            value = getattr(config, key, default)
        return default if value is None else value

    def _get_project_config_value(self, project_id: str, key: str, default: Any = ""):
        config = self.projects.get(project_id, {}).get("config") or {}
        return self._get_config_value(config, key, default)



    def _project_meta_path(self, project_id: str) -> Path:
        return self.base_dir / project_id / "meta.json"

    def _project_dir(self, project_id: str) -> Path:
        root = self.base_dir / project_id
        chapter = self.projects.get(project_id, {}).get("active_chapter")
        return root / "chapters" / chapter if chapter and chapter != "original" else root

    def _artifacts_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "artifacts"

    def _artifact_section_dir(self, project_id: str, section: str) -> Path:
        return self._prepare_output_dir(self._artifacts_dir(project_id) / section)

    def _to_serializable(self, value: Any):
        if isinstance(value, dict):
            return {str(k): self._to_serializable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._to_serializable(v) for v in value]
        if hasattr(value, "model_dump"):
            return self._to_serializable(value.model_dump())
        if hasattr(value, "dict"):
            return self._to_serializable(value.dict())
        return value

    def _register_artifact(self, project_id: str, section: str, key: str, value: Any):
        task_data = TASKS.setdefault(project_id, {})
        artifacts = task_data.setdefault("artifacts", {})
        section_map = artifacts.setdefault(section, {})
        section_map[key] = value

    def _write_artifact_text(self, project_id: str, section: str, filename: str, content: str, key: Optional[str] = None) -> str:
        directory = self._artifact_section_dir(project_id, section)
        path = directory / filename
        path.write_text(content or "", encoding="utf-8")
        relative_path = str(path.relative_to(self._project_dir(project_id))).replace("\\", "/")
        self._register_artifact(project_id, section, key or filename, relative_path)
        return relative_path

    def _write_artifact_json(self, project_id: str, section: str, filename: str, data: Any, key: Optional[str] = None) -> str:
        directory = self._artifact_section_dir(project_id, section)
        path = directory / filename
        serializable = self._to_serializable(data)
        path.write_text(json.dumps(serializable, indent=4, ensure_ascii=False), encoding="utf-8")
        relative_path = str(path.relative_to(self._project_dir(project_id))).replace("\\", "/")
        self._register_artifact(project_id, section, key or filename, relative_path)
        return relative_path


    def _persist_story_artifacts(self, project_id: str, story_result: Dict[str, Any]):
        self._write_artifact_json(project_id, "story", "characters.json", story_result.get("characters", []), key="characters_json")
        self._write_artifact_json(project_id, "story", "character_specs.json", story_result.get("character_specs", []), key="character_specs_json")
        self._write_artifact_json(project_id, "story", "items.json", story_result.get("items", {}), key="items_json")
        self._write_artifact_json(project_id, "story", "scenes.json", story_result.get("scenes", []), key="scenes_json")
        self._write_artifact_json(project_id, "story", "world_scenes.json", story_result.get("world_scenes", []), key="world_scenes_json")
        self._write_artifact_json(project_id, "story", "scene_to_world_scene.json", story_result.get("scene_to_world_scene", {}), key="scene_to_world_scene_json")
        self._write_artifact_json(project_id, "story", "shots.json", story_result.get("shots", []), key="shots_json")
        self._write_artifact_json(project_id, "story", "segments.json", story_result.get("segments", []), key="segments_json")
        self._write_artifact_json(project_id, "story", "anchor_store.json", story_result.get("anchor_store", {}), key="anchor_store_json")
        self._register_artifact(project_id, "story", "scene_count", story_result.get("scene_count", 0))
        self._register_artifact(project_id, "story", "world_scene_count", story_result.get("world_scene_count", 0))
        self._register_artifact(project_id, "story", "shot_count", story_result.get("shot_count", 0))

    def _build_story_visual_session(
        self,
        project_id: str,
        story_result: Dict[str, Any],
        character_result: Dict[str, Any],
        scene_result: Dict[str, Any],
    ) -> StoryVisualSession:
        character_bindings = {
            item.get("source_character_id"): item.get("mw_character_id")
            for item in character_result.get("characters", [])
            if item.get("source_character_id") and item.get("mw_character_id")
        }
        scene_bindings = {}
        for item in scene_result.get("scenes", []):
            world_scene_id = item.get("world_scene_id") or item.get("source_scene_id") or item.get("scene_id")
            mw_scene_instance_id = item.get("mw_scene_instance_id") or item.get("scene_instance_id") or item.get("mw_scene_id")
            if world_scene_id and mw_scene_instance_id:
                scene_bindings[world_scene_id] = mw_scene_instance_id
        return StoryVisualSession(
            project_id=project_id,
            style_id="default",
            character_bindings=character_bindings,
            scene_bindings=scene_bindings,
            raw_character_mappings=character_result.get("characters", []),
            raw_scene_mappings=scene_result.get("scenes", []),
        )

    def _persist_story_visual_session(self, project_id: str, session: StoryVisualSession):
        set_progress_data(project_id=project_id, key="story_visual_session", data=session.model_dump())
        self._write_artifact_json(
            project_id,
            "story",
            "story_visual_session.json",
            session,
            key="story_visual_session_json",
        )
        return session

    def _load_story_visual_session(self, project_id: str) -> Optional[StoryVisualSession]:
        session_data = get_progress_data(project_id=project_id, key="story_visual_session")
        if session_data:
            return StoryVisualSession(**session_data)
        artifacts = (TASKS.get(project_id, {}) or {}).get("artifacts", {}).get("story", {})
        session_rel = artifacts.get("story_visual_session_json")
        if not session_rel:
            return None
        session_path = self._project_dir(project_id) / session_rel
        if not session_path.exists():
            return None
        return StoryVisualSession(**json.loads(session_path.read_text(encoding="utf-8")))

    def _prepare_story_world(self, project_id: str, image_model_name: str, image_api_key: str, story_result: Dict[str, Any]):
        character_specs = story_result.get("character_specs", [])
        scene_specs = story_result.get("world_scenes", [])
        if not character_specs and not scene_specs:
            return {"success": True, "characters": {}, "scenes": {}}

        if not imageGenerationService.ensure_engine(image_model_name=image_model_name, image_api_key=image_api_key):
            return {"success": False, "error": "创建 mw 图像引擎失败"}
        if not imageGenerationService.supports_story_world_preparation():
            return {"success": True, "characters": {}, "scenes": {}}

        set_progress_status(project_id=project_id, status="in_building_characters")
        update_progress(project_id=project_id, percent=55, stage="正在构建故事角色")
        character_result = imageGenerationService.build_characters(character_specs)
        if not character_result.get("success"):
            return {"success": False, "error": "mw 构建角色失败", "detail": character_result}

        character_mapping = {
            item.get("source_character_id"): item.get("mw_character_id")
            for item in character_result.get("characters", [])
            if item.get("source_character_id") and item.get("mw_character_id")
        }

        enriched_scene_specs = []
        for scene_spec in scene_specs:
            scene_copy = dict(scene_spec)
            object_bindings = {}
            for character_id in scene_copy.get("characters_in_scene", []):
                if character_id in character_mapping:
                    object_bindings[character_id] = character_mapping[character_id]
            scene_copy["character_bindings"] = object_bindings
            enriched_scene_specs.append(scene_copy)

        set_progress_status(project_id=project_id, status="in_building_scenes")
        update_progress(project_id=project_id, percent=65, stage="正在构建固定场景")
        scene_result = imageGenerationService.build_scenes(enriched_scene_specs, character_mapping)
        if not scene_result.get("success"):
            return {"success": False, "error": "mw 构建场景失败", "detail": scene_result}

        set_progress_data(project_id=project_id, key="story_character_mappings", data=character_result.get("characters", []))
        set_progress_data(project_id=project_id, key="story_scene_mappings", data=scene_result.get("scenes", []))
        self._write_artifact_json(project_id, "story", "mw_character_mappings.json", character_result.get("characters", []), key="mw_character_mappings_json")
        self._write_artifact_json(project_id, "story", "mw_scene_mappings.json", scene_result.get("scenes", []), key="mw_scene_mappings_json")
        self._register_artifact(project_id, "story", "mw_character_count", len(character_result.get("characters", [])))
        self._register_artifact(project_id, "story", "mw_scene_count", len(scene_result.get("scenes", [])))
        session = self._build_story_visual_session(project_id, story_result, character_result, scene_result)
        self._persist_story_visual_session(project_id, session)
        return {"success": True, "characters": character_result, "scenes": scene_result, "story_visual_session": session.model_dump()}

    def _restore_story_world_if_needed(self, project_id: str, image_model_name: str, image_api_key: str):
        session = self._load_story_visual_session(project_id)
        if session is not None:
            set_progress_data(project_id=project_id, key="story_character_mappings", data=session.raw_character_mappings)
            set_progress_data(project_id=project_id, key="story_scene_mappings", data=session.raw_scene_mappings)
            set_progress_data(project_id=project_id, key="story_visual_session", data=session.model_dump())
            return True

        artifacts = (TASKS.get(project_id, {}) or {}).get("artifacts", {}).get("story", {})
        if get_progress_data(project_id=project_id, key="story_character_mappings") and get_progress_data(project_id=project_id, key="story_scene_mappings"):
            return True
        character_specs_rel = artifacts.get("character_specs_json")
        world_scenes_rel = artifacts.get("world_scenes_json")
        if not character_specs_rel and not world_scenes_rel:
            return True
        base_dir = self._project_dir(project_id)
        story_result = {
            "character_specs": json.loads((base_dir / character_specs_rel).read_text(encoding="utf-8")) if character_specs_rel else [],
            "world_scenes": json.loads((base_dir / world_scenes_rel).read_text(encoding="utf-8")) if world_scenes_rel else [],
        }
        result = self._prepare_story_world(project_id, image_model_name, image_api_key, story_result)
        if not result.get("success"):
            raise ValueError(result.get("error") or "恢复 story world 失败")
        return True

    def _build_shot_render_request(
        self,
        project_id: str,
        segment: Dict[str, Any],
        size: str,
        n: int,
    ) -> ShotRenderRequest:
        session = self._load_story_visual_session(project_id)
        return ShotRenderRequest(
            story_session=session,
            scene_ref=segment.get("world_scene_id") or segment.get("scene_id", ""),
            character_refs=segment.get("focus_characters", []),
            shot_id=segment.get("shot_id") or f"shot_{segment.get('shot_idx', 0)}",
            shot={
                "scene_id": segment.get("scene_id", ""),
                "shot_idx": segment.get("shot_idx", 0),
                "text": segment.get("text", ""),
            },
            prompt=ShotRenderPrompt(positive=segment.get("image_prompt", ""), negative=""),
            size=size,
            n=n,
        )

    def render_story_shot(
        self,
        project_id: str,
        segment: Dict[str, Any],
        model_name: str,
        api_key: str,
        size: str,
        n: int,
    ):
        shot_id = segment.get("shot_id") or f"shot_{segment.get('shot_idx', 0)}"
        scene_ref = segment.get("world_scene_id") or segment.get("scene_id", "")
        print(f"[PipelineManager.render_story_shot] start project_id={project_id} shot_id={shot_id} scene_ref={scene_ref}")
        if not imageGenerationService.ensure_engine(image_model_name=model_name, image_api_key=api_key):
            return self._image_result(False, error="创建 mw 图像引擎失败")
        if not imageGenerationService.supports_shot_render():
            print(f"[PipelineManager.render_story_shot] engine lacks shot render, fallback to gen_image shot_id={shot_id}")
            return self.gen_image(
                project_id=project_id,
                text=segment.get("image_prompt", ""),
                model_name=model_name,
                api_key=api_key,
                n=n,
                size=size,
            )
        request = self._build_shot_render_request(project_id, segment, size, n)
        response = imageGenerationService.render_shot(request)
        if not response.success:
            print(f"[PipelineManager.render_story_shot] failed shot_id={shot_id} error={response.error}")
            return self._image_result(False, error=response.error)
        print(f"[PipelineManager.render_story_shot] success shot_id={shot_id} image_paths={response.image_paths}")
        return self._image_result(True, image_paths=response.image_paths)

    def _story_result(self, success: bool, error: Optional[str] = None, **kwargs):
        result = {"success": success, "error": error}
        result.update(kwargs)
        return result


    def _text_result(self, success: bool, error: Optional[str] = None, content: str = "", prompts: Optional[List[str]] = None):
        return {
            "success": success,
            "error": error,
            "content": content or "",
            "prompts": prompts or [],
        }

    def _audio_result(self, success: bool, error: Optional[str] = None, audio_path: str = "", duration: float = 0):
        return {
            "success": success,
            "error": error,
            "audio_path": audio_path or "",
            "duration": duration or 0,
        }

    def _image_result(self, success: bool, error: Optional[str] = None, image_paths: Optional[List[str]] = None):
        return {
            "success": success,
            "error": error,
            "image_paths": image_paths or [],
        }

    def _audio_sequence_result(
        self,
        success: bool,
        error: Optional[str] = None,
        audios: Optional[List[str]] = None,
        durations: Optional[List[float]] = None,
        cancelled: bool = False,
    ):
        return {
            "success": success,
            "error": error,
            "audios": audios or [],
            "durations": durations or [],
            "cancelled": cancelled,
        }

    def _image_sequence_result(
        self,
        success: bool,
        error: Optional[str] = None,
        images: Optional[List[str]] = None,
        cancelled: bool = False,
    ):
        return {
            "success": success,
            "error": error,
            "images": images or [],
            "cancelled": cancelled,
        }

    def _video_result(
        self,
        success: bool,
        error: Optional[str] = None,
        video_path: str = "",
        cancelled: bool = False,
        **kwargs,
    ):
        result = {
            "success": success,
            "error": error,
            "video_path": video_path or "",
            "cancelled": cancelled,
        }
        result.update(kwargs)
        return result

    def _set_project_error(self, project_id: str, error: str):
        task_data = TASKS.setdefault(project_id, {})
        task_data["error"] = error
        set_progress_data(project_id=project_id, key="errors", data=error)
        if task_data.get("status") != "completed":
            set_progress_status(project_id=project_id, status="error")

    def _persist_project_failure(self, project_id: str, error: str):
        self._set_project_error(project_id, error)
        try:
            self.save_project(project_id)
        except Exception as save_error:
            print(f"[persist_project_failure] save_project failed for {project_id}: {save_error}")

    def _build_partial_video_payload(self, project_id: str):
        task_data = TASKS.get(project_id, {})
        payload = {
            "text": task_data.get("text", ""),
            "lines": task_data.get("lines", []),
            "prompts": task_data.get("prompts", []),
            "images": task_data.get("images", []),
            "audios": task_data.get("audios", []),
            "durations": task_data.get("durations", []),
            "images_configs": task_data.get("images_configs", []),
            "audios_configs": task_data.get("audios_configs", []),
            "clips": task_data.get("clips", []),
            "video_segments": task_data.get("video_segments", []),
            "shot_texts": task_data.get("shot_texts", []),
            "scene_segment_files": task_data.get("scene_segment_files", []),
        }
        return payload

    def _cancelled_video_result(self, project_id: str):
        return self._video_result(False, error="任务已取消", cancelled=True, **self._build_partial_video_payload(project_id))

    def _failed_video_result(self, project_id: str, error: str):
        self._set_project_error(project_id, error)
        return self._video_result(False, error=error, **self._build_partial_video_payload(project_id))

    def _video_result_with_assets(self, success: bool, project_id: str, video_path: str = "", error: Optional[str] = None):
        return self._video_result(success, error=error, video_path=video_path, **self._build_partial_video_payload(project_id))


    def _video_segments_root_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "video_segments"

    def _video_segments_mode_dir(self, project_id: str, mode: str) -> Path:
        return self._video_segments_root_dir(project_id) / mode

    def _prepare_output_dir(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _prepare_fresh_output_dir(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        for child in directory.iterdir():
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                import shutil

                shutil.rmtree(child, ignore_errors=True)
        return directory

    def _set_video_artifact_metadata(
        self,
        project_id: str,
        *,
        mode: str,
        segments_dir: Path,
        segment_paths: List[str],
    ):
        task_data = TASKS.setdefault(project_id, {})
        task_data["video_segments_mode"] = mode
        task_data["video_segments_dir"] = str(segments_dir).replace("\\", "/")
        task_data["video_segments"] = [str(path).replace("\\", "/") for path in segment_paths]

        mode_key = f"{mode}_video_segments"
        mode_dir_key = f"{mode}_video_segments_dir"
        task_data[mode_key] = task_data["video_segments"]
        task_data[mode_dir_key] = task_data["video_segments_dir"]


        self._sync_clips_from_assets(project_id)

    def _supports_clip_rebuild(self, project_id: str) -> bool:
        return True

    def _sync_clips_from_assets(self, project_id: str):
        task_data = TASKS.setdefault(project_id, {})
        images = task_data.get("images") or []
        audios = task_data.get("audios") or []
        durations = task_data.get("durations") or []
        segments = task_data.get("video_segments") or []
        prompts = task_data.get("prompts") or []
        lines = task_data.get("lines") or []
        existing = task_data.get("clips") or []
        total = max(len(images), len(audios), len(durations), len(segments), len(lines))
        clips = []
        for index in range(total):
            previous = existing[index] if index < len(existing) and isinstance(existing[index], dict) else {}
            image_path = images[index] if index < len(images) else previous.get("image_path", "")
            clip_path = segments[index] if index < len(segments) else previous.get("clip_path", "")
            clips.append({
                "render_mode": previous.get("render_mode", "static"),
                "generated_at": previous.get("generated_at"),
                "index": index,
                "clip_path": clip_path,
                "image_path": image_path,
                "audio_path": audios[index] if index < len(audios) else previous.get("audio_path", ""),
                "duration": durations[index] if index < len(durations) else previous.get("duration", 0),
                "prompt": prompts[index] if index < len(prompts) else previous.get("prompt", ""),
                "text": lines[index] if index < len(lines) else previous.get("text", ""),
                "dirty": bool(previous.get("dirty", False)) or not clip_path or not Path(clip_path).is_file(),
            })
        task_data["clips"] = clips
        return clips

    def _mark_clips_dirty(self, project_id: str, indices: List[int]):
        clips = self._sync_clips_from_assets(project_id)
        for index in indices:
            if 0 <= index < len(clips):
                clips[index]["dirty"] = True
        return clips

    def _dirty_clip_indices(self, project_id: str) -> List[int]:
        clips = self._sync_clips_from_assets(project_id)
        return [clip.get("index", idx) for idx, clip in enumerate(clips) if clip.get("dirty")]

    def _run_ffmpeg_with_timeout(self, ffmpeg_cmd, timeout=120):
        """
        运行ffmpeg命令并添加超时控制
        Args:
            ffmpeg_cmd: ffmpeg命令对象（ffmpeg.Stream对象）
            timeout: 超时时间（秒）
        Returns:
            无，成功执行
        Raises:
            ffmpeg.Error: ffmpeg执行错误
            subprocess.TimeoutExpired: 命令执行超时
        """
        timeout_sec = max(float(timeout or 120), 1.0)
        try:
            # 编译ffmpeg命令获取命令行参数
            cmd = ffmpeg_cmd.compile()
            cmd_args = [str(part) for part in cmd]
            cmd_text = shlex.join(cmd_args)
            started_at = time()
            logger.info("[ffmpeg] start timeout=%ss cmd=%s", timeout_sec, cmd_text)

            # 使用subprocess.run执行命令，设置超时
            result = subprocess.run(
                cmd_args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_sec,
            )
            elapsed = time() - started_at
            logger.info("[ffmpeg] done returncode=%s elapsed=%.2fs cmd=%s", result.returncode, elapsed, cmd_text)

            # 检查返回码
            if result.returncode != 0:
                stderr_text = (result.stderr or b"").decode("utf-8", errors="ignore")
                logger.error("[ffmpeg] failed returncode=%s elapsed=%.2fs stderr=%s", result.returncode, elapsed, stderr_text)
                raise ffmpeg.Error(cmd_text, result.stdout, result.stderr)

        except subprocess.TimeoutExpired as exc:
            elapsed = time() - started_at
            stderr_raw = exc.stderr or b""
            stderr_text = stderr_raw.decode("utf-8", errors="ignore") if isinstance(stderr_raw, (bytes, bytearray)) else str(stderr_raw)
            logger.error(
                "[ffmpeg] timeout elapsed=%.2fs timeout=%ss cmd=%s stderr=%s",
                elapsed,
                timeout_sec,
                cmd_text,
                (stderr_text or "")[:2000],
            )
            # 重新抛出超时异常，但包装成ffmpeg.Error以保持兼容性
            raise ffmpeg.Error(
                cmd_text,
                b"",
                f"Command timeout after {timeout_sec} seconds".encode(),
            )
        except Exception:
            raise




    def _strip_inline_formula_markers(self, text: Any) -> str:
        raw = str(text or "")
        if not raw:
            return ""

        cleaned = re.sub(
            r"\$([^$]+)\$|\\\((.*?)\\\)",
            lambda m: (m.group(1) or m.group(2) or "").strip(),
            raw,
        )
        cleaned = cleaned.replace("$", "")
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.strip()



    def _to_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _render_story_style_clip(
        self,
        image_path: str,
        audio_path: str,
        duration: float,
        clip_path: Path,
        fps: int = 30,
    ) -> str:
        if duration <= 0:
            duration = 5.0
        if not self._is_valid_media_file(image_path):
            raise FileNotFoundError(f"图片素材缺失: {image_path}")
        if not self._is_valid_media_file(audio_path):
            raise FileNotFoundError(f"音频素材缺失: {audio_path}")

        video_stream = (
            ffmpeg
            .input(image_path, loop=1, framerate=fps)
            .video
            # Preserve the source dimensions; yuv420p requires even width/height.
            .filter("pad", "ceil(iw/2)*2", "ceil(ih/2)*2", 0, 0)
            .filter("setsar", 1)
            .filter("fps", fps=fps)
            .filter("trim", duration=duration)
            .filter("setpts", "PTS-STARTPTS")
        )
        audio_stream = ffmpeg.input(audio_path).audio.filter("atrim", duration=duration).filter("asetpts", "PTS-STARTPTS")
        ffmpeg_cmd = ffmpeg.output(
            video_stream,
            audio_stream,
            str(clip_path),
            vcodec="libx264",
            preset="ultrafast",
            pix_fmt="yuv420p",
            acodec="aac",
            r=fps,
            t=duration,
            shortest=None,
        ).overwrite_output()
        clip_timeout = max(45, int(duration * 12))
        self._run_ffmpeg_with_timeout(ffmpeg_cmd, timeout=clip_timeout)
        return str(clip_path).replace("\\", "/")

    def _rebuild_dirty_clips(self, project_id: str, shot_index: Optional[int] = None):
        task = TASKS.get(project_id, {})
        if shot_index is None:
            self._validate_video_resume_assets(task.get("lines"), task.get("images"), task.get("audios"), task.get("durations"))
        if not self._supports_clip_rebuild(project_id):
            raise ValueError("当前项目暂不支持片段级重建")
        task_data = TASKS.setdefault(project_id, {})
        clips = self._sync_clips_from_assets(project_id)
        clip_mode = self._get_project_config_value(project_id, "clip_mode", "static")
        if shot_index is not None:
            import math
            if not 0 <= shot_index < len(clips):
                raise ValueError("找不到该分镜的视频素材")
            selected = clips[shot_index]
            if not self._is_valid_media_file(selected.get("image_path")):
                raise ValueError("请先生成并提交当前分镜图片")
            if not self._is_valid_media_file(selected.get("audio_path")):
                raise ValueError("请先生成当前分镜配音")
            duration = float(selected.get("duration") or 0)
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError("当前分镜配音时长无效，请重新生成配音")
            selected["dirty"] = True
        for clip in clips:
            if clip.get("render_mode", "static") != clip_mode:
                clip["dirty"] = True
            if not clip.get("clip_path") or not Path(clip["clip_path"]).is_file():
                clip["dirty"] = True
        dirty_indices = [shot_index] if shot_index is not None else [i for i, clip in enumerate(clips) if clip.get("dirty")]
        if not dirty_indices:
            return clips

        segments_dir_path = task_data.get("video_segments_dir")
        if not segments_dir_path:
            segments_dir_path = str(self._video_segments_mode_dir(project_id, "story"))
            task_data["video_segments_dir"] = segments_dir_path
        segments_dir = self._prepare_output_dir(Path(segments_dir_path))
        segments = task_data.get("video_segments") or []

        emit_progress_status(project_id, "in_video_rebuild", "正在重建视频段", 75)
        for order, index in enumerate(dirty_indices, start=1):
            if task_data.get("stop_requested"):
                raise InterruptedError("视频段生成已停止")
            clip = clips[index]
            # Publish a new media URL only after rendering succeeds. Reusing the
            # old filename can leave browsers playing buffered video and can
            # fail on Windows while the old file is being served.
            clip_path = segments_dir / f"clip_{index:04d}_{uuid4().hex}.mp4"
            if clip_mode == "jimeng":
                print("===============run in create clip with jimeng")
                from app.video_engine.video_engine import render_clip_with_jimeng
                rendered_path = render_clip_with_jimeng(self, project_id, index, clip, clip_path)
            else:
                rendered_path = self._render_story_style_clip(
                    clip.get("image_path", ""), clip.get("audio_path", ""),
                    float(clip.get("duration") or 0) or 5.0, clip_path,
                )
            rendered_file = Path(rendered_path)
            if not rendered_file.is_file() or not rendered_file.stat().st_size:
                raise RuntimeError(f"分镜 {index + 1} 视频段未生成有效文件：{rendered_path}")
            if task_data.get("stop_requested"):
                raise InterruptedError("视频段生成已停止，保留原视频段")
            clip["render_mode"] = clip_mode
            clip["generated_at"] = int(time() * 1000)
            clip["clip_path"] = rendered_path
            clip["dirty"] = False
            while len(segments) <= index:
                segments.append("")
            segments[index] = clip["clip_path"]
            task_data["video_segments"] = segments
            task_data["clips"] = clips
            task_data.pop("video_path", None)
            self.save_project(project_id)
            logger.info("分镜 %s 视频段引用已更新：%s", index + 1, rendered_path)
            update_progress(project_id, 75 + int(10 * order / max(len(dirty_indices), 1)), f"分镜 {index + 1} 视频段已更新（{order}/{len(dirty_indices)}）")

        task_data["video_segments"] = segments
        task_data["clips"] = clips
        emit_progress_status(project_id, "in_video_concat", "视频段已更新，待拼接整片", 90)
        self.save_project(project_id)
        return clips

    def _concat_existing_clips(self, project_id: str):
        task_data = TASKS.setdefault(project_id, {})
        self._validate_video_resume_assets(task_data.get("lines"), task_data.get("images"), task_data.get("audios"), task_data.get("durations"))
        clips = self._sync_clips_from_assets(project_id)
        dirty_indices = self._dirty_clip_indices(project_id)
        if dirty_indices:
            raise ValueError("仍有待重建的视频段，请先执行重建视频段")
        lines = task_data.get("lines") or []
        durations = task_data.get("durations") or []
        return self._compose_existing_video_segments(project_id, lines, durations)

    async def async_rebuild_dirty_clips(
        self,
        project_id: str,
        cancel_event: asyncio.Event,
        progress_cb: Callable[[Dict], None],
    ):
        register_progress_callback(project_id, progress_cb)
        try:
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}
            self._ensure_project_loaded(project_id)
            clips = await asyncio.to_thread(self._rebuild_dirty_clips, project_id)
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}
            video_path = await asyncio.to_thread(self._concat_existing_clips, project_id)
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}
            snapshot = self.get_project_snapshot(project_id)
            return {
                "status": "completed",
                "project_id": project_id,
                "snapshot": snapshot,
                "clips": clips,
                **self._build_partial_video_payload(project_id),
                "video_path": video_path,
            }
        except asyncio.CancelledError:
            return {"status": "cancelled", "project_id": project_id}
        except Exception as e:
            self._persist_project_failure(project_id, str(e))
            return {"status": "error", "project_id": project_id, "error": str(e), "snapshot": self.get_project_snapshot(project_id), **self._build_partial_video_payload(project_id)}
        finally:
            unregister_progress_callback(project_id)

    async def async_concat_video_clips(
        self,
        project_id: str,
        cancel_event: asyncio.Event,
        progress_cb: Callable[[Dict], None],
    ):
        register_progress_callback(project_id, progress_cb)
        try:
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}
            self._ensure_project_loaded(project_id)
            video_path = await asyncio.to_thread(self._concat_existing_clips, project_id)
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}
            snapshot = self.get_project_snapshot(project_id)
            return {
                "status": "completed",
                "project_id": project_id,
                "video_path": video_path,
                "snapshot": snapshot,
                **self._build_partial_video_payload(project_id),
            }
        except asyncio.CancelledError:
            return {"status": "cancelled", "project_id": project_id}
        except Exception as e:
            self._persist_project_failure(project_id, str(e))
            return {"status": "error", "project_id": project_id, "error": str(e), "snapshot": self.get_project_snapshot(project_id), **self._build_partial_video_payload(project_id)}
        finally:
            unregister_progress_callback(project_id)

    def _is_valid_media_file(self, file_path: Optional[str]) -> bool:
        if not file_path or not isinstance(file_path, str):
            return False
        normalized = file_path.strip()
        if not normalized or normalized in {".", ".."}:
            return False
        return os.path.isfile(normalized)

    def _ensure_audio_configs(
        self,
        project_id: str,
        lines: list,
        model_name: str,
        api_key: str,
        voice: str,
        language: Optional[str] = None,
        start_index: int = 0,
    ) -> List[Dict[str, Any]]:
        existing = get_progress_data(project_id=project_id, key="audios_configs") or []
        configs: List[Dict[str, Any]] = []
        for idx, line in enumerate(lines):
            line_text = self._strip_inline_formula_markers(line or "")
            if idx < len(existing) and idx < start_index and existing[idx]:
                config = existing[idx]
                if hasattr(config, "model_dump"):
                    config = config.model_dump()
                elif hasattr(config, "dict"):
                    config = config.dict()
                else:
                    config = dict(config)
                config = dict(config)
                if line_text:
                    config["text"] = line_text
            else:
                config = {
                    "audio_model_name": model_name,
                    "audio_api_key": api_key,
                    "voice": voice,
                    "text": line_text,
                    "language": self._get_project_language(project_id, text=line_text, requested_language=language),
                }
            configs.append(config)
        set_progress_data(project_id=project_id, key="audios_configs", data=configs)
        return configs

    def _concat_video_segments(self, project_id: str, segments_dir: Path, clip_paths: List[str], output_path: str):
        print(f"拼接 {len(clip_paths)} 个片段...")
        emit_progress_status(
            project_id=project_id,
            status="in_video_concat",
            percent=90,
            stage="视频片段已生成，正在拼接整片",
        )

        if len(clip_paths) == 1:
            import shutil

            shutil.copy2(clip_paths[0], output_path)
            return output_path

        concat_list = segments_dir / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for clip in clip_paths:
                f.write(f"file '{os.path.abspath(clip)}'\n")

        try:
            ffmpeg_cmd = ffmpeg.input(str(concat_list), format="concat", safe=0).output(
                output_path,
                vcodec="libx264",
                acodec="aac",
                preset="ultrafast",
                pix_fmt="yuv420p",
                r=30,
                shortest=None,
                loglevel="error",
            )
            # Re-encoding a long story can take minutes even when every clip is ready.
            durations = get_progress_data(project_id=project_id, key="durations") or []
            total_duration = sum(float(value) for value in durations if isinstance(value, (int, float)) and value > 0)
            concat_timeout = max(600.0, total_duration * 2, len(clip_paths) * 10.0)
            logger.info("拼接预算: clips=%s duration=%.1fs timeout=%.1fs", len(clip_paths), total_duration, concat_timeout)
            self._run_ffmpeg_with_timeout(ffmpeg_cmd, timeout=concat_timeout)
            print(f"🎬 完整视频合成完成：{output_path}")
        except ffmpeg.Error as e:
            stderr = getattr(e, "stderr", None)
            stderr_text = stderr.decode(errors="replace") if isinstance(stderr, (bytes, bytearray)) else str(stderr or e)
            print(f"视频拼接时出错：{stderr_text}")
            raise

        return output_path

    def _finalize_video_output(self, project_id: str, lines: list, durations: list, video_path: str, with_subtitles: bool = True):
        pdir = self._project_dir(project_id)
        if not with_subtitles:
            update_progress(project_id=project_id, percent=100, stage="已完成视频制作！")
            set_progress_data(project_id=project_id, key="video_path", data=video_path)
            print("无字幕视频总工程完毕")
            return video_path

        print("视频生成完成，正在生成字幕……")

        # Encoded clips can be longer than TTS estimates; align captions to actual boundaries.
        clip_paths = get_progress_data(project_id=project_id, key="video_segments") or []
        if len(clip_paths) == len(lines) and all(Path(path).is_file() for path in clip_paths):
            durations = [float(ffmpeg.probe(path)["format"]["duration"]) for path in clip_paths]
        subtitle_segments = [
            {"text": line, "duration": dur} for line, dur in zip(lines, durations)
        ]
        subtitle_path = sub.generate_srt(segments=subtitle_segments, output_dir=pdir, video_path=video_path)

        print("字幕生成完成，正在组装视频……")
        update_progress(project_id=project_id, percent=95, stage="字幕已生成，正在组装视频！")
        video_path_with_subtitle = video_path.replace(".mp4", ".with_subtitle.mp4")

        final_with_subtitle = sub.burn_subtitles(
            video_path, subtitle_path, video_path_with_subtitle
        )
        final_video_path = final_with_subtitle or video_path_with_subtitle or video_path
        update_progress(project_id=project_id, percent=100, stage="已完成视频制作！")
        set_progress_data(project_id=project_id, key="video_path", data=final_video_path)
        print("带字幕视频总工程完毕")
        return final_video_path

    def _compose_video_by_style(
        self,
        project_id: str,
        style: str,
        lines: list,
        image_files: list,
        audio_files: list,
        durations: list,
    ):
        pdir = self._project_dir(project_id)
        video_path = os.path.join(pdir, f"final_{int(time())}.mp4")
        set_progress_status(project_id=project_id, status="in_video_progress")

        self._create_video(project_id, image_files, audio_files, durations, video_path)

        final_video_path = self._finalize_video_output(
            project_id,
            lines,
            durations,
            video_path,
            with_subtitles=True,
        )
        return final_video_path

    def _compose_existing_video_segments(self, project_id: str, lines: list, durations: list):
        video_segments = get_progress_data(project_id=project_id, key="video_segments") or []
        segments_dir_path = get_progress_data(project_id=project_id, key="video_segments_dir")
        if not video_segments or not segments_dir_path:
            raise ValueError("video segments are missing for concat stage")
        pdir = self._project_dir(project_id)
        video_path = os.path.join(pdir, f"final_{int(time())}.mp4")
        self._concat_video_segments(
            project_id=project_id,
            segments_dir=Path(segments_dir_path),
            clip_paths=video_segments,
            output_path=video_path,
        )
        style = str(self._get_project_config_value(project_id, "style", "") or "")
        final_video_path = self._finalize_video_output(
            project_id,
            lines,
            durations,
            video_path,
            with_subtitles=True,
        )
        set_progress_status(project_id=project_id, status="completed")
        return final_video_path

    def _resume_video_output(self, project_id: str, style: str, lines: list, image_files: list, audio_files: list, durations: list):
        if get_progress_status(project_id=project_id) == "in_video_concat":
            return self._compose_existing_video_segments(project_id, lines, durations)
        return self._compose_video_by_style(
            project_id=project_id,
            style=style,
            lines=lines,
            image_files=image_files,
            audio_files=audio_files,
            durations=durations,
        )

    def _build_audio_configs_from_project(self, project_id: str, lines: list):
        config = self.projects[project_id]["config"]
        return self._ensure_audio_configs(
            project_id=project_id,
            lines=lines,
            model_name=config["audio_model_name"],
            api_key=config["audio_api_key"],
            voice=config["voice"],
        )

    def _build_audio_configs_for_values(self, project_id: str, lines: list, model_name: str, api_key: str, voice: str, start_index: int = 0):
        return self._ensure_audio_configs(project_id, lines, model_name, api_key, voice, start_index)

    def _ensure_video_pipeline_status(self, project_id: str):
        if get_progress_status(project_id=project_id) not in {"in_video_progress", "in_video_concat", "completed"}:
            set_progress_status(project_id=project_id, status="in_video_progress")

    def _normalize_existing_video_stage(self, project_id: str):
        current_status = get_progress_status(project_id=project_id)
        if current_status == "completed" and get_progress_data(project_id=project_id, key="video_segments"):
            set_progress_status(project_id=project_id, status="in_video_concat")
        return get_progress_status(project_id=project_id)

    def _validate_video_resume_assets(self, lines: list, image_files: list, audio_files: list, durations: list):
        if not lines or not audio_files or not durations:
            raise ValueError("video rebuild assets are incomplete")
        if image_files is None:
            raise ValueError("video rebuild image assets are missing")
        if not (len(lines) == len(image_files) == len(audio_files) == len(durations)):
            raise ValueError("旁白、图像、音频和时长数量不一致，禁止合成")
        missing = [i + 1 for i, path in enumerate(image_files) if not path or not Path(path).is_file()]
        if missing:
            raise ValueError(f"第 {missing} 个分镜缺少图像，请修改提示词后重抽，禁止合成")
        return True

    def _restore_story_inputs(self, project_id: str, segments=None):
        """Persist the complete shot plan before media generation; recover legacy failures."""
        task = TASKS[project_id]
        config = self._normalize_config_for_save(self.projects[project_id].get("config")) or {}
        if "story" not in (config.get("style") or ""):
            return
        if segments is None:
            segments = task.get("prompts")
            if not segments:
                source = self._artifact_section_dir(project_id, "story") / "segments.json"
                if not source.is_file():
                    return
                segments = json.loads(source.read_text(encoding="utf-8"))
        if not segments or not all(isinstance(s, dict) for s in segments):
            return
        task["prompts"] = list(segments)
        task["lines"] = [s.get("text", "") for s in segments]
        task["text"] = "\n".join(task["lines"])
        configs = task.setdefault("images_configs", [])
        for index, segment in enumerate(segments):
            if index < len(configs) and configs[index]:
                continue
            entry = dict(image_model_name=config.get("image_model_name", ""),
                         prompt=segment.get("image_prompt", ""), text=segment.get("image_prompt", ""),
                         n=config.get("n", 1), size=config.get("size", "1024*1024"),
                         render_mode="story_shot", story_segment=dict(segment))
            if index < len(configs):
                configs[index] = entry
            else:
                configs.append(entry)
        images = task.setdefault("images", [])
        while len(images) < len(segments):
            images.append("")  # Explicit missing slots, rejected by the composition gate.

    def _record_image_failure(self, project_id: str, index: int, total: int, error):
        message = f"第 {index + 1}/{total} 个分镜图像生成失败：{error}"
        task = TASKS[project_id]
        task.setdefault("image_errors", {})[str(index)] = message
        task["error"] = message
        task["errors"] = message
        task["stage"] = message
        task["status"] = "error"
        self.save_project(project_id)
        return message

    def _prepare_video_concat_resume(self, project_id: str):
        if get_progress_status(project_id=project_id) == "in_video_concat":
            emit_progress_status(project_id, "in_video_concat", "继续视频拼接", 90)

    def _resume_video_segments_or_render(self, project_id: str, style: str, lines: list, image_files: list, audio_files: list, durations: list):
        if get_progress_status(project_id=project_id) == "in_video_concat":
            return self._compose_existing_video_segments(project_id, lines, durations)
        return self._compose_video_by_style(
            project_id,
            style,
            lines,
            image_files,
            audio_files,
            durations,
        )

    def _finalize_video_task(self, project_id: str, video_path: str):
        set_progress_data(project_id=project_id, key="video_path", data=video_path)
        set_progress_status(project_id=project_id, status="completed")
        return video_path

    def _normalize_redraw_history(self, history: Any, kind: str) -> List[List[Dict[str, Any]]]:
        if not isinstance(history, list):
            return []

        normalized_history: List[List[Dict[str, Any]]] = []
        for entry in history:
            if not isinstance(entry, list):
                normalized_history.append([])
                continue

            normalized_candidates: List[Dict[str, Any]] = []
            for candidate in entry:
                if not isinstance(candidate, dict):
                    continue
                candidate_copy = dict(candidate)
                config = candidate_copy.get("config")
                candidate_copy["config"] = self._normalize_config_for_save(config) if isinstance(config, dict) else config
                if kind == "image" and candidate_copy.get("prompt") is None:
                    candidate_copy["prompt"] = candidate_copy.get("text", "")
                normalized_candidates.append(candidate_copy)
            normalized_history.append(normalized_candidates)
        return normalized_history

    def _ensure_history_container(self, project_id: str, key: str, expected_len: int) -> List[List[Dict[str, Any]]]:
        history = TASKS[project_id].setdefault(key, [])
        while len(history) < expected_len:
            history.append([])
        return history

    def _ensure_image_history_entry(self, project_id: str, index: int) -> List[Dict[str, Any]]:
        images = get_progress_data(project_id=project_id, key="images") or []
        image_configs = get_progress_data(project_id=project_id, key="images_configs") or []
        prompts = get_progress_data(project_id=project_id, key="prompts") or []
        history = self._ensure_history_container(project_id, "image_redraw_history", len(images))
        entry = history[index]
        if entry:
            return entry

        prompt = prompts[index] if index < len(prompts) else ""
        config = image_configs[index] if index < len(image_configs) else {}
        if config is None:
            config = {}
        if hasattr(config, "model_dump"):
            config = config.model_dump()
        elif hasattr(config, "dict"):
            config = config.dict()
        elif not isinstance(config, dict):
            config = {
                "image_model_name": getattr(config, "image_model_name", ""),
                "image_api_key": getattr(config, "image_api_key", ""),
                "prompt": getattr(config, "prompt", prompt),
                "text": getattr(config, "text", prompt),
                "n": getattr(config, "n", 1),
                "size": getattr(config, "size", ""),
            }
        config = dict(config)
        config_prompt = config.get("prompt") or config.get("text") or prompt
        config["prompt"] = config_prompt
        config["text"] = config.get("text") or config_prompt
        config.setdefault("render_mode", "prompt")
        config.setdefault("story_segment", None)
        entry.append(
            {
                "image_path": images[index] if index < len(images) else "",
                "prompt": config_prompt,
                "config": config,
                "created_at": int(time()),
                "is_current": True,
            }
        )
        return entry

    def _ensure_audio_history_entry(self, project_id: str, index: int) -> List[Dict[str, Any]]:
        audios = get_progress_data(project_id=project_id, key="audios") or []
        durations = get_progress_data(project_id=project_id, key="durations") or []
        audio_configs = get_progress_data(project_id=project_id, key="audios_configs") or []
        history = self._ensure_history_container(project_id, "audio_redraw_history", len(audios))
        entry = history[index]
        if entry:
            return entry

        config = audio_configs[index] if index < len(audio_configs) else {}
        if config is None:
            config = {}
        if hasattr(config, "model_dump"):
            config = config.model_dump()
        elif hasattr(config, "dict"):
            config = config.dict()
        elif not isinstance(config, dict):
            config = {
                "audio_model_name": getattr(config, "audio_model_name", ""),
                "audio_api_key": getattr(config, "audio_api_key", ""),
                "text": getattr(config, "text", ""),
                "voice": getattr(config, "voice", ""),
            }
        config = dict(config)
        entry.append(
            {
                "audio_path": audios[index] if index < len(audios) else "",
                "duration": durations[index] if index < len(durations) else 0,
                "config": config,
                "created_at": int(time()),
                "is_current": True,
            }
        )
        return entry

    def _append_redraw_history_candidate(self, project_id: str, kind: str, index: int, candidate: Dict[str, Any]):
        if kind == "image":
            entry = self._ensure_image_history_entry(project_id, index)
        else:
            entry = self._ensure_audio_history_entry(project_id, index)

        for item in entry:
            item["is_current"] = False
        entry.append(candidate)
        while len(entry) > self.REDRAW_HISTORY_LIMIT:
            del entry[1]

    def _build_project_snapshot(self, project_id: str) -> Dict[str, Any]:
        project = self.projects.get(project_id, {})
        task_data = TASKS.get(project_id, {})
        return {
            "project_id": project_id,
            "active_chapter": project.get("active_chapter"),
            "chapters": project.get("chapters", []),
            "project_name": project.get("name", ""),
            "project_target": project.get("target", ""),
            "project_config": self._normalize_config_for_save(project.get("config")),
            "task_data": task_data,
            "status": task_data.get("status"),
            "stage": task_data.get("stage"),
            "progress": task_data.get("percent", 0),
            "updated_at": int(time()),
        }

    def create_project(self, name: str, target: str) -> str:
        if target not in targets:
            return None
        pid = str(uuid4())
        pdir = self.base_dir / pid
        pdir.mkdir(exist_ok=True)
        meta = {
            "project_id": pid,
            "name": name,
            "target": target,
            "config": None,
        }
        self.projects[pid] = meta
        TASKS[pid] = {}
        return pid

    def _normalize_redraw_history(self, history: Any, kind: str) -> List[List[Dict[str, Any]]]:
        if not isinstance(history, list):
            return []

        normalized_history: List[List[Dict[str, Any]]] = []
        for entry in history:
            if not isinstance(entry, list):
                normalized_history.append([])
                continue

            normalized_candidates: List[Dict[str, Any]] = []
            for candidate in entry:
                if not isinstance(candidate, dict):
                    continue
                candidate_copy = dict(candidate)
                config = candidate_copy.get("config")
                candidate_copy["config"] = self._normalize_config_for_save(config) if isinstance(config, dict) else config
                if kind == "image" and candidate_copy.get("prompt") is None:
                    candidate_copy["prompt"] = candidate_copy.get("text", "")
                normalized_candidates.append(candidate_copy)
            normalized_history.append(normalized_candidates)
        return normalized_history

    def _ensure_history_container(self, project_id: str, key: str, expected_len: int) -> List[List[Dict[str, Any]]]:
        history = TASKS[project_id].setdefault(key, [])
        while len(history) < expected_len:
            history.append([])
        return history

    def _ensure_image_history_entry(self, project_id: str, index: int) -> List[Dict[str, Any]]:
        images = get_progress_data(project_id=project_id, key="images") or []
        image_configs = get_progress_data(project_id=project_id, key="images_configs") or []
        prompts = get_progress_data(project_id=project_id, key="prompts") or []
        history = self._ensure_history_container(project_id, "image_redraw_history", len(images))
        entry = history[index]
        if entry:
            return entry

        prompt = prompts[index] if index < len(prompts) else ""
        config = image_configs[index] if index < len(image_configs) else {}
        if config is None:
            config = {}
        if hasattr(config, "model_dump"):
            config = config.model_dump()
        elif hasattr(config, "dict"):
            config = config.dict()
        elif not isinstance(config, dict):
            config = {
                "image_model_name": getattr(config, "image_model_name", ""),
                "image_api_key": getattr(config, "image_api_key", ""),
                "prompt": getattr(config, "prompt", prompt),
                "text": getattr(config, "text", prompt),
                "n": getattr(config, "n", 1),
                "size": getattr(config, "size", ""),
            }
        config = dict(config)
        config_prompt = config.get("prompt") or config.get("text") or prompt
        config["prompt"] = config_prompt
        config["text"] = config.get("text") or config_prompt
        config.setdefault("render_mode", "prompt")
        config.setdefault("story_segment", None)
        entry.append(
            {
                "image_path": images[index] if index < len(images) else "",
                "prompt": config_prompt,
                "config": config,
                "created_at": int(time()),
                "is_current": True,
            }
        )
        return entry

    def _ensure_audio_history_entry(self, project_id: str, index: int) -> List[Dict[str, Any]]:
        audios = get_progress_data(project_id=project_id, key="audios") or []
        durations = get_progress_data(project_id=project_id, key="durations") or []
        audio_configs = get_progress_data(project_id=project_id, key="audios_configs") or []
        history = self._ensure_history_container(project_id, "audio_redraw_history", len(audios))
        entry = history[index]
        if entry:
            return entry

        config = audio_configs[index] if index < len(audio_configs) else {}
        if config is None:
            config = {}
        if hasattr(config, "model_dump"):
            config = config.model_dump()
        elif hasattr(config, "dict"):
            config = config.dict()
        elif not isinstance(config, dict):
            config = {
                "audio_model_name": getattr(config, "audio_model_name", ""),
                "audio_api_key": getattr(config, "audio_api_key", ""),
                "text": getattr(config, "text", ""),
                "voice": getattr(config, "voice", ""),
            }
        config = dict(config)
        entry.append(
            {
                "audio_path": audios[index] if index < len(audios) else "",
                "duration": durations[index] if index < len(durations) else 0,
                "config": config,
                "created_at": int(time()),
                "is_current": True,
            }
        )
        return entry

    def _append_redraw_history_candidate(self, project_id: str, kind: str, index: int, candidate: Dict[str, Any]):
        if kind == "image":
            entry = self._ensure_image_history_entry(project_id, index)
        else:
            entry = self._ensure_audio_history_entry(project_id, index)

        for item in entry:
            item["is_current"] = False
        entry.append(candidate)
        while len(entry) > self.REDRAW_HISTORY_LIMIT:
            del entry[1]

    def apply_redraw_selection(
        self,
        project_id: str,
        image_selected_history: Optional[Dict[str, int]] = None,
        audio_selected_history: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        self._ensure_project_loaded(project_id)
        task_data = TASKS.setdefault(project_id, {})

        image_selected_history = image_selected_history or {}
        audio_selected_history = audio_selected_history or {}
        changed_indices = set()

        images = task_data.setdefault("images", [])
        image_configs = task_data.setdefault("images_configs", [])
        prompts = task_data.setdefault("prompts", [])
        image_history = self._ensure_history_container(project_id, "image_redraw_history", len(images))

        for index_str, history_index in image_selected_history.items():
            index = int(index_str)
            if index >= len(image_history):
                raise IndexError(f"image history index out of range: {index}")
            candidates = image_history[index]
            if history_index < 0 or history_index >= len(candidates):
                raise IndexError(f"selected image history item out of range: {index}:{history_index}")
            selected = dict(candidates[history_index])
            config = dict(selected.get("config") or {})
            prompt = selected.get("prompt") or config.get("prompt") or config.get("text") or ""
            config["prompt"] = prompt
            config["text"] = prompt
            images[index] = selected.get("image_path", "")
            if task_data.get("story_review"):
                review = task_data["story_review"]
                review["dirty_images"] = [i for i in review.get("dirty_images", []) if i != index]
            segment = config.get("story_segment")
            if not isinstance(segment, dict) and index < len(prompts) and isinstance(prompts[index], dict):
                segment = prompts[index]
            if isinstance(segment, dict):
                segment = dict(segment, image_prompt=prompt)
                config["story_segment"] = segment
                prompts[index] = segment
            else:
                prompts[index] = prompt
            image_configs[index] = config
            changed_indices.add(index)
            for idx, item in enumerate(candidates):
                item["is_current"] = idx == history_index

        audios = task_data.setdefault("audios", [])
        durations = task_data.setdefault("durations", [])
        audio_configs = task_data.setdefault("audios_configs", [])
        audio_history = self._ensure_history_container(project_id, "audio_redraw_history", len(audios))
        lines = task_data.setdefault("lines", [])

        for index_str, history_index in audio_selected_history.items():
            index = int(index_str)
            if index >= len(audio_history):
                raise IndexError(f"audio history index out of range: {index}")
            candidates = audio_history[index]
            if history_index < 0 or history_index >= len(candidates):
                raise IndexError(f"selected audio history item out of range: {index}:{history_index}")
            selected = dict(candidates[history_index])
            config = dict(selected.get("config") or {})
            if index < len(lines):
                config["text"] = lines[index]
            audios[index] = selected.get("audio_path", "")
            durations[index] = selected.get("duration", 0)
            audio_configs[index] = config
            changed_indices.add(index)
            for idx, item in enumerate(candidates):
                item["is_current"] = idx == history_index

        self._mark_clips_dirty(project_id, sorted(changed_indices))
        if changed_indices:
            emit_progress_status(project_id, "in_video_rebuild", "素材已更新，待重建视频段", 72)
        self.save_project(project_id)
        return self.get_project_snapshot(project_id)

    def _apply_latest_image_redraw(self, project_id: str, index: int):
        TASKS[project_id].setdefault("image_errors", {}).pop(str(index), None)
        history = TASKS[project_id]["image_redraw_history"][index]
        return self.apply_redraw_selection(project_id, image_selected_history={str(index): len(history) - 1})

        # data={"text":str,"prompts":list,"audios":list,"images":list,"vid"}
        meta = {
            "project_id": pid,
            "name": name,
            "target": target,
            "config": None,
            # "status": "draft"
            # "data"
        }
        # (pdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self.projects[pid] = meta
        TASKS[pid] = {}
        return pid

    def save_project(self, project_id: str):
        print("save project id==", project_id)
        if project_id not in self.projects:
            raise KeyError(f"project not found: {project_id}")

        pdir = self._project_dir(project_id)
        pdir.mkdir(parents=True, exist_ok=True)
        data = self._build_project_snapshot(project_id)
        # print("保存时的task_data:", data.get("task_data"))

        with open(self._project_meta_path(project_id), "w", encoding="utf-8") as json_file:
            json.dump(clear_legacy_credentials(data), json_file, indent=4, ensure_ascii=False)

        print("text_config=====", get_progress_data(project_id=project_id, key="text_config"))
        chapter = self.projects[project_id].get("active_chapter")
        if chapter:
            chapter_dir = self.base_dir / project_id / "chapters" / chapter
            chapter_dir.mkdir(parents=True, exist_ok=True)
            (chapter_dir / "meta.json").write_text(json.dumps(clear_legacy_credentials(data), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"project_info saved in {pdir}/meta.json")

    def list_projects(self) -> Dict[str, Any]:
        projects = []
        invalid_meta_projects = []
        for meta_path in sorted(self.base_dir.glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                with open(meta_path, "r", encoding="utf-8") as file:
                    data = clear_legacy_credentials(json.load(file))
                task_data = data.get("task_data") or {}
                projects.append(
                    {
                        "project_id": data.get("project_id") or meta_path.parent.name,
                        "name": data.get("project_name") or meta_path.parent.name,
                        "target": data.get("project_target"),
                        "status": task_data.get("status") or data.get("status") or "draft",
                        "stage": task_data.get("stage") or data.get("stage") or "",
                        "progress": task_data.get("percent", data.get("progress", 0)),
                        "updated_at": data.get("updated_at") or int(meta_path.stat().st_mtime),
                        "video_path": task_data.get("video_path"),
                    }
                )
            except Exception as e:
                invalid_meta_projects.append(meta_path.parent.name)
                print(f"list_projects skip invalid meta {meta_path}: {e}")
        warning = None
        if invalid_meta_projects:
            warning = {
                "invalid_meta_count": len(invalid_meta_projects),
                "invalid_meta_projects": invalid_meta_projects,
            }
        return {"projects": projects, "warning": warning}

    def get_project_snapshot(self, project_id: str) -> Dict[str, Any]:
        if project_id not in self.projects:
            self.load_project(project_id)
        return self._build_project_snapshot(project_id)

    def load_project(self, project_id: str):
        print("load porject id==", project_id)
        file_path = self._project_meta_path(project_id)

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = clear_legacy_credentials(json.load(file))

            print("JSON data loaded successfully:")
            project_config = data.get("project_config")
            if isinstance(project_config, str):
                project_config = clear_legacy_credentials(json.loads(project_config))

            self.projects[project_id] = {
                "project_id": data.get("project_id", project_id),
                "name": data.get("project_name", project_id),
                "target": data.get("project_target", "video"),
                "config": project_config,
                "active_chapter": data.get("active_chapter"),
                "chapters": data.get("chapters", []),
            }

            task_data = data.get("task_data") or {}
            task_data.setdefault("status", data.get("status") or "draft")
            task_data.setdefault("stage", data.get("stage") or "")
            task_data.setdefault("percent", data.get("progress", 0))
            task_data["image_redraw_history"] = self._normalize_redraw_history(
                task_data.get("image_redraw_history"), "image"
            )
            task_data["audio_redraw_history"] = self._normalize_redraw_history(
                task_data.get("audio_redraw_history"), "audio"
            )
            TASKS[project_id] = task_data
            self._restore_story_inputs(project_id)
            self._sync_clips_from_assets(project_id)
            # print("task data:", task_data)
            print("text_config=====", get_progress_data(project_id=project_id, key="text_config"))

        except FileNotFoundError:
            print(f"Error: The file '{file_path}' was not found.")
            return None
        except json.JSONDecodeError:
            print(
                f"Error: Could not decode JSON from '{file_path}'. Check if the file contains valid JSON."
            )
            return None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return None
        return self.get_project_snapshot(project_id)

    def update_config(self, project_id: str, config: dict):
        print(
            f"[update_config] project_id: {project_id}, config type: {type(config)}, config keys: {list(config.keys()) if isinstance(config, dict) else 'not dict'}"
        )
        print(f"[update_config] project exists: {project_id in self.projects}")
        if project_id in self.projects:
            print(
                f"[update_config] current project config before update: {self.projects[project_id].get('config')}"
            )
            if hasattr(config, "model_dump"):
                config = config.model_dump()
            elif hasattr(config, "dict"):
                config = config.dict()

            # 确保article字段是字符串类型（文章内容）
            if isinstance(config, dict) and "article" in config:
                article = config["article"]
                if article is not None:
                    # 确保article是字符串
                    if not isinstance(article, str):
                        print(
                            f"[update_config] WARNING: article is not string, type: {type(article)}, converting to string"
                        )
                        config["article"] = str(article)

                    article_str = config["article"]
                    print(
                        f"[update_config] article content: length={len(article_str)}, preview: {article_str[:100]}{'...' if len(article_str) > 100 else ''}"
                    )
                else:
                    print(f"[update_config] article is None")
            else:
                print(f"[update_config] article not in config or config not dict")

            self.projects[project_id]["config"] = config
            print(f"[update_config] config updated successfully")
        else:
            print(f"[update_config] ERROR: project {project_id} not found in projects")

    # def update_status(self, project_id: str,status:str):
    #     # 更新 meta.json，记录当前阶段、最新脚本路径等
    #     if status not in all_status:
    #         return
    #     self.projects[project_id]["status"]=status

    def gen_texts(
        self,
        project_id: str,
        with_media_prompts: bool = False,
        media_prompt_style: str = "",
        model_name: str = "",
        api_key: str = "",
        theme: str = "",
        style: str = "",
        language: str = "",
        rebuild: bool = False,
    ):
        if rebuild == False:
            config = self.projects[project_id]["config"]
            # 支持字典和对象两种 config 格式
            if isinstance(config, dict):
                if model_name == "":
                    model_name = config.get("text_model_name", "") or ""
                # if api_key == "":
                #     api_key = config.get("text_api_key", "") or ""
                if theme == "":
                    theme = config.get("theme", "") or ""
                if not style:
                    style = config.get("style", "") or ""
                if not language:
                    language = config.get("language", "") or ""
                if not media_prompt_style:
                    media_prompt_style = config.get("media_prompt_style", "") or ""
            else:
                # 假设 config 是有属性的对象
                if model_name == "":
                    model_name = config.text_model_name
                # if api_key == "":
                #     api_key = config.text_api_key
                if theme == "":
                    theme = config.theme
                if not style:
                    style = config.style or ""
                if not language:
                    language = getattr(config, "language", "") or ""
                if not media_prompt_style:
                    media_prompt_style = getattr(config, "media_prompt_style", "") or ""
        else:
            text_config = get_progress_data(project_id=project_id, key="text_config")
            # 同样支持字典和对象
            if isinstance(text_config, dict):
                model_name = text_config.get("text_model_name", "")
                api_key = text_config.get("text_api_key", "")
                theme = text_config.get("theme", "")
                style = text_config.get("style", "")
                language = text_config.get("language", "")
                media_prompt_style = text_config.get("media_prompt_style", "")
            else:
                model_name = text_config.text_model_name
                api_key = text_config.text_api_key
                theme = text_config.theme
                style = text_config.style
                language = getattr(text_config, "language", "")
                media_prompt_style = getattr(text_config, "media_prompt_style", "")

        print("设置当前状态=====“in_text_progress”")
        set_progress_status(project_id=project_id, status="in_text_progress")

        print(f"正在创建{model_name}文案生成模型")
        if False == textGenerationService.use_model(model_name=model_name, api_key=api_key):
            error = "创建模型失败，可能是不支持的模型名"
            set_progress_status(project_id=project_id, status="error")
            set_progress_data(project_id=project_id, key="errors", data=error)
            print("文案模型生成出错，可能是不支持的文案模型")
            return self._text_result(False, error=error)

        print("正在生成文案……")
        language = self._get_project_language(project_id, text=theme, requested_language=language)
        text = textGenerationService.generate_text(theme=theme, style=style, language=language)
        #临时添加
        print("received text:=====>",text)
        ##小测试
        # text="健康时自己最大的财富，他决定了你的身心平衡.\n 请爱惜你自己，正如你爱惜阳光，空气，食物，生活"
        print("with_media_prompts====>",with_media_prompts)
        if self.projects[project_id]["target"] == "text" and not with_media_prompts:
            print("正在更新提示词生成状态和数据……")
            update_progress(project_id=project_id, percent=100, stage="文案已经生成")
        else:
            update_progress(project_id=project_id, percent=50, stage="文案已经生成")

        set_progress_data(project_id=project_id, key="text", data=text)
        self._write_artifact_text(
            project_id,
            "text",
            "generated_text.txt",
            text,
            key="generated_text",
        )
        set_progress_data(
            project_id=project_id,
            key="text_config",
            data={
                "text_model_name": model_name,
                "text_api_key": api_key,
                "theme": theme,
                "style": style,
                "language": language,
                "media_prompt_style": media_prompt_style,
            },
        )
        print("文案生成完成。")
        print("正在释放文案引擎")
        textGenerationService.release_model()
        prompts = []

        if with_media_prompts == True:
            prompts = self.gen_prompts(
                project_id=project_id,
                text=text,
                model_name=model_name,
                api_key=api_key,
                language=language,
                media_prompt_style=media_prompt_style,
            )

        print("正在更新提示词生成状态数据……")
        if self.projects[project_id]["target"] == "text":
            set_progress_status(project_id=project_id, status="completed")

        if self.projects[project_id]["target"] == "text":
            update_progress(project_id=project_id, percent=100, stage="文案和提示词生成完成")
        else:
            update_progress(project_id=project_id, percent=99, stage="文案和提示词生成完成")

        set_progress_data(project_id=project_id, key="prompts", data=prompts)

        return self._text_result(True, content=text, prompts=prompts)

    def gen_prompts(
        self,
        project_id: str,
        text: str = "",
        model_name: str = "",
        api_key: str = "",
        language: str = "",
        media_model_name: str = "",
        media_prompt_style: str = "",
        start_index: int = 0,
    ):
        if model_name == "":
            model_name = self.projects[project_id]["config"].text_model_name
        # if api_key == "":
        #     api_key = self.projects[project_id]["config"].text_api_key
        if text == "":
            text = self.projects[project_id]["config"].text

        print(f"正在创建 media prompt 模型{model_name}……")
        textGenerationService.use_model(model_name=model_name, api_key=api_key)

        print("正在根据文案生成 media prompt 集合……")
        prompts = []
        if start_index > 0:
            prompts = get_progress_data(project_id=project_id, key="prompts")
        lines = text.replace("\n\n", "\n").split("\n")
        for i, line in enumerate(lines):
            if line == "" or len(line) < 2 or i < start_index:
                continue
            # 3️ 打磨 media prompt
            polished_prompt = textGenerationService.polish_media_prompts(
                text=line,
                language=self._get_project_language(project_id, text=line, requested_language=language),
                media_model_name=media_model_name or self._get_project_config_value(project_id, "image_model_name", ""),
                media_prompt_style=media_prompt_style or self._get_project_config_value(project_id, "media_prompt_style", "image_default"),
                texts=text,
            )
            update_progress(
                project_id=project_id,
                percent=50 + 50 * i / len(lines),
                stage=f"生成第{i}/{len(lines)}个提示词",
            )
            prompts.append(polished_prompt)
            TASKS[project_id]["prompts"] = prompts
        print("提示词生成完成。")
        print("正在释放提示词引擎")
        textGenerationService.release_model()
        return prompts

    def gen_prompts_by_story_structure(
        self,
        project_id: str,
        text: str = "",
        model_name: str = "",
        api_key: str = "",
    ):
        if model_name == "":
            model_name = self.projects[project_id]["config"].text_model_name
        # if api_key == "":
        #     api_key = self.projects[project_id]["config"].text_api_key
        if text == "":
            text = self.projects[project_id]["config"].text
        result = run_story_pipeline(story=text, model_name=model_name, api_key=api_key)
        return [segment["image_prompt"] for segment in result["segments"]]

    def gen_audio(
        self,
        project_id: str,
        text: str = "",
        model_name: str = "",
        api_key: str = "",
        voice: str = "",
        language: str = "",
        index: int = -1,
    ):
        pdir = self._project_dir(project_id)

        if index == -1:
            if model_name == "":
                model_name = self.projects[project_id]["config"].audio_model_name
            # if api_key == "":
            #     api_key = self.projects[project_id]["config"].audio_api_key
            if text == "":
                text = self.projects[project_id]["config"].text
            if voice == "":
                voice = self.projects[project_id]["config"].voice
        else:
            audio_config = {
                "audio_model_name": model_name,
                "audio_api_key": api_key,
                "text": text,
                "voice": voice,
                "language": language,
            }
            if not all(audio_config.values()):
                stored_audio_config = get_progress_data_with_index(
                    project_id=project_id, key="audios_configs", index=index
                )
                if hasattr(stored_audio_config, "model_dump"):
                    stored_audio_config = stored_audio_config.model_dump()
                elif hasattr(stored_audio_config, "dict"):
                    stored_audio_config = stored_audio_config.dict()
                elif not isinstance(stored_audio_config, dict):
                    stored_audio_config = {
                        "audio_model_name": getattr(stored_audio_config, "audio_model_name", ""),
                        "audio_api_key": getattr(stored_audio_config, "audio_api_key", ""),
                        "text": getattr(stored_audio_config, "text", ""),
                        "voice": getattr(stored_audio_config, "voice", ""),
                        "language": getattr(stored_audio_config, "language", ""),
                    }
                audio_config = {
                    "audio_model_name": audio_config.get("audio_model_name") or stored_audio_config.get("audio_model_name", ""),
                    "audio_api_key": audio_config.get("audio_api_key") or stored_audio_config.get("audio_api_key", ""),
                    "text": audio_config.get("text") or stored_audio_config.get("text", ""),
                    "voice": audio_config.get("voice") or stored_audio_config.get("voice", ""),
                    "language": audio_config.get("language") or stored_audio_config.get("language", ""),
                }
            model_name = audio_config.get("audio_model_name", "")
            api_key = audio_config.get("audio_api_key", "")
            text = audio_config.get("text", "")
            voice = audio_config.get("voice", "")
            language = audio_config.get("language", "")

        text = self._strip_inline_formula_markers(text)

        print("设置当前状态=====“in_audio_progress”")
        set_progress_status(project_id=project_id, status="in_audio_progress")

        if (
            self.projects[project_id]["target"] == "audio" or index != -1
        ):  # 考虑视频中音频序列重抽情况
            print("正在生成音频引擎……")
            if False == audioGenerationService.create_engine(
                audio_model_name=model_name, audio_api_key=api_key
            ):
                error = "创建音频引擎出错"
                set_progress_status(project_id=project_id, status="error")
                set_progress_data(project_id=project_id, key="errors", data=error)
                return self._audio_result(False, error=error)

        print("正在生成语音信息……")
        success, audio_path, duration = audioGenerationService.generate_audio(
            text, voice, output_dir=pdir, language=language
        )
        print("生成语音：", audio_path)

        if not success:
            error = "生成语音失败"
            set_progress_status(project_id=project_id, status="error")
            set_progress_data(project_id=project_id, key="errors", data=error)
            if index != -1 or self.projects[project_id]["target"] == "audio":
                self._persist_project_failure(project_id, error)
            return self._audio_result(False, error=error)

        if self.projects[project_id]["target"] == "audio":
            print("正在更新音频生成状态和数据……")
            set_progress_data(project_id=project_id, key="text", data=text)

            set_progress_data(project_id=project_id, key="audios", data=[audio_path])
            set_progress_data(project_id=project_id, key="durations", data=[duration])

            set_progress_status(project_id=project_id, status="completed")

            audios_len = get_progress_data_len(project_id=project_id, key="audios")
            update_progress(
                project_id=project_id,
                percent=99,
                stage=f"已经生成第{audios_len+1}/{audios_len}个音频",
            )

            print("正在释放音频引擎……")
            audioGenerationService.release_engine()
        elif index != -1:
            print("正在缓存音频重抽历史……")
            source_lines = get_progress_data(project_id=project_id, key="lines") or []
            locked_text = source_lines[index] if 0 <= index < len(source_lines) else text
            locked_text = self._strip_inline_formula_markers(locked_text)
            candidate_config = {
                "audio_model_name": model_name,
                "audio_api_key": api_key,
                "text": locked_text,
                "voice": voice,
                "language": self._get_project_language(project_id, text=locked_text, requested_language=language),
            }
            self._append_redraw_history_candidate(
                project_id=project_id,
                kind="audio",
                index=index,
                candidate={
                    "audio_path": audio_path,
                    "duration": duration,
                    "config": candidate_config,
                    "created_at": int(time()),
                    "is_current": False,
                },
            )


        if index != -1:
            self.save_project(project_id)
        print("语音信息生成完成。")
        return self._audio_result(True, audio_path=audio_path, duration=duration)

    def gen_image(
        self,
        project_id: str,
        text: str = "",
        model_name: str = "",
        api_key: str = "",
        n: int = 0,
        size: str = "",
        language: str = "",
        index: int = -1,
        apply_result: bool = True,
    ):
        self._ensure_project_loaded(project_id)
        pdir = self._project_dir(project_id)

        if index == -1:
            if model_name == "":
                model_name = self.projects[project_id]["config"].image_model_name
            # if api_key == "":
            #     api_key = self.projects[project_id]["config"].image_api_key
            if text == "":
                text = self.projects[project_id]["config"].prompt
            if n == 0:
                n = self.projects[project_id]["config"].n
            if size == "":
                size = self.projects[project_id]["config"].size
        else:
            image_config = {
                "image_model_name": model_name,
                "image_api_key": api_key,
                "prompt": text,
                "text": text,
                "n": n,
                "size": size,
                "language": language,
                "render_mode": "",
                "story_segment": None,
            }
            stored_image_config = get_progress_data_with_index(
                project_id=project_id, key="images_configs", index=index
            )
            if hasattr(stored_image_config, "model_dump"):
                stored_image_config = stored_image_config.model_dump()
            elif hasattr(stored_image_config, "dict"):
                stored_image_config = stored_image_config.dict()
            elif not isinstance(stored_image_config, dict):
                stored_image_config = {
                    "image_model_name": getattr(stored_image_config, "image_model_name", ""),
                    "image_api_key": getattr(stored_image_config, "image_api_key", ""),
                    "prompt": getattr(stored_image_config, "prompt", getattr(stored_image_config, "text", "")),
                    "text": getattr(stored_image_config, "text", getattr(stored_image_config, "prompt", "")),
                    "n": getattr(stored_image_config, "n", 1),
                    "size": getattr(stored_image_config, "size", ""),
                    "language": getattr(stored_image_config, "language", ""),
                    "render_mode": getattr(stored_image_config, "render_mode", ""),
                    "story_segment": getattr(stored_image_config, "story_segment", None),
                }
            if stored_image_config is None:
                stored_image_config = {}
            image_config = {
                "image_model_name": image_config.get("image_model_name") or stored_image_config.get("image_model_name", ""),
                "image_api_key": image_config.get("image_api_key") or stored_image_config.get("image_api_key", ""),
                "prompt": image_config.get("prompt") or image_config.get("text") or stored_image_config.get("prompt") or stored_image_config.get("text", ""),
                "text": image_config.get("text") or image_config.get("prompt") or stored_image_config.get("text") or stored_image_config.get("prompt", ""),
                "n": image_config.get("n") or stored_image_config.get("n", 1),
                "size": image_config.get("size") or stored_image_config.get("size", ""),
                "language": image_config.get("language") or stored_image_config.get("language", ""),
                "render_mode": image_config.get("render_mode") or stored_image_config.get("render_mode", ""),
                "story_segment": image_config.get("story_segment") or stored_image_config.get("story_segment"),
            }
            print("image_config====", image_config)
            model_name = image_config.get("image_model_name", "")
            print(model_name)
            api_key = image_config.get("image_api_key", "")
            text = image_config.get("prompt") or image_config.get("text", "")
            n = image_config.get("n", 1)
            size = image_config.get("size", "")
            language = image_config.get("language", "")
            print(model_name, ",", text, ",", n, ",", size)
            if image_config.get("render_mode") == "story_shot" and image_config.get("story_segment"):
                image_config["story_segment"] = dict(image_config["story_segment"], image_prompt=text)
                image_result = self.render_story_shot(
                    project_id=project_id,
                    segment=dict(image_config.get("story_segment") or {}),
                    model_name=model_name,
                    api_key=api_key,
                    size=size,
                    n=n,
                )
                if not image_result["success"]:
                    error = image_result.get("error") or "生成图像失败"
                    set_progress_status(project_id=project_id, status="error")
                    set_progress_data(project_id=project_id, key="errors", data=error)
                    if index != -1 or self.projects[project_id]["target"] == "image":
                        self._persist_project_failure(project_id, error)
                    return self._image_result(False, error=error)
                image_paths = image_result["image_paths"]
                if index != -1:
                    story_segment = dict(image_config.get("story_segment") or {})
                    prompt = story_segment.get("image_prompt") or story_segment.get("text", "")
                    candidate_config = dict(image_config)
                    self._append_redraw_history_candidate(
                        project_id=project_id,
                        kind="image",
                        index=index,
                        candidate={
                            "image_path": image_paths[0],
                            "prompt": prompt,
                            "config": candidate_config,
                            "created_at": int(time()),
                            "is_current": False,
                        },
                    )
                    images_len = get_progress_data_len(project_id=project_id, key="images")
                    update_progress(
                        project_id=project_id,
                        percent=99,
                        stage=f"已经生成第{images_len}/{images_len}个文案图像候选",
                    )
                    imageGenerationService.release_engine()
                    if apply_result:
                        self._apply_latest_image_redraw(project_id, index)
                    else:
                        self.save_project(project_id)
                return self._image_result(True, image_paths=image_paths)

        print("设置当前状态======“in_image_progress”")
        set_progress_status(project_id=project_id, status="in_image_progress")

        if self.projects[project_id]["target"] == "image" or (index != -1):
            print(f"正在创建{model_name}图像引擎……")
            if False == imageGenerationService.create_engine(
                image_model_name=model_name, image_api_key=api_key
            ):
                error = "创建图像引擎出错"
                set_progress_status(project_id=project_id, status="error")
                set_progress_data(project_id=project_id, key="errors", data=error)
                return self._image_result(False, error=error)

        print("正在创建图像……")
        success, image_paths = imageGenerationService.generate(text, pdir, size=size, n=n)
        print("生成图像：", image_paths)

        if not success or not image_paths:
            error = "生成图像失败"
            set_progress_status(project_id=project_id, status="error")
            set_progress_data(project_id=project_id, key="errors", data=error)
            if index != -1 or self.projects[project_id]["target"] == "image":
                self._persist_project_failure(project_id, error)
            return self._image_result(False, error=error)

        if self.projects[project_id]["target"] == "image":
            print("正在更新图像生成状态和数据……")
            set_progress_data(project_id=project_id, key="prompts", data=[text])
            set_progress_data(project_id=project_id, key="images", data=[image_paths[0]])
            set_progress_status(project_id=project_id, status="completed")
            print("正在释放图像引擎……")
            imageGenerationService.release_engine()
        elif index != -1:  # 在视频的图像序列中
            print("正在缓存图像重抽历史……")
            prompt = text
            candidate_config = {
                "image_model_name": model_name,
                "image_api_key": api_key,
                "prompt": prompt,
                "text": prompt,
                "n": n,
                "size": size,
                "language": self._get_project_language(project_id, text=prompt, requested_language=language),
                "render_mode": image_config.get("render_mode", "prompt") if index != -1 else "prompt",
                "story_segment": image_config.get("story_segment") if index != -1 else None,
            }
            self._append_redraw_history_candidate(
                project_id=project_id,
                kind="image",
                index=index,
                candidate={
                    "image_path": image_paths[0],
                    "prompt": prompt,
                    "config": candidate_config,
                    "created_at": int(time()),
                    "is_current": False,
                },
            )
            images_len = get_progress_data_len(project_id=project_id, key="images")
            update_progress(
                project_id=project_id,
                percent=99,
                stage=f"已经生成第{images_len}/{images_len}个文案图像候选",
            )
            print("正在释放图像引擎……")
            imageGenerationService.release_engine()

            if apply_result:
                self._apply_latest_image_redraw(project_id, index)
            else:
                self.save_project(project_id)

        return self._image_result(True, image_paths=image_paths)

        return self._image_result(True, image_paths=image_paths)

    def _gen_audios(
        self,
        project_id: str,
        lines: list,
        model_name: str,
        api_key: str,
        voice: str,
        language: str = "",
        start_index: int = 0,
        cancel_event=None,
    ):
        audio_files = []
        durations = []

        if start_index > 0:
            audio_files = get_progress_data(project_id=project_id, key="audios") or []
            durations = get_progress_data(project_id=project_id, key="durations") or []

        self._ensure_audio_configs(project_id, lines, model_name, api_key, voice, language, start_index)

        print(f"正在生成{model_name}音频引擎……")
        if False == audioGenerationService.create_engine(
            audio_model_name=model_name, audio_api_key=api_key
        ):
            error = "创建音频引擎出错"
            set_progress_status(project_id=project_id, status="error")
            set_progress_data(project_id=project_id, key="errors", data=error)
            print("出错")
            return self._audio_sequence_result(False, error=error, audios=audio_files, durations=durations)
        for i, line in enumerate(lines):
            if cancel_event and cancel_event.is_set():
                print(f"音频生成被取消，已生成 {len(audio_files)} 个音频")
                audioGenerationService.release_engine()
                return self._audio_sequence_result(True, audios=audio_files, durations=durations, cancelled=True)

            line = self._strip_inline_formula_markers(line or "")
            if line == "" or len(line) < 2 or i < start_index:
                continue
            print(line)
            audio_result = self.gen_audio(
                project_id=project_id,
                text=line,
                model_name=model_name,
                api_key=api_key,
                voice=voice,
                language=self._get_project_language(project_id, text=line, requested_language=language),
            )
            if not audio_result["success"]:
                audioGenerationService.release_engine()
                return self._audio_sequence_result(
                    False,
                    error=audio_result.get("error"),
                    audios=audio_files,
                    durations=durations,
                )
            audio_files.append(audio_result["audio_path"])
            durations.append(audio_result["duration"])
            update_progress(
                project_id=project_id,
                percent=99 * i / len(lines),
                stage=f"已经生成第{i}/{len(lines)}个配音音频",
            )
            set_progress_data(project_id=project_id, key="audios", data=audio_files)
            set_progress_data(project_id=project_id, key="durations", data=durations)

        print("正在释放音频引擎……")
        audioGenerationService.release_engine()

        print("音频序列创建完成。")
        return self._audio_sequence_result(True, audios=audio_files, durations=durations)

    def _gen_images(
        self,
        project_id: str,
        lines: list,
        model_name: str = "",
        api_key: str = "",
        n: int = 1,
        size: str = "1024*1024",
        language: str = "",
        start_index: int = 0,
        is_prompts=True,
        cancel_event=None,
    ):
        image_files = list(get_progress_data(project_id=project_id, key="images") or [])
        while len(image_files) < len(lines):
            image_files.append("")

        if is_prompts == False:
            print("正在生成图像提示词引擎")
            textGenerationService.use_polish_model(
                model_name=model_name,
                api_key=api_key,
            )
        print(f"正在生成{model_name}图像引擎……")
        if False == imageGenerationService.create_engine(
            image_model_name=model_name, image_api_key=api_key
        ):
            error = "创建图像引擎出错"
            set_progress_status(project_id=project_id, status="error")
            set_progress_data(project_id=project_id, key="errors", data=error)
            return self._image_sequence_result(False, error=error, images=image_files)
        for i, line in enumerate(lines):
            if cancel_event and cancel_event.is_set():
                print(f"图像生成被取消，已生成 {len(image_files)} 张图像")
                imageGenerationService.release_engine()
                return self._image_sequence_result(True, images=image_files, cancelled=True)

            if i < start_index:
                continue
            if image_files[i] and Path(image_files[i]).is_file():
                continue
            if isinstance(line, str) and (line == "" or len(line) < 2):
                continue
            if isinstance(line, str) and (line == "use previous background" or line == "use first background"):
                if line == "use previous background" :
                    if i==0:
                        print("there is an error in parsing story segments")
                    image_files[i] = image_files[i-1]
                else:
                    image_files[i] = image_files[0]
                update_progress(
                    project_id=project_id,
                    percent=99 * (i + 1) / len(lines),
                    stage=f"已经生成第{i + 1}/{len(lines)}个文案图像",
                    )
                set_progress_data(project_id=project_id, key="images", data=image_files)
                continue

            set_progress_data(project_id=project_id, key="images", data=image_files)

            try:
                if isinstance(line, dict):
                    segment = dict(line)
                    if not segment.get("image_prompt"):
                        segment["image_prompt"] = segment.get("text", "")
                    image_result = self.render_story_shot(
                        project_id=project_id,
                        segment=segment,
                        model_name=model_name,
                        api_key=api_key,
                        n=n,
                        size=size,
                    )
                else:
                    if is_prompts == False:
                        polished_prompt = textGenerationService.polish_media_prompts(
                            line,
                            language=self._get_project_language(project_id, text=line, requested_language=language),
                            media_model_name=model_name,
                            media_prompt_style=self._get_project_config_value(project_id, "media_prompt_style", "image_default"),
                            texts="\n".join(lines),
                        )
                    else:
                        polished_prompt = line
                    image_result = self.gen_image(
                        project_id=project_id,
                        text=polished_prompt,
                        model_name=model_name,
                        api_key=api_key,
                        n=n,
                        size=size,
                    )
                if not image_result["success"] or not image_result.get("image_paths"):
                    raise ValueError(image_result.get("error") or "图像服务未返回图片")
            except Exception as exc:
                error = self._record_image_failure(project_id, i, len(lines), exc)
                imageGenerationService.release_engine()
                return self._image_sequence_result(False, error=error, images=image_files)
            image_files[i] = image_result["image_paths"][0]
            TASKS[project_id].setdefault("image_errors", {}).pop(str(i), None)
            update_progress(
                project_id=project_id,
                percent=99 * (i + 1) / len(lines),
                stage=f"已经生成第{i + 1}/{len(lines)}个文案图像",
            )
            set_progress_data(project_id=project_id, key="images", data=image_files)
            self.save_project(project_id)
        print("正在释放图像引擎……")
        imageGenerationService.release_engine()
        return self._image_sequence_result(True, images=image_files)

    def _gen_video(
        self, project_id: str, lines: list, image_files: list, audio_files: list, durations: list
    ):
        return self._compose_video_by_style(
            project_id=project_id,
            style="",
            lines=lines,
            image_files=image_files,
            audio_files=audio_files,
            durations=durations,
        )

    def gen_video(self, project_id: str, cancel_event=None):
        # 检查取消
        if cancel_event and cancel_event.is_set():
            print("视频生成任务被取消")
            return self._cancelled_video_result(project_id)
        if TASKS.get(project_id, {}).get("story_review"):
            # Automatic mode also consumes the saved plan; never re-extract
            # over a user's reviewed items, scenes or shots.
            import threading
            from app.service.story_review import run_stage
            event = cancel_event or threading.Event()
            callback = PROGRESS_CALLBACKS.get(project_id, lambda value: None)
            try:
                if "inherited_items" in TASKS[project_id]:
                    document = TASKS[project_id]["story_review"]
                    if not document.get("scenes"):
                        if not TASKS[project_id].get("chapter_items_extracted"):
                            run_stage(project_id, "items", event, callback)
                        run_stage(project_id, "scenes", event, callback)
                    if any(not scene.get("shots") for scene in TASKS[project_id]["story_review"]["scenes"]):
                        run_stage(project_id, "shots", event, callback)
                run_stage(project_id, "media", event, callback)
                run_stage(project_id, "compose", event, callback)
                return self._video_result(True, video_path=TASKS[project_id].get("video_path", ""))
            except InterruptedError:
                return self._cancelled_video_result(project_id)
        # os.makedirs(output_dir, exist_ok=True)
        print("正在初始化视频参数……")
        print(f"[gen_video] project_id: {project_id}, projects keys: {list(self.projects.keys())}")
        config = self.projects[project_id]["config"]
        print(f"[gen_video] config type: {type(config)}, config: {config}")

        # 记录article字段详细信息
        def get_article_info(cfg):
            if isinstance(cfg, dict):
                article = cfg.get("article")
                if article is not None:
                    return f"length={len(article)}, preview: {article[:100]}{'...' if len(article) > 100 else ''}"
                else:
                    return "article is None"
            else:
                # 对象类型
                try:
                    article = getattr(cfg, "article", None)
                    if article is not None:
                        return f"length={len(article)}, preview: {article[:100]}{'...' if len(article) > 100 else ''}"
                    else:
                        return "article is None"
                except:
                    return "cannot get article from object"

        print(f"[gen_video] article info: {get_article_info(config)}")

        # 支持字典和对象两种 config 格式，若值为 None 则使用默认值
        def get_config_value(key, default=""):
            if isinstance(config, dict):
                val = config.get(key, default)
                return val if val is not None else default
            else:
                # 假设 config 是有属性的对象
                val = getattr(config, key, default)
                return val if val is not None else default

        text_model_name = get_config_value("text_model_name", "")
        # text_api_key = get_config_value("text_api_key", "")
        audio_model_name = get_config_value("audio_model_name", "")
        # audio_api_key = get_config_value("audio_api_key", "")
        image_model_name = get_config_value("image_model_name", "")
        # image_api_key = get_config_value("image_api_key", "")
        voice = get_config_value("voice", "")
        n = get_config_value("n", 1)
        size = get_config_value("size", "1024x1024")
        style = get_config_value("style", "")
        with_media_prompts = bool(get_config_value("with_media_prompts", True))
        media_prompt_style = get_config_value("media_prompt_style", "image_default")

        lines = []
        prompts = []
        image_files = []
        if "story" not in style:
            # 检查取消
            if cancel_event and cancel_event.is_set():
                print("视频生成任务被取消")
                return self._cancelled_video_result(project_id)
            text_result = self.gen_texts(
                project_id=project_id,
                with_media_prompts=with_media_prompts,
                media_prompt_style=media_prompt_style,
                model_name=text_model_name,
                api_key="",
            )
            if not text_result["success"]:
                return self._failed_video_result(project_id, text_result.get("error") or "文案生成失败")
            text = text_result["content"]
            prompts = text_result["prompts"]
            lines = text.split("\n") if text else []
            set_progress_data(project_id=project_id, key="lines", data=lines)
            audio_result = self._gen_audios(
                project_id=project_id,
                lines=lines,
                model_name=audio_model_name,
                api_key="",
                voice=voice,
                cancel_event=cancel_event,
            )
            if audio_result.get("cancelled"):
                return self._cancelled_video_result(project_id)
            if not audio_result["success"]:
                return self._failed_video_result(project_id, audio_result.get("error") or "音频生成失败")
            audio_files = audio_result["audios"]
            durations = audio_result["durations"]
            image_result = self._gen_images(
                project_id=project_id,
                lines=prompts,
                model_name=image_model_name,
                api_key="",
                n=n,
                size=size,
                cancel_event=cancel_event,
            )
            if image_result.get("cancelled"):
                return self._cancelled_video_result(project_id)
            if not image_result["success"]:
                return self._failed_video_result(project_id, image_result.get("error") or "图像生成失败")
            image_files = image_result["images"]
        elif "story" in style:
            article = get_config_value("article", "")
            if not article:
                text_result = self.gen_texts(
                    project_id=project_id,
                    with_media_prompts=with_media_prompts,
                    media_prompt_style=media_prompt_style,
                    model_name=text_model_name,
                    api_key="",
                )
                if not text_result["success"]:
                    return self._failed_video_result(project_id, text_result.get("error") or "文案生成失败")
                article = text_result["content"]
                prompts = text_result["prompts"]

            story_result = run_story_pipeline(
                story=article,
                model_name=text_model_name,
                api_key="",
                checkpoint_dir=self._artifact_section_dir(project_id, "story") / "analysis_cache",
                initial_items=TASKS[project_id].get("inherited_items"),
                identity_prefix=self.projects[project_id].get("active_chapter") or "",
                cancel_event=cancel_event,
            )
            self._persist_story_artifacts(project_id, story_result)
            story_world_result = self._prepare_story_world(
                project_id=project_id,
                image_model_name=image_model_name,
                image_api_key="",
                story_result=story_result,
            )
            if not story_world_result.get("success"):
                return self._failed_video_result(
                    project_id,
                    story_world_result.get("error") or "故事世界构建失败",
                )

            # 提取segments
            segments = story_result.get("segments", [])


            lines = []
            prompts = []
            durations = []
            audio_files = []
            image_files = []

            lines = [segment.get("text", "") for segment in segments]
            prompts = list(segments)
            self._restore_story_inputs(project_id, segments)
            self.save_project(project_id)

            # 生成音频（所有lines）
            # 检查取消
            if cancel_event and cancel_event.is_set():
                print("视频生成任务被取消")
                return self._cancelled_video_result(project_id)
            audio_result = self._gen_audios(
                project_id=project_id,
                lines=lines,
                model_name=audio_model_name,
                api_key="",
                voice=voice,
                cancel_event=cancel_event,
            )
            if audio_result.get("cancelled"):
                return self._cancelled_video_result(project_id)
            if not audio_result["success"]:
                return self._failed_video_result(project_id, audio_result.get("error") or "音频生成失败")
            audio_files = audio_result["audios"]
            durations = audio_result["durations"]

            if cancel_event and cancel_event.is_set():
                print("视频生成任务被取消")
                return self._cancelled_video_result(project_id)

            image_result = self._gen_images(
                project_id=project_id,
                lines=prompts,
                model_name=image_model_name,
                api_key="",
                n=n,
                size=size,
                cancel_event=cancel_event,
            )
            if image_result.get("cancelled"):
                return self._cancelled_video_result(project_id)
            if not image_result["success"]:
                return self._failed_video_result(project_id, image_result.get("error") or "图像生成失败")
            image_files = image_result["images"]

            set_progress_data(project_id=project_id, key="images", data=image_files)
            self._validate_video_resume_assets(lines, image_files, audio_files, durations)

            if len(prompts) != len(image_files):
                raise ValueError("story 模式图像数量与 prompts 数量不一致")


            if len(audio_files) != len(image_files) or len(durations) != len(image_files):
                raise ValueError("story 模式音频/时长/图像数量不一致")

            if len(lines) != len(image_files):
                raise ValueError("story 模式文案与图像数量不一致")

            set_progress_data(project_id=project_id, key="prompts", data=prompts)

            image_configs = [
                {
                    "image_model_name": image_model_name,
                    "image_api_key": "",
                    "prompt": prompt if isinstance(prompt, str) else prompt.get("image_prompt", prompt.get("media_prompt", "")),
                    "text": prompt if isinstance(prompt, str) else prompt.get("text", prompt.get("image_prompt", prompt.get("media_prompt", ""))),
                    "n": n,
                    "size": size,
                    "render_mode": "story_shot" if isinstance(prompt, dict) and prompt.get("type") == "story" else "prompt",
                    "story_segment": dict(prompt) if isinstance(prompt, dict) and prompt.get("type") == "story" else None,
                }
                for prompt in prompts
            ]
            set_progress_data(project_id=project_id, key="images_configs", data=image_configs)

            valid_image_count = sum(1 for path in image_files if path)
            update_progress(
                project_id=project_id,
                percent=99,
                stage=f"已经生成第{valid_image_count}/{len(prompts)}个文案图像",
            )

            assert len(lines) == len(prompts) == len(audio_files) == len(durations) == len(image_files)


            set_progress_data(project_id=project_id, key="lines", data=lines)
            set_progress_data(project_id=project_id, key="audios", data=audio_files)
            set_progress_data(project_id=project_id, key="durations", data=durations)


        # # 检查取消
        if cancel_event and cancel_event.is_set():
            print("视频生成任务被取消")
            return self._cancelled_video_result(project_id)
        final_video_path = self._compose_video_by_style(
            project_id=project_id,
            style=style,
            lines=lines,
            image_files=image_files,
            audio_files=audio_files,
            durations=durations,
        )
        self._finalize_video_task(project_id, final_video_path)
        return self._video_result(True, video_path=final_video_path, **self._build_partial_video_payload(project_id))

    def _ensure_project_loaded(self, project_id: str):
        if project_id not in self.projects:
            loaded = self.load_project(project_id)
            if not loaded:
                raise ValueError(f"project not found or failed to load: {project_id}")

    def update_missing_image_prompts(self, project_id: str, updates: Dict[str, str]):
        self._ensure_project_loaded(project_id)
        self._restore_story_inputs(project_id)
        task = TASKS[project_id]
        changes = []
        for key, prompt in updates.items():
            index = int(key)
            if not 0 <= index < len(task.get("prompts", [])) or not prompt.strip():
                raise ValueError("分镜编号无效或提示词为空")
            path = task["images"][index]
            if path and Path(path).is_file():
                continue
            changes.append((index, prompt))
        for index, prompt in changes:
            segment = dict(task["prompts"][index], image_prompt=prompt)
            task["prompts"][index] = segment
            task["images_configs"][index].update(prompt=prompt, text=prompt, story_segment=segment)
        self.save_project(project_id)

    def _resume_story_audios(self, project_id: str, cancel_event=None):
        """Fill missing audio slots independently of the current image stage."""
        import math
        task = TASKS[project_id]
        lines = task.get("lines") or []
        config = self._normalize_config_for_save(self.projects[project_id]["config"])
        self._ensure_audio_configs(project_id, lines, config.get("audio_model_name", ""), "", config.get("voice", ""))
        audios = task.setdefault("audios", [])
        durations = task.setdefault("durations", [])
        while len(audios) < len(lines):
            audios.append("")
        while len(durations) < len(lines):
            durations.append(0)
        for index, text in enumerate(lines):
            if cancel_event and cancel_event.is_set():
                self.save_project(project_id)
                return {"success": True, "cancelled": True}
            try:
                duration = float(durations[index])
            except (ValueError, TypeError):
                duration = 0
            if self._is_valid_media_file(audios[index]) and math.isfinite(duration) and duration > 0:
                continue
            result = self.gen_audio(project_id, text=text, model_name=config.get("audio_model_name", ""),
                                    voice=config.get("voice", ""), language=config.get("language", "") or "", index=index)
            if not result["success"]:
                self.save_project(project_id)
                return result
            history = task["audio_redraw_history"][index]
            self.apply_redraw_selection(project_id, audio_selected_history={str(index): len(history) - 1})
        return {"success": True}

    def rebuild_video(self, project_id: str, cancel_event=None):
        self._ensure_project_loaded(project_id)
        self._restore_story_inputs(project_id)
        task = TASKS[project_id]
        if task.get("story_review"):
            # Resume the reviewed plan through its media readiness checks,
            # including missing/dirty audio, rather than the legacy image branch.
            return self.gen_video(project_id, cancel_event)
        style = self._get_project_config_value(project_id, "style", "") or ""
        if "story" in style and task.get("prompts"):
            config = self._normalize_config_for_save(self.projects[project_id]["config"])
            task.pop("error", None)
            task.pop("errors", None)
            audio_result = self._resume_story_audios(project_id, cancel_event)
            if audio_result.get("cancelled"):
                return self._cancelled_video_result(project_id)
            if not audio_result["success"]:
                return self._video_result(False, error=audio_result.get("error") or "配音生成失败")
            result = self._gen_images(project_id, task["prompts"],
                                      model_name=config.get("image_model_name", ""),
                                      size=config.get("size", "1024*1024"), n=config.get("n", 1),
                                      cancel_event=cancel_event)
            if result.get("cancelled"):
                return self._cancelled_video_result(project_id)
            if not result["success"]:
                return self._video_result(False, error=result.get("error"))
            self._validate_video_resume_assets(task.get("lines"), task.get("images"), task.get("audios"), task.get("durations"))
            self._rebuild_dirty_clips(project_id)
            if cancel_event and cancel_event.is_set():
                return self._cancelled_video_result(project_id)
            video_path = self._concat_existing_clips(project_id)
            return self._video_result(True, video_path=video_path)
        current_status = get_progress_status(project_id=project_id)
        print("start rebuild video,current status:", current_status)
        config = self.projects[project_id]["config"]
        image_model_name = config.get("image_model_name")
        if image_model_name is None:
            raise ValueError("image model name should not be None Type.")
        image_api_key = config.get("image_api_key")
        # if image_api_key is None:
        #     raise ValueError("image api key should not be None Type.")

        if current_status in {"in_building_characters", "in_building_scenes"}:
            print("continue from story world preparation stage.")
            self._restore_story_world_if_needed(project_id, image_model_name, image_api_key)
            current_status = "in_image_progress"
            set_progress_status(project_id=project_id, status=current_status)

        cascade = False
        if current_status == "in_text_progress":
            text_config = get_progress_data(project_id=project_id, key="text_config")
            text_config = self.projects[project_id]["config"]
            if text_config is None:
                raise ValueError("text_config should not be NoneType.")
            text_model_name = text_config.get("text_model_name")
            if text_model_name is None:
                raise ValueError("text_model_name should not be NoneType.")
            text_api_key = text_config.get("text_api_key")
            if text_api_key is None:
                raise ValueError("text_api_key should not be NoneType.")
            style = text_config.get("style")
            if style is None:
                raise ValueError("text style should not be NoneType.")
            theme = text_config.get("theme")
            if theme is None:
                raise ValueError("text theme should not be NoneType.")
            text = get_progress_data(project_id=project_id, key="text")
            if text is None:
                print("在重构项目时，发现text并未生成/保存，重新生成文案")
                text_result = self.gen_texts(
                    project_id=project_id,
                    with_media_prompts=with_media_prompts,
                    media_prompt_style=media_prompt_style,
                    model_name=text_model_name,
                    api_key=text_api_key,
                    theme=theme,
                    style=style,
                )
                if not text_result["success"]:
                    raise ValueError(text_result.get("error") or "文案生成失败")
                text = text_result["content"]
            texts = text.replace("\n\n", "\n").split("\n")
            prompts = get_progress_data(project_id=project_id, key="prompts")
            if prompts is None:
                print("在重构项目时，发现prompts并未生成/保存，开始生成 media prompt")
                prompts = self.gen_prompts(
                    project_id=project_id,
                    text=text,
                    model_name=text_model_name,
                    api_key=text_api_key,
                    media_prompt_style=self._get_project_config_value(project_id, "media_prompt_style", "image_default"),
                )

            if len(prompts) != len(texts):
                print("在重构项目时，发现text的行数和prompts个数不一致，继续生成图像提示词")
                start_index = len(prompts)
                prompts = self.gen_prompts(
                    project_id=project_id,
                    text=text,
                    model_name=text_model_name,
                    api_key=text_api_key,
                    start_index=start_index,
                )

            cascade = True

        cascade2 = False
        if current_status == "in_audio_progress" or (cascade is True):
            text = get_progress_data(project_id=project_id, key="text")
            texts = text.replace("\n\n", "\n").split("\n")
            # texts=[audio_config["text"] for audio_config in audios_configs]
            audios = get_progress_data(project_id=project_id, key="audios")
            print("config====", self.projects[project_id]["config"])
            audio_model_name = self.projects[project_id]["config"]["audio_model_name"]
            if audio_model_name is None:
                raise ValueError("audio model name should not be None Type.")
            audio_api_key = self.projects[project_id]["config"]["audio_api_key"]
            if audio_api_key is None:
                raise ValueError("audio api key should not be None Type.")
            voice = self.projects[project_id]["config"]["voice"]
            if voice is None:
                raise ValueError("voice should not be None Type.")

            if audios is None or cascade is True:
                self._ensure_audio_configs(
                    project_id=project_id,
                    lines=texts,
                    model_name=audio_model_name,
                    api_key=audio_api_key,
                    voice=voice,
                )
                audios, durations = self._gen_audios(
                    project_id=project_id,
                    lines=texts,
                    model_name=audio_model_name,
                    api_key=audio_api_key,
                    voice=voice,
                )

            if len(audios) != len(texts):
                audios, durations = self._gen_audios(
                    project_id=project_id,
                    lines=texts,
                    model_name=audio_model_name,
                    api_key=audio_api_key,
                    voice=voice,
                    start_index=len(audios),
                )

            cascade2 = True

        if current_status == "in_image_progress" or (cascade is True):
            print("continue from in_image_progress.")
            prompts = get_progress_data(project_id=project_id, key="prompts")
            images = get_progress_data(project_id=project_id, key="images")

            image_model_name = self.projects[project_id]["config"]["image_model_name"]
            if image_model_name is None:
                raise ValueError("image model name should not be None Type.")
            image_api_key = self.projects[project_id]["config"]["image_api_key"]
            # if image_api_key is None:
            #     raise ValueError("image api key should not be None Type.")
            n = self.projects[project_id]["config"]["n"]
            if n is None:
                raise ValueError("image number should not be None Type.")
            size = self.projects[project_id]["config"]["size"]
            if size is None:
                raise ValueError("image size should not be None Type.")

            if images is None or cascade is True:
                images_configs = [
                    {
                        "image_model_name": image_model_name,
                        "image_api_key": image_api_key,
                        "n": n,
                        "size": size,
                        "text": prompts[i] if isinstance(prompts[i], str) else prompts[i].get("text", prompts[i].get("image_prompt", "")),
                        "prompt": prompts[i] if isinstance(prompts[i], str) else prompts[i].get("image_prompt", ""),
                        "render_mode": "story_shot" if isinstance(prompts[i], dict) and prompts[i].get("type") == "story" else "prompt",
                        "story_segment": dict(prompts[i]) if isinstance(prompts[i], dict) and prompts[i].get("type") == "story" else None,
                    }
                    for i in range(len(prompts))
                ]
                set_progress_data(project_id=project_id, key="images_configs", data=images_configs)
                images = self._gen_images(
                    project_id=project_id,
                    lines=prompts,
                    model_name=image_model_name,
                    api_key=image_api_key,
                    n=n,
                    size=size,
                )

            if len(images) != len(prompts):
                images = self._gen_images(
                    project_id=project_id,
                    lines=prompts,
                    model_name=image_model_name,
                    api_key=image_api_key,
                    n=n,
                    size=size,
                    start_index=len(images),
                )

            cascade2 = True

        if current_status in {"in_video_progress", "in_video_concat"} or (cascade2 is True):
            print("continue from video output stage.")
            lines = get_progress_data(project_id=project_id, key="lines")
            print("lines====", lines)
            image_files = get_progress_data(project_id=project_id, key="images")
            print("images====", image_files)
            audio_files = get_progress_data(project_id=project_id, key="audios")
            print("audios====", audio_files)
            durations = get_progress_data(project_id=project_id, key="durations")
            print("durations====", durations)
            style = self.projects[project_id]["config"].get("style", "")
            self._validate_video_resume_assets(lines, image_files, audio_files, durations)
            self._prepare_video_concat_resume(project_id)
            video_path = self._resume_video_segments_or_render(
                project_id=project_id,
                style=style,
                lines=lines,
                image_files=image_files,
                audio_files=audio_files,
                durations=durations,
            )
            self._finalize_video_task(project_id, video_path)

        return get_progress_data(project_id=project_id, key="video_path")

    def _create_video(self, project_id, images, audios, durations, output_path, fps=30):
        """
        将多张图像与对应音频拼接为完整视频
        Args:
            images: list[str] 图片路径
            audios: list[str] 音频路径
            durations: list[float] 每段音频时长
            output_path: 最终视频输出路径
            fps: 帧率
        """

        assert len(images) == len(audios) == len(durations), "图片、音频、时长数量必须一致"

        if self._get_project_config_value(project_id, "clip_mode", "static") == "jimeng":
            self._rebuild_dirty_clips(project_id)
            task = TASKS[project_id]
            self._concat_video_segments(project_id, Path(task["video_segments_dir"]), task["video_segments"], output_path)
            return output_path

        segments_dir = self._prepare_fresh_output_dir(self._video_segments_mode_dir(project_id, "story"))
        temp_videos = []

        # 1️⃣ 为每个片段生成视频（图像+音频）
        for i, (img, audio, dur) in enumerate(zip(images, audios, durations)):
            clip_path = segments_dir / f"clip_{i:04d}.mp4"
            print(f"[CreateVideo] clip={i} image={img} audio={audio} duration={dur}")
            video_center = ffmpeg.input(img, loop=1, t=dur, framerate=fps)

            video_input = video_center
            audio_input = ffmpeg.input(audio)
            ffmpeg_cmd = ffmpeg.output(
                video_input,
                audio_input,
                str(clip_path),
                vcodec="libx264",
                pix_fmt="yuv420p",
                acodec="aac",
            ).overwrite_output()
            self._run_ffmpeg_with_timeout(ffmpeg_cmd, timeout=30)

            temp_videos.append(str(clip_path).replace("\\", "/"))
            print(f"✅ 片段 {i} 合成完成：{clip_path}")

        self._concat_video_segments(project_id, segments_dir, temp_videos, output_path)

        self._set_video_artifact_metadata(
            project_id,
            mode="story",
            segments_dir=segments_dir,
            segment_paths=temp_videos,
        )
        return output_path


    async def async_rebuild_video(
        self,
        project_id: str,
        cancel_event: asyncio.Event,
        progress_cb: Callable[[Dict], None],
    ):
        register_progress_callback(project_id, progress_cb)

        try:
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}

            self._ensure_project_loaded(project_id)
            self._restore_story_inputs(project_id)
            is_story_resume = "story" in (self._get_project_config_value(project_id, "style", "") or "") and bool(TASKS[project_id].get("prompts"))
            rebuild_result = await asyncio.to_thread(self.rebuild_video if is_story_resume else self.gen_video, project_id, cancel_event)

            if cancel_event.is_set() or rebuild_result.get("cancelled"):
                return {"status": "cancelled", "project_id": project_id}
            if not rebuild_result["success"]:
                self._persist_project_failure(project_id, rebuild_result.get("error") or "视频重建失败")
                return {
                    "status": "error",
                    "project_id": project_id,
                    "error": rebuild_result.get("error") or "视频重建失败",
                    "snapshot": self.get_project_snapshot(project_id),
                    **self._build_partial_video_payload(project_id),
                }

            snapshot = self.get_project_snapshot(project_id)
            result = {
                "status": "completed",
                "project_id": project_id,
                "video_path": rebuild_result["video_path"],
                "snapshot": snapshot,
            }
            task_data = TASKS.get(project_id, {})
            if "text" in task_data:
                result["text"] = task_data["text"]
            if "lines" in task_data:
                result["lines"] = task_data["lines"]
            for key in ["images", "audios", "durations", "prompts", "images_configs", "audios_configs", "clips", "video_segments"]:
                if key in task_data:
                    result[key] = task_data[key]
            return result
        except asyncio.CancelledError:
            return {"status": "cancelled", "project_id": project_id}
        except Exception as e:
            try:
                self.save_project(project_id)
            except Exception as save_error:
                print(f"[async_rebuild_video] save_project failed after rebuild error: {save_error}")
            return {"status": "error", "project_id": project_id, "error": str(e)}
        finally:
            unregister_progress_callback(project_id)

    async def async_generate_video(
        self,
        project_id: str,
        config: Dict,
        cancel_event: asyncio.Event,
        progress_cb: Callable[[Dict], None],
    ):
        """
        可取消的异步视频生成（替代原 video_job 功能）

        Args:
            project_id: 项目ID
            config: 配置字典
            cancel_event: 取消事件，用于检查是否应该停止
            progress_cb: 进度回调函数

        Returns:
            Dict: 包含视频路径等信息
        """
        # 注册进度回调
        register_progress_callback(project_id, progress_cb)
        print(
            f"[async_generate_video] project_id: {project_id}, config type: {type(config)}, config keys: {list(config.keys()) if isinstance(config, dict) else 'not dict'}"
        )

        # 记录article字段详细信息
        if isinstance(config, dict):
            article = config.get("article")
            if article is not None:
                if isinstance(article, str):
                    print(
                        f"[async_generate_video] article content: length={len(article)}, preview: {article[:100]}{'...' if len(article) > 100 else ''}"
                    )
                else:
                    print(
                        f"[async_generate_video] WARNING: article is not string, type: {type(article)}, value: {article}"
                    )
            else:
                print(f"[async_generate_video] article is None")
        else:
            print(f"[async_generate_video] config is not dict, cannot check article directly")

        try:
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}

            self.update_config(project_id, config)
            video_result = await self._async_gen_video_with_cancel(project_id, config, cancel_event)

            if cancel_event.is_set() or video_result.get("cancelled"):
                return {"status": "cancelled", "project_id": project_id}
            if not video_result["success"]:
                self._persist_project_failure(project_id, video_result.get("error") or "视频生成失败")
                return {
                    "status": "error",
                    "project_id": project_id,
                    "error": video_result.get("error") or "视频生成失败",
                    "snapshot": self.get_project_snapshot(project_id),
                    **self._build_partial_video_payload(project_id),
                }

            self.save_project(project_id)

            result = {
                "status": "completed",
                "project_id": project_id,
                "video_path": video_result["video_path"],
                "snapshot": self.get_project_snapshot(project_id),
            }

            task_data = TASKS.get(project_id, {})
            if "text" in task_data:
                result["text"] = task_data["text"]
            if "lines" in task_data:
                result["lines"] = task_data["lines"]
            for key in ["images", "audios", "durations", "prompts", "images_configs", "audios_configs", "clips", "video_segments"]:
                if key in task_data:
                    result[key] = task_data[key]

            return result

        except asyncio.CancelledError:
            try:
                self.save_project(project_id)
            except Exception as save_error:
                print(f"[async_generate_video] save_project failed after cancel: {save_error}")
            return {"status": "cancelled", "project_id": project_id}
        except Exception as e:
            task_data = TASKS.setdefault(project_id, {})
            task_data["error"] = str(e)
            if task_data.get("status") != "completed":
                task_data["status"] = "error"
            try:
                self.save_project(project_id)
            except Exception as save_error:
                print(f"[async_generate_video] save_project failed after error: {save_error}")
            return {
                "status": "error",
                "project_id": project_id,
                "error": str(e),
                "snapshot": self.get_project_snapshot(project_id),
            }
        finally:
            unregister_progress_callback(project_id)

    async def _async_gen_video_with_cancel(
        self, project_id: str, config: Dict, cancel_event: asyncio.Event
    ):
        """
        支持取消的视频生成包装器 - 直接调用 gen_video 方法
        """

        # 定期检查取消事件
        async def check_cancel():
            if cancel_event.is_set():
                raise asyncio.CancelledError(f"任务被取消: {project_id}")

        # 检查取消
        await check_cancel()
        update_progress(project_id, 0, "正在生成视频...")

        try:
            # 调用同步的 gen_video 方法，传入 cancel_event 参数
            # 使用 asyncio.to_thread 避免阻塞事件循环
            video_result = await asyncio.to_thread(self.gen_video, project_id, cancel_event)

            # 再次检查取消
            await check_cancel()

            if video_result.get("cancelled"):
                raise asyncio.CancelledError(f"视频生成任务被取消: {project_id}")

            if video_result["success"]:
                update_progress(project_id, 100, "视频生成完成")
            return video_result

        except asyncio.CancelledError:
            # 任务被取消，重新抛出异常
            raise
        except Exception as e:
            print(f"视频生成过程中出错: {e}")
            task_data = TASKS.setdefault(project_id, {})
            if task_data.get("status") != "completed":
                task_data["status"] = "error"
            task_data["error"] = str(e)
            raise


pipelineManager = PipelineManager()


def getPipelineManager():
    return pipelineManager
