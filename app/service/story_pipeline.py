"""
故事视频 Pipeline
解析故事文本，生成角色、场景、分镜结构
"""

import json
import re
import time
import hashlib
from pathlib import Path
from collections import OrderedDict
from typing import Optional, List, Dict, Tuple, Any
from httpx import RemoteProtocolError

from app.langchain_pipeline.story_structure import (
    Character,
    Scene,
    Shot,
    StorySturctureChainGenerator,
)
from app.configs.constants import (
    CHARACTER_PROMPT_TEMPLATE,
    SCENE_PROMPT_TEMPLATE,
    SHOT_PROMPT_TEMPLATE,
    STYLE_REALISTIC,
)
from app.service.base_pipeline import BasePipeline
from app.utils.language_utils import estimate_narration_duration
from app.service.story_chunks import split_story, empty_items, merge_items, relevant_items, compact_index, consolidate_characters
from app.service.story_chunks import source_units, numbered_source, restore_source_ranges


AnchorStore = Dict[Tuple[str, int, str], dict]


class StoryPipeline(BasePipeline):
    """
    故事视频生成 Pipeline

    职责：
    - 解析故事文本为角色、场景、分镜结构
    - 生成图像提示词（保持角色一致性）

    输出：
    - segments: 分镜列表，每个分镜包含：
        - shot_text: 旁白/TTS文本
        - image_prompt: 图像提示词
        - character_ids: 涉及的角色
        - type: "story"
    """

    def __init__(self, checkpoint_dir=None):
        super().__init__(StorySturctureChainGenerator)
        self.items: Optional[dict] = None
        self.scenes: Optional[List[Scene]] = None
        self.anchor_store: AnchorStore = {}
        self.character_dict: Dict[str, Character] = {}
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else None
        self.chunk_elements = []

    def _json_response(self, prompt, validate):
        if getattr(self, "cancel_event", None) and self.cancel_event.is_set():
            raise InterruptedError("故事解析已停止")
        # Cache only validated responses. The prompt hash invalidates changed text/templates.
        if len(prompt) > 24000:
            raise ValueError("故事分析提示词超过 24000 字符预算，请减少单段长度或拆分故事")
        path = None
        if self.checkpoint_dir:
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
            path = self.checkpoint_dir / (hashlib.sha256(prompt.encode("utf-8")).hexdigest() + ".json")
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    validate(data)
                    return data
                except (ValueError, TypeError, KeyError):
                    pass
        retry_prompt = prompt
        for attempt in range(3):
            if getattr(self, "cancel_event", None) and self.cancel_event.is_set():
                raise InterruptedError("故事解析已停止")
            raw = ""
            try:
                raw = self.call_llm_with_retry(retry_prompt)
                data = json.loads(raw.replace("```json", "").replace("```", "").strip())
                validate(data)
                if path:
                    temporary = path.with_suffix(".tmp")
                    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                    temporary.replace(path)
                return data
            except (ValueError, TypeError, KeyError) as exc:
                if path:
                    failure = path.with_name(f"{path.stem}.failed-{attempt + 1}.json")
                    failure.write_text(json.dumps({"prompt": retry_prompt, "response": raw, "error": str(exc)}, ensure_ascii=False, indent=2), encoding="utf-8")
                retry_prompt = prompt + "\n上次输出未通过校验，请重新生成完整 JSON。具体原因：" + str(exc)[:1200]
                if attempt == 2:
                    raise ValueError(f"故事解析输出校验失败：{exc}") from exc

    def parse(self, story: str) -> List[Scene]:
        """
        三阶段解析：角色 -> 场景 -> 分镜
        """
        # 1. 提取角色
        items = self._extract_characters(story)
        character_list = [Character(**c) for c in items.get("characters", [])]
        self.character_dict: Dict[str, Character] = {c.character_id: c for c in character_list}

        # 2. 划分场景
        scenes = self._segment_scenes(story, items)

        # 3. 为每个场景生成分镜
        for scene in scenes:
            shots = self._generate_shots(scene)
            scene.shots = shots

        self.scenes = scenes
        return scenes

    def generate(self, story: str, style_tokens: str = STYLE_REALISTIC) -> Dict[str, Any]:
        """Parse a story into illustrated, narrated shots."""
        scenes = self.parse(story)
        return self.compile_story(self.items or {}, scenes, style_tokens)

    def compile_story(self, items: dict, scenes: List[Scene], style_tokens: str = STYLE_REALISTIC) -> Dict[str, Any]:
        """Compile an edited plan without calling the language model again."""
        self.items = items
        self.scenes = scenes
        self.character_dict = {c["character_id"]: Character(**c) for c in items.get("characters", [])}
        character_specs = self._export_character_specs()
        world_scenes, scene_to_world_scene = self._build_world_scenes(scenes)
        segments = []
        for scene_idx, scene in enumerate(scenes):
            for shot in scene.shots:
                scene_id = str(scene.scene_info.scene_id)
                prompt = self._build_image_prompt(scene=scene, shot=shot, style_tokens=style_tokens)
                segments.append({
                    "scene_idx": scene_idx,
                    "scene_id": scene_id,
                    "world_scene_id": scene_to_world_scene.get(scene_id, ""),
                    "shot_idx": len(segments),
                    "shot_id": shot.shot_id,
                    "type": "story",
                    "text": shot.narration_text if shot.narration_text is not None else shot.shot_text,
                    "source_text": shot.shot_text,
                    "image_prompt": prompt,
                    "focus_characters": shot.focus_characters,
                    "duration": self._estimate_duration(shot.narration_text if shot.narration_text is not None else shot.shot_text),
                })
        return {
            "segments": segments,
            "characters": list(self.character_dict.values()),
            "character_specs": character_specs,
            "items": self.items or {},
            "scenes": scenes,
            "world_scenes": world_scenes,
            "scene_to_world_scene": scene_to_world_scene,
            "shots": [shot for scene in scenes for shot in scene.shots],
            "anchor_store": self.anchor_store,
            "scene_count": len(scenes),
            "world_scene_count": len(world_scenes),
            "shot_count": len(segments),
        }

    def _extract_characters(self, story: str) -> dict:
        """Sequentially extract deltas while preserving stable global identities."""
        self.items = json.loads(json.dumps(getattr(self, "initial_items", None) or empty_items()))
        self.chunk_elements = []
        previous_text = ""
        for index, chunk in enumerate(split_story(story)):
            context = {"index": compact_index(self.items)}
            if self.chunk_elements:
                context["recent_elements"] = relevant_items(self.items, self.chunk_elements[-1])
            prompt = self._render_template(CHARACTER_PROMPT_TEMPLATE, story=chunk, items=context)
            prompt += "\n前块结尾（仅供消解代词，不重复提取）：\n" + previous_text[-300:]
            prompt += f"\n本块编号：{index + 1}。新增角色 ID 使用 {getattr(self, 'identity_prefix', '')}chunk{index + 1}_person_序号，已有角色必须复用 ID。"

            def validate(delta):
                merged = merge_items(self.items, delta, index)
                for character in merged["characters"]:
                    Character(**character)
                consolidate_characters(merged, self.chunk_elements + [delta], delta.get("character_merges", {}))

            delta = self._json_response(prompt, validate)
            self.items = merge_items(self.items, delta, index)
            self.chunk_elements.append(delta)
            self.items, self.chunk_elements = consolidate_characters(
                self.items, self.chunk_elements, delta.get("character_merges", {}))
            if self.checkpoint_dir:
                # Keep a reviewable merged snapshot in addition to reusable model responses.
                snapshot = self.checkpoint_dir / "elements_latest.json"
                temporary = snapshot.with_suffix(".tmp")
                temporary.write_text(json.dumps({
                    "story_sha256": hashlib.sha256(story.encode("utf-8")).hexdigest(),
                    "completed_chunks": index + 1,
                    "items": self.items,
                    "chunk_elements": self.chunk_elements,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.replace(snapshot)
            previous_text = chunk
        return self.items

    def _segment_scenes(self, story: str, items: dict) -> List[Scene]:
        """划分场景"""
        scenes = []
        for index, chunk in enumerate(split_story(story)):
            local_items = relevant_items(items, self.chunk_elements[index])
            units = source_units(chunk)
            prompt = self._render_template(SCENE_PROMPT_TEMPLATE, story=numbered_source(units), items=local_items)
            prompt += f"\n当前故事块 {index + 1}，共有 {len(units)} 个原文片段。范围从 1 开始连续覆盖到 {len(units)}，不得遗漏或重叠。"
            prompt += "\n程序必需字段：每个场景对象必须包含整数 source_start 和 source_end（闭区间，引用本次输入片段的 id，非字符位置）。不要用 scene_text 代替这两个字段；原文由程序还原。"
            if scenes:
                prompt += "\n前块末场景（仅供衔接，不复制原文）：" + scenes[-1].scene_info.model_dump_json()
                prompt += "\n若延续同一叙事线，复用 chain_id；时间跳跃或回忆必须明确区分。"

            def validate(data):
                if not isinstance(data, list) or not data:
                    raise ValueError("场景输出必须为非空数组")
                parsed = [Scene(**entry) for entry in restore_source_ranges(data, units, "scene_text")]
                allowed = {c["character_id"] for c in local_items["characters"]}
                for scene in parsed:
                    if not scene.scene_text.strip():
                        raise ValueError("场景原文不能为空")
                    unknown_by_field = {
                        field: sorted(set(refs) - allowed)
                        for field, refs in (
                            ("characters_in_scene", scene.scene_info.characters_in_scene),
                            ("scene_visual_overrides", scene.scene_info.scene_visual_overrides),
                        )
                        if set(refs) - allowed
                    }
                    if unknown_by_field:
                        details = "；".join(
                            f"{field}={json.dumps(refs, ensure_ascii=False)}"
                            for field, refs in unknown_by_field.items()
                        )
                        raise ValueError(
                            f"场景引用了未知角色（故事块 {index + 1}，"
                            f"场景 {scene.scene_info.scene_id}）：{details}；"
                            f"本块允许的角色 ID={json.dumps(sorted(allowed), ensure_ascii=False)}"
                        )

            data = self._json_response(prompt, validate)
            for entry in restore_source_ranges(data, units, "scene_text"):
                scene = Scene(**entry)
                # Join a continuous boundary only while keeping downstream inputs bounded.
                if scenes and len(scenes[-1].scene_text) + len(scene.scene_text) <= 1000:
                    before = scenes[-1].scene_info.model_dump(exclude={"scene_id"})
                    after = scene.scene_info.model_dump(exclude={"scene_id"})
                    if before == after:
                        scenes[-1].scene_text += scene.scene_text
                        continue
                scene.scene_info.scene_id = len(scenes) + 1
                scenes.append(scene)
        return scenes

    def _generate_shots(self, scene: Scene) -> List[Shot]:
        """为场景生成分镜"""
        shots = []
        for chunk in split_story(scene.scene_text):
            shots.extend(self._generate_chunk_shots(scene, chunk))
        for index, shot in enumerate(shots, 1):
            shot.scene_id = scene.scene_info.scene_id
            shot.shot_id = f"scene{shot.scene_id}-shot{index}"
        return shots

    def _generate_chunk_shots(self, scene: Scene, text: str) -> List[Shot]:
        units = source_units(text)
        prompt = self._render_template(
            SHOT_PROMPT_TEMPLATE,
            scene_text=numbered_source(units),
            scene_info=scene.scene_info.model_dump_json(),
        )
        prompt += f"\n共有 {len(units)} 个原文片段。范围从 1 开始连续覆盖到 {len(units)}，不得遗漏或重叠。"
        prompt += "\n程序必需字段：每个分镜对象必须包含整数 source_start 和 source_end（闭区间，引用本次输入片段的 id，非字符位置）。不要用 shot_text 代替这两个字段；原文由程序还原。"
        def validate(data):
            if not isinstance(data, list) or not data:
                raise ValueError("分镜输出必须为非空数组")
            shots = [Shot(**entry) for entry in restore_source_ranges(data, units, "shot_text")]
            for shot in shots:
                if not shot.shot_text.strip() or not set(shot.focus_characters) <= set(scene.scene_info.characters_in_scene):
                    raise ValueError("分镜正文为空或引用未知角色")
        shot_list = self._json_response(prompt, validate)
        return [Shot(**sd) for sd in restore_source_ranges(shot_list, units, "shot_text")]

    def _export_character_specs(self) -> List[Dict[str, Any]]:
        """导出适合 mw 的角色规格。"""
        specs = []
        for char in self.character_dict.values():
            specs.append(
                {
                    "character_id": char.character_id,
                    "name": char.name,
                    "object_type": self._normalize_character_object_type(char.type),
                    "description": char.visual_core,
                    "visual_core": char.visual_core,
                    "visual_variants_allowed": char.visual_variants_allowed,
                    "key_features": self._extract_key_features(char),
                    "style_tags": char.style_tags,
                    "is_main_character": char.is_main,
                }
            )
        return specs

    def _build_world_scenes(self, scenes: List[Scene]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """将时序 scenes 归并为固定场景层。"""
        world_scene_index: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        scene_to_world_scene: Dict[str, str] = {}

        for scene in scenes:
            scene_info = scene.scene_info
            location = (scene_info.location or "unknown_location").strip().lower()
            time_value = (scene_info.time or "unspecified_time").strip().lower()
            characters = sorted(scene_info.characters_in_scene or [])
            objects = sorted(scene_info.objects_in_scene or [])
            world_key = self._build_world_scene_key(location, time_value, characters, objects)

            if world_key not in world_scene_index:
                world_scene_index[world_key] = {
                    "world_scene_id": world_key,
                    "source_scene_ids": [str(scene_info.scene_id)],
                    "location": scene_info.location,
                    "time": scene_info.time,
                    "emotion": scene_info.emotion,
                    "chain_id": scene_info.chain_id,
                    "characters_in_scene": characters,
                    "objects_in_scene": objects,
                    "scene_visual_overrides": dict(scene_info.scene_visual_overrides or {}),
                    "template": self._infer_template(scene_info.location, objects),
                    "style_id": "default",
                }
            else:
                entry = world_scene_index[world_key]
                entry["source_scene_ids"].append(str(scene_info.scene_id))
                entry["characters_in_scene"] = sorted(set(entry["characters_in_scene"]) | set(characters))
                entry["objects_in_scene"] = sorted(set(entry["objects_in_scene"]) | set(objects))
                entry["scene_visual_overrides"].update(scene_info.scene_visual_overrides or {})
                if not entry.get("emotion") and scene_info.emotion:
                    entry["emotion"] = scene_info.emotion
                if not entry.get("chain_id") and scene_info.chain_id:
                    entry["chain_id"] = scene_info.chain_id

            scene_to_world_scene[str(scene_info.scene_id)] = world_key

        return list(world_scene_index.values()), scene_to_world_scene

    def _build_world_scene_key(
        self,
        location: str,
        time_value: str,
        characters: List[str],
        objects: List[str],
    ) -> str:
        normalized_location = re.sub(r"[^a-z0-9]+", "_", location).strip("_") or "scene"
        normalized_time = re.sub(r"[^a-z0-9]+", "_", time_value).strip("_") or "time"
        char_token = str(len(characters))
        obj_token = str(len(objects))
        return f"{normalized_location}_{normalized_time}_{char_token}c_{obj_token}o"

    def _infer_template(self, location: Optional[str], objects: List[str]) -> str:
        location_text = (location or "").lower()
        object_text = " ".join(objects).lower()
        combined = f"{location_text} {object_text}"
        if any(token in combined for token in ["bridge", "river", "lake", "stream"]):
            return "bridge_river"
        if any(token in combined for token in ["street", "road", "city", "avenue"]):
            return "street"
        return "indoor_room"

    def _normalize_character_object_type(self, char_type: str) -> str:
        normalized = (char_type or "").lower()
        if normalized in {"human", "person"}:
            return "adult"
        if normalized in {"animal", "object"}:
            return normalized
        return normalized or "adult"

    def _extract_key_features(self, char: Character) -> List[str]:
        source = char.visual_core or ""
        features = [part.strip() for part in source.split(",") if part.strip()]
        return features[:8]

    def _build_image_prompt(self, scene: Scene, shot: Shot, style_tokens: str) -> str:
        """Resolve structured references before sending the prompt to an image model."""
        info = scene.scene_info
        items = self.items or {}
        objects = items.get("objects", {})
        details = shot.additional_detail or []
        if isinstance(details, str):
            details = [details]

        # Match complete references, longest first (bow must not match crossbow).
        def pattern(refs):
            return re.compile(r"(?<![\w])(?:" + "|".join(
                re.escape(ref) for ref in sorted(refs, key=len, reverse=True)
            ) + r")(?![\w])") if refs else None

        character_refs = list(dict.fromkeys(shot.focus_characters))
        object_refs = list(dict.fromkeys(shot.focus_objects))
        # Also resolve references mentioned in actions or scene overrides, even
        # when the model omitted them from the focus lists.
        referenced_text = " ".join(details + [getattr(info, "environment_description", "")] + [info.scene_visual_overrides.get(cid, "")
                                               for cid in character_refs])
        for refs, allowed in ((character_refs, info.characters_in_scene),
                              (object_refs, info.objects_in_scene)):
            for ref in allowed:
                if ref not in refs and pattern([ref]).search(referenced_text):
                    refs.append(ref)

        descriptions = {}
        for cid in character_refs:
            char = self.character_dict.get(cid)
            if char is None:
                raise ValueError(f"Shot {shot.shot_id} references unknown character: {cid}")
            descriptions[cid] = char.visual_core.strip()
        for name in object_refs:
            if name not in objects:
                raise ValueError(f"Shot {shot.shot_id} references unknown object: {name}")
            description = objects[name]
            descriptions[name] = f"{name} ({description})" if description else name

        ref_pattern = pattern(descriptions)
        def resolve(text):
            # One substitution pass: descriptions themselves are never rewritten.
            return ref_pattern.sub(lambda match: descriptions[match.group()], text) if ref_pattern else text

        subjects = []
        for cid in character_refs:
            description = descriptions[cid]
            override = info.scene_visual_overrides.get(cid, "")
            if override:
                description += ", " + resolve(override)
            subjects.append(description)
        subjects.extend(descriptions[name] for name in object_refs)

        location = info.location
        for entry in items.get("locations", []):
            if entry.get("name") == location and entry.get("description"):
                location += ": " + entry["description"]
                break
        environment = [f"in {location}" if location else "", info.time,
                       resolve(getattr(info, "environment_description", "")),
                       f"mood: {info.emotion}" if info.emotion else ""]
        camera = [f"{shot.shot_type} shot" if shot.shot_type else "",
                  f"camera {shot.camera_move.replace('_', ' ')}" if shot.camera_move and shot.camera_move != "static" else "",
                  shot.lighting]
        return ", ".join(part.strip() for part in
                         subjects + environment + camera + [resolve(detail) for detail in details] + [style_tokens]
                         if part and part.strip())

    def _estimate_duration(self, text: str) -> float:
        return estimate_narration_duration(text)




    def call_llm_with_retry(self, messages, max_retries: int = 3):
        """带重试的 LLM 调用"""
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                return self._call_llm(messages)
            except RemoteProtocolError as e:
                last_exc = e
                print(f"[LLM] attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    raise
                time.sleep(2 * attempt)


def run_story_pipeline(story: str, model_name: str, api_key: str, style_tokens: str = STYLE_REALISTIC, checkpoint_dir=None, cancel_event=None, initial_items=None, identity_prefix=""):
    """Return structured story shots, characters and scenes."""
    pipeline = StoryPipeline(checkpoint_dir=checkpoint_dir)
    pipeline.initial_items = initial_items
    pipeline.identity_prefix = identity_prefix
    pipeline.cancel_event = cancel_event
    pipeline.use_model(model_name, api_key)
    try:
        return pipeline.generate(story, style_tokens)
    finally:
        pipeline.release_model()
