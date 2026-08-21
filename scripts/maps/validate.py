from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image

from scripts.maps.core import (
    DEFAULT_MAX_ASSET_BYTES,
    OVERLAY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    TILES_SCHEMA_VERSION,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(catalog_path: Path, assets_root: Path, max_assets_bytes: int) -> None:
    data = read_json(catalog_path)
    if not isinstance(data, dict) or data.get("schemaVersion") != SCHEMA_VERSION:
        raise RuntimeError(f"Unexpected map schemaVersion: {data.get('schemaVersion')}")
    maps = data.get("maps")
    if not isinstance(maps, list) or not maps:
        raise RuntimeError("Map catalog has no maps")
    ids: set[str] = set()
    paths: set[str] = set()
    expected_files: set[Path] = {catalog_path.resolve()}

    for entry in maps:
        if not isinstance(entry, dict):
            raise RuntimeError("Map entry is not an object")
        map_id = entry.get("id")
        map_path = entry.get("mapPath")
        if not isinstance(map_id, str) or not map_id or map_id in ids:
            raise RuntimeError(f"Invalid or duplicate map id: {map_id!r}")
        if not isinstance(map_path, str) or map_path in paths:
            raise RuntimeError(f"Invalid or duplicate map path: {map_path!r}")
        ids.add(map_id)
        paths.add(map_path)
        if entry.get("kind") not in {"ship", "planet"}:
            raise RuntimeError(f"Invalid map kind: {map_id}")
        if entry.get("origin") not in {"stories", "rmc14"}:
            raise RuntimeError(f"Vanilla/upstream map leaked into catalog: {map_id}")
        if entry["kind"] == "ship" and "/_Stories/" not in map_path:
            raise RuntimeError(f"Ship does not use the SSMC map: {map_id}")

        overlay_relative = entry.get("overlay")
        if not isinstance(overlay_relative, str):
            raise RuntimeError(f"Map has no overlay: {map_id}")
        overlay_path = assets_root / overlay_relative
        expected_files.add(overlay_path.resolve())
        overlay = read_json(overlay_path)
        if overlay.get("schemaVersion") != OVERLAY_SCHEMA_VERSION:
            raise RuntimeError(f"Invalid overlay schema: {map_id}")
        if overlay.get("mapPath") != map_path:
            raise RuntimeError(f"Overlay map path mismatch: {map_id}")
        if not isinstance(overlay.get("prototypes"), dict):
            raise RuntimeError(f"Overlay has no prototype registry: {map_id}")
        if not isinstance(overlay.get("occurrences"), dict):
            raise RuntimeError(f"Overlay has no occurrences: {map_id}")
        if not isinstance(overlay.get("insertMaps"), dict):
            raise RuntimeError(f"Overlay has no insert maps: {map_id}")

        tiles_relative = entry.get("tiles")
        if tiles_relative is None:
            continue
        if not isinstance(tiles_relative, str):
            raise RuntimeError(f"Invalid tiles path: {map_id}")
        manifest_path = assets_root / tiles_relative
        expected_files.add(manifest_path.resolve())
        manifest = read_json(manifest_path)
        if manifest.get("schemaVersion") != TILES_SCHEMA_VERSION:
            raise RuntimeError(f"Invalid tile schema: {map_id}")
        if manifest.get("renderScale") != 1:
            raise RuntimeError(f"Map is not published at native resolution: {map_id}")
        if manifest.get("maxZoomLossless") is not True:
            raise RuntimeError(f"Map maximum zoom is not lossless: {map_id}")
        tile_size = manifest.get("tileSize")
        if not isinstance(tile_size, int) or tile_size < 128:
            raise RuntimeError(f"Invalid tile size: {map_id}")
        for grid in manifest.get("grids", []):
            pattern = grid.get("path")
            if not isinstance(pattern, str):
                raise RuntimeError(f"Grid has no tile pattern: {map_id}")
            world_min = grid.get("worldMin")
            if (
                not isinstance(world_min, dict)
                or not isinstance(world_min.get("X"), (int, float))
                or not isinstance(world_min.get("Y"), (int, float))
            ):
                raise RuntimeError(f"Grid has no world bounds: {map_id}")
            levels = grid.get("levels", [])
            if not levels or levels[-1].get("lossless") is not True:
                raise RuntimeError(f"Map maximum tile level is not lossless: {map_id}")
            for level in levels:
                zoom = level.get("z")
                for coordinate in level.get("tiles", []):
                    x, y = coordinate
                    relative = pattern.format(z=zoom, x=x, y=y)
                    tile_path = assets_root / map_id / relative
                    expected_files.add(tile_path.resolve())
                    if not tile_path.is_file():
                        raise RuntimeError(f"Missing map tile: {tile_path}")
                    with Image.open(tile_path) as image:
                        if image.format != "WEBP":
                            raise RuntimeError(f"Map tile is not WebP: {tile_path}")
                        if image.width > tile_size or image.height > tile_size:
                            raise RuntimeError(f"Oversized map tile: {tile_path}")

    actual_files = {
        path.resolve() for path in assets_root.rglob("*") if path.is_file()
    }
    extras = sorted(str(path) for path in actual_files - expected_files)
    if extras:
        raise RuntimeError("Unexpected map asset files: " + ", ".join(extras[:20]))
    published_bytes = sum(path.stat().st_size for path in actual_files)
    assets_bytes = sum(
        path.stat().st_size
        for path in actual_files
        if path != catalog_path.resolve()
    )
    if published_bytes > max_assets_bytes:
        raise RuntimeError(
            f"Published map data exceeds budget: {published_bytes} > {max_assets_bytes}"
        )
    counts = data.get("counts", {})
    expected_counts = {
        "maps": len(maps),
        "ships": sum(entry["kind"] == "ship" for entry in maps),
        "planets": sum(entry["kind"] == "planet" for entry in maps),
        "assetBytes": assets_bytes,
    }
    if counts != expected_counts:
        raise RuntimeError(f"Map counts mismatch: stored={counts}, actual={expected_counts}")
    print(f"Maps: {len(maps)}")
    print(f"Published map bytes: {published_bytes}")
    print("Map catalog validation passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the SSMC map dataset")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--max-assets-bytes", type=int, default=DEFAULT_MAX_ASSET_BYTES)
    args = parser.parse_args()
    validate(args.catalog, args.assets, args.max_assets_bytes)


if __name__ == "__main__":
    main()
