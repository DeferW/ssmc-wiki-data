from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Iterable

import yaml

from .core import EntityPrototype


class GameYamlLoader(yaml.SafeLoader):
    """YAML loader that preserves SS14 custom tags as plain JSON values."""


def construct_tagged_value(
    loader: GameYamlLoader,
    tag_suffix: str,
    node: yaml.Node,
) -> Any:
    if isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_scalar(node)
    return {"yamlTag": f"!{tag_suffix}", "value": value}


GameYamlLoader.add_multi_constructor("!", construct_tagged_value)


def normalize_parents(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def origin_from_path(path: str) -> str:
    if "/_Stories/" in path:
        return "stories"
    if "/_RMC14/" in path:
        return "rmc14"
    return "upstream"


def iter_prototype_documents(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as stream:
        for document in yaml.load_all(stream, Loader=GameYamlLoader):
            if document is None:
                continue
            values = document if isinstance(document, list) else [document]
            for value in values:
                if isinstance(value, dict):
                    yield value


def read_entity_prototypes(game_source: Path) -> dict[str, EntityPrototype]:
    root = game_source / "Resources/Prototypes"
    if not root.is_dir():
        raise FileNotFoundError(f"Missing prototype directory: {root}")

    result: dict[str, EntityPrototype] = {}
    files = sorted([*root.rglob("*.yml"), *root.rglob("*.yaml")])

    for path in files:
        source_file = path.relative_to(game_source).as_posix()
        for raw in iter_prototype_documents(path):
            if raw.get("type") != "entity":
                continue
            prototype_id = raw.get("id")
            if not isinstance(prototype_id, str) or not prototype_id:
                continue
            if prototype_id in result:
                previous = result[prototype_id].source_file
                raise RuntimeError(
                    f"Duplicate entity prototype {prototype_id}: "
                    f"{previous}, {source_file}"
                )

            raw_components = raw.get("components", [])
            components: list[dict[str, Any]] = []
            if isinstance(raw_components, list):
                components = [
                    copy.deepcopy(component)
                    for component in raw_components
                    if isinstance(component, dict)
                    and isinstance(component.get("type"), str)
                ]

            fields = {
                key: copy.deepcopy(value)
                for key, value in raw.items()
                if key not in {"type", "id", "parent", "abstract", "components"}
            }
            result[prototype_id] = EntityPrototype(
                id=prototype_id,
                parents=normalize_parents(raw.get("parent")),
                abstract=bool(raw.get("abstract", False)),
                source_file=source_file,
                origin=origin_from_path(source_file),
                fields=fields,
                components=tuple(components),
            )

    if not result:
        raise RuntimeError("No entity prototypes found")
    return result


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


class PrototypeResolver:
    """Resolve entity inheritance with component-level SS14 semantics."""

    def __init__(self, prototypes: dict[str, EntityPrototype]):
        self.prototypes = prototypes
        self.cache: dict[str, dict[str, Any]] = {}
        self.active: list[str] = []

    def resolve(self, prototype_id: str) -> dict[str, Any]:
        cached = self.cache.get(prototype_id)
        if cached is not None:
            return cached

        prototype = self.prototypes.get(prototype_id)
        if prototype is None:
            raise RuntimeError(f"Unknown entity prototype: {prototype_id}")
        if prototype_id in self.active:
            start = self.active.index(prototype_id)
            cycle = self.active[start:] + [prototype_id]
            raise RuntimeError("Entity inheritance cycle: " + " -> ".join(cycle))

        self.active.append(prototype_id)
        fields: dict[str, Any] = {}
        components: dict[str, dict[str, Any]] = {}

        for parent_id in prototype.parents:
            if parent_id not in self.prototypes:
                raise RuntimeError(
                    f"Unknown parent {parent_id} used by {prototype_id}"
                )
            parent = self.resolve(parent_id)
            fields.update(copy.deepcopy(parent["fields"]))
            for component_type, component in parent["components"].items():
                merged_parent = copy.deepcopy(components.get(component_type, {}))
                merged_parent.update(copy.deepcopy(component))
                components[component_type] = merged_parent

        # Prototype fields and individual component fields replace the matching
        # inherited field as a whole. Nested maps are intentionally not merged:
        # Empty weapon variants rely on replacing ItemSlots.slots so an inherited
        # startingItem does not survive.
        fields.update(copy.deepcopy(prototype.fields))
        for raw_component in prototype.components:
            component_type = raw_component["type"]
            merged = copy.deepcopy(components.get(component_type, {}))
            merged.update(
                {
                    key: copy.deepcopy(value)
                    for key, value in raw_component.items()
                    if key != "type"
                }
            )
            components[component_type] = merged

        self.active.pop()
        resolved = {
            "id": prototype_id,
            "parents": list(prototype.parents),
            "abstract": prototype.abstract,
            "sourceFile": prototype.source_file,
            "origin": prototype.origin,
            "fields": fields,
            "components": components,
        }
        self.cache[prototype_id] = resolved
        return resolved
