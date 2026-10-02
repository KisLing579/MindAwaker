"""Chapter snapshots within one project; media paths remain chapter-local."""
import copy
import json
import time
from uuid import uuid4

from app.configs.constants import STYLE_REALISTIC
from app.service.pipeline_manager import TASKS
from app.service.story_chunks import empty_items, merge_items
from app.service.story_review import read_review


def create_chapter(manager, project_id, title, source_text):
    if not source_text.strip():
        raise ValueError("章节正文不能为空")
    project = manager.projects[project_id]
    document = read_review(project_id)
    chapters = copy.deepcopy(project.get("chapters") or [])
    if not chapters:
        chapters = [{"id": "original", "title": "原始章节"}]
        project.update(active_chapter="original", chapters=chapters)
    manager.save_project(project_id)
    # Fold the latest saved version of every chapter, then the selected chapter.
    items = empty_items()
    root = manager.base_dir / project_id
    for chapter in chapters:
        path = root / "chapters" / chapter["id"] / "meta.json"
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        task = snapshot.get("task_data") or {}
        previous = (task.get("story_review") or {}).get("items")
        if previous is None:
            directory = root if chapter["id"] == "original" else path.parent
            item_path = directory / "artifacts" / "story" / "items.json"
            previous = json.loads(item_path.read_text(encoding="utf-8")) if item_path.exists() else task.get("inherited_items", {})
        items = merge_items(items, previous, 0)
    items = merge_items(items, document["items"], 0)
    chapter_id = uuid4().hex
    chapters.append({"id": chapter_id, "title": title.strip() or f"第 {len(chapters) + 1} 章"})
    config = copy.deepcopy(manager._normalize_config_for_save(project["config"]))
    config["article"] = source_text
    project.update(config=config, active_chapter=chapter_id, chapters=chapters)
    TASKS[project_id] = {
        "status": "draft", "percent": 0, "stage": "新章节",
        "inherited_items": copy.deepcopy(items),
        "story_review": dict(revision=max(document["revision"] + 1, int(time.time() * 1000)), source_text=source_text,
                             items=items, scenes=[], style_tokens=document.get("style_tokens", STYLE_REALISTIC),
                             stage="draft", dirty_images=[], dirty_audio=[]),
    }
    manager._write_artifact_json(project_id, "story", "items.json", items, key="items_json")
    manager.save_project(project_id)
    return manager.get_project_snapshot(project_id)


def select_chapter(manager, project_id, chapter_id):
    project = manager.projects[project_id]
    chapters = copy.deepcopy(project.get("chapters") or [])
    if chapter_id not in {c["id"] for c in chapters}:
        raise ValueError("章节不存在")
    if chapter_id == project.get("active_chapter"):
        return manager.get_project_snapshot(project_id)
    path = manager.base_dir / project_id / "chapters" / chapter_id / "meta.json"
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    manager.save_project(project_id)
    project.update(config=snapshot["project_config"], active_chapter=chapter_id, chapters=chapters)
    TASKS[project_id] = snapshot.get("task_data") or {}
    # Invalidate edits left open in another browser tab.
    review = TASKS[project_id].get("story_review")
    if review:
        review["revision"] = max(review["revision"] + 1, int(time.time() * 1000))
    manager.save_project(project_id)
    return manager.load_project(project_id)
