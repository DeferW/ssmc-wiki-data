import pytest

from scripts.common.items.classification import classify_item


@pytest.mark.parametrize(
    "components,tags,slots,expected",
    [
        (["Item", "Clothing", "Food"], [], ["head"], "clothing"),
        (["Item", "Clothing", "Storage", "Flare"], [], ["belt"], "equipment"),
        (["Item", "Material", "Stack"], ["Metal"], [], "materials"),
        (["Item", "Material", "Stack"], ["Glass"], [], "materials"),
        (["Item", "Food"], [], [], "food"),
        (["Item", "Drink", "SolutionContainerManager"], [], [], "food"),
        (["Item", "Food", "DrainableSolution"], ["Soap"], [], "household"),
        (["Item", "Storage", "StorageFill"], ["CigaretteCase"], [], "household"),
        (["Item", "Tool", "MeleeWeapon"], ["BotanyShovel"], [], "tools"),
        (["Item", "Welder", "Tool"], [], [], "gear"),
        (["Item", "Tool", "MeleeWeapon"], [], [], "gear"),
        (["Item", "PowerCell", "Battery"], [], [], "electronics"),
        (["Item", "Headset", "Clothing"], [], ["ears"], "electronics"),
        (["Item", "Geiger"], [], [], "electronics"),
        (["Item", "HandheldLight"], [], [], "electronics"),
        (["Item", "Storage", "CrateOpenable"], [], [], "containers"),
        (["Item", "Syringe", "SolutionContainerManager"], [], [], "medicine"),
        (["Item", "Gun", "Attachable"], [], [], "attachment"),
        (["Item", "Gun", "Sentry"], [], [], "gear"),
        (["Item", "WeaponMount", "Foldable", "Strap"], [], [], "gear"),
        (["Item", "Flare", "MortarShell"], [], [], "ammunition"),
    ],
)
def test_new_prototypes_are_categorized_by_mechanics(components, tags, slots, expected):
    item = {
        "id": "NeverSeenBefore",
        "componentTypes": components,
        "tags": tags,
        "equipmentSlots": slots,
    }
    assert classify_item(item, {})["categoryId"] == expected


@pytest.mark.parametrize("suffix", ["Empty", "Filled", "Loaded", "Пустой", "AP"])
def test_load_state_and_vendor_absence_do_not_hide_real_items(suffix):
    item = {
        "id": "NewDeviceEmpty",
        "suffix": suffix,
        "availability": [],
        "componentTypes": ["Item", "Defibrillator"],
    }
    assert classify_item(item, {})["categoryId"] == "medicine"


def test_armor_wins_over_clothing_but_empty_marker_does_not():
    item = {
        "id": "NewHelmet",
        "componentTypes": ["Item", "Clothing", "CMArmor"],
        "equipmentSlots": ["head"],
        "properties": {"CMArmor": {"bullet": 0}},
    }
    assert classify_item(item, {})["categoryId"] == "clothing"
    item["properties"]["CMArmor"]["bullet"] = 10
    assert classify_item(item, {})["categoryId"] == "armor"


def test_stack_recipe_distinguishes_sandbags_from_raw_materials():
    item = {
        "id": "NewFortification",
        "componentTypes": ["Item", "Stack", "Construction"],
        "properties": {"Construction": {"graph": "Sandbag", "node": "bag"}},
    }
    assert classify_item(item, {})["categoryId"] == "gear"


def test_real_projectiles_remain_hidden():
    assert (
        classify_item({"id": "NewBullet", "componentTypes": ["Projectile"]}, {})["categoryId"]
        == "hidden"
    )


def test_spillable_drink_is_not_a_pill_or_medical_supply():
    item = {
        "id": "NewDrink",
        "componentTypes": ["Item", "Drink", "Spillable", "SolutionContainerManager"],
    }
    assert classify_item(item, {})["categoryId"] == "food"


def test_disabled_surgery_capability_does_not_make_a_device_medical():
    item = {"id": "NewRadio", "componentTypes": ["Item", "RadioMicrophone", "CMSurgeryToolBlocked"]}
    assert classify_item(item, {})["categoryId"] == "electronics"


def test_riggable_battery_is_not_explosive_ammunition():
    item = {"id": "NewBattery", "componentTypes": ["Item", "PowerCell", "Battery", "Explosive"]}
    assert classify_item(item, {})["categoryId"] == "electronics"


def test_empty_medical_vessel_is_a_container_but_filled_bottle_is_medicine():
    item = {
        "id": "NewVessel",
        "sourceFile": "Resources/Prototypes/Entities/Objects/Medical/bottle.yml",
        "componentTypes": ["Item", "Drink", "SolutionContainerManager"],
        "properties": {"SolutionContainerManager": {"solutions": {"bottle": {"reagents": []}}}},
    }
    assert classify_item(item, {})["categoryId"] == "containers"
    item["properties"]["SolutionContainerManager"]["solutions"]["bottle"]["reagents"] = [
        {"ReagentId": "NewMedicine", "Quantity": 10}
    ]
    assert classify_item(item, {})["categoryId"] == "medicine"


def test_stunbaton_is_a_weapon_despite_having_a_battery():
    item = {"id": "NewBaton", "componentTypes": ["Item", "Battery", "Stunbaton", "MeleeWeapon"]}
    assert classify_item(item, {})["categoryId"] == "weapon"


def test_surgical_utensil_with_trash_tag_is_still_medical():
    item = {
        "id": "NewSurgicalItem",
        "componentTypes": ["Item", "CMSurgeryTool", "Utensil"],
        "tags": ["Trash"],
    }
    assert classify_item(item, {})["categoryId"] == "medicine"


def test_shipping_container_and_wearable_storage_do_not_depend_on_id():
    assert (
        classify_item({"id": "FutureCase", "componentTypes": ["Item", "Storage"]}, {})["categoryId"]
        == "containers"
    )


def test_public_roots_and_map_roots_share_content_aware_categories():
    from scripts.catalog.catalog import build_public_catalog

    items = {
        "NewCase": {"id": "NewCase", "name": "Case", "componentTypes": ["Item", "Storage"]},
        "NewMedicine": {
            "id": "NewMedicine",
            "name": "Medicine",
            "componentTypes": ["Item", "Syringe"],
        },
    }
    relations = [{"from": "NewCase", "to": "NewMedicine", "type": "contains"}]
    for trade_entries, map_roots in [([{"itemId": "NewCase"}], set()), ([], {"NewCase"})]:
        result = build_public_catalog(trade_entries, items, relations, {}, map_roots)
        assert result["categories"]["Медицина"] == ["NewCase", "NewMedicine"]
        assert items["NewCase"]["classification"]["signals"] == ["contents:medicine"]


def test_content_classification_terminates_on_container_cycles():
    from scripts.catalog.catalog import build_public_catalog

    items = {
        name: {"id": name, "name": name, "componentTypes": ["Item", "Storage"]}
        for name in ["Alpha", "Beta"]
    }
    relations = [
        {"from": a, "to": b, "type": "contains"} for a, b in [("Alpha", "Beta"), ("Beta", "Alpha")]
    ]
    result = build_public_catalog([{"itemId": "Alpha"}], items, relations, {})
    assert result["categories"]["Контейнеры"] == ["Alpha", "Beta"]


@pytest.mark.parametrize(
    "components,tags,slots,path,expected",
    [
        (["Item", "Storage", "CrateOpenable", "PaperLabel"], [], [], "", "containers"),
        (
            ["Item", "Clothing", "MeleeWeapon", "Sharp", "Tool", "Utensil"],
            ["Knife"],
            ["mask", "pocket"],
            "",
            "weapon",
        ),
        (["Item", "MeleeWeapon", "Sharp", "Utensil"], ["KitchenKnife"], [], "", "household"),
        (["Item", "Drink", "Spray"], [], [], "", "tools"),
        (["Item", "Drink"], ["Bucket"], [], "", "tools"),
        (
            ["Item", "Drink", "SolutionContainerManager"],
            [],
            [],
            "Resources/Prototypes/Entities/Objects/Weapons/Throwable/chem_grenades.yml",
            "containers",
        ),
        (["Item", "Clothing", "Food", "FlashImmunity"], [], ["head"], "", "clothing"),
        (["Item", "Clothing", "Food", "HandheldLight"], [], ["head"], "", "clothing"),
        (["Item", "Drink", "Clothing"], ["Trash"], ["head"], "", "food"),
        (["Item", "RMCNightVisionVisible"], [], [], "", "other"),
    ],
)
def test_incidental_capabilities_do_not_replace_primary_purpose(
    components, tags, slots, path, expected
):
    item = {
        "id": "FuturePrototype",
        "componentTypes": components,
        "tags": tags,
        "equipmentSlots": slots,
        "sourceFile": path,
    }
    assert classify_item(item, {})["categoryId"] == expected


@pytest.mark.parametrize(
    "components,tags,path,expected",
    [
        (
            ["Item", "Clothing", "MeleeWeapon"],
            [],
            "Resources/Prototypes/Entities/Objects/Fun/toys.yml",
            "household",
        ),
        (["Item", "Clothing"], ["ToyRubberDuck"], "", "household"),
        (["Item", "Clothing", "Whistle"], [], "", "gear"),
        (
            ["Item", "Clothing", "Sharp", "MeleeWeapon", "Utensil"],
            ["Knife"],
            "Resources/Prototypes/Entities/Objects/Weapons/Melee/kitchen.yml",
            "household",
        ),
        (
            ["Item", "Sharp", "MeleeWeapon"],
            [],
            "Resources/Prototypes/Entities/Objects/Specific/Hydroponics/tools.yml",
            "tools",
        ),
    ],
)
def test_explicit_civilian_and_signalling_roles_precede_incidental_wearability(
    components, tags, path, expected
):
    item = {
        "id": "NewUtility",
        "componentTypes": components,
        "tags": tags,
        "equipmentSlots": ["head", "mask", "pocket"],
        "sourceFile": path,
    }
    assert classify_item(item, {})["categoryId"] == expected
