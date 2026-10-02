from app.model.credential_request import CredentialRequest
"""
app/model/text_schema.py
========================
定义文案生成的输入与输出数据结构
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal


class TextRequest(CredentialRequest):
    # pid:str=Field(...,description="项目ID")
    theme: str = Field(..., description="视频主题或关键词")
    text_model_name: str = Field(..., description="使用的大模型名称（如 gpt-4-turbo）")
    text_api_key: str = Field("", description="Deprecated; credentials are read from server environment")
    style: Optional[str] = Field(None, description="可选文案风格（如 温柔 / 励志 / 科普）")
    language: Optional[Literal["zh", "en"]] = Field(None, description="文本语言")
    with_media_prompts: bool = Field(False, description="是否生成 media prompt")
    media_prompt_style: Optional[str] = Field(None, description="media prompt 风格")


class TextResponse(BaseModel):
    theme: str
    model_name: str
    content: str = ""
    success: bool = True
    error: Optional[str] = None
    prompts: List[str] = []



class Character(BaseModel):
    character_id: str
    name: str
    type: str              # "human" | "animal" | "object" | ...
    can_talk: bool
    is_main: bool
    visual_core: str
    visual_variants_allowed: Optional[str] = ""
    style_tags: List[str] = []
    # 可扩展：fixed_features, personality, voice_hint 等


class LocationInfo(BaseModel):
    name: str
    description: str


class Scene(BaseModel):
    scene_id: int
    text: str                     # 该场景对应的原文段落
    location: str
    time: str
    characters_in_scene: List[str]
    objects_in_scene: List[str]
    scene_visual_overrides: Dict[str, str] = {}
    emotion: Optional[str] = None
    chain_id: Optional[str] = None
    # 可扩展：why_this_is_scene 等


class Shot(BaseModel):
    shot_id: str                  # "scene{scene_id}-shot{k}"
    scene_id: int
    focus_characters: List[str]
    shot_type: str                # "wide" | "medium" | ...
    camera_move: str              # "static" | "push_in" | ...
    lighting: str
    additional_detail: str
