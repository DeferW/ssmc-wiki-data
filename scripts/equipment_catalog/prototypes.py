from __future__ import annotations

from pathlib import Path
from typing import Any

from prototype_resolution import (
    EntityPrototype as EntityPrototype,
    GameYamlLoader as GameYamlLoader,
    PrototypeResolver as PrototypeResolver,
    construct_tagged_value as construct_tagged_value,
    iter_prototype_documents as iter_prototype_documents,
    normalize_parents as normalize_parents,
    origin_from_path as origin_from_path,
    read_entity_prototypes as read_entity_prototypes,
)


def parse_box2i(value: Any) -> tuple[int, int, int, int] | None:
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return None
    if len(parts) != 4:
        return None
    try:
        return tuple(int(part) for part in parts)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def read_item_size_definitions(game_source: Path) -> dict[str, dict[str, Any]]:
    """Read the same item-size prototypes used by SharedItemSystem."""
    result: dict[str, dict[str, Any]] = {}
    prototype_root = game_source / "Resources/Prototypes"
    for path in sorted(prototype_root.rglob("item_size.yml")):
        for raw in iter_prototype_documents(path):
            if raw.get("type") != "itemSize" or not isinstance(raw.get("id"), str):
                continue
            boxes = [
                box
                for value in raw.get("defaultShape", [])
                if (box := parse_box2i(value)) is not None
            ]
            if not boxes:
                continue
            result[raw["id"]] = {
                "weight": raw.get("weight", 1),
                "boxes": boxes,
            }
    if not result:
        raise RuntimeError("No item-size prototypes were found")
    return result


def read_reagent_colors(game_source: Path) -> dict[str, str]:
    """Read reagent colors used by runtime-filled bottle/injector visuals."""
    root = game_source / "Resources/Prototypes"
    result: dict[str, str] = {}
    for path in sorted([*root.rglob("*.yml"), *root.rglob("*.yaml")]):
        for raw in iter_prototype_documents(path):
            if raw.get("type") != "reagent":
                continue
            reagent_id = raw.get("id")
            color = raw.get("color")
            if isinstance(reagent_id, str) and isinstance(color, str):
                result[reagent_id] = color
    return result

