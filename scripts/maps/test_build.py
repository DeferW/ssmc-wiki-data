from __future__ import annotations

from pathlib import Path

import yaml
from PIL import Image

from scripts.common.prototypes import EntityPrototype, PrototypeResolver
from scripts.maps.core import (
    _save_tiles,
    build_overlay,
    discover_active_maps,
    parse_vector,
)
from scripts.maps.prepare_render import prepare_render_maps, sanitize_map_text


def make_prototype(
    prototype_id: str,
    *,
    parents: tuple[str, ...] = (),
    components: tuple[dict, ...] = (),
    fields: dict | None = None,
    source_file: str = "Resources/Prototypes/_RMC14/test.yml",
    abstract: bool = False,
) -> EntityPrototype:
    return EntityPrototype(
        id=prototype_id,
        parents=parents,
        abstract=abstract,
        source_file=source_file,
        origin="rmc14",
        fields=fields or {},
        components=components,
    )


def write_yaml(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_discovery_uses_stories_ship_and_live_planet_path(tmp_path: Path):
    write_yaml(
        tmp_path / "Resources/Prototypes/_Stories/Maps/maps.yml",
        [
            {"type": "gameMap", "id": "STShip", "mapName": "Ship", "mapPath": "/Maps/_Stories/ship.yml"},
            {"type": "gameMapPool", "id": "STPool", "maps": ["STShip"]},
        ],
    )
    write_yaml(tmp_path / "Resources/Maps/_Stories/ship.yml", {"entities": []})
    write_yaml(tmp_path / "Resources/Maps/_RMC14/planet.yml", {"entities": []})
    write_yaml(tmp_path / "Resources/Maps/_RMC14/old_ship.yml", {"entities": []})
    prototypes = {
        "RMCPlanet": make_prototype(
            "RMCPlanet",
            components=({"type": "RMCPlanetMapPrototype", "map": "/Maps/_RMC14/planet.yml"},),
            fields={"name": "Planet"},
        )
    }
    maps = discover_active_maps(tmp_path, prototypes, PrototypeResolver(prototypes))
    assert [entry["mapPath"] for entry in maps] == [
        "/Maps/_Stories/ship.yml",
        "/Maps/_RMC14/planet.yml",
    ]


def test_overlay_keeps_spawner_locations_options_and_insert_markers(tmp_path: Path):
    prototypes = {
        "MarkerBase": make_prototype(
            "MarkerBase",
            abstract=True,
            source_file="Resources/Prototypes/Entities/Markers/base.yml",
        ),
        "Loot": make_prototype(
            "Loot",
            parents=("MarkerBase",),
            components=(
                {"type": "RandomSpawner", "chance": 0.5, "prototypes": ["A", "B"]},
            ),
            fields={"name": "Loot spot"},
            source_file="Resources/Prototypes/_RMC14/Entities/Markers/loot.yml",
        ),
        "Insert": make_prototype(
            "Insert",
            parents=("MarkerBase",),
            components=(
                {
                    "type": "MapInsert",
                    "variations": [
                        {"spawn": "/Maps/_Stories/Inserts/new.yml", "probability": 0.25}
                    ],
                },
            ),
            source_file="Resources/Prototypes/_Stories/Entities/Markers/insert.yml",
        ),
    }
    write_yaml(
        tmp_path / "Resources/Maps/_RMC14/map.yml",
        {
            "entities": [
                {"proto": "Loot", "entities": [{"components": [{"type": "Transform", "pos": "1.5,2.5", "parent": 7}]}]},
                {"proto": "Insert", "entities": [{"components": [{"type": "Transform", "pos": "3,4"}]}]},
            ]
        },
    )
    write_yaml(
        tmp_path / "Resources/Maps/_Stories/Inserts/new.yml",
        {"entities": [{"proto": "Loot", "entities": [{"components": [{"type": "Transform", "pos": "5,6"}]}]}]},
    )
    overlay = build_overlay(
        tmp_path,
        "/Maps/_RMC14/map.yml",
        prototypes,
        PrototypeResolver(prototypes),
    )
    assert overlay["occurrences"]["Loot"] == [[1.5, 2.5, 0.0, 7]]
    assert overlay["prototypes"]["Loot"]["components"]["RandomSpawner"]["prototypes"] == ["A", "B"]
    assert overlay["insertMaps"]["/Maps/_Stories/Inserts/new.yml"]["occurrences"]["Loot"] == [[5.0, 6.0]]


def test_tile_pyramid_is_sparse_and_webp(tmp_path: Path):
    image = Image.new("RGBA", (1024, 512), (0, 0, 0, 0))
    for x in range(512):
        for y in range(512):
            image.putpixel((x, y), (255, 0, 0, 255))
    levels = _save_tiles(image, tmp_path, tile_size=512, quality=80)
    assert [level["z"] for level in levels] == [0, 1]
    assert levels[1]["tiles"] == [[0, 0]]
    with Image.open(tmp_path / "1/0-0.webp") as tile:
        assert tile.format == "WEBP"


def test_parse_vector_rejects_bad_values():
    assert parse_vector("1.25,-2") == [1.25, -2.0]
    assert parse_vector("bad") is None


def test_render_sanitizer_removes_only_transient_ui_state():
    source = """- proto: RMCBookcase
  entities:
  - uid: 18502
    components:
    - type: Transform
      pos: -0.5,81.5
    - type: UserInterface
      interfaces:
        enum.StorageUiKey.Key: StorageBoundUserInterface
      actors:
        enum.StorageUiKey.Key:
        - invalid
      requireInputValidation: false
    - type: ActiveUserInterface
      key: invalid
    - type: DoorSignalControl
      openPort: Entrance to the Center
    - type: Physics
"""
    clean, removed = sanitize_map_text(source)
    assert removed == 3
    assert "actors:" not in clean
    assert "ActiveUserInterface" not in clean
    assert "DoorSignalControl" not in clean
    assert "Entrance to the Center" not in clean
    assert "interfaces:" in clean
    assert "requireInputValidation: false" in clean
    assert "- type: Transform" in clean
    assert "- type: Physics" in clean


def test_prepare_render_maps_keeps_renderer_filenames(tmp_path: Path):
    source = tmp_path / "source" / "almayer.yml"
    source.parent.mkdir()
    source.write_text("entities: []\n", encoding="utf-8")
    render_list = tmp_path / "render-list.txt"
    render_list.write_text(f"{source}\n", encoding="utf-8")

    removed = prepare_render_maps(
        render_list,
        tmp_path / "prepared",
        tmp_path / "prepared-list.txt",
    )

    assert removed == 0
    prepared = Path((tmp_path / "prepared-list.txt").read_text(encoding="utf-8").strip())
    assert prepared.name == "almayer.yml"
    assert prepared.read_text(encoding="utf-8") == "entities: []\n"
