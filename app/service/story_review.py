"""Persistent, editable story stages. No model call is made by save/preview."""
import asyncio
import copy
import json
import threading
from pathlib import Path
from uuid import UUID, uuid4

from app.configs.constants import STYLE_REALISTIC
from app.langchain_pipeline.story_structure import Character, Scene
from app.service.story_pipeline import StoryPipeline
from app.service.story_chunks import empty_items, split_story
from app.service.pipeline_manager import TASKS, getPipelineManager, register_progress_callback, unregister_progress_callback


class ReviewConflict(ValueError):
    pass


_locks = {}


def project_lock(project_id):
    UUID(project_id)  # Route input must never become an arbitrary filesystem path.
    return _locks.setdefault(project_id, threading.Lock())


def manager_for(project_id):
    UUID(project_id)
    manager = getPipelineManager()
    manager._ensure_project_loaded(project_id)
    if project_id not in manager.projects:
        raise FileNotFoundError("项目不存在")
    if "story" not in (manager._get_project_config_value(project_id, "style", "") or ""):
        raise ValueError("此编辑器仅支持故事项目")
    return manager


def read_review(project_id):
    manager = manager_for(project_id)
    task = TASKS[project_id]
    if task.get("story_review"):
        return copy.deepcopy(task["story_review"])
    directory = manager._artifact_section_dir(project_id, "story")
    def artifact(name, default):
        path = directory / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
    scenes = artifact("scenes.json", [])
    shots = artifact("shots.json", [])
    for scene in scenes:
        if not scene.get("shots"):
            scene["shots"] = [s for s in shots if str(s.get("scene_id")) == str(scene["scene_info"]["scene_id"])]
    return dict(revision=0, source_text=manager._get_project_config_value(project_id, "article", "") or task.get("text", ""),
                items=artifact("items.json", empty_items()), scenes=scenes, style_tokens=STYLE_REALISTIC,
                stage="shots" if shots else "scenes" if scenes else "draft", dirty_images=[], dirty_audio=[])


def validate_review(document, require_shots=False):
    """Validate identity references and ordered source coverage before any write."""
    items = document["items"]
    characters = [Character(**c) for c in items.get("characters", [])]
    ids = [c.character_id for c in characters]
    if len(ids) != len(set(ids)) or any(not cid.strip() for cid in ids):
        raise ValueError("人物编号必须唯一且非空")
    objects = items.get("objects", {})
    if not isinstance(objects, dict) or any(not k.strip() or not isinstance(v, str) for k, v in objects.items()):
        raise ValueError("物品必须由名称和文本描述组成")
    locations = items.get("locations", [])
    names = [location["name"] for location in locations]
    if len(set(names)) != len(names) or any(not name.strip() for name in names):
        raise ValueError("地点名称必须唯一且非空")
    for location in locations:
        if not isinstance(location.get("description", ""), str):
            raise ValueError("地点描述必须是文本")
    for key in ("time", "emotion"):
        if not isinstance(items.get(key, []), list) or any(not isinstance(v, str) for v in items.get(key, [])):
            raise ValueError(f"{key} 必须是文本列表")
    scenes = [Scene(**s) for s in document.get("scenes", [])]
    scene_ids, shot_ids = set(), set()
    compact = lambda text: "".join(text.split())
    for scene in scenes:
        info = scene.scene_info
        if info.scene_id in scene_ids:
            raise ValueError("场景编号重复")
        scene_ids.add(info.scene_id)
        if not scene.scene_text.strip():
            raise ValueError("场景原文不能为空")
        if not set(info.characters_in_scene) <= set(ids) or not set(info.scene_visual_overrides) <= set(info.characters_in_scene):
            raise ValueError(f"场景 {info.scene_id} 引用未知人物或覆盖了未出场人物")
        if not set(info.objects_in_scene) <= set(objects):
            raise ValueError(f"场景 {info.scene_id} 引用未知物品")
        if info.location not in names or info.time not in items.get("time", []) or (info.emotion and info.emotion not in items.get("emotion", [])):
            raise ValueError(f"场景 {info.scene_id} 的地点、时间或情绪不在元素列表中")
        if require_shots and not scene.shots:
            raise ValueError(f"场景 {info.scene_id} 尚无分镜")
        for shot in scene.shots:
            if shot.shot_id in shot_ids or not shot.shot_id.strip() or shot.scene_id != info.scene_id:
                raise ValueError("分镜编号重复、为空或所属场景不匹配")
            shot_ids.add(shot.shot_id)
            if shot.narration_text is not None and not shot.narration_text.strip():
                raise ValueError(f"分镜 {shot.shot_id} 的旁白不能为空")
            if not shot.shot_text.strip() or not set(shot.focus_characters) <= set(info.characters_in_scene) or not set(shot.focus_objects) <= set(info.objects_in_scene):
                raise ValueError(f"分镜 {shot.shot_id} 原文为空或引用了场景外的元素")
        if scene.shots and compact("".join(s.shot_text for s in scene.shots)) != compact(scene.scene_text):
            raise ValueError(f"场景 {info.scene_id} 的分镜原文必须按顺序完整覆盖场景，不得遗漏或重叠")
    if scenes and compact("".join(s.scene_text for s in scenes)) != compact(document["source_text"]):
        raise ValueError("场景原文必须按顺序完整覆盖故事原文")
    if require_shots and not scenes:
        raise ValueError("请先生成或添加场景和分镜")
    return scenes


def compile_review(document):
    scenes = validate_review(document, require_shots=True)
    pipeline = StoryPipeline()
    return pipeline.compile_story(document["items"], scenes, document.get("style_tokens", STYLE_REALISTIC))


def save_review(project_id, changes, expected_revision):
    manager = manager_for(project_id)
    previous = read_review(project_id)
    if previous["revision"] != expected_revision:
        raise ReviewConflict("内容已在其他页面更新，请重新加载后再编辑")
    updated = copy.deepcopy(previous)
    for key in ("source_text", "items", "scenes", "style_tokens"):
        if key in changes:
            updated[key] = changes[key]
    validate_review(updated)
    task = TASKS[project_id]
    old_segments = task.get("prompts") or []
    complete = bool(updated["scenes"]) and all(s.get("shots") for s in updated["scenes"])
    if complete:
        result = compile_review(updated)
        segments = result["segments"]
        old_ids = [s.get("shot_id") for s in old_segments if isinstance(s, dict)]
        new_ids = [s["shot_id"] for s in segments]
        # Structural edits are allowed before media; after rendering require a
        # separate project so positional media/history can never be misassigned.
        has_media = any(task.get("images", [])) or any(task.get("audios", []))
        if has_media and old_ids != new_ids:
            raise ValueError("已有媒体时不能增删或重排分镜；请新建项目调整分镜结构。描述和原文仍可编辑。")
        dirty_images = set(updated.get("dirty_images", []))
        dirty_audio = set(updated.get("dirty_audio", []))
        # Compare edited plans, not a chosen image's historical prompt. Audio-only
        # edits must not invalidate an explicitly accepted older image.
        previous_segments = old_segments
        if old_segments and previous.get("scenes") and all(s.get("shots") for s in previous["scenes"]):
            previous_segments = compile_review(previous)["segments"]
        for index, segment in enumerate(segments):
            old = previous_segments[index] if index < len(previous_segments) and isinstance(previous_segments[index], dict) else {}
            if old.get("image_prompt") != segment["image_prompt"]:
                dirty_images.add(index)
            if old.get("text") != segment["text"]:
                dirty_audio.add(index)
        # Capture old input/config before installing the new plan.
        for index in dirty_images:
            if index < len(task.get("images", [])) and task["images"][index]:
                manager._ensure_image_history_entry(project_id, index)
        for index in dirty_audio:
            if index < len(task.get("audios", [])) and task["audios"][index]:
                manager._ensure_audio_history_entry(project_id, index)
        manager._persist_story_artifacts(project_id, result)
        task["images_configs"] = []
        if not has_media:
            for key in ("images", "audios", "durations", "clips", "video_segments", "image_redraw_history", "audio_redraw_history"):
                task[key] = []
        manager._restore_story_inputs(project_id, segments)
        manager._ensure_audio_configs(project_id, task["lines"],
                                      manager._get_project_config_value(project_id, "audio_model_name", ""), "",
                                      manager._get_project_config_value(project_id, "voice", ""))
        updated["dirty_images"] = sorted(i for i in dirty_images if i < len(segments))
        updated["dirty_audio"] = sorted(i for i in dirty_audio if i < len(segments))
        updated["stage"] = "shots"
    elif old_segments and (any(task.get("images", [])) or any(task.get("audios", []))):
        raise ValueError("已有媒体的项目不能移除场景或分镜")
    else:
        updated["stage"] = "scenes" if updated["scenes"] else "items" if any(updated["items"].values()) else "draft"
        for key in ("prompts", "lines", "images", "images_configs", "audios", "durations", "clips"):
            task[key] = []
        for filename, value in (("items.json", updated["items"]), ("scenes.json", updated["scenes"]),
                                ("shots.json", [shot for scene in updated["scenes"] for shot in scene.get("shots", [])]),
                                ("segments.json", [])):
            manager._write_artifact_json(project_id, "story", filename, value)
    updated["revision"] += 1
    updated.pop("error", None)
    task["story_review"] = updated
    task.update(status="review", stage="等待审阅：" + updated["stage"])
    manager._write_artifact_json(project_id, "story", "review.json", updated)
    manager.save_project(project_id)
    return copy.deepcopy(updated)


def run_stage(project_id, stage, cancel_event, progress_cb, shot_id=None):
    import math
    manager = manager_for(project_id)
    document = read_review(project_id)
    task = TASKS[project_id]
    document.pop("error", None)
    task.pop("error", None)
    task.pop("errors", None)
    config = manager._normalize_config_for_save(manager.projects[project_id]["config"])
    def check_cancel():
        if cancel_event.is_set():
            raise InterruptedError("任务已取消，已保存的内容保留")
    check_cancel()
    if stage == "pipeline":
        # All stages operate on the active chapter's persisted plan and assets.
        # Retrying fills missing shots/media without replacing reviewed work.
        if not document.get("scenes"):
            if not task.get("chapter_items_extracted"):
                run_stage(project_id, "items", cancel_event, progress_cb)
            run_stage(project_id, "scenes", cancel_event, progress_cb)
        if any(not scene.get("shots") for scene in read_review(project_id)["scenes"]):
            run_stage(project_id, "shots", cancel_event, progress_cb)
        run_stage(project_id, "media", cancel_event, progress_cb)
        run_stage(project_id, "compose", cancel_event, progress_cb)
        return {"status": "completed", "project_id": project_id,
                **manager._video_result_with_assets(True, project_id, TASKS[project_id].get("video_path", ""))}
    if stage in ("items", "scenes", "shots"):
        pipeline = StoryPipeline(checkpoint_dir=manager._artifact_section_dir(project_id, "story") / "analysis_cache")
        pipeline.initial_items = document["items"]
        pipeline.identity_prefix = manager.projects[project_id].get("active_chapter") or ""
        pipeline.cancel_event = cancel_event
        pipeline.use_model(config.get("text_model_name", ""), "")
        try:
            if stage == "items":
                if document["scenes"]:
                    raise ValueError("已有场景，请直接编辑元素；重新抽取请新建项目")
                if not document["source_text"].strip():
                    raise ValueError("请先输入故事原文")
                document["items"] = pipeline._extract_characters(document["source_text"])
                task["chapter_items_extracted"] = True
            elif stage == "scenes":
                if document["scenes"]:
                    raise ValueError("已有场景，请先编辑；如需重新划分，请在生成媒体前清空场景并保存")
                if "inherited_items" in task and not task.get("chapter_items_extracted"):
                    raise ValueError("本章尚未抽取新增元素，请先执行“抽取本章新增元素”，再生成场景")
                validate_review(document)
                pipeline.items = document["items"]
                pipeline.chunk_elements = [document["items"] for _ in split_story(document["source_text"])]
                document["scenes"] = [s.model_dump() for s in pipeline._segment_scenes(document["source_text"], document["items"])]
            else:
                scenes = validate_review(document)
                if not scenes:
                    raise ValueError("请先生成场景")
                for index, scene in enumerate(scenes):
                    check_cancel()
                    if not scene.shots:
                        scene.shots = pipeline._generate_shots(scene)
                    document["scenes"][index] = scene.model_dump()
                    # Persist each completed scene, so retry skips completed work.
                    document = save_review(project_id, document, document["revision"])
                    progress_cb({"progress": 100 * (index + 1) / len(scenes), "stage": f"分镜 {index + 1}/{len(scenes)}"})
            check_cancel()
            document = save_review(project_id, document, document["revision"])
        finally:
            pipeline.release_model()
    elif stage == "clip":
        shots = [shot for scene in document["scenes"] for shot in scene.get("shots", [])]
        index = next((i for i, shot in enumerate(shots) if shot["shot_id"] == shot_id), None)
        if index is None:
            raise ValueError("找不到该分镜")
        if index in document.get("dirty_images", []):
            raise ValueError("当前分镜图片待更新，请先生成或提交图片")
        if index in document.get("dirty_audio", []):
            raise ValueError("当前分镜配音待更新，请先生成配音")
        progress_cb({"progress": 0, "stage": f"正在生成分镜 {index + 1} 的视频段"})
        manager._rebuild_dirty_clips(project_id, shot_index=index)
        check_cancel()
        document["revision"] += 1
        task["story_review"] = document
        task.update(status="review", stage=f"分镜 {index + 1} 视频段已生成，可预览")
        manager.save_project(project_id)
    elif stage in ("media", "images", "audio", "redraw", "compose"):
        result = compile_review(document)
        segments = result["segments"]
        if stage == "compose":
            if document.get("dirty_images") or document.get("dirty_audio"):
                raise ValueError("存在待更新的图片或配音，请先生成或提交新版本")
            manager._validate_video_resume_assets(task.get("lines"), task.get("images"), task.get("audios"), task.get("durations"))
            manager._rebuild_dirty_clips(project_id)
            check_cancel()
            video = manager._concat_existing_clips(project_id)
            task["video_path"] = video
            document["stage"] = "completed"
        else:
            if stage == "redraw" and shot_id not in [s["shot_id"] for s in segments]:
                raise ValueError("找不到该分镜")
            if not task.get("prompts"):
                document = save_review(project_id, document, document["revision"])
            # Immutable input snapshot, referenced by generated candidates.
            snapshot = manager._write_artifact_json(project_id, "story/renders", f"{uuid4()}.json", document)
            for index, segment in enumerate(segments):
                check_cancel()
                if stage == "redraw" and segment["shot_id"] != shot_id:
                    continue
                need_image = stage != "audio" and (stage == "redraw" or index in document["dirty_images"] or not manager._is_valid_media_file(task["images"][index]))
                if need_image:
                    response = manager.gen_image(project_id, text=segment["image_prompt"], model_name=config.get("image_model_name", ""),
                                                 size=config.get("size", "1024*1024"), n=1, index=index, apply_result=False)
                    if not response["success"]:
                        raise ValueError(response.get("error") or "图片生成失败")
                    candidate = task["image_redraw_history"][index][-1]
                    candidate["story_input_snapshot"] = snapshot
                    candidate["story_revision"] = document["revision"]
                    if stage in ("media", "images"):
                        manager._apply_latest_image_redraw(project_id, index)
                        document["dirty_images"] = [i for i in document["dirty_images"] if i != index]
                    task["story_review"] = document
                    manager.save_project(project_id)
                if stage in ("media", "audio"):
                    audios = task.setdefault("audios", [])
                    durations = task.setdefault("durations", [])
                    while len(audios) <= index:
                        audios.append("")
                    while len(durations) <= index:
                        durations.append(0)
                    valid_duration = isinstance(durations[index], (int, float)) and math.isfinite(durations[index]) and durations[index] > 0
                    if index in document["dirty_audio"] or not manager._is_valid_media_file(audios[index]) or not valid_duration:
                        response = manager.gen_audio(project_id, text=segment["text"], model_name=config.get("audio_model_name", ""),
                                                     voice=config.get("voice", ""), language=config.get("language", "") or "", index=index)
                        if not response["success"]:
                            raise ValueError(response.get("error") or "配音生成失败")
                        manager.apply_redraw_selection(project_id, audio_selected_history={str(index): len(task["audio_redraw_history"][index]) - 1})
                        document["dirty_audio"] = [i for i in document["dirty_audio"] if i != index]
                        manager._mark_clips_dirty(project_id, [index])
                task["story_review"] = document
                manager.save_project(project_id)
                progress_cb({"progress": 100 * (index + 1) / len(segments), "stage": f"素材 {index + 1}/{len(segments)}"})
            document["stage"] = stage if stage in ("media", "images", "audio") else document["stage"]
        document["revision"] += 1
        task["story_review"] = document
        task.update(status="completed" if stage == "compose" else "review", stage="完成，等待审阅")
        manager.save_project(project_id)
    else:
        raise ValueError("未知阶段")
    return {"status": "completed", "project_id": project_id}


async def stage_job(project_id, stage, cancel_event, progress_cb, shot_id=None):
    register_progress_callback(project_id, progress_cb)
    def execute():
        try:
            return run_stage(project_id, stage, cancel_event, progress_cb, shot_id), None
        except Exception as exc:
            return None, exc
    worker = asyncio.create_task(asyncio.to_thread(execute))
    try:
        result, failure = await asyncio.shield(worker)
        if failure:
            raise failure
        return result
    except asyncio.CancelledError:
        # Cancelling an await does not stop a Python thread. Keep the project
        # locked until its current external call returns and the worker exits.
        cancel_event.set()
        try:
            await worker
        except Exception:
            pass
        TASKS[project_id].update(status="review", stage="已取消，已保存内容保留")
        getPipelineManager().save_project(project_id)
        return {"status": "cancelled"}
    except InterruptedError as exc:
        TASKS[project_id].update(status="review", stage=str(exc))
        getPipelineManager().save_project(project_id)
        return {"status": "cancelled", "error": str(exc)}
    except Exception as exc:
        TASKS[project_id].setdefault("story_review", read_review(project_id))["error"] = str(exc)
        TASKS[project_id].update(status="error", stage=str(exc))
        getPipelineManager().save_project(project_id)
        raise
    finally:
        unregister_progress_callback(project_id)
        project_lock(project_id).release()
