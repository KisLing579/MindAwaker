import json
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.configs.logging_config import get_logger
from app.model.settings_schema import SETTINGS_PATH, Settings

logger = get_logger(__name__)
router = APIRouter()

TEMPLATES_DIR = Path("app/assets/templates")
VOICES_DIR = Path("app/assets/voices")


def _load_settings_data() -> Settings:
    if not os.path.exists(SETTINGS_PATH):
        return Settings()
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Settings(**data)


def _save_settings_data(cfg: Settings) -> None:
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg.model_dump(), f, ensure_ascii=False, indent=2)


def _sanitize_filename(filename: str, fallback: str) -> str:
    name = Path(filename or fallback).name
    return name or fallback


@router.post("/load")
def load_settings():
    return _load_settings_data()


@router.post("/save")
def save_settings(cfg: Settings):
    logger.info(f"保存设置: {cfg}")
    _save_settings_data(cfg)
    return {"saved": True, "settings": cfg}


@router.get("/templates")
def list_templates():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    templates = [
        {"name": path.name, "path": str(path).replace("\\", "/")}
        for path in sorted(TEMPLATES_DIR.iterdir())
        if path.is_file()
    ]
    return {"templates": templates}


@router.post("/templates/upload")
def upload_template(file: UploadFile = File(...)):
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(file.filename or "template.j2", "template.j2")
    destination = TEMPLATES_DIR / filename
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"name": destination.name, "path": str(destination).replace("\\", "/")}


@router.post("/voices/upload")
def upload_voice(file: UploadFile = File(...)):
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(file.filename or "voice.wav", "voice.wav")
    destination = VOICES_DIR / filename
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"name": destination.name, "path": str(destination).replace("\\", "/")}


@router.get("/defaults")
def load_setting_defaults():
    settings = _load_settings_data()
    return {
        "default_language": settings.default_language,
        "default_text_model_name": settings.default_text_model_name,
        "default_audio_model_name": settings.default_audio_model_name,
        "default_image_model_name": settings.default_image_model_name,
        "voices": [voice.model_dump() for voice in settings.voices],
    }
