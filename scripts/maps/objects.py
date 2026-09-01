from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MAP_OBJECT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config/map-objects.json"


def load_map_object_config(path: Path = MAP_OBJECT_CONFIG_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = data.get("groups")
    if data.get("schemaVersion") != 1 or not isinstance(groups, list):
        raise RuntimeError(f"Invalid map object config: {path}")

    registry: dict[str, dict[str, str]] = {}
    public_groups: list[dict[str, str]] = []
    for raw_group in groups:
        if not isinstance(raw_group, dict) or not isinstance(raw_group.get("id"), str):
            raise RuntimeError(f"Invalid map object group: {raw_group!r}")
        group_id = raw_group["id"]
        group_name = raw_group.get("name")
        objects = raw_group.get("objects")
        if not isinstance(group_name, str) or not isinstance(objects, list):
            raise RuntimeError(f"Invalid map object group: {group_id}")
        public_groups.append({
            "id": group_id,
            "name": group_name,
            "detail": str(raw_group.get("detail") or ""),
        })
        for raw_object in objects:
            if not isinstance(raw_object, dict):
                raise RuntimeError(f"Invalid map object in group: {group_id}")
            prototype_id = raw_object.get("id")
            name = raw_object.get("name")
            if not isinstance(prototype_id, str) or not isinstance(name, str):
                raise RuntimeError(f"Invalid map object in group: {group_id}")
            if prototype_id in registry:
                raise RuntimeError(f"Duplicate map object prototype: {prototype_id}")
            registry[prototype_id] = {"name": name, "group": group_id}
    return {"groups": public_groups, "prototypes": registry}
