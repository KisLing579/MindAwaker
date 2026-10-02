"""Import a local background into a project's image history and select it."""
from copy import deepcopy
from io import BytesIO
from time import time
from uuid import uuid4

from PIL import Image, ImageOps


def replace_background(manager, project_id, index, data):
    manager._ensure_project_loaded(project_id)
    snapshot = manager.get_project_snapshot(project_id)
    task = snapshot["task_data"]
    images = task.get("images") or []
    if index < 0 or index >= len(images):
        raise ValueError("视频段索引无效")
    if not data or len(data) > 20 * 1024 * 1024:
        raise ValueError("请选择不超过20MB的图片")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP", "BMP"}:
                raise ValueError("支持 PNG、JPEG、WebP、BMP 图片")
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("无法读取该图片文件") from exc
    manager._ensure_image_history_entry(project_id, index)
    configs = task.get("images_configs") or []
    config = deepcopy(configs[index] if index < len(configs) else {})
    prompt = config.get("prompt") or config.get("text") or ""
    path = manager._project_dir(project_id) / f"uploaded_background_{uuid4().hex}.png"
    image.save(path, format="PNG")
    manager._append_redraw_history_candidate(project_id, "image", index, {
        "image_path": str(path), "prompt": prompt, "config": config,
        "created_at": int(time()), "is_current": False, "source": "upload",
    })
    history = manager.get_project_snapshot(project_id)["task_data"]["image_redraw_history"][index]
    manager.apply_redraw_selection(project_id, image_selected_history={str(index): len(history) - 1})
    if task.get("story_review"):
        task["story_review"]["revision"] += 1
    manager.save_project(project_id)
    return manager.get_project_snapshot(project_id)
