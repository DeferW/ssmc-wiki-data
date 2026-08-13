from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from scripts.catalog.models import Prototype
from scripts.common.yaml import iter_documents, normalize_parents


def origin_from_path(path: str) -> str:
    if "/_Stories/" in path:
        return "stories"
    if "/_RMC14/" in path:
        return "rmc14"
    return "upstream"


def read_prototypes(game_source: Path) -> dict[str, Prototype]:
    root = game_source / "Resources/Prototypes"
    if not root.is_dir():
        raise FileNotFoundError(f"Missing prototype directory: {root}")

    prototypes: dict[str, Prototype] = {}
    for path in sorted((*root.rglob("*.yml"), *root.rglob("*.yaml"))):
        source_file = path.relative_to(game_source).as_posix()
        for raw in iter_documents(path):
            if raw.get("type") != "entity":
                continue
            prototype_id = raw.get("id")
            if not isinstance(prototype_id, str) or not prototype_id:
                continue
            if prototype_id in prototypes:
                raise RuntimeError(
                    f"Duplicate entity prototype {prototype_id}: "
                    f"{prototypes[prototype_id].source_file}, {source_file}"
                )
            raw_components = raw.get("components", [])
            components = tuple(
                copy.deepcopy(component)
                for component in raw_components
                if isinstance(raw_components, list)
                and isinstance(component, dict)
                and isinstance(component.get("type"), str)
            )
            fields = {
                key: copy.deepcopy(value)
                for key, value in raw.items()
                if key not in {"type", "id", "parent", "abstract", "components"}
            }
            prototypes[prototype_id] = Prototype(
                id=prototype_id,
                parents=normalize_parents(raw.get("parent")),
                abstract=bool(raw.get("abstract", False)),
                source_file=source_file,
                origin=origin_from_path(source_file),
                fields=fields,
                components=components,
            )
    if not prototypes:
        raise RuntimeError("No entity prototypes found")
    return prototypes


class PrototypeResolver:
    """Resolve inheritance once and expose stable normalized dictionaries."""

    def __init__(self, prototypes: dict[str, Prototype]):
        self.prototypes = prototypes
        self.cache: dict[str, dict[str, Any]] = {}
        self._active: list[str] = []

    def resolve(self, prototype_id: str) -> dict[str, Any]:
        if prototype_id in self.cache:
            return self.cache[prototype_id]
        prototype = self.prototypes.get(prototype_id)
        if prototype is None:
            raise RuntimeError(f"Unknown entity prototype: {prototype_id}")
        if prototype_id in self._active:
            start = self._active.index(prototype_id)
            cycle = self._active[start:] + [prototype_id]
            raise RuntimeError("Entity inheritance cycle: " + " -> ".join(cycle))

        self._active.append(prototype_id)
        fields: dict[str, Any] = {}
        components: dict[str, dict[str, Any]] = {}
        for parent_id in prototype.parents:
            parent = self.resolve(parent_id)
            fields.update(copy.deepcopy(parent["fields"]))
            for component_type, component in parent["components"].items():
                merged = copy.deepcopy(components.get(component_type, {}))
                merged.update(copy.deepcopy(component))
                components[component_type] = merged
        fields.update(copy.deepcopy(prototype.fields))
        for component in prototype.components:
            component_type = str(component["type"])
            merged = copy.deepcopy(components.get(component_type, {}))
            merged.update(
                {
                    key: copy.deepcopy(value)
                    for key, value in component.items()
                    if key != "type"
                }
            )
            components[component_type] = merged
        self._active.pop()

        value = {
            "id": prototype_id,
            "parents": list(prototype.parents),
            "abstract": prototype.abstract,
            "origin": prototype.origin,
            "sourceFile": prototype.source_file,
            "fields": fields,
            "components": components,
        }
        self.cache[prototype_id] = value
        return value


def parse_box(value: Any) -> tuple[int, int, int, int] | None:
    parts = [part.strip() for part in value.split(",")] if isinstance(value, str) else value
    if not isinstance(parts, (list, tuple)) or len(parts) != 4:
        return None
    try:
        return tuple(int(part) for part in parts)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def read_item_sizes(game_source: Path) -> dict[str, dict[str, Any]]:
    root = game_source / "Resources/Prototypes"
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("item_size.yml")):
        for raw in iter_documents(path):
            if raw.get("type") != "itemSize" or not isinstance(raw.get("id"), str):
                continue
            boxes = [
                box
                for value in raw.get("defaultShape", [])
                if (box := parse_box(value)) is not None
            ]
            if boxes:
                result[raw["id"]] = {"weight": raw.get("weight", 1), "boxes": boxes}
    if not result:
        raise RuntimeError("No item-size prototypes found")
    return result


def read_reagent_colors(game_source: Path) -> dict[str, str]:
    root = game_source / "Resources/Prototypes"
    colors: dict[str, str] = {}
    for path in sorted((*root.rglob("*.yml"), *root.rglob("*.yaml"))):
        for raw in iter_documents(path):
            if raw.get("type") == "reagent" and isinstance(raw.get("id"), str):
                if isinstance(raw.get("color"), str):
                    colors[raw["id"]] = raw["color"]
    return colors

