from scripts.catalog.statistics import (
    box_cells,
    default_storage_max_size,
    packing_capacity,
    parse_vector2i,
    populate_skill_statistics,
    populate_weapon_statistics,
    shape_cells,
    storage_whitelist_matches,
)


def _sniper_items(weapon_aimed_shot: dict, has_focused_shooting: bool) -> dict:
    weapon_components = ["Gun", "AimedShot"]
    if has_focused_shooting:
        weapon_components.append("RMCFocusedShooting")
    return {
        "Rifle": {
            "componentTypes": weapon_components,
            "properties": {
                "Gun": {"selectedMode": "SemiAuto"},
                "AimedShot": weapon_aimed_shot,
            },
            "ammunitionPaths": [
                {
                    "magazineId": "Mag",
                    "cartridgeIds": ["Cartridge"],
                    "projectileIds": ["Bullet"],
                }
            ],
        },
        "Mag": {"properties": {"BallisticAmmoProvider": {"capacity": 10}}},
        "Bullet": {
            "name": "Bullet",
            "properties": {
                "Projectile": {"damage": {"types": {"Piercing": 70}}},
                "AimedShotEffect": {"extraHits": 2},
            },
        },
    }


def test_populate_weapon_statistics_includes_bare_aimed_shot_as_empty_dict():
    # AimedShotComponent is often inherited bare (e.g. M96S via
    # RMCBaseWeaponSniperRifle) -- an empty dict here still means "has the
    # ability, C# defaults apply", distinguishing it from not having AimedShot.
    items = _sniper_items(weapon_aimed_shot={}, has_focused_shooting=False)

    populate_weapon_statistics(items, relations=[], public_item_ids={"Rifle"})

    assert items["Rifle"]["weaponStats"]["aimedShot"] == {}
    assert "hasFocusedShooting" not in items["Rifle"]["weaponStats"]


def test_populate_weapon_statistics_includes_overridden_aimed_shot_fields():
    items = _sniper_items(
        weapon_aimed_shot={"aimDuration": 2, "aimedShotCooldown": 4.5},
        has_focused_shooting=True,
    )

    populate_weapon_statistics(items, relations=[], public_item_ids={"Rifle"})

    assert items["Rifle"]["weaponStats"]["aimedShot"] == {
        "aimDuration": 2,
        "aimedShotCooldown": 4.5,
    }
    assert items["Rifle"]["weaponStats"]["hasFocusedShooting"] is True


def test_populate_weapon_statistics_includes_projectile_aimed_shot_effect():
    items = _sniper_items(weapon_aimed_shot={}, has_focused_shooting=False)

    populate_weapon_statistics(items, relations=[], public_item_ids={"Rifle"})

    projectile = items["Rifle"]["weaponStats"]["ammunition"][0]["projectiles"][0]
    assert projectile["aimedShotEffect"] == {"extraHits": 2}


def test_populate_weapon_statistics_expands_holo_targeting_defaults():
    items = _sniper_items(weapon_aimed_shot={}, has_focused_shooting=False)
    items["Bullet"]["componentTypes"] = ["Projectile", "HoloTargeting"]
    items["Bullet"]["properties"]["HoloTargeting"] = {}

    populate_weapon_statistics(items, relations=[], public_item_ids={"Rifle"})

    projectile = items["Rifle"]["weaponStats"]["ammunition"][0]["projectiles"][0]
    assert projectile["holoTargeting"] == {
        "stacksPerHit": 10,
        "maxStacks": 100,
        "decayPerSecond": 5,
        "decayDelaySeconds": 5,
        "damageMultiplierPerStack": 0.001,
    }


def test_populate_weapon_statistics_preserves_holo_targeting_overrides():
    items = _sniper_items(weapon_aimed_shot={}, has_focused_shooting=False)
    items["Bullet"]["componentTypes"] = ["Projectile", "HoloTargeting"]
    items["Bullet"]["properties"]["HoloTargeting"] = {
        "stacks": 20,
        "maxStacks": 80,
        "decay": 4,
    }

    populate_weapon_statistics(items, relations=[], public_item_ids={"Rifle"})

    projectile = items["Rifle"]["weaponStats"]["ammunition"][0]["projectiles"][0]
    assert projectile["holoTargeting"] == {
        "stacksPerHit": 20,
        "maxStacks": 80,
        "decayPerSecond": 4,
        "decayDelaySeconds": 5,
        "damageMultiplierPerStack": 0.001,
    }


def test_populate_weapon_statistics_normalizes_toggleable_ammo_modes():
    items = {
        "SmartGun": {
            "componentTypes": ["Gun", "GunToggleableAmmo"],
            "properties": {
                "Gun": {},
                "GunToggleableAmmo": {
                    "settings": [
                        {
                            "name": "rmc-toggleable-ammo-highly-precise",
                            "damage": {"types": {"Piercing": 30}},
                            "armorPiercing": 0,
                        },
                        {
                            "name": "rmc-toggleable-ammo-armor-shredding",
                            "damage": {"types": {"Piercing": 20}},
                            "armorPiercing": 40,
                        },
                    ]
                },
            },
        }
    }

    populate_weapon_statistics(items, relations=[], public_item_ids={"SmartGun"})

    assert items["SmartGun"]["weaponStats"]["ammoModes"] == [
        {
            "id": "0",
            "nameId": "rmc-toggleable-ammo-highly-precise",
            "damage": {"Piercing": 30},
            "armorPiercing": 0,
        },
        {
            "id": "1",
            "nameId": "rmc-toggleable-ammo-armor-shredding",
            "damage": {"Piercing": 20},
            "armorPiercing": 40,
        },
    ]
    assert items["SmartGun"]["weaponStats"]["defaultAmmoModeIndex"] == 0


def test_populate_weapon_statistics_expands_bare_overheat_defaults():
    items = {
        "M2C": {
            "componentTypes": ["Gun", "Overheat"],
            "properties": {"Gun": {}, "Overheat": {}},
        }
    }

    populate_weapon_statistics(items, relations=[], public_item_ids={"M2C"})

    assert items["M2C"]["weaponStats"]["overheat"] == {
        "maxHeat": 40,
        "heatPerShot": 1,
        "cooldownRate": 2,
        "emergencyCooldownMultiplier": 0.375,
        "emergencyCooldownDelaySeconds": 1,
        "damage": {"Heat": 30},
        "shotsToOverheatFromCold": 40,
    }


def test_populate_skill_statistics_normalizes_pamphlet_effects():
    items = {
        "Pamphlet": {
            "properties": {
                "SkillPamphlet": {
                    "addSkills": {"RMCSkillEngineer": 1},
                    "skillCap": {"RMCSkillEngineer": 2},
                    "language": "Russian",
                    "bypassLimit": True,
                }
            }
        }
    }

    populate_skill_statistics(items, {"Pamphlet"})

    assert items["Pamphlet"]["skillStats"] == {
        "skills": {"RMCSkillEngineer": 1},
        "skillCaps": {"RMCSkillEngineer": 2},
        "language": "Russian",
        "bypassesPamphletLimit": True,
    }


def test_box_cells_single_1x1_box():
    assert box_cells([(0, 0, 0, 0)]) == {(0, 0)}


def test_box_cells_covers_full_rectangle():
    assert box_cells([(0, 0, 1, 1)]) == {(0, 0), (0, 1), (1, 0), (1, 1)}


def test_shape_cells_normalizes_to_origin():
    # A box that doesn't start at (0, 0) should be shifted so its minimum corner is (0, 0).
    assert shape_cells([(2, 3, 3, 4)]) == {(0, 0), (0, 1), (1, 0), (1, 1)}


def test_packing_capacity_fits_expected_count():
    grid = [(0, 0, 1, 1)]  # 2x2 grid = 4 cells
    item = [(0, 0, 0, 0)]  # 1x1 item
    assert packing_capacity(grid, item) == 4


def test_packing_capacity_item_bigger_than_grid():
    grid = [(0, 0, 0, 0)]  # 1x1 grid
    item = [(0, 0, 1, 1)]  # 2x2 item
    assert packing_capacity(grid, item) == 0


def test_packing_capacity_empty_grid_or_item_returns_zero():
    assert packing_capacity([], [(0, 0, 0, 0)]) == 0
    assert packing_capacity([(0, 0, 0, 0)], []) == 0


def test_parse_vector2i_from_string():
    assert parse_vector2i("3,4", default=(0, 0)) == (3, 4)


def test_parse_vector2i_from_list():
    assert parse_vector2i([3, 4], default=(0, 0)) == (3, 4)


def test_parse_vector2i_invalid_returns_default():
    assert parse_vector2i("not-a-vector", default=(1, 1)) == (1, 1)
    assert parse_vector2i(None, default=(1, 1)) == (1, 1)


def test_storage_whitelist_matches_true_when_no_rule():
    assert storage_whitelist_matches(None, {}) is True


def test_storage_whitelist_matches_by_component():
    rule = {"components": ["Gun"]}
    item = {"componentTypes": ["Gun"], "tags": []}
    assert storage_whitelist_matches(rule, item) is True


def test_storage_whitelist_matches_require_all():
    rule = {"requireAll": True, "components": ["Gun"], "sizes": ["Small"]}
    item = {"componentTypes": ["Gun"], "itemSize": "Normal", "tags": []}
    assert storage_whitelist_matches(rule, item) is False


def test_default_storage_max_size_picks_size_below_container():
    item_sizes = {
        "Small": {"weight": 1},
        "Normal": {"weight": 2},
        "Large": {"weight": 3},
    }
    assert default_storage_max_size("Large", item_sizes) == "Normal"


def test_default_storage_max_size_unknown_container_prefers_normal():
    item_sizes = {"Small": {"weight": 1}, "Normal": {"weight": 2}}
    assert default_storage_max_size("Unknown", item_sizes) == "Normal"
