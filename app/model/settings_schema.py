# settings_model.py
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Union, Literal

SETTINGS_PATH = str(Path(__file__).resolve().parents[1] / "configs" / "settings.json")


class VoiceConfig(BaseModel):
    name: str
    file_path: str  # 录音文件在服务器上的路径


LanguageCode = Literal["zh", "en"]
TemplateLanguageMap = Dict[str, str]
TemplateConfigValue = Union[str, TemplateLanguageMap]


class Settings(BaseModel):
    voices: List[VoiceConfig] = Field(default_factory=list)
    enable_image_consistency: bool = False
    image_consistency_weight: float = 0.7  # 0~1 或者 0~2 都可以
    default_language: LanguageCode = "zh"
    theme2text_mode: str = "default"       # "default" or "custom"
    theme2text_template_global: TemplateConfigValue = ""   # 全局模板
    theme2text_templates: Dict[str, TemplateConfigValue] = Field(default_factory=dict)  # 针对特定 theme 的模板
    media_prompt_template_global: TemplateConfigValue = ""
    media_prompt_templates: Dict[str, TemplateConfigValue] = Field(default_factory=dict)
    default_text_model_name: str = "deepseek"
    default_audio_model_name: str = "azure"
    default_image_model_name: str = "jimeng"
