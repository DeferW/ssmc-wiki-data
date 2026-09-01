from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from scripts.maps.core import (
    OVERLAY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    TILES_SCHEMA_VERSION,
)
from scripts.maps.validate import validate
from scripts.maps.items import STATIC_ITEM_SCHEMA_VERSION


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_tiles(root: Path) -> None:
    tile_path = root / "tiles/g0/0/0-0.webp"
    tile_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(tile_path, format="WEBP", lossless=True)
    write_json(
        root / "tiles.json",
        {
            "schemaVersion": TILES_SCHEMA_VERSION,
            "renderScale": 1,
            "maxZoomLossless": True,
            "tileSize": 512,
            "grids": [
                {
                    "path": "tiles/g0/{z}/{x}-{y}.webp",
                    "worldMin": {"X": 0, "Y": 0},
                    "levels": [{"z": 0, "lossless": True, "tiles": [[0, 0]]}],
                }
            ],
        },
    )


def make_dataset(tmp_path: Path) -> tuple[Path, Path]:
    assets_root = tmp_path / "maps"
    main_root = assets_root / "test-map"
    insert_root = assets_root / "inserts/test-insert"
    write_tiles(main_root)
    write_tiles(insert_root)
    write_json(
        main_root / "overlay.json",
        {
            "schemaVersion": OVERLAY_SCHEMA_VERSION,
            "mapPath": "/Maps/_Stories/test.yml",
            "prototypes": {},
            "occurrences": {},
            "itemOccurrences": {},
            "objectGroups": [],
            "objectPrototypes": {},
            "objectOccurrences": {},
            "insertMaps": {
                "/Maps/_Stories/Inserts/test.yml": {
                    "tiles": "inserts/test-insert/tiles.json",
                    "itemOccurrences": {},
                    "objectOccurrences": {}
                }
            },
        },
    )
    write_json(
        assets_root / "static-items.json",
        {
            "schemaVersion": STATIC_ITEM_SCHEMA_VERSION,
            "items": {},
            "publicCatalog": {"itemIds": [], "categories": {}},
        },
    )
    asset_bytes = sum(path.stat().st_size for path in assets_root.rglob("*") if path.is_file())
    catalog_path = assets_root / "catalog.json"
    write_json(
        catalog_path,
        {
            "schemaVersion": SCHEMA_VERSION,
            "items": "static-items.json",
            "maps": [
                {
                    "id": "test-map",
                    "mapPath": "/Maps/_Stories/test.yml",
                    "kind": "planet",
                    "origin": "stories",
                    "overlay": "test-map/overlay.json",
                    "tiles": "test-map/tiles.json",
                }
            ],
            "counts": {"maps": 1, "ships": 0, "planets": 1, "assetBytes": asset_bytes},
        },
    )
    return catalog_path, assets_root


def test_validate_accepts_insert_tiles(tmp_path: Path) -> None:
    catalog_path, assets_root = make_dataset(tmp_path)

    validate(catalog_path, assets_root, 10_000_000)


def test_validate_still_rejects_unreferenced_assets(tmp_path: Path) -> None:
    catalog_path, assets_root = make_dataset(tmp_path)
    (assets_root / "unexpected.webp").write_bytes(b"not a referenced asset")

    with pytest.raises(RuntimeError, match="Unexpected map asset files"):
        validate(catalog_path, assets_root, 10_000_000)
