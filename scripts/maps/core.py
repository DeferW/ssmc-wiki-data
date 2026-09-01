from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

import yaml
from PIL import Image

from scripts.common.prototypes import (
    EntityPrototype,
    GameYamlLoader,
    PrototypeResolver,
    iter_prototype_documents,
)
from scripts.maps.items import STATIC_ITEM_CATALOG_PATH, static_item_classification
from scripts.maps.objects import load_map_object_config

SCHEMA_VERSION = 1
OVERLAY_SCHEMA_VERSION = 6
TILES_SCHEMA_VERSION = 3
DEFAULT_TILE_SIZE = 512
DEFAULT_RENDER_SCALE = 1.0
DEFAULT_WEBP_QUALITY = 82
DEFAULT_MAX_ASSET_BYTES = 512 * 1024 * 1024
STORIES_SHIP_PROTOTYPE_ID = "STAlmayer"
AREA_SUPPORT_FIELDS = (
    "CAS",
    "fulton",
    "lasing",
    "mortarPlacement",
    "mortarFire",
    "medevac",
    "paradropping",
    "OB",
    "supplyDrop",
)


def resource_path(game_source: Path, path: str) -> Path:
    return game_source / "Resources" / path.lstrip("/")


def map_origin(path: str) -> str:
    if "/_Stories/" in path:
        return "stories"
    if "/_RMC14/" in path:
        return "rmc14"
    return "upstream"


def map_slug(path: str) -> str:
    stem = Path(path).stem.casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    if not slug:
        raise RuntimeError(f"Cannot derive a public id from map path: {path}")
    return slug


def insert_render_key(path: str) -> str:
    """Return a stable collision-proof renderer name for an insert map."""
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:10]
    return f"{map_slug(path)}-{digest}"


def _prototype_documents(root: Path) -> Iterable[dict[str, Any]]:
    files = sorted([*root.rglob("*.yml"), *root.rglob("*.yaml")])
    for path in files:
        yield from iter_prototype_documents(path)


def _stories_ship_maps(game_source: Path) -> list[dict[str, Any]]:
    root = game_source / "Resources/Prototypes/_Stories"
    if not root.is_dir():
        raise FileNotFoundError(f"Missing SSMC prototype directory: {root}")

    game_maps: dict[str, dict[str, Any]] = {}
    for raw in _prototype_documents(root):
        if raw.get("type") == "gameMap" and isinstance(raw.get("id"), str):
            game_maps[raw["id"]] = raw

    prototype_id = STORIES_SHIP_PROTOTYPE_ID
    raw = game_maps.get(prototype_id)
    if raw is None:
        raise RuntimeError(f"Missing required SSMC ship gameMap: {prototype_id}")
    path = raw.get("mapPath")
    if not isinstance(path, str) or not path.startswith("/Maps/_Stories/"):
        raise RuntimeError(
            f"SSMC gameMap {prototype_id} must point to /Maps/_Stories/: {path!r}"
        )
    return [
        {
            "id": map_slug(path),
            "name": str(raw.get("mapName") or prototype_id),
            "kind": "ship",
            "mapPath": path,
            "origin": map_origin(path),
            "sourcePrototypeIds": [prototype_id],
        }
    ]


def discover_active_maps(
    game_source: Path,
    prototypes: dict[str, EntityPrototype],
    resolver: PrototypeResolver,
) -> list[dict[str, Any]]:
    """Discover the Almayer and live planets enabled for map rotation.

    Planet names and paths are deliberately not hard-coded. The resolved
    RMCPlanetMapPrototype component is the source of truth, including inherited
    ``inRotation`` values; the game's component default is true when omitted.
    """

    maps = _stories_ship_maps(game_source)
    paths = {entry["mapPath"] for entry in maps}

    for prototype_id in sorted(prototypes):
        prototype = prototypes[prototype_id]
        if prototype.abstract:
            continue
        resolved = resolver.resolve(prototype_id)
        planet = resolved["components"].get("RMCPlanetMapPrototype")
        if not isinstance(planet, dict):
            continue
        in_rotation = planet.get("inRotation", True)
        if not isinstance(in_rotation, bool):
            raise RuntimeError(
                f"Planet {prototype_id} has invalid inRotation value: {in_rotation!r}"
            )
        if not in_rotation:
            continue
        path = planet.get("map")
        if not isinstance(path, str) or not path.startswith("/Maps/"):
            raise RuntimeError(f"Planet {prototype_id} has invalid map path: {path!r}")
        if path in paths:
            raise RuntimeError(f"Map is selected both as a ship and planet: {path}")
        paths.add(path)

        entry: dict[str, Any] = {
            "id": map_slug(path),
            "name": str(resolved["fields"].get("name") or prototype_id),
            "kind": "planet",
            "mapPath": path,
            "origin": map_origin(path),
            "sourcePrototypeIds": [prototype_id],
        }
        for source_key, output_key in (
            ("camouflage", "camouflage"),
            ("minPlayers", "minPlayers"),
            ("maxPlayers", "maxPlayers"),
            ("nightmareScenarios", "nightmareScenarios"),
            ("replacements", "replacements"),
        ):
            if source_key in planet:
                entry[output_key] = planet[source_key]
        maps.append(entry)

    seen_ids: dict[str, str] = {}
    for entry in maps:
        path = entry["mapPath"]
        local_path = resource_path(game_source, path)
        if not local_path.is_file():
            raise FileNotFoundError(f"Active map does not exist: {path} ({local_path})")
        previous = seen_ids.setdefault(entry["id"], path)
        if previous != path:
            raise RuntimeError(f"Map id collision {entry['id']}: {previous}, {path}")

    return sorted(maps, key=lambda entry: (entry["kind"] != "ship", entry["name"].casefold()))


def parse_vector(value: Any) -> list[float] | None:
    if isinstance(value, str):
        parts = value.split(",")
        if len(parts) == 2:
            try:
                return [float(parts[0]), float(parts[1])]
            except ValueError:
                return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        if all(isinstance(part, (int, float)) for part in value):
            return [float(value[0]), float(value[1])]
    if isinstance(value, dict):
        x = value.get("x", value.get("X"))
        y = value.get("y", value.get("Y"))
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            return [float(x), float(y)]
    return None


def parse_rotation(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.match(r"^\s*(-?[0-9]+(?:\.[0-9]+)?)", value)
        if match:
            return float(match.group(1))
    return 0.0


def _load_map(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        loaded = yaml.load(stream, Loader=GameYamlLoader)
    if not isinstance(loaded, dict) or not isinstance(loaded.get("entities"), list):
        raise RuntimeError(f"Invalid SS14 map document: {path}")
    return loaded


def semantic_component_types(components: dict[str, Any]) -> list[str]:
    return sorted(
        component_type
        for component_type in components
        if component_type in {"MapInsert", "SpawnPoint"} or "Spawner" in component_type
    )


def _is_marker(resolved: dict[str, Any], semantic_types: list[str]) -> bool:
    source = str(resolved.get("sourceFile", "")).replace("\\", "/")
    return bool(semantic_types) or "/Entities/Markers/" in source


def _prototype_entry(resolved: dict[str, Any], semantic_types: list[str]) -> dict[str, Any]:
    components = resolved["components"]
    if "MapInsert" in semantic_types:
        kind = "insert"
    elif semantic_types:
        kind = "spawner"
    else:
        kind = "marker"
    entry: dict[str, Any] = {
        "name": str(resolved["fields"].get("name") or resolved["id"]),
        "kind": kind,
    }
    if semantic_types:
        entry["components"] = {
            component_type: components[component_type]
            for component_type in semantic_types
        }
    return entry


def _occurrence(raw: dict[str, Any]) -> list[Any] | None:
    components = raw.get("components", [])
    if not isinstance(components, list):
        return None
    transform: dict[str, Any] | None = None
    label: str | None = None
    for component in components:
        if not isinstance(component, dict):
            continue
        if component.get("type") == "Transform":
            transform = component
        elif component.get("type") == "MetaData" and isinstance(component.get("name"), str):
            label = component["name"]
    if transform is None:
        return None
    position = parse_vector(transform.get("pos"))
    if position is None:
        return None
    rotation = parse_rotation(transform.get("rot"))
    parent = transform.get("parent")
    result: list[Any] = [position[0], position[1]]
    if rotation or parent is not None or label is not None:
        result.append(rotation)
    if parent is not None or label is not None:
        result.append(parent)
    if label is not None:
        result.append(label)
    return result


def _static_item_occurrences(
    document: dict[str, Any],
    prototypes: dict[str, EntityPrototype],
    resolver: PrototypeResolver,
    *,
    relative_to_grid: bool = False,
) -> dict[str, list[list[Any]]]:
    """Return unanchored Items placed directly on a map grid."""
    transforms: dict[Any, tuple[list[float], float, Any]] = {}
    anchored_entities: set[Any] = set()
    grid_entities: set[Any] = set()
    entities_by_prototype: list[tuple[str, list[dict[str, Any]]]] = []
    for group in document["entities"]:
        if not isinstance(group, dict):
            continue
        prototype_id = group.get("proto")
        entities = group.get("entities", [])
        if not isinstance(prototype_id, str) or not isinstance(entities, list):
            continue
        valid_entities = [entity for entity in entities if isinstance(entity, dict)]
        entities_by_prototype.append((prototype_id, valid_entities))
        resolved_components = (
            resolver.resolve(prototype_id)["components"]
            if prototype_id in prototypes
            else {}
        )
        prototype_transform = resolved_components.get("Transform", {})
        prototype_is_grid = "MapGrid" in resolved_components
        for entity in valid_entities:
            uid = entity.get("uid")
            if uid is None:
                continue
            components = [
                component
                for component in entity.get("components", [])
                if isinstance(component, dict)
            ]
            if prototype_is_grid or any(component.get("type") == "MapGrid" for component in components):
                grid_entities.add(uid)
            transform = next(
                (component for component in components if component.get("type") == "Transform"),
                None,
            )
            if transform is None:
                continue
            transforms[uid] = (
                parse_vector(transform.get("pos")) or [0.0, 0.0],
                parse_rotation(transform.get("rot")),
                transform.get("parent"),
            )
            anchored = transform.get("anchored", prototype_transform.get("anchored", False))
            if anchored is True:
                anchored_entities.add(uid)

    resolved_transforms: dict[Any, tuple[float, float, float]] = {}

    def world_transform(uid: Any, active: set[Any] | None = None) -> tuple[float, float, float]:
        if uid in resolved_transforms:
            return resolved_transforms[uid]
        local = transforms.get(uid)
        if local is None:
            return 0.0, 0.0, 0.0
        active = set() if active is None else active
        if uid in active:
            return local[0][0], local[0][1], local[1]
        active.add(uid)
        position, rotation, parent = local
        if parent is None or parent not in transforms:
            result = position[0], position[1], rotation
        else:
            parent_x, parent_y, parent_rotation = world_transform(parent, active)
            cosine = math.cos(parent_rotation)
            sine = math.sin(parent_rotation)
            result = (
                parent_x + position[0] * cosine - position[1] * sine,
                parent_y + position[0] * sine + position[1] * cosine,
                parent_rotation + rotation,
            )
        active.remove(uid)
        resolved_transforms[uid] = result
        return result

    result: dict[str, list[list[Any]]] = {}
    for prototype_id, entities in entities_by_prototype:
        if prototype_id not in prototypes:
            continue
        resolved = resolver.resolve(prototype_id)
        if static_item_classification(prototype_id, resolved) is None:
            continue
        points: list[list[Any]] = []
        for entity in entities:
            uid = entity.get("uid")
            if uid not in transforms:
                continue
            if uid in anchored_entities:
                continue
            parent = transforms[uid][2]
            if parent in transforms and parent not in grid_entities:
                continue
            x, y, rotation = world_transform(uid)
            if relative_to_grid and parent in grid_entities:
                grid_x, grid_y, grid_rotation = world_transform(parent)
                delta_x = x - grid_x
                delta_y = y - grid_y
                cosine = math.cos(grid_rotation)
                sine = math.sin(grid_rotation)
                x = delta_x * cosine + delta_y * sine
                y = -delta_x * sine + delta_y * cosine
                rotation -= grid_rotation
            point: list[Any] = [x, y]
            if rotation:
                point.append(rotation)
            points.append(point)
        if points:
            result[prototype_id] = points
    return result


def _configured_object_occurrences(
    document: dict[str, Any], configured_ids: set[str]
) -> dict[str, list[list[Any]]]:
    """Return positions only for non-item prototypes selected in map-objects.json."""
    result: dict[str, list[list[Any]]] = {}
    for group in document["entities"]:
        if not isinstance(group, dict):
            continue
        prototype_id = group.get("proto")
        if prototype_id not in configured_ids:
            continue
        entities = group.get("entities", [])
        if not isinstance(entities, list):
            continue
        points = [point for raw in entities if isinstance(raw, dict) if (point := _occurrence(raw))]
        if points:
            result[prototype_id] = points
    return result


def _extract_occurrences(
    document: dict[str, Any],
    prototypes: dict[str, EntityPrototype],
    resolver: PrototypeResolver,
    registry: dict[str, Any],
) -> tuple[dict[str, list[list[Any]]], set[str]]:
    result: dict[str, list[list[Any]]] = {}
    insert_paths: set[str] = set()
    for group in document["entities"]:
        if not isinstance(group, dict):
            continue
        prototype_id = group.get("proto")
        if not isinstance(prototype_id, str) or prototype_id not in prototypes:
            continue
        resolved = resolver.resolve(prototype_id)
        semantic_types = semantic_component_types(resolved["components"])
        if not _is_marker(resolved, semantic_types):
            continue
        registry.setdefault(prototype_id, _prototype_entry(resolved, semantic_types))
        entities = group.get("entities", [])
        if not isinstance(entities, list):
            continue
        points = [point for raw in entities if isinstance(raw, dict) if (point := _occurrence(raw))]
        if points:
            result[prototype_id] = points

        insert = resolved["components"].get("MapInsert")
        if isinstance(insert, dict):
            variations = insert.get("variations", [])
            if isinstance(variations, list):
                for variation in variations:
                    if isinstance(variation, dict) and isinstance(variation.get("spawn"), str):
                        insert_paths.add(variation["spawn"])
    return result, insert_paths


def _area_position(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    parts = value.split(",")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _area_grid(
    document: dict[str, Any],
    prototypes: dict[str, EntityPrototype],
    resolver: PrototypeResolver,
) -> dict[str, Any] | None:
    cells: dict[tuple[int, int], str] = {}
    for group in document["entities"]:
        if not isinstance(group, dict):
            continue
        entities = group.get("entities", [])
        if not isinstance(entities, list):
            continue
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            components = entity.get("components", [])
            if not isinstance(components, list):
                continue
            for component in components:
                if not isinstance(component, dict) or component.get("type") != "AreaGrid":
                    continue
                areas = component.get("areas", {})
                if not isinstance(areas, dict):
                    continue
                for raw_position, prototype_id in areas.items():
                    position = _area_position(raw_position)
                    if position is None or not isinstance(prototype_id, str):
                        raise RuntimeError(
                            f"Invalid AreaGrid entry: {raw_position!r}: {prototype_id!r}"
                        )
                    if prototype_id not in prototypes:
                        raise RuntimeError(f"AreaGrid references unknown area: {prototype_id}")
                    cells[position] = prototype_id

    if not cells:
        return None

    type_ids = sorted(set(cells.values()))
    type_index = {prototype_id: index for index, prototype_id in enumerate(type_ids)}
    types: list[list[Any]] = []
    for prototype_id in type_ids:
        resolved = resolver.resolve(prototype_id)
        area = resolved["components"].get("Area")
        if not isinstance(area, dict):
            raise RuntimeError(f"AreaGrid prototype has no Area component: {prototype_id}")
        support_mask = 0
        for bit, field in enumerate(AREA_SUPPORT_FIELDS):
            value = area.get(field, False)
            if not isinstance(value, bool):
                raise RuntimeError(
                    f"Area {prototype_id} has invalid {field} value: {value!r}"
                )
            if value:
                support_mask |= 1 << bit
        types.append(
            [prototype_id, str(resolved["fields"].get("name") or prototype_id), support_mask]
        )

    by_row: dict[int, list[tuple[int, int]]] = {}
    for (x, y), prototype_id in cells.items():
        by_row.setdefault(y, []).append((x, type_index[prototype_id]))

    rows: list[list[int]] = []
    for y in sorted(by_row):
        positions = sorted(by_row[y])
        row = [y]
        start_x, current_type = positions[0]
        previous_x = start_x
        for x, area_type in positions[1:]:
            if x == previous_x + 1 and area_type == current_type:
                previous_x = x
                continue
            row.extend((start_x, previous_x - start_x + 1, current_type))
            start_x = previous_x = x
            current_type = area_type
        row.extend((start_x, previous_x - start_x + 1, current_type))
        rows.append(row)

    return {"types": types, "rows": rows}


def _tile_footprint(document: dict[str, Any]) -> dict[str, Any] | None:
    """Return compact non-space tile runs that approximate MapInsertSmimsh fixtures."""
    tilemap = document.get("tilemap", {})
    if not isinstance(tilemap, dict):
        return None
    space_ids = {
        int(raw_id)
        for raw_id, prototype_id in tilemap.items()
        if isinstance(raw_id, (int, str))
        and str(raw_id).isdigit()
        and prototype_id == "Space"
    }
    cells: set[tuple[int, int]] = set()
    for group in document["entities"]:
        if not isinstance(group, dict):
            continue
        entities = group.get("entities", [])
        if not isinstance(entities, list):
            continue
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            components = entity.get("components", [])
            if not isinstance(components, list):
                continue
            for component in components:
                if not isinstance(component, dict) or component.get("type") != "MapGrid":
                    continue
                chunks = component.get("chunks", {})
                if not isinstance(chunks, dict):
                    continue
                for chunk in chunks.values():
                    if not isinstance(chunk, dict) or not isinstance(chunk.get("tiles"), str):
                        continue
                    index = _area_position(chunk.get("ind"))
                    if index is None:
                        continue
                    raw = base64.b64decode(chunk["tiles"], validate=True)
                    if len(raw) % 256 != 0:
                        raise RuntimeError(f"Invalid MapGrid chunk payload: {len(raw)} bytes")
                    tile_bytes = len(raw) // 256
                    if tile_bytes < 2:
                        raise RuntimeError(f"Invalid serialized tile size: {tile_bytes}")
                    for offset in range(256):
                        start = offset * tile_bytes
                        tile_id = int.from_bytes(raw[start:start + 2], "little")
                        if tile_id in space_ids:
                            continue
                        cells.add((
                            index[0] * 16 + offset % 16,
                            index[1] * 16 + offset // 16,
                        ))
    if not cells:
        return None

    by_row: dict[int, list[int]] = {}
    for x, y in cells:
        by_row.setdefault(y, []).append(x)
    rows: list[list[int]] = []
    for y in sorted(by_row):
        positions = sorted(by_row[y])
        row = [y]
        start = previous = positions[0]
        for x in positions[1:]:
            if x == previous + 1:
                previous = x
                continue
            row.extend((start, previous - start + 1))
            start = previous = x
        row.extend((start, previous - start + 1))
        rows.append(row)
    return {"rows": rows}


def build_overlay(
    game_source: Path,
    map_path: str,
    prototypes: dict[str, EntityPrototype],
    resolver: PrototypeResolver,
) -> dict[str, Any]:
    registry: dict[str, Any] = {}
    document = _load_map(resource_path(game_source, map_path))
    occurrences, pending = _extract_occurrences(document, prototypes, resolver, registry)
    item_occurrences = _static_item_occurrences(document, prototypes, resolver)
    object_config = load_map_object_config()
    object_registry = object_config["prototypes"]
    object_ids = set(object_registry)
    object_occurrences = _configured_object_occurrences(document, object_ids)
    insert_maps: dict[str, Any] = {}
    visited: set[str] = set()

    while pending:
        insert_path = min(pending)
        pending.remove(insert_path)
        if insert_path in visited:
            continue
        visited.add(insert_path)
        local_path = resource_path(game_source, insert_path)
        if not local_path.is_file():
            raise FileNotFoundError(
                f"MapInsert referenced by {map_path} does not exist: {insert_path}"
            )
        insert_document = _load_map(local_path)
        insert_occurrences, nested = _extract_occurrences(
            insert_document, prototypes, resolver, registry
        )
        render_key = insert_render_key(insert_path)
        insert_maps[insert_path] = {
            "occurrences": insert_occurrences,
            "itemOccurrences": _static_item_occurrences(
                insert_document,
                prototypes,
                resolver,
                relative_to_grid=True,
            ),
            "objectOccurrences": _configured_object_occurrences(insert_document, object_ids),
            "areas": _area_grid(insert_document, prototypes, resolver),
            "footprint": _tile_footprint(insert_document),
            "tiles": f"inserts/{render_key}/tiles.json",
        }
        pending.update(nested - visited)

    return {
        "schemaVersion": OVERLAY_SCHEMA_VERSION,
        "mapPath": map_path,
        "prototypes": dict(sorted(registry.items())),
        "occurrences": dict(sorted(occurrences.items())),
        "itemOccurrences": dict(sorted(item_occurrences.items())),
        "objectGroups": object_config["groups"],
        "objectPrototypes": dict(sorted(object_registry.items())),
        "objectOccurrences": dict(sorted(object_occurrences.items())),
        "insertMaps": dict(sorted(insert_maps.items())),
        "areas": _area_grid(document, prototypes, resolver),
    }


def discover_insert_paths(
    game_source: Path,
    maps: list[dict[str, Any]],
    prototypes: dict[str, EntityPrototype],
    resolver: PrototypeResolver,
) -> list[str]:
    paths: set[str] = set()
    pending: set[str] = set()

    def collect(document: dict[str, Any]) -> set[str]:
        result: set[str] = set()
        for group in document["entities"]:
            if not isinstance(group, dict):
                continue
            prototype_id = group.get("proto")
            if not isinstance(prototype_id, str) or prototype_id not in prototypes:
                continue
            insert = resolver.resolve(prototype_id)["components"].get("MapInsert")
            if not isinstance(insert, dict):
                continue
            variations = insert.get("variations", [])
            if not isinstance(variations, list):
                continue
            for variation in variations:
                if isinstance(variation, dict) and isinstance(variation.get("spawn"), str):
                    result.add(variation["spawn"])
        return result

    for entry in maps:
        pending.update(collect(_load_map(resource_path(game_source, entry["mapPath"]))))
    while pending:
        insert_path = min(pending)
        pending.remove(insert_path)
        if insert_path in paths:
            continue
        paths.add(insert_path)
        local_path = resource_path(game_source, insert_path)
        if not local_path.is_file():
            raise FileNotFoundError(f"MapInsert does not exist: {insert_path}")
        pending.update(collect(_load_map(local_path)) - paths)
    return sorted(paths)


def write_json(path: Path, data: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {"ensure_ascii": False}
    if compact:
        kwargs["separators"] = (",", ":")
    else:
        kwargs["indent"] = 2
    path.write_text(json.dumps(data, **kwargs) + "\n", encoding="utf-8")


def write_overlays(
    game_source: Path,
    output_root: Path,
    maps: list[dict[str, Any]],
    prototypes: dict[str, EntityPrototype],
    resolver: PrototypeResolver,
) -> set[str]:
    active_ids = {entry["id"] for entry in maps}
    if output_root.is_dir():
        for child in output_root.iterdir():
            if (
                child.is_dir()
                and child.name not in active_ids
                and ((child / "overlay.json").is_file() or (child / "tiles.json").is_file())
            ):
                shutil.rmtree(child)
    item_ids: set[str] = set()
    for entry in maps:
        overlay = build_overlay(
            game_source, entry["mapPath"], prototypes, resolver
        )
        item_ids.update(overlay["itemOccurrences"])
        for insert in overlay["insertMaps"].values():
            item_ids.update(insert["itemOccurrences"])
        relative = Path(entry["id"]) / "overlay.json"
        write_json(output_root / relative, overlay, compact=True)
        entry["overlay"] = relative.as_posix()
        existing_tiles = output_root / entry["id"] / "tiles.json"
        if existing_tiles.is_file():
            entry["tiles"] = (Path(entry["id"]) / "tiles.json").as_posix()
    return item_ids


def _level_size(width: int, height: int, divisor: int) -> tuple[int, int]:
    return max(1, math.ceil(width / divisor)), max(1, math.ceil(height / divisor))


def _save_tiles(
    image: Image.Image,
    output_root: Path,
    tile_size: int,
    quality: int,
) -> list[dict[str, Any]]:
    max_zoom = max(0, math.ceil(math.log2(max(image.size) / tile_size)))
    levels: list[dict[str, Any]] = []
    for zoom in range(max_zoom + 1):
        divisor = 2 ** (max_zoom - zoom)
        lossless = zoom == max_zoom
        size = _level_size(image.width, image.height, divisor)
        level_image = image if divisor == 1 else image.resize(size, Image.Resampling.NEAREST)
        present: list[list[int]] = []
        columns = math.ceil(size[0] / tile_size)
        rows = math.ceil(size[1] / tile_size)
        level_root = output_root / str(zoom)
        for y in range(rows):
            for x in range(columns):
                box = (
                    x * tile_size,
                    y * tile_size,
                    min((x + 1) * tile_size, size[0]),
                    min((y + 1) * tile_size, size[1]),
                )
                tile = level_image.crop(box)
                alpha = tile.getchannel("A")
                is_empty = alpha.getbbox() is None
                alpha.close()
                if is_empty:
                    tile.close()
                    continue
                level_root.mkdir(parents=True, exist_ok=True)
                tile.save(
                    level_root / f"{x}-{y}.webp",
                    "WEBP",
                    quality=quality,
                    method=4 if lossless else 6,
                    lossless=lossless,
                    exact=True,
                )
                tile.close()
                present.append([x, y])
        if level_image is not image:
            level_image.close()
        levels.append(
            {
                "z": zoom,
                "width": size[0],
                "height": size[1],
                "columns": columns,
                "rows": rows,
                "lossless": lossless,
                "tiles": present,
            }
        )
    return levels


def _package_render_tiles(
    rendered_root: Path,
    output_root: Path,
    render_key: str,
    relative_root: Path,
    *,
    tile_size: int,
    scale: float,
    quality: int,
) -> None:
    render_root = rendered_root / render_key
    viewer_path = render_root / "map.json"
    if not viewer_path.is_file():
        raise FileNotFoundError(f"Renderer did not produce viewer data: {viewer_path}")
    viewer = json.loads(viewer_path.read_text(encoding="utf-8"))
    grids = viewer.get("Grids", viewer.get("grids"))
    if not isinstance(grids, list) or not grids:
        raise RuntimeError(f"Renderer viewer data has no grids: {viewer_path}")

    map_root = output_root / relative_root / "tiles"
    if map_root.exists():
        shutil.rmtree(map_root)
    manifest_grids: list[dict[str, Any]] = []
    for index, grid in enumerate(grids):
        if not isinstance(grid, dict):
            raise RuntimeError(f"Invalid renderer grid in {viewer_path}")
        url = grid.get("Url", grid.get("url"))
        if not isinstance(url, str):
            raise RuntimeError(f"Renderer grid has no Url in {viewer_path}")
        image_path = rendered_root / Path(url.replace("\\", "/"))
        if not image_path.is_file():
            image_path = render_root / Path(url).name
        if not image_path.is_file():
            raise FileNotFoundError(f"Missing rendered grid image: {url}")
        with Image.open(image_path) as source:
            rgba = source.convert("RGBA")
            scaled_size = (
                max(1, round(rgba.width * scale)),
                max(1, round(rgba.height * scale)),
            )
            scaled = (
                rgba
                if scaled_size == rgba.size
                else rgba.resize(scaled_size, Image.Resampling.NEAREST)
            )
            levels = _save_tiles(
                scaled, map_root / f"g{index}", tile_size, quality
            )
            if scaled is not rgba:
                scaled.close()
            rgba.close()
        manifest_grids.append(
            {
                "id": str(grid.get("GridId", grid.get("gridId", index))),
                "offset": grid.get("Offset", grid.get("offset", {"X": 0, "Y": 0})),
                "worldMin": grid.get("WorldMin", grid.get("worldMin")),
                "extent": grid.get("Extent", grid.get("extent")),
                "pixelsPerMeter": 32 * scale,
                "path": f"tiles/g{index}/{{z}}/{{x}}-{{y}}.webp",
                "levels": levels,
            }
        )

    manifest = {
        "schemaVersion": TILES_SCHEMA_VERSION,
        "tileSize": tile_size,
        "format": "webp",
        "quality": quality,
        "maxZoomLossless": True,
        "renderScale": scale,
        "grids": manifest_grids,
    }
    manifest_path = output_root / relative_root / "tiles.json"
    write_json(manifest_path, manifest, compact=True)


def package_render(
    rendered_root: Path,
    output_root: Path,
    entry: dict[str, Any],
    *,
    tile_size: int,
    scale: float,
    quality: int,
) -> None:
    _package_render_tiles(
        rendered_root,
        output_root,
        Path(entry["mapPath"]).stem,
        Path(entry["id"]),
        tile_size=tile_size,
        scale=scale,
        quality=quality,
    )
    entry["tiles"] = (Path(entry["id"]) / "tiles.json").as_posix()


def package_insert_render(
    rendered_root: Path,
    output_root: Path,
    insert_path: str,
    *,
    tile_size: int,
    scale: float,
    quality: int,
) -> None:
    render_key = insert_render_key(insert_path)
    _package_render_tiles(
        rendered_root,
        output_root,
        render_key,
        Path("inserts") / render_key,
        tile_size=tile_size,
        scale=scale,
        quality=quality,
    )


def package_insert_renders(
    rendered_root: Path,
    output_root: Path,
    insert_paths: list[str],
    *,
    tile_size: int,
    scale: float,
    quality: int,
) -> None:
    insert_root = output_root / "inserts"
    if insert_root.exists():
        shutil.rmtree(insert_root)
    for insert_path in insert_paths:
        package_insert_render(
            rendered_root,
            output_root,
            insert_path,
            tile_size=tile_size,
            scale=scale,
            quality=quality,
        )


def directory_size(path: Path, *, exclude: set[Path] | None = None) -> int:
    excluded = {value.resolve() for value in (exclude or set())}
    return sum(
        file.stat().st_size
        for file in path.rglob("*")
        if file.is_file() and file.resolve() not in excluded
    )


def build_catalog(
    maps: list[dict[str, Any]], game_commit: str, assets_bytes: int
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "source": "MetalSage/space-stories-cm14",
        "gameCommit": game_commit,
        "items": STATIC_ITEM_CATALOG_PATH,
        "maps": maps,
        "counts": {
            "maps": len(maps),
            "ships": sum(entry["kind"] == "ship" for entry in maps),
            "planets": sum(entry["kind"] == "planet" for entry in maps),
            "assetBytes": assets_bytes,
        },
    }
