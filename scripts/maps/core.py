from __future__ import annotations

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

SCHEMA_VERSION = 1
OVERLAY_SCHEMA_VERSION = 1
TILES_SCHEMA_VERSION = 2
DEFAULT_TILE_SIZE = 512
DEFAULT_RENDER_SCALE = 1.0
DEFAULT_WEBP_QUALITY = 82
DEFAULT_MAX_ASSET_BYTES = 512 * 1024 * 1024


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


def _prototype_documents(root: Path) -> Iterable[dict[str, Any]]:
    files = sorted([*root.rglob("*.yml"), *root.rglob("*.yaml")])
    for path in files:
        yield from iter_prototype_documents(path)


def _stories_game_maps(game_source: Path) -> list[dict[str, Any]]:
    root = game_source / "Resources/Prototypes/_Stories"
    if not root.is_dir():
        raise FileNotFoundError(f"Missing SSMC prototype directory: {root}")

    game_maps: dict[str, dict[str, Any]] = {}
    pooled_ids: set[str] = set()
    for raw in _prototype_documents(root):
        if raw.get("type") == "gameMap" and isinstance(raw.get("id"), str):
            game_maps[raw["id"]] = raw
        elif raw.get("type") == "gameMapPool":
            maps = raw.get("maps", [])
            if isinstance(maps, list):
                pooled_ids.update(value for value in maps if isinstance(value, str))

    by_path: dict[str, dict[str, Any]] = {}
    for prototype_id in sorted(pooled_ids):
        raw = game_maps.get(prototype_id)
        if raw is None:
            raise RuntimeError(f"SSMC map pool references unknown gameMap: {prototype_id}")
        path = raw.get("mapPath")
        if not isinstance(path, str) or not path.startswith("/Maps/_Stories/"):
            raise RuntimeError(
                f"SSMC gameMap {prototype_id} must point to /Maps/_Stories/: {path!r}"
            )
        entry = by_path.setdefault(
            path,
            {
                "id": map_slug(path),
                "name": str(raw.get("mapName") or prototype_id),
                "kind": "ship",
                "mapPath": path,
                "origin": map_origin(path),
                "sourcePrototypeIds": [],
            },
        )
        entry["sourcePrototypeIds"].append(prototype_id)
    return list(by_path.values())


def discover_active_maps(
    game_source: Path,
    prototypes: dict[str, EntityPrototype],
    resolver: PrototypeResolver,
) -> list[dict[str, Any]]:
    """Discover maps reachable from SSMC pools and live planet prototypes.

    The directory name is deliberately not used to decide whether a colony is
    active. SSMC currently references several updated maps under ``_RMC14``;
    the live RMCPlanetMapPrototype component is the source of truth.
    """

    maps = _stories_game_maps(game_source)
    paths = {entry["mapPath"] for entry in maps}

    for prototype_id in sorted(prototypes):
        prototype = prototypes[prototype_id]
        if prototype.abstract:
            continue
        resolved = resolver.resolve(prototype_id)
        planet = resolved["components"].get("RMCPlanetMapPrototype")
        if not isinstance(planet, dict):
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
        if component_type == "MapInsert" or "Spawner" in component_type
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


def build_overlay(
    game_source: Path,
    map_path: str,
    prototypes: dict[str, EntityPrototype],
    resolver: PrototypeResolver,
) -> dict[str, Any]:
    registry: dict[str, Any] = {}
    document = _load_map(resource_path(game_source, map_path))
    occurrences, pending = _extract_occurrences(document, prototypes, resolver, registry)
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
        insert_maps[insert_path] = {"occurrences": insert_occurrences}
        pending.update(nested - visited)

    return {
        "schemaVersion": OVERLAY_SCHEMA_VERSION,
        "mapPath": map_path,
        "prototypes": dict(sorted(registry.items())),
        "occurrences": dict(sorted(occurrences.items())),
        "insertMaps": dict(sorted(insert_maps.items())),
    }


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
) -> None:
    active_ids = {entry["id"] for entry in maps}
    if output_root.is_dir():
        for child in output_root.iterdir():
            if (
                child.is_dir()
                and child.name not in active_ids
                and ((child / "overlay.json").is_file() or (child / "tiles.json").is_file())
            ):
                shutil.rmtree(child)
    for entry in maps:
        overlay = build_overlay(
            game_source, entry["mapPath"], prototypes, resolver
        )
        relative = Path(entry["id"]) / "overlay.json"
        write_json(output_root / relative, overlay, compact=True)
        entry["overlay"] = relative.as_posix()
        existing_tiles = output_root / entry["id"] / "tiles.json"
        if existing_tiles.is_file():
            entry["tiles"] = (Path(entry["id"]) / "tiles.json").as_posix()


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


def package_render(
    rendered_root: Path,
    output_root: Path,
    entry: dict[str, Any],
    *,
    tile_size: int,
    scale: float,
    quality: int,
) -> None:
    short_name = Path(entry["mapPath"]).stem
    render_root = rendered_root / short_name
    viewer_path = render_root / "map.json"
    if not viewer_path.is_file():
        raise FileNotFoundError(f"Renderer did not produce viewer data: {viewer_path}")
    viewer = json.loads(viewer_path.read_text(encoding="utf-8"))
    grids = viewer.get("Grids", viewer.get("grids"))
    if not isinstance(grids, list) or not grids:
        raise RuntimeError(f"Renderer viewer data has no grids: {viewer_path}")

    map_root = output_root / entry["id"] / "tiles"
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
    manifest_path = output_root / entry["id"] / "tiles.json"
    write_json(manifest_path, manifest, compact=True)
    entry["tiles"] = (Path(entry["id"]) / "tiles.json").as_posix()


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
        "maps": maps,
        "counts": {
            "maps": len(maps),
            "ships": sum(entry["kind"] == "ship" for entry in maps),
            "planets": sum(entry["kind"] == "planet" for entry in maps),
            "assetBytes": assets_bytes,
        },
    }
