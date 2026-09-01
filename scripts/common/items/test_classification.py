from scripts.common.items.classification import (
    classify_item,
    has_meaningful_armor,
    infer_types,
    is_ammunition_container,
    is_dedicated_melee_weapon,
    source_category_hint,
)

EMPTY_POLICY: dict = {"excludePrototypeIds": []}


def test_classify_item_excluded_by_policy():
    item = {"id": "Secret", "componentTypes": [], "tags": []}
    policy = {"excludePrototypeIds": ["Secret"]}
    result = classify_item(item, policy)
    assert result["status"] == "excluded"


def test_classify_item_weapon_via_gun_component():
    item = {"id": "RMCWeaponM13", "componentTypes": ["Gun"], "tags": []}
    result = classify_item(item, EMPTY_POLICY)
    assert result["categoryId"] == "weapon"


def test_classify_item_attachment_via_attachable_component():
    item = {"id": "RMCAttachmentScope", "componentTypes": ["Attachable"], "tags": []}
    result = classify_item(item, EMPTY_POLICY)
    assert result["categoryId"] == "attachment"


def test_classify_item_ammunition_via_cartridge():
    item = {"id": "RMCCartridge9mm", "componentTypes": ["CartridgeAmmo"], "tags": []}
    result = classify_item(item, EMPTY_POLICY)
    assert result["categoryId"] == "ammunition"


def test_classify_item_armor_via_meaningful_cmarmor_and_slot():
    item = {
        "id": "CMArmorM3",
        "componentTypes": [],
        "tags": [],
        "properties": {"CMArmor": {"bullet": 10}},
        "equipmentSlots": ["outerclothing"],
    }
    result = classify_item(item, EMPTY_POLICY)
    assert result["categoryId"] == "armor"


def test_classify_item_melee_via_dedicated_melee_weapon():
    item = {"id": "RMCKnifeCombat", "componentTypes": ["MeleeWeapon"], "tags": []}
    result = classify_item(item, EMPTY_POLICY)
    assert result["categoryId"] == "weapon"


def test_classify_item_medicine_via_pill_component():
    item = {"id": "CMPillTramadol", "componentTypes": ["Pill"], "tags": []}
    result = classify_item(item, EMPTY_POLICY)
    assert result["categoryId"] == "medicine"


def test_classify_item_fallback_other_when_nothing_matches():
    item = {"id": "MysteryItem", "componentTypes": [], "tags": []}
    result = classify_item(item, EMPTY_POLICY)
    assert result["categoryId"] == "other"
    assert result["reason"] == "no stronger universal functional rule matched"


def test_classify_item_packaging_box_defaults_to_other():
    item = {
        "id": "RMCBoxSupplies",
        "name": "ящик снабжения",
        "componentTypes": ["Storage"],
        "tags": [],
    }
    result = classify_item(item, EMPTY_POLICY)
    assert result["categoryId"] == "other"
    assert "container" in result["signals"][0]


def test_classify_shipping_ammo_crate_as_other_but_portable_box_as_ammo():
    crate = {
        "id": "RMCCrateGrenadesFrag",
        "name": "wooden ammunition crate",
        "componentTypes": ["CrateOpenable"],
        "tags": [],
    }
    box = {
        "id": "RMCBoxMagazineRifle",
        "name": "magazine box",
        "componentTypes": ["Item", "Storage"],
        "tags": [],
    }
    assert classify_item(crate, EMPTY_POLICY)["categoryId"] == "other"
    assert classify_item(box, EMPTY_POLICY)["categoryId"] == "ammunition"


def test_classify_armored_helmet_before_incidental_grenade_signal():
    item = {
        "id": "RMCHelmetGrenadeProtection",
        "componentTypes": ["Clothing"],
        "equipmentSlots": ["head"],
        "properties": {"CMArmor": {"bullet": 10}},
        "tags": [],
    }
    assert classify_item(item, EMPTY_POLICY)["categoryId"] == "armor"


def test_classify_runtime_projectile_as_hidden():
    item = {
        "id": "RMCBulletInternal",
        "componentTypes": ["Projectile"],
        "tags": [],
    }
    assert classify_item(item, EMPTY_POLICY)["categoryId"] == "hidden"


def test_classify_real_item_without_sprite_as_hidden():
    item = {
        "id": "RMCBrokenInternalItem",
        "origin": "RMCBrokenInternalItem",
        "sourceFile": "/Entities/Internal/broken.yml",
        "componentTypes": ["Item"],
        "tags": [],
    }
    assert classify_item(item, EMPTY_POLICY)["categoryId"] == "hidden"


def test_classify_wearable_grenade_belt_as_equipment_before_ammunition():
    item = {
        "id": "RMCBeltGrenade",
        "componentTypes": ["Clothing", "Storage"],
        "equipmentSlots": ["belt"],
        "tags": [],
    }
    assert classify_item(item, EMPTY_POLICY)["categoryId"] == "equipment"


def test_classify_sentry_with_gun_as_deployable_gear():
    item = {
        "id": "RMCSentry",
        "componentTypes": ["Item", "Gun", "Sentry", "Turret"],
        "tags": [],
    }
    assert classify_item(item, EMPTY_POLICY)["categoryId"] == "gear"


def test_classify_magazine_with_suit_storage_slot_as_ammunition():
    item = {
        "id": "CMMagazineRifleM54C",
        "componentTypes": ["Item", "Clothing", "BallisticAmmoProvider"],
        "equipmentSlots": ["suitStorage"],
        "tags": [],
    }
    assert classify_item(item, EMPTY_POLICY)["categoryId"] == "ammunition"


def test_classify_nailgun_as_weapon_despite_back_slot():
    item = {
        "id": "RMCNailgunTactical",
        "componentTypes": ["Item", "Nailgun", "MagazineAmmoProvider", "Clothing"],
        "equipmentSlots": ["back", "suitStorage"],
        "tags": [],
    }
    assert classify_item(item, EMPTY_POLICY)["categoryId"] == "weapon"


def test_classify_handheld_radio_as_other():
    item = {
        "id": "RadioHandheld",
        "componentTypes": ["Item", "RadioMicrophone"],
        "tags": [],
    }
    assert classify_item(item, EMPTY_POLICY)["categoryId"] == "other"


def test_classify_belt_compatible_tool_as_gear_not_equipment():
    item = {
        "id": "CMCrowbar",
        "componentTypes": ["Item", "Clothing", "Tool", "MeleeWeapon"],
        "equipmentSlots": ["Belt", "Suitstorage"],
        "tags": [],
    }
    assert classify_item(item, EMPTY_POLICY)["categoryId"] == "gear"


def test_classify_back_compatible_ammo_box_as_ammunition():
    item = {
        "id": "RMCBoxBulletsRifle",
        "componentTypes": ["Item", "Clothing", "BulletBox"],
        "equipmentSlots": ["Back"],
        "tags": [],
    }
    assert classify_item(item, EMPTY_POLICY)["categoryId"] == "ammunition"


def test_classify_stethoscope_as_medicine_not_uniform_accessory():
    item = {
        "id": "RMCStethoscope",
        "componentTypes": ["Item", "RMCStethoscope", "UniformAccessory"],
        "tags": [],
    }
    assert classify_item(item, EMPTY_POLICY)["categoryId"] == "medicine"


def test_has_meaningful_armor_true_for_nonzero_stat():
    assert has_meaningful_armor({"CMArmor": {"bullet": 10}}) is True


def test_has_meaningful_armor_false_for_empty_marker():
    assert has_meaningful_armor({"Armor": {}}) is False


def test_is_ammunition_container_by_tag():
    assert is_ammunition_container("SomeBox", set(), {"RMCAmmoBox"}) is True


def test_is_ammunition_container_by_prefix():
    assert is_ammunition_container("RMCBoxMagazinePistol", set(), set()) is True


def test_is_ammunition_container_false_for_unrelated_item():
    assert is_ammunition_container("RandomItem", set(), set()) is False


def test_is_dedicated_melee_weapon_requires_melee_component():
    assert is_dedicated_melee_weapon("RMCKnife", set(), set()) is False


def test_is_dedicated_melee_weapon_matches_keyword():
    assert is_dedicated_melee_weapon("RMCKnifeCombat", {"MeleeWeapon"}, set()) is True


def test_source_category_hint_direct_match():
    assert source_category_hint("Armor") == "armor"


def test_source_category_hint_fragment_match():
    assert source_category_hint("Restricted Firearm Ammunition") == "magazine-or-ammo-container"


def test_source_category_hint_no_match_returns_none():
    assert source_category_hint("Not A Real Section") is None


def test_infer_types_detects_weapon():
    assert "weapon" in infer_types("RMCWeaponM13", {"Gun": {}}, set())


def test_infer_types_falls_back_to_misc():
    assert infer_types("Unknown", {}, set()) == ["misc"]
