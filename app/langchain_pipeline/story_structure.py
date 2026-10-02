import json
from pydantic import BaseModel
from typing import Optional, List, Dict, Tuple

from app.langchain_pipeline.base_text import BaseTextGenerator


# ========= 数据结构 =========


class Character(BaseModel):
    character_id: str
    name: str
    type: str  # "human" | "animal" | "object" | ...
    can_talk: bool
    is_main: bool
    visual_core: str
    visual_variants_allowed: Optional[str] = ""
    style_tags: List[str] = []


class LocationInfo(BaseModel):
    name: str
    description: str


class SceneInfo(BaseModel):
    scene_id: int
    location: str
    time: str
    characters_in_scene: List[str]
    objects_in_scene: List[str]
    scene_visual_overrides: Dict[str, str] = {}
    environment_description: str = ""
    emotion: Optional[str] = None
    chain_id: Optional[str] = None

    def model_post_init(self, context):
        # Older prompts put set descriptions among character overrides.
        descriptions = [self.environment_description] if self.environment_description else []
        for key in ("environment", "setting", "layout", "spatial_layout", "set_dressing"):
            if key in self.scene_visual_overrides and key not in self.characters_in_scene:
                description = self.scene_visual_overrides.pop(key)
                if description and description not in descriptions:
                    descriptions.append(description)
        self.environment_description = "\n".join(descriptions)


class Scene(BaseModel):
    scene_text: str
    scene_info: SceneInfo
    shots: List["Shot"] = []


class Shot(BaseModel):
    shot_id: str  # "scene{scene_id}-shot{k}"
    scene_id: int
    focus_characters: List[str] = []
    focus_objects: List[str] = []
    shot_type: str
    camera_move: str
    lighting: str
    additional_detail: List[str] = []
    shot_text: str
    narration_text: Optional[str] = None  # User-edited narration; None uses source text.


# ========= LLM 封装 =========
import httpx

http_client = httpx.Client(
    timeout=httpx.Timeout(180.0, connect=10.0, read=180.0),
    http2=False,  # 很关键：关掉 http2，很多云 + 代理在 http2 下容易出怪错
)


class StorySturctureChainGenerator(BaseTextGenerator):
    """故事结构生成器"""

    def generate(self, prompt: str) -> str:
        """生成故事结构"""
        response = self._invoke_model(prompt)
        return response["content"].strip()
