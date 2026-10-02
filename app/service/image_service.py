"""
app/service/image_service.py
=============================
图像生成服务层
"""

from app.image_engine.volc_engine import VolcEngine
from app.image_engine.flux_engine import FluxEngine
from app.model.story_visual_schema import ShotRenderRequest


class ImageGenerationService:
    def __init__(self):
        print("init the Image Diffuser")

    def create_engine(self, image_model_name: str = "", image_api_key: str = ""):
        model_name = (image_model_name or "").lower()
        if "sdxl" in model_name:
            return True
        if "jimeng" in model_name or "volc" in model_name:
            self.engine = VolcEngine(image_api_key=image_api_key)
            return True
        if "flux" in model_name:
            self.engine = FluxEngine(image_api_key=image_api_key)
            return True
        return False

    def has_active_engine(self):
        return hasattr(self, "engine")

    def ensure_engine(self, image_model_name: str = "", image_api_key: str = ""):
        if self.has_active_engine():
            return True
        return self.create_engine(image_model_name=image_model_name, image_api_key=image_api_key)

    def current_engine_name(self):
        return self.engine.__class__.__name__ if hasattr(self, "engine") else ""

    def supports_story_world_preparation(self):
        return hasattr(self.engine, "build_characters") and hasattr(self.engine, "build_scenes") if hasattr(self, "engine") else False

    def build_characters(self, character_specs):
        if not hasattr(self.engine, "build_characters"):
            raise ValueError("current image engine does not support build_characters")
        return self.engine.build_characters(character_specs)

    def build_scenes(self, scene_specs, character_bindings=None):
        if not hasattr(self.engine, "build_scenes"):
            raise ValueError("current image engine does not support build_scenes")
        return self.engine.build_scenes(scene_specs, character_bindings)

    def prepare_story_world(self, character_specs, scene_specs, character_bindings=None):
        return {
            "characters": self.build_characters(character_specs),
            "scenes": self.build_scenes(scene_specs, character_bindings),
        }

    def supports_shot_render(self):
        return hasattr(self.engine, "render_shot") if hasattr(self, "engine") else False

    def render_shot(self, request: ShotRenderRequest):
        if not hasattr(self.engine, "render_shot"):
            raise ValueError("current image engine does not support render_shot")
        return self.engine.render_shot(request)

    def release_engine(self):
        self.engine.release()
        del self.engine

    def release_engine_if_exists(self):
        if hasattr(self, "engine"):
            self.release_engine()
            return True
        return False

    def generate(self, prompt: str, output_dir: str = "", size: str = "1024*1024", n: int = 1):
        print("before gen the Image by Diffuser")
        if output_dir == "":
            paths = self.engine.generate_images(prompt=prompt, n=n, size=size)
        else:
            paths = self.engine.generate_images(prompt=prompt, n=n, size=size, output_dir=output_dir)
        print("after gen the Image by Diffuser")
        return True, paths
