
import json
import os
from typing import Dict, Optional

from app.model.settings_schema import SETTINGS_PATH, Settings
from app.utils.language_utils import LanguageCode, normalize_language


DEFAULT_LANGUAGE: LanguageCode = "zh"


def load_settings() -> Settings:
    if not os.path.exists(SETTINGS_PATH):
        return Settings()
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Settings(**data)


def get_voices():
    settings = load_settings()
    return [voice.model_dump() for voice in settings.voices]


def get_voice_path(voice_name: str):
    voices = get_voices()
    return next((v["file_path"] for v in voices if v["name"] == voice_name), None)


def get_default_language() -> LanguageCode:
    settings = load_settings()
    return settings.default_language


def get_themes_templates() -> Dict[str, object]:
    settings = load_settings()
    return settings.theme2text_templates


def get_media_prompt_templates() -> Dict[str, object]:
    settings = load_settings()
    return settings.media_prompt_templates


def _resolve_template_value(template_value, language: Optional[str]) -> Optional[str]:
    if isinstance(template_value, str):
        return template_value
    if not isinstance(template_value, dict):
        return None

    normalized_language = normalize_language(language) or DEFAULT_LANGUAGE
    if template_value.get(normalized_language):
        return template_value[normalized_language]
    if template_value.get(DEFAULT_LANGUAGE):
        return template_value[DEFAULT_LANGUAGE]
    if template_value.get("en"):
        return template_value["en"]
    if template_value:
        return next(iter(template_value.values()))
    return None


def _get_template_path(template_map: Dict[str, object], key: Optional[str], fallback_key: Optional[str], language: Optional[str]) -> str:
    normalized_key = key or fallback_key or "温柔"
    template_path = _resolve_template_value(template_map.get(normalized_key), language)

    if template_path is None and fallback_key and normalized_key != fallback_key:
        template_path = _resolve_template_value(template_map.get(fallback_key), language)

    if template_path is None and template_map:
        template_path = _resolve_template_value(next(iter(template_map.values())), language)

    if template_path is None:
        raise KeyError(f"No template configured for key: {key!r}")

    return template_path


def get_template_path(style_name: str, language: Optional[str] = None):
    return _get_template_path(get_themes_templates(), style_name, "温柔", language)


def get_media_prompt_template_path(style_name: Optional[str] = None, language: Optional[str] = None):
    settings = load_settings()
    templates = settings.media_prompt_templates or {}
    if not templates and settings.media_prompt_template_global:
        return _resolve_template_value(settings.media_prompt_template_global, language)
    return _get_template_path(templates, style_name, "image_default", language)
