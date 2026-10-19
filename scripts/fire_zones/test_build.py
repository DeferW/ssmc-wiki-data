import copy

import pytest

from scripts.common.localization import Localizer
from scripts.common.prototypes import EntityPrototype, PrototypeResolver
from scripts.fire_zones.build import (
    build_mortars,
    build_orbital_warheads,
    build_roofs,
    explosion_parts,
)
from scripts.fire_zones.rules import intensity_to_radius, radius_to_intensity
from scripts.fire_zones.validate import validate


def entity(prototype_id, components, parents=(), name=None, abstract=False):
    fields = {"name": name} if name else {}
    return EntityPrototype(
        id=prototype_id, parents=tuple(parents), abstract=abstract,
        source_file="Resources/Prototypes/_RMC14/test.yml", origin="rmc14",
        fields=fields, components=tuple(components),
    )


def resolver(*prototypes):
    return PrototypeResolver({prototype.id: prototype for prototype in prototypes})


LOCALIZER = Localizer({"ent-HiveCoreXeno": "ядро улья"})


def test_explosion_radius_mirrors_the_engine():
    # Known values for game commit 024d853a.
    assert intensity_to_radius(50000, 10, 90) == pytest.approx(17.542, abs=1e-3)
    assert intensity_to_radius(5000, 1500, 200) == pytest.approx(2.887, abs=1e-3)
    # Below the max-intensity cap the formula is the plain cone inverse.
    assert radius_to_intensity(intensity_to_radius(100, 10, 1000), 10) == pytest.approx(100)


def test_explosion_parts_cover_circles_fire_and_scatter():
    steps = [
        {"type": "RMCOB", "total": 5000, "slope": 1500, "max": 200, "delay": 1},
        {"fire": "RMCTileFireOB", "fireRange": 18},
        {"type": "RMCOB", "total": 6500, "slope": 100, "max": 350, "times": 75, "timesPer": 3, "spread": 12},
    ]
    assert explosion_parts(steps, "test") == [
        {"shape": "circle", "radius": 2.887},
        {"shape": "diamond", "radius": 18.0},
        {"shape": "scatter", "spread": 12.0, "radius": 3.961, "count": 225},
    ]


def test_explosion_parts_use_default_fire_range_and_drop_duplicates():
    step = {"type": "RMCOB", "total": 5000, "slope": 1500, "max": 200}
    parts = explosion_parts([step, copy.deepcopy(step), {"fire": "Fire"}], "test")
    assert parts == [{"shape": "circle", "radius": 2.887}, {"shape": "diamond", "radius": 18.0}]
    with pytest.raises(RuntimeError, match="no steps"):
        explosion_parts([], "test")


def test_mortar_uses_component_defaults_unless_yaml_overrides():
    found = build_mortars(resolver(
        entity("Mortar", [{"type": "Mortar"}], name="mortar"),
        entity("LongMortar", [{"type": "Mortar", "maximumRange": 80}], name="long mortar"),
        entity("AbstractMortar", [{"type": "Mortar"}], abstract=True),
    ), LOCALIZER)
    assert found == [
        {"id": "LongMortar", "name": "Long mortar", "minRange": 15.0, "maxRange": 80.0},
        {"id": "Mortar", "name": "Mortar", "minRange": 15.0, "maxRange": 65.0},
    ]


def test_warheads_follow_the_cannon_list_and_their_explosions():
    warheads = build_orbital_warheads(resolver(
        entity("Cannon", [{"type": "OrbitalCannon", "warheadTypes": ["HE"]}]),
        entity("HE", [{"type": "OrbitalCannonWarhead", "explosion": "HEBoom"}], name="HE warhead"),
        entity("HEBoom", [{"type": "OrbitalCannonExplosion", "steps": [
            {"type": "RMCOB", "total": 50000, "slope": 10, "max": 90},
        ]}]),
    ), LOCALIZER)
    assert warheads == [{
        "id": "HE", "name": "HE warhead", "explosionId": "HEBoom",
        "parts": [{"shape": "circle", "radius": 17.542}],
    }]


def test_roofs_block_every_support_they_do_not_allow():
    roofs = build_roofs(resolver(
        entity("HiveCoreXeno", [{"type": "RoofingEntity", "range": 11.848}], name="hive core"),
        entity("HivePylonXeno", [{"type": "RoofingEntity", "range": 8.463, "canOrbitalBombard": True}], name="pylon"),
    ), LOCALIZER)
    assert roofs[0]["name"] == "Ядро улья"
    assert "OB" in roofs[0]["blocks"] and len(roofs[0]["blocks"]) == 9
    assert "OB" not in roofs[1]["blocks"] and len(roofs[1]["blocks"]) == 8


def test_validator_rejects_broken_catalogs():
    catalog = {
        "schemaVersion": 1, "gameCommit": "abc",
        "counts": {"mortars": 1, "orbitalWarheads": 3, "roofs": 1},
        "mortars": [{"id": "M", "name": "M", "minRange": 15, "maxRange": 65}],
        "orbitalWarheads": [
            {"id": f"W{i}", "name": "W", "parts": [{"shape": "circle", "radius": 17.5}]} for i in range(3)
        ],
        "roofs": [{"id": "R", "name": "R", "radius": 8.4, "blocks": ["CAS", "fulton"]}],
    }
    validate(catalog)
    broken = copy.deepcopy(catalog)
    broken["roofs"][0]["blocks"] = ["CAS", "teleport"]
    with pytest.raises(RuntimeError, match="invalid blocks"):
        validate(broken)
    broken = copy.deepcopy(catalog)
    broken["mortars"][0]["minRange"] = 70
    with pytest.raises(RuntimeError, match="below maxRange"):
        validate(broken)
