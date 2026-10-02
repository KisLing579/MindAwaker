from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StoryCharacterBinding(BaseModel):
    source_character_id: str
    mw_character_id: str


class StorySceneBinding(BaseModel):
    world_scene_id: str
    mw_scene_instance_id: str
    source_scene_ids: List[str] = Field(default_factory=list)


class StoryVisualSession(BaseModel):
    project_id: str
    style_id: str = "default"
    character_bindings: Dict[str, str] = Field(default_factory=dict)
    scene_bindings: Dict[str, str] = Field(default_factory=dict)
    raw_character_mappings: List[Dict[str, Any]] = Field(default_factory=list)
    raw_scene_mappings: List[Dict[str, Any]] = Field(default_factory=list)


class ShotRenderPrompt(BaseModel):
    positive: str
    negative: str = ""


class ShotRenderRequest(BaseModel):
    story_session: Optional[StoryVisualSession] = None
    scene_ref: str = ""
    character_refs: List[str] = Field(default_factory=list)
    shot_id: str
    shot: Dict[str, Any] = Field(default_factory=dict)
    prompt: ShotRenderPrompt
    size: str = "1024*720"
    n: int = 1


class ShotRenderResponse(BaseModel):
    success: bool = True
    error: Optional[str] = None
    image_paths: List[str] = Field(default_factory=list)
    workflow: Optional[Dict[str, Any]] = None
