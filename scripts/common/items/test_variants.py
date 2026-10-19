from scripts.catalog.catalog import build_public_catalog
from scripts.common.items.variants import hidden_variant_reasons


def card(item_id, components, *, parent=None, suffix="", name="Same item"):
    return {
        "id": item_id,
        "name": name,
        "baseName": name,
        "suffix": suffix,
        "parents": [parent] if parent else [],
        "componentTypes": list(components),
        "_classificationComponents": components,
        "properties": components,
        "equipmentSlots": [],
    }


def categorize(items):
    build_public_catalog([], items, [], {}, set(items))
    return {key: item["category"] for key, item in items.items()}


def test_empty_magazine_is_hidden_even_when_it_spawns_on_maps():
    items = {
        "FutureMagazine": card(
            "FutureMagazine",
            {"Item": {}, "BallisticAmmoProvider": {"capacity": 30, "proto": "Ammo"}},
        ),
        "FutureMagazineEmpty": card(
            "FutureMagazineEmpty",
            {
                "Item": {},
                "BallisticAmmoProvider": {"capacity": 30, "proto": None},
                "RMCEmptyMag": {},
            },
            parent="FutureMagazine",
            suffix="Empty",
        ),
    }
    assert categorize(items) == {"FutureMagazine": "Боезапас", "FutureMagazineEmpty": "Скрытые"}


def test_empty_powered_device_keeps_one_normal_card():
    components = {"Item": {}, "Defibrillator": {"zapDamage": 5}}
    items = {
        "FutureDevice": card("FutureDevice", components),
        "FutureDeviceDischarged": card(
            "FutureDeviceDischarged", components, parent="FutureDevice", suffix="Empty"
        ),
    }
    assert categorize(items)["FutureDeviceDischarged"] == "Скрытые"


def test_filled_weapon_state_is_hidden_but_different_damage_is_not():
    components = {
        "Item": {},
        "Gun": {"fireRate": 4},
        "RMCWeaponAccuracy": {"accuracyMultiplier": 1.5},
    }
    items = {
        "FutureRifle": card("FutureRifle", components),
        "FutureRifleLoaded": card(
            "FutureRifleLoaded", components, parent="FutureRifle", suffix="Filled"
        ),
        "FutureRifleSpecial": card(
            "FutureRifleSpecial",
            {**components, "Gun": {"fireRate": 6}},
            parent="FutureRifle",
            suffix="Filled",
        ),
    }
    result = categorize(items)
    assert result["FutureRifle"] == "Оружие"
    assert result["FutureRifleLoaded"] == "Скрытые"
    assert result["FutureRifleSpecial"] == "Оружие"


def test_id_lock_card_is_canonical_even_when_locked_prototype_is_the_child():
    components = {"Item": {}, "Gun": {"fireRate": 4}}
    items = {
        "FutureRifle": card("FutureRifle", components),
        "FutureRifleSecured": card(
            "FutureRifleSecured", {**components, "GunIDLock": {}}, parent="FutureRifle"
        ),
    }
    result = categorize(items)
    assert result["FutureRifle"] == "Скрытые"
    assert result["FutureRifleSecured"] == "Оружие"


def test_different_id_locked_weapon_is_not_deduplicated_by_lock_alone():
    items = {
        "FutureRifle": card("FutureRifle", {"Item": {}, "Gun": {"fireRate": 4}}),
        "FutureRifleSecured": card(
            "FutureRifleSecured",
            {"Item": {}, "Gun": {"fireRate": 8}, "GunIDLock": {}},
            parent="FutureRifle",
        ),
    }
    assert set(categorize(items).values()) == {"Оружие"}


def test_service_armor_fill_is_hidden_but_normal_armor_is_kept():
    components = {"Item": {}, "CMArmor": {"bullet": 20}, "PDTBraceletHolderTarget": {}}
    items = {
        "FutureArmor": card("FutureArmor", components),
        "FutureArmorRestraints": card(
            "FutureArmorRestraints",
            {**components, "StorageFill": {"contents": [{"id": "Restraints"}]}},
            parent="FutureArmor",
        ),
    }
    result = categorize(items)
    assert result["FutureArmor"] != "Скрытые"
    assert result["FutureArmorRestraints"] == "Скрытые"


def test_empty_name_alone_does_not_hide_independent_fortification():
    items = {
        "FutureBagEmpty": card(
            "FutureBagEmpty", {"Item": {}, "Stack": {}, "EmptySandbag": {}}, suffix="Empty"
        )
    }
    assert categorize(items)["FutureBagEmpty"] == "Снаряжение"


def test_an_empty_only_item_is_not_hidden_without_a_canonical_alternative():
    items = {
        "FutureContainerEmpty": card(
            "FutureContainerEmpty", {"Item": {}, "Storage": {}}, suffix="Empty"
        )
    }
    assert categorize(items)["FutureContainerEmpty"] == "Контейнеры"


def test_unknown_new_game_mechanics_are_not_silently_discarded_when_deduplicating():
    components = {"Item": {}, "Gun": {"fireRate": 4}}
    items = {
        "FutureRifle": card("FutureRifle", components),
        "FutureSpecial": card(
            "FutureSpecial",
            {**components, "NewDamageMechanic": {"multiplier": 2}},
            parent="FutureRifle",
            suffix="Filled",
        ),
    }
    assert categorize(items)["FutureSpecial"] == "Оружие"


def test_hidden_load_state_does_not_change_the_role_of_its_medical_case():
    components = {"Item": {}, "Defibrillator": {}}
    items = {
        "NormalDevice": card("NormalDevice", components),
        "EmptyDevice": card("EmptyDevice", components, parent="NormalDevice", suffix="Empty"),
        "Case": card("Case", {"Item": {}, "Storage": {}}, name="Case"),
    }
    build_public_catalog(
        [], items, [{"from": "Case", "to": "EmptyDevice", "type": "contains"}], {}, set(items)
    )
    assert items["EmptyDevice"]["category"] == "Скрытые"
    assert items["Case"]["category"] == "Медицина"


def test_empty_revolver_is_a_state_variant_but_capacity_changes_are_not():
    base = {
        "Item": {},
        "Gun": {},
        "RevolverAmmoProvider": {"capacity": 2, "proto": "Round", "chambers": [True, True]},
    }
    empty = {
        "Item": {},
        "Gun": {},
        "RevolverAmmoProvider": {"capacity": 2, "proto": None, "chambers": [None, None]},
    }
    larger = {
        "Item": {},
        "Gun": {},
        "RevolverAmmoProvider": {"capacity": 3, "proto": None, "chambers": [None, None, None]},
    }
    items = {
        "Revolver": card("Revolver", base),
        "EmptyRevolver": card("EmptyRevolver", empty, parent="Revolver", suffix="Empty"),
        "LargerRevolver": card("LargerRevolver", larger, parent="Revolver", suffix="Empty"),
    }
    result = categorize(items)
    assert result["EmptyRevolver"] == "Скрытые"
    assert result["LargerRevolver"] == "Оружие"


def test_spawn_loadout_does_not_create_a_second_weapon_card():
    base = {
        "Item": {},
        "Gun": {"fireRate": 4},
        "AttachableHolder": {"slots": {"underbarrel": {"locked": True}}},
    }
    loaded = {
        "Item": {},
        "Gun": {"fireRate": 4},
        "AttachableHolder": {"slots": {"underbarrel": {}}},
    }
    items = {
        "FutureWeapon": card("FutureWeapon", base),
        "LoadedWeapon": card("LoadedWeapon", loaded, parent="FutureWeapon", suffix="Filled"),
    }
    assert categorize(items)["LoadedWeapon"] == "Скрытые"


def test_empty_tools_and_partial_ammo_boxes_are_loading_states():
    for provider, full, empty in [
        ("LightReplacer", {"contents": [{"amount": 50}]}, {"contents": []}),
        ("BulletBox", {"amount": 600}, {"amount": 0}),
    ]:
        items = {
            "Normal": card("Normal", {"Item": {}, provider: full}),
            "Empty": card("Empty", {"Item": {}, provider: empty}, parent="Normal", suffix="Empty"),
        }
        assert categorize(items)["Empty"] == "Скрытые"


def test_stack_counts_share_one_card_even_when_the_base_is_not_published():
    items = {}
    for amount in [1, 10, 100]:
        key = f"FutureCash{amount}"
        items[key] = card(
            key, {"Item": {}, "Cash": {}, "Stack": {"stackType": "FutureCurrency", "count": amount}}
        )
    result = categorize(items)
    assert result["FutureCash1"] == "Быт"
    assert result["FutureCash10"] == result["FutureCash100"] == "Скрытые"


def test_stack_deduplication_preserves_distinct_materials_and_game_mechanics():
    items = {
        "A": card("A", {"Item": {}, "Stack": {"stackType": "Steel", "count": 1}}),
        "B": card("B", {"Item": {}, "Stack": {"stackType": "Steel", "count": 10}}),
        "C": card("C", {"Item": {}, "Stack": {"stackType": "Glass", "count": 10}}),
        "D": card(
            "D", {"Item": {}, "Stack": {"stackType": "Steel", "count": 10}, "NewMechanic": {}}
        ),
    }
    hidden = hidden_variant_reasons(items, set(items))
    assert set(hidden) == {"B"}


def test_stack_renderer_quantity_state_is_not_a_different_item():
    common = {
        "Item": {},
        "Cash": {},
        "Stack": {"stackType": "Cash", "layerStates": ["cash", "cash_10"]},
    }
    items = {}
    for count in [1, 10]:
        items[str(count)] = card(
            str(count),
            {
                **common,
                "Stack": {**common["Stack"], "count": count},
                "Sprite": {"sprite": "cash.rsi", "state": f"cash_{count}"},
            },
        )
    items["different"] = card(
        "different", {**common, "Sprite": {"sprite": "other.rsi", "state": "cash_10"}}
    )
    assert set(hidden_variant_reasons(items, set(items))) == {"10"}


def test_excluded_stack_cannot_be_the_only_canonical_card():
    items = {
        str(count): card(str(count), {"Item": {}, "Stack": {"stackType": "A", "count": count}})
        for count in [1, 10, 20]
    }
    build_public_catalog([], items, [], {"excludePrototypeIds": ["1"]}, set(items))
    assert items["10"]["category"] != "Скрытые"
    assert items["20"]["category"] == "Скрытые"
