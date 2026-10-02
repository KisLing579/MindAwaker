"""Paragraph-preserving chunking and deterministic story element accumulation."""
import copy
import re
import json


def source_units(text):
    """Index complete sentences/lines, retaining every original character."""
    units, start = [], 0
    for match in re.finditer(r'[。！？!?]+[”’"\u300d\u300f]*[ \t]*(?:\r\n|\r|\n)*|(?:\r\n|\r|\n)+|\.(?=\s|$)\s*', text):
        end = match.end()
        if text[start:end].strip():
            units.append(text[start:end])
            start = end
    if start < len(text):
        if text[start:].strip() or not units:
            units.append(text[start:])
        else:
            units[-1] += text[start:]
    return units


def numbered_source(units):
    return json.dumps([{"id": i, "text": text} for i, text in enumerate(units, 1)], ensure_ascii=False)


def restore_source_ranges(data, units, field):
    """Require a contiguous partition; model-written narration is never used."""
    if not isinstance(data, list) or not data:
        raise ValueError("场景/分镜输出必须为非空数组")
    cursor = 1
    restored = []
    for index, entry in enumerate(data, 1):
        if not isinstance(entry, dict):
            raise ValueError(f"第 {index} 项必须是 JSON 对象")
        start, end = entry.get("source_start"), entry.get("source_end")
        if type(start) is not int or type(end) is not int:
            raise ValueError(f"第 {index} 项缺少整数 source_start/source_end")
        if start != cursor or not start <= end <= len(units):
            raise ValueError(f"第 {index} 项原文范围无效：应从 {cursor} 开始，实际 {start}–{end}，总片段数 {len(units)}")
        record = dict(entry)
        record[field] = "".join(units[start - 1:end])
        restored.append(record)
        cursor = end + 1
    if cursor != len(units) + 1:
        raise ValueError(f"原文范围遗漏：尚未覆盖 {cursor}–{len(units)}")
    return restored


def split_story(text, target=500, max_paragraph=6000):
    if not text.strip():
        raise ValueError("故事正文不能为空")
    paragraphs = re.findall(r"[^\r\n]+(?:\r\n|\r|\n)*|[\r\n]+", text)
    chunks, current = [], ""
    for paragraph in paragraphs:
        if len(paragraph.strip()) > max_paragraph:
            raise ValueError(f"单个完整段落超过 {max_paragraph} 字，请先为该段添加段落换行")
        if current and len(current) + len(paragraph) > target:
            chunks.append(current)
            current = ""
        current += paragraph
    if current:
        chunks.append(current)
    return chunks


def empty_items():
    return dict(characters=[], objects={}, locations=[], time=[], emotion=[])


def merge_items(previous, delta, chunk_index):
    """Only explicit stable identifiers match; similar appearances never imply identity."""
    result = copy.deepcopy(previous)
    if not isinstance(delta, dict):
        raise ValueError("元素输出必须为 JSON 对象")
    for key, identity in (("characters", "character_id"), ("locations", "name")):
        records = delta.get(key, [])
        if not isinstance(records, list):
            raise ValueError(f"{key} 必须为数组")
        index = {entry[identity]: entry for entry in result[key]}
        for record in records:
            if not isinstance(record, dict) or not record.get(identity):
                raise ValueError(f"{key} 缺少 {identity}")
            record = copy.deepcopy(record)
            entity_id = record[identity]
            old = index.get(entity_id)
            if old is None:
                old = record
                old["source_chunks"] = []
                result[key].append(old)
                index[entity_id] = old
            else:
                for field, value in record.items():
                    if field in ("source_chunks", identity):
                        continue
                    if field in ("aliases", "style_tags"):
                        old[field] = list(dict.fromkeys(old.get(field, []) + value))
                    elif field == "is_main":
                        old[field] = old.get(field, False) or value
                    elif value not in (None, "", []):
                        old[field] = value
            old.setdefault("source_chunks", [])
            if chunk_index not in old["source_chunks"]:
                old["source_chunks"].append(chunk_index)
    objects = delta.get("objects", {})
    if not isinstance(objects, dict) or any(not isinstance(v, str) for v in objects.values()):
        raise ValueError("objects 必须为名称到描述的字典")
    result["objects"].update(objects)
    for key in ("time", "emotion"):
        values = delta.get(key, [])
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ValueError(f"{key} 必须为字符串数组")
        result[key] = list(dict.fromkeys(result[key] + values))
    return result


def relevant_items(items, delta):
    character_ids = {c["character_id"] for c in delta.get("characters", [])}
    locations = {c["name"] for c in delta.get("locations", [])}
    return {
        "characters": [c for c in items["characters"] if c["character_id"] in character_ids],
        "objects": {k: items["objects"][k] for k in delta.get("objects", {})},
        "locations": [c for c in items["locations"] if c["name"] in locations],
        "time": delta.get("time", []), "emotion": delta.get("emotion", []),
    }


def compact_index(items):
    return {
        "characters": [{k: c[k] for k in ("character_id", "name", "aliases") if k in c}
                       for c in items["characters"]],
        "objects": list(items["objects"]),
        "locations": [{"name": c["name"]} for c in items["locations"]],
    }


def consolidate_characters(items, deltas, mapping):
    """Apply explicit identity revelations to all earlier block references."""
    result, blocks = copy.deepcopy(items), copy.deepcopy(deltas)
    index = {c["character_id"]: c for c in result["characters"]}
    if not isinstance(mapping, dict):
        raise ValueError("character_merges 必须为字典")
    resolved = {}
    for source in mapping:
        target, seen = source, set()
        while target in mapping:
            if target in seen:
                raise ValueError("角色合并关系存在循环")
            seen.add(target)
            target = mapping[target]
        if source not in index or target not in index:
            raise ValueError("合并引用未知角色")
        resolved[source] = target
    for source, target in resolved.items():
        old, kept = index[source], index[target]
        kept["aliases"] = list(dict.fromkeys(kept.get("aliases", []) + old.get("aliases", []) + [old["name"]]))
        kept["source_chunks"] = sorted(set(kept["source_chunks"] + old["source_chunks"]))
        kept["is_main"] = kept["is_main"] or old["is_main"]
    result["characters"] = [c for c in result["characters"] if c["character_id"] not in resolved]
    for delta in blocks:
        for character in delta.get("characters", []):
            character["character_id"] = resolved.get(character["character_id"], character["character_id"])
    return result, blocks
