from __future__ import annotations

import base64
import json
from pathlib import Path

import yaml
from PIL import Image

from scripts.common.prototypes import EntityPrototype, PrototypeResolver
from scripts.maps.core import (
    _static_item_occurrences,
    _save_tiles,
    _tile_footprint,
    build_overlay,
    discover_active_maps,
    insert_render_key,
    package_insert_render,
    package_render,
    parse_vector,
)
from scripts.maps.prepare_render import prepare_render_maps, sanitize_map_text


def test_renderer_patch_keeps_fractional_sprite_offsets_and_reuses_pool():
    patch = (Path(__file__).with_name("renderer-world-bounds.patch")).read_text(encoding="utf-8")
    assert "Matrix3x2.Multiply(entity.Sprite.LocalMatrix, entityMatrix)" in patch
    assert "concreteLayer.GetLayerDrawMatrix(drawDirection, out var layerMatrix)" in patch
    assert "Vector2.Transform(Vector2.Zero, transform)" in patch
    assert "MathF.Round((localCenter.X + customOffset.X) * EyeManager.PixelsPerMeter)" in patch
    assert "MathF.Round((localCenter.Y + customOffset.Y) * EyeManager.PixelsPerMeter)" in patch
    assert "offsetX - image.Width / 2" in patch
    assert "offsetY - image.Height / 2" in patch
    assert "+                Fresh = false" in patch
    assert "+                Dirty = true" in patch


def test_insert_footprint_excludes_space_tiles():
    records = bytearray(256 * 7)
    records[0:2] = (3).to_bytes(2, "little")
    records[7:9] = (8).to_bytes(2, "little")
    document = {
        "tilemap": {0: "Space", 3: "CMFloorSteel", 8: "Space"},
        "entities": [{
            "entities": [{
                "components": [{
                    "type": "MapGrid",
                    "chunks": {"0,0": {"ind": "-1,2", "tiles": base64.b64encode(records).decode()}},
                }],
            }],
        }],
    }

    footprint = _tile_footprint(document)

    assert footprint is not None
    assert footprint["rows"] == [[32, -16, 1]]


def test_map_workflow_resumes_after_renderer_process_crash():
    workflow = (Path(__file__).parents[2] / ".github" / "workflows" / "build-maps.yml").read_text(
        encoding="utf-8"
    )
    assert 'PENDING_MAPS=("${MAP_FILES[@]}")' in workflow
    assert 'PENDING_INSERTS=("${MAP_FILES[@]}")' in workflow
    assert workflow.count("Renderer made no progress") == 2
    assert workflow.count("--no-build") >= 2
    assert workflow.count("dotnet build Content.MapRenderer --configuration Release") == 2
    assert "dotnet build --project" not in workflow


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


def test_static_items_include_only_unanchored_grid_children():
    prototypes = {
        "Grid": make_prototype(
            "Grid",
            components=({"type": "Transform"}, {"type": "MapGrid"}),
        ),
        "Plasteel": make_prototype(
            "Plasteel",
            components=({"type": "Transform"}, {"type": "Item"}),
        ),
        "TurretUpgrade": make_prototype(
            "TurretUpgrade",
            components=({"type": "Transform"}, {"type": "Item"}),
        ),
        "Pipe": make_prototype(
            "Pipe",
            components=({"type": "Transform", "anchored": True}, {"type": "Item"}),
        ),
        "Container": make_prototype(
            "Container",
            components=({"type": "Transform"},),
        ),
        "InternalItem": make_prototype(
            "InternalItem",
            components=({"type": "Transform"}, {"type": "Item"}),
        ),
    }
    document = {
        "entities": [
            {"proto": "Grid", "entities": [{"uid": 1, "components": [
                {"type": "Transform", "pos": "0,0"},
                {"type": "MapGrid"},
            ]}]},
            {"proto": "Plasteel", "entities": [{"uid": 2, "components": [
                {"type": "Transform", "pos": "1,2", "parent": 1},
            ]}]},
            {"proto": "TurretUpgrade", "entities": [{"uid": 3, "components": [
                {"type": "Transform", "pos": "3,4", "parent": 1},
            ]}]},
            {"proto": "Pipe", "entities": [{"uid": 4, "components": [
                {"type": "Transform", "pos": "5,6", "parent": 1},
            ]}]},
            {"proto": "Container", "entities": [{"uid": 5, "components": [
                {"type": "Transform", "pos": "7,8", "parent": 1},
            ]}]},
            {"proto": "InternalItem", "entities": [{"uid": 6, "components": [
                {"type": "Transform", "pos": "0,0", "parent": 5},
            ]}]},
        ],
    }

    occurrences = _static_item_occurrences(
        document,
        prototypes,
        PrototypeResolver(prototypes),
    )

    assert occurrences == {
        "Plasteel": [[1.0, 2.0]],
        "TurretUpgrade": [[3.0, 4.0]],
    }


def write_yaml(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_discovery_uses_almayer_and_only_planets_in_rotation(tmp_path: Path):
    write_yaml(
        tmp_path / "Resources/Prototypes/_Stories/Maps/maps.yml",
        [
            {"type": "gameMap", "id": "STAlmayer", "mapName": "Almayer", "mapPath": "/Maps/_Stories/almayer.yml"},
            {"type": "gameMap", "id": "STAlmayerLowPop", "mapName": "Almayer LowPop", "mapPath": "/Maps/_Stories/almayer.yml"},
            {"type": "gameMap", "id": "STOtherShip", "mapName": "Other", "mapPath": "/Maps/_Stories/other.yml"},
            {"type": "gameMapPool", "id": "STPool", "maps": ["STAlmayer", "STOtherShip"]},
        ],
    )
    write_yaml(tmp_path / "Resources/Maps/_Stories/almayer.yml", {"entities": []})
    write_yaml(tmp_path / "Resources/Maps/_Stories/other.yml", {"entities": []})
    write_yaml(tmp_path / "Resources/Maps/_RMC14/planet.yml", {"entities": []})
    write_yaml(tmp_path / "Resources/Maps/_RMC14/pve.yml", {"entities": []})
    prototypes = {
        "RMCPlanet": make_prototype(
            "RMCPlanet",
            components=({"type": "RMCPlanetMapPrototype", "map": "/Maps/_RMC14/planet.yml"},),
            fields={"name": "Planet"},
        ),
        "RMCPvePlanet": make_prototype(
            "RMCPvePlanet",
            components=({"type": "RMCPlanetMapPrototype", "map": "/Maps/_RMC14/pve.yml", "inRotation": False},),
            fields={"name": "PVE Planet"},
        ),
    }
    maps = discover_active_maps(tmp_path, prototypes, PrototypeResolver(prototypes))
    assert [entry["mapPath"] for entry in maps] == [
        "/Maps/_Stories/almayer.yml",
        "/Maps/_RMC14/planet.yml",
    ]
    assert maps[0]["sourcePrototypeIds"] == ["STAlmayer"]


def test_discovery_respects_inherited_in_rotation(tmp_path: Path):
    write_yaml(
        tmp_path / "Resources/Prototypes/_Stories/Maps/maps.yml",
        [
            {"type": "gameMap", "id": "STAlmayer", "mapName": "Almayer", "mapPath": "/Maps/_Stories/almayer.yml"},
            {"type": "gameMap", "id": "STAlmayerLowPop", "mapName": "Almayer LowPop", "mapPath": "/Maps/_Stories/almayer.yml"},
        ],
    )
    write_yaml(tmp_path / "Resources/Maps/_Stories/almayer.yml", {"entities": []})
    write_yaml(tmp_path / "Resources/Maps/_RMC14/inherited.yml", {"entities": []})
    prototypes = {
        "PlanetBase": make_prototype(
            "PlanetBase",
            abstract=True,
            components=({"type": "RMCPlanetMapPrototype", "inRotation": False},),
        ),
        "InheritedPvePlanet": make_prototype(
            "InheritedPvePlanet",
            parents=("PlanetBase",),
            components=({"type": "RMCPlanetMapPrototype", "map": "/Maps/_RMC14/inherited.yml"},),
        ),
    }

    maps = discover_active_maps(tmp_path, prototypes, PrototypeResolver(prototypes))

    assert [entry["mapPath"] for entry in maps] == ["/Maps/_Stories/almayer.yml"]


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
        "Survivor": make_prototype(
            "Survivor",
            components=({"type": "SpawnPoint", "job_id": "CMSurvivor"},),
            fields={"name": "Survivor spawn"},
            source_file="Resources/Prototypes/_RMC14/Roles/Jobs/Survivor/test.yml",
        ),
    }
    write_yaml(
        tmp_path / "Resources/Maps/_RMC14/map.yml",
        {
            "entities": [
                {"proto": "Loot", "entities": [{"components": [{"type": "Transform", "pos": "1.5,2.5", "parent": 7}]}]},
                {"proto": "Insert", "entities": [{"components": [{"type": "Transform", "pos": "3,4"}]}]},
                {"proto": "Survivor", "entities": [{"components": [{"type": "Transform", "pos": "7.5,8.5"}]}]},
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
    assert overlay["occurrences"]["Survivor"] == [[7.5, 8.5]]
    assert overlay["prototypes"]["Survivor"]["components"]["SpawnPoint"]["job_id"] == "CMSurvivor"
    assert overlay["prototypes"]["Loot"]["components"]["RandomSpawner"]["prototypes"] == ["A", "B"]
    insert = overlay["insertMaps"]["/Maps/_Stories/Inserts/new.yml"]
    assert insert["occurrences"]["Loot"] == [[5.0, 6.0]]
    assert insert["tiles"].startswith("inserts/new-")
    assert insert["tiles"].endswith("/tiles.json")


def test_overlay_compacts_area_support_into_row_runs(tmp_path: Path):
    prototypes = {
        "AreaBase": make_prototype(
            "AreaBase",
            abstract=True,
            components=(
                {
                    "type": "Area",
                    "CAS": True,
                    "fulton": True,
                    "lasing": True,
                    "mortarPlacement": True,
                    "mortarFire": True,
                    "medevac": True,
                    "paradropping": True,
                    "OB": True,
                    "supplyDrop": True,
                },
            ),
        ),
        "AreaOutside": make_prototype(
            "AreaOutside",
            parents=("AreaBase",),
            fields={"name": "Colony Grounds"},
        ),
        "AreaInside": make_prototype(
            "AreaInside",
            parents=("AreaBase",),
            components=(
                {
                    "type": "Area",
                    "fulton": False,
                    "lasing": False,
                    "mortarPlacement": False,
                    "mortarFire": False,
                    "medevac": False,
                    "paradropping": False,
                    "supplyDrop": False,
                },
            ),
            fields={"name": "Medical"},
        ),
    }
    write_yaml(
        tmp_path / "Resources/Maps/_RMC14/map.yml",
        {
            "entities": [
                {
                    "proto": "",
                    "entities": [
                        {
                            "components": [
                                {
                                    "type": "AreaGrid",
                                    "areas": {
                                        "0,0": "AreaOutside",
                                        "1,0": "AreaOutside",
                                        "2,0": "AreaInside",
                                        "0,1": "AreaInside",
                                    },
                                }
                            ]
                        }
                    ],
                }
            ]
        },
    )

    overlay = build_overlay(
        tmp_path,
        "/Maps/_RMC14/map.yml",
        prototypes,
        PrototypeResolver(prototypes),
    )

    assert overlay["schemaVersion"] == 4
    assert overlay["areas"] == {
        "types": [
            ["AreaInside", "Medical", 129],
            ["AreaOutside", "Colony Grounds", 511],
        ],
        "rows": [[0, 0, 2, 1, 2, 1, 0], [1, 0, 1, 0]],
    }


def test_tile_pyramid_is_sparse_and_webp(tmp_path: Path):
    image = Image.new("RGBA", (1024, 512), (0, 0, 0, 0))
    for x in range(512):
        for y in range(512):
            image.putpixel((x, y), (255, 0, 0, 255))
    levels = _save_tiles(image, tmp_path, tile_size=512, quality=80)
    assert [level["z"] for level in levels] == [0, 1]
    assert [level["lossless"] for level in levels] == [False, True]
    assert levels[1]["tiles"] == [[0, 0]]
    with Image.open(tmp_path / "1/0-0.webp") as tile:
        assert tile.format == "WEBP"


def test_package_render_keeps_renderer_world_bounds(tmp_path: Path):
    rendered = tmp_path / "rendered"
    render_root = rendered / "test"
    render_root.mkdir(parents=True)
    Image.new("RGBA", (64, 32), (255, 0, 0, 255)).save(render_root / "grid.webp")
    (render_root / "map.json").write_text(
        json.dumps(
            {
                "Grids": [
                    {
                        "GridId": "1",
                        "Url": "test/grid.webp",
                        "Offset": {"X": 0, "Y": 0},
                        "WorldMin": {"X": -50, "Y": -125},
                        "Extent": {"X1": 0, "Y1": 0, "X2": 64, "Y2": 32},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    entry = {"id": "test", "mapPath": "/Maps/test.yml"}
    package_render(rendered, output, entry, tile_size=512, scale=1, quality=82)
    manifest = json.loads((output / "test/tiles.json").read_text(encoding="utf-8"))
    assert manifest["grids"][0]["worldMin"] == {"X": -50, "Y": -125}


def test_package_insert_render_uses_stable_public_path(tmp_path: Path):
    insert_path = "/Maps/_RMC14/Inserts/Test/room.yml"
    render_key = insert_render_key(insert_path)
    rendered = tmp_path / "rendered"
    render_root = rendered / render_key
    render_root.mkdir(parents=True)
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(render_root / "grid.webp")
    (render_root / "map.json").write_text(
        json.dumps({"Grids": [{"Url": f"{render_key}/grid.webp"}]}),
        encoding="utf-8",
    )

    output = tmp_path / "output"
    package_insert_render(
        rendered,
        output,
        insert_path,
        tile_size=512,
        scale=1,
        quality=82,
    )

    assert (output / "inserts" / render_key / "tiles.json").is_file()


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


def test_prepare_render_maps_gives_inserts_unique_stable_names(tmp_path: Path):
    source = tmp_path / "game" / "Resources" / "Maps" / "_RMC14" / "Inserts" / "Test" / "room.yml"
    source.parent.mkdir(parents=True)
    source.write_text("entities: []\n", encoding="utf-8")
    render_list = tmp_path / "insert-render-list.txt"
    render_list.write_text(f"{source}\n", encoding="utf-8")

    prepare_render_maps(
        render_list,
        tmp_path / "prepared",
        tmp_path / "prepared-list.txt",
        unique_names=True,
    )

    prepared = Path((tmp_path / "prepared-list.txt").read_text(encoding="utf-8").strip())
    assert prepared.name == f"{insert_render_key('/Maps/_RMC14/Inserts/Test/room.yml')}.yml"
