"""Primary roles must win over incidental engine capabilities."""

import pytest

from scripts.common.items.classification import classify_item


@pytest.mark.parametrize(
    "source,expected",
    [
        ("stock_parts", "electronics"),
        ("laptop", "electronics"),
        ("bedsheets", "household"),
        ("magazine", "household"),
        ("flight_recorder", "electronics"),
        ("mining_prop_tools", "tools"),
        ("surveying_device", "electronics"),
        ("prop_trash", "household"),
    ],
)
def test_props_use_source_semantics_after_mechanics(source, expected):
    item = {
        "id": "NewProp",
        "componentTypes": ["Item"],
        "sourceFile": f"Resources/Prototypes/New/Entities/Objects/Misc/{source}.yml",
    }
    assert classify_item(item, {})["categoryId"] == expected


def test_vendor_bundles_are_runtime_wrappers_not_portable_items():
    assert (
        classify_item({"id": "NewBundle", "componentTypes": ["Sprite", "CMVendorBundle"]}, {})[
            "categoryId"
        ]
        == "hidden"
    )


def test_back_worn_fuel_tank_is_field_gear_not_clothing():
    item = {
        "id": "NewWeldingPack",
        "componentTypes": ["Item", "Clothing", "ReagentTank", "SolutionContainerManager"],
        "equipmentSlots": ["back"],
        "properties": {"ReagentTank": {"tankType": "Fuel"}},
        "sourceFile": "Resources/Prototypes/New/Entities/Clothing/Back/utility.yml",
    }
    assert classify_item(item, {})["categoryId"] == "gear"


def test_mechanical_mousetrap_is_not_electronics():
    item = {
        "id": "NewTrap",
        "componentTypes": ["Item", "Mousetrap", "StepTrigger"],
        "sourceFile": "Resources/Prototypes/Entities/Objects/Devices/trap.yml",
    }
    assert classify_item(item, {})["categoryId"] == "tools"


@pytest.mark.parametrize(
    "components,tags,slots,path,expected",
    [
        (["Item", "RMCTelephone", "BlockEntityStorage"], [], [], "", "electronics"),
        (["Item", "UniversalRecorder", "ItemSlots"], [], [], "", "electronics"),
        (["Item", "UniversalRecorderTape"], [], [], "", "electronics"),
        (["Item", "IdCard", "StationRecordKeyStorage"], [], ["idcard"], "", "equipment"),
        (["Item", "GasTank", "Explosive", "Clothing"], ["GasTank"], ["belt"], "", "gear"),
        (["Item", "Cash", "Material", "Stack"], [], [], "", "household"),
        (
            ["Item", "Clothing", "WebbingClothing", "StorageStoreSkillRequired", "Food"],
            [],
            ["innerclothing"],
            "",
            "clothing",
        ),
        (
            ["Item", "Clothing", "Storage", "UniformAccessoryHolder"],
            [],
            ["outerClothing"],
            "",
            "clothing",
        ),
        (
            ["Item", "Clothing", "Storage", "FixedItemSizeStorage"],
            [],
            ["outerClothing"],
            "",
            "equipment",
        ),
        (["Item", "Clothing", "Storage"], ["TrashBag"], ["belt"], "", "tools"),
        (["Item", "Clothing", "Storage"], ["Book"], ["belt"], "", "household"),
        (["Item", "Clothing", "Storage"], ["Folder"], ["belt"], "", "household"),
        (["Item", "Clothing"], [], ["ears"], "", "clothing"),
        (["Item", "Headset", "Clothing"], [], ["ears"], "", "electronics"),
        (["Item", "DeployFoldable", "Strap"], ["CMRollerBed"], ["back"], "", "medicine"),
        (["Item", "DeployFoldable"], ["BodyBag"], [], "", "medicine"),
        (["Item", "GrantParaDroppable", "Clothing"], [], ["back"], "", "gear"),
        (["Item", "SpawnAfterInteract", "Stack"], ["RMCInflatableBarrier"], [], "", "gear"),
        (["Item", "HandLabeler"], [], [], "", "household"),
        (["Item", "RMCPortableCrewMonitor"], [], ["belt"], "", "electronics"),
        (["Item", "Pinpointer"], [], [], "", "electronics"),
        (["Item", "StorageStoreSkillRequired"], [], [], "", "other"),
        (["Item", "BlockEntityStorage"], [], [], "", "other"),
        (["Item", "MaterialStorageMagnetPickup"], [], [], "", "other"),
        (["Item", "Storage"], [], [], "", "containers"),
        (["Item", "Stack"], ["CableCoil"], [], "", "materials"),
        (
            ["Item", "MeleeWeapon", "Wieldable"],
            [],
            [],
            "Resources/Prototypes/New/Entities/Objects/Weapons/Melee/bat.yml",
            "weapon",
        ),
        (
            ["Item", "Blocking"],
            [],
            [],
            "Resources/Prototypes/New/Entities/Objects/Shields/shield.yml",
            "armor",
        ),
        (
            ["Item"],
            [],
            [],
            "Resources/Prototypes/New/Entities/Objects/Devices/player.yml",
            "electronics",
        ),
        (
            ["Item"],
            [],
            [],
            "Resources/Prototypes/New/Entities/Objects/Materials/parts.yml",
            "materials",
        ),
        (
            ["Item"],
            [],
            [],
            "Resources/Prototypes/New/Entities/Structures/Furniture/chairs.yml",
            "household",
        ),
        (
            ["Item", "SolutionContainerManager"],
            [],
            [],
            "Resources/Prototypes/New/Entities/Objects/Specific/Janitorial/rag.yml",
            "tools",
        ),
    ],
)
def test_primary_role(components, tags, slots, path, expected):
    item = {
        "id": "FuturePrototype",
        "componentTypes": components,
        "tags": tags,
        "equipmentSlots": slots,
        "sourceFile": path,
    }
    assert classify_item(item, {})["categoryId"] == expected
