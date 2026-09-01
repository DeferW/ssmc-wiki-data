from __future__ import annotations

import re
from typing import Any, Iterable

from .core import (
    PUBLIC_CATEGORY_LABELS,
    SOURCE_CATEGORY_HINTS,
    WEARABLE_EQUIPMENT_SLOTS,
    WEARABLE_STORAGE_SLOTS,
)


def has_meaningful_armor(components: dict[str, Any]) -> bool:
    """Ignore the empty Armor marker inherited by backpacks and satchels."""
    cm_armor = components.get("CMArmor")
    if isinstance(cm_armor, dict) and any(
        isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0
        for key, value in cm_armor.items()
        if key
        in {
            "xenoArmor",
            "frontalArmor",
            "sideArmor",
            "melee",
            "bullet",
            "bio",
            "explosionArmor",
        }
    ):
        return True
    if isinstance(cm_armor, dict) and cm_armor.get("immuneToAP") is True:
        return True
    if any(
        component_type in components
        for component_type in ("CMHardArmor", "RMCBulkyArmor", "SquadArmor")
    ):
        return True
    armor = components.get("Armor")
    if not isinstance(armor, dict):
        return False
    modifiers = armor.get("modifiers")
    if isinstance(modifiers, dict) and modifiers:
        return True
    modifier_sets = armor.get("modifierSets")
    return isinstance(modifier_sets, list) and bool(modifier_sets)


def equipment_slots(components: dict[str, Any]) -> set[str]:
    clothing = components.get("Clothing")
    if not isinstance(clothing, dict):
        return set()
    slots = clothing.get("slots")
    if isinstance(slots, str):
        return {slots}
    if isinstance(slots, list):
        return {str(slot) for slot in slots if isinstance(slot, str)}
    return set()


def is_ammunition_container(
    prototype_id: str,
    component_types: set[str],
    tags: set[str],
) -> bool:
    if "RMCAmmoBox" in tags or "RMCBoxShotgunShells" in tags:
        return True
    if prototype_id.startswith((
        "RMCBoxMagazine",
        "RMCBoxBullets",
        "RMCBoxShells",
        "RMCBoxShotgun",
        "RMCBox458SOCOM",
    )):
        return True
    return "RMCFlamerTank" in component_types


def is_dedicated_melee_weapon(
    prototype_id: str,
    component_types: set[str],
    tags: set[str],
) -> bool:
    if "MeleeWeapon" not in component_types:
        return False
    melee_words = ("knife", "machete", "bayonet", "sword", "blade")
    signals = {prototype_id.casefold(), *(tag.casefold() for tag in tags)}
    return "Sharp" in component_types or any(
        word in signal for signal in signals for word in melee_words
    )


def source_category_hint(section_name: str) -> str | None:
    normalized = re.sub(r"\s+", " ", section_name.strip().casefold())
    direct = SOURCE_CATEGORY_HINTS.get(normalized)
    if direct:
        return direct
    for fragment, category in SOURCE_CATEGORY_HINTS.items():
        if fragment in normalized:
            return category
    return None


def has_any_component(component_types: set[str], fragments: tuple[str, ...]) -> bool:
    return any(
        fragment.casefold() in component_type.casefold()
        for component_type in component_types
        for fragment in fragments
    )


def infer_types(
    prototype_id: str,
    components: dict[str, Any],
    tags: set[str],
    source_hints: set[str] | None = None,
) -> list[str]:
    result: set[str] = set()
    component_types = set(components)
    source_hints = source_hints or set()
    folded_id = prototype_id.casefold()

    if (
        "Attachable" not in component_types
        and ("Gun" in component_types or "RMCFlamerAmmoProvider" in component_types)
    ):
        result.add("weapon")
    if "Attachable" in component_types:
        result.add("attachment")
    if "Projectile" in component_types:
        result.add("projectile")
    if "CartridgeAmmo" in component_types:
        result.add("cartridge")
    if "BallisticAmmoProvider" in component_types and "Gun" not in component_types:
        result.add("magazine-or-ammo-container")
    if is_ammunition_container(prototype_id, component_types, tags):
        result.add("magazine-or-ammo-container")
    if "Storage" in component_types or "CMItemSlots" in component_types:
        result.add("container")
    if has_meaningful_armor(components):
        result.add("armor")
    if "Explosive" in component_types or any("Grenade" in tag for tag in tags):
        result.add("explosive")
    if is_dedicated_melee_weapon(prototype_id, component_types, tags):
        result.add("melee")
    if "Tool" in component_types or any(
        component_type.endswith("Tool") for component_type in component_types
    ):
        result.add("tool")
    if "Clothing" in component_types or has_any_component(
        component_types, ("uniformaccessory", "helmetaccessory")
    ):
        result.add("clothing")
    if has_any_component(
        component_types,
        ("healing", "healthanalyzer", "surgery", "defibrillator", "hypospray"),
    ):
        result.add("medical")
    if (
        has_any_component(
            component_types,
            ("pill", "injector", "hypospray", "syringe", "injectablesolution"),
        )
        or any(
            word in folded_id
            for word in ("pill", "tablet", "autoinjector", "syringe")
        )
    ):
        result.add("medicine")
    if has_any_component(component_types, ("edible",)):
        result.add("food")
    if has_any_component(
        component_types,
        (
            "radio",
            "headset",
            "binocular",
            "motiondetector",
            "camera",
            "computer",
            "encryption",
            "visor",
        ),
    ):
        result.add("electronics")
    if "Flash" in component_types:
        result.add("electronics")
    if has_any_component(component_types, ("light", "flashlight", "flare")):
        result.add("lighting")
    if "Stack" in component_types or any(
        word in folded_id for word in ("sheet", "plank", "sandbag", "plastic", "phoron")
    ):
        result.add("material")
    if any(word in folded_id for word in ("pamphlet", "manual", "guidebook")):
        result.add("training")
    if has_any_component(component_types, ("crayon", "stamp")) or any(
        word in folded_id for word in ("crayon", "stamp")
    ):
        result.add("office")
    if has_any_component(component_types, ("mop", "broom", "janitor")) or any(
        word in folded_id
        for word in ("cleaner", "wetsign", "mop", "broom", "janitor")
    ):
        result.add("janitorial")
    if has_any_component(component_types, ("cprdummy", "healthscannable")):
        result.add("medical")
    if has_any_component(
        component_types,
        ("welder", "construction", "powercell", "generator", "barricade"),
    ):
        result.add("engineering")
    if "WeaponMount" in component_types or has_any_component(
        component_types, ("sentry", "mortar")
    ):
        result.add("weapon-support")
    if (
        "vehicle-ammunition" in source_hints
        and (
            "magazine-or-ammo-container" in result
            or "cartridge" in result
            or "explosive" in result
        )
    ):
        result.add("vehicle-ammunition")
    if not result:
        result.update(source_hints)
    if not result:
        result.add("misc")
    return sorted(result)


def classification_result(
    status: str,
    *,
    category_id: str | None = None,
    reason: str,
    signals: Iterable[str] = (),
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "confidence": "high" if status == "public" else "none",
        "reason": reason,
        "signals": sorted(set(signals)),
    }
    if category_id is not None:
        result["categoryId"] = category_id
        result["category"] = PUBLIC_CATEGORY_LABELS[category_id]
    return result


def is_packaging_container(item: dict[str, Any]) -> bool:
    """Return true for an actual box/crate/case, not every storage item."""
    item_id = str(item.get("id", "")).casefold()
    name = str(item.get("name", "")).casefold()
    component_types = set(item.get("componentTypes", []))
    has_container_mechanics = bool(
        component_types.intersection(
            {
                "Storage",
                "StorageFill",
                "CMItemSlots",
                "ContainerFill",
                "CrateOpenable",
                "EntityTableContainerFill",
                "ItemSlots",
                "SpawnOnTerminate",
            }
        )
    )
    if not has_container_mechanics:
        return False
    return any(
        marker in item_id or marker in name
        for marker in ("box", "crate", "case", "короб", "ящик", "кейс")
    )


def is_shipping_crate(item: dict[str, Any]) -> bool:
    """Distinguish map/cargo crates from portable ammunition boxes."""
    if not is_packaging_container(item):
        return False
    item_id = str(item.get("id", "")).casefold()
    source_file = str(item.get("sourceFile", "")).replace("\\", "/").casefold()
    component_types = set(item.get("componentTypes", []))
    return (
        "Item" not in component_types
        or item_id.startswith("rmccrate")
        or "/structures/storage/securecrates" in source_file
        or "/structures/storage/crates" in source_file
    )


def is_ammunition_or_magazine_box(item: dict[str, Any]) -> bool:
    """Recognize portable ammunition boxes, never full-sized cargo crates."""
    if is_shipping_crate(item):
        return False
    item_id = str(item.get("id", "")).casefold()
    name = str(item.get("name", "")).casefold()
    source_file = str(item.get("sourceFile", "")).casefold()
    signal = f"{item_id} {name} {source_file}"
    return any(
        marker in signal
        for marker in (
            "boxmagazine",
            "boxbullets",
            "boxshells",
            "boxshotgun",
            "packetgrenade",
            "boxclaymore",
            "boxccdp",
            "boxhedp",
            "boxhefa",
            "boxagmf",
            "boxagmi",
            "box458socom",
            "ammunition box",
            "ammo box",
            "magazine box",
            "коробка магазинов",
            "коробка патрон",
            "коробка дроб",
            "коробка боеприпасов",
            "коробка гранат",
        )
    )


def is_utility_supply_box(item: dict[str, Any]) -> bool:
    item_id = str(item.get("id", "")).casefold()
    return any(marker in item_id for marker in ("boxmre", "boxpackflare", "boxflashlights"))


def is_technical_hidden_item(item: dict[str, Any]) -> bool:
    """Hide runtime helpers and non-player-facing variants using stable signals."""
    item_id = str(item.get("id", ""))
    folded_id = item_id.casefold()
    component_types = set(item.get("componentTypes", []))
    suffix = str(item.get("suffix", "")).strip().casefold()
    availability = item.get("availability")
    has_availability = isinstance(availability, list) and bool(availability)

    # Real catalog cards carry origin/sourceFile. A drawable Item without any
    # sprite summary is a broken/internal prototype, not a useful public card.
    if (
        (item.get("origin") or item.get("sourceFile"))
        and "Item" in component_types
        and not isinstance(item.get("sprite"), dict)
    ):
        return True
    if "CMVendorMapToSquad" in component_types:
        return True
    if "Item" not in component_types and component_types.intersection(
        {"Projectile", "RMCArmorVariant"}
    ):
        return True
    if folded_id.endswith("empty") or folded_id.startswith("stcartridgesharp"):
        return True
    if {
        "WeaponMount",
        "Foldable",
        "Strap",
    }.issubset(component_types):
        return True
    if (
        "Gun" in component_types
        and not has_availability
        and suffix in {"ap", "unmc", "марксманский", "marksman", "пустой", "empty"}
    ):
        return True
    return False


def is_miscellaneous_item(item: dict[str, Any]) -> bool:
    """Recognize ordinary supplies that should not be promoted to field gear."""
    item_id = str(item.get("id", "")).casefold()
    component_types = set(item.get("componentTypes", []))
    tags = {str(tag).casefold() for tag in item.get("tags", [])}
    if component_types.intersection({"GasTank", "MachineBoard", "PDTLocator"}):
        return True
    if tags.intersection({"gastank", "trash", "trashbag", "cigarette"}):
        return True
    return any(
        marker in item_id
        for marker in (
            "bucket",
            "mop",
            "wetsign",
            "spraybottle",
            "spacecleaner",
            "lightbulb",
            "lighttube",
            "cigarette",
            "trashbag",
            "inflatabledoor",
            "inflatablewall",
            "handcuff",
            "ziptie",
            "bedroll",
            "helmetgarbgunoil",
            "overwatchcameratripod",
            "radiohandheld",
            "pdtlocator",
            "machinecircuitboard",
            "circuitboard",
        )
    )


def classify_item(
    item: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Assign exactly one wiki category from reusable mechanical signals."""
    item_id = str(item.get("id", ""))
    component_types = set(item.get("componentTypes", []))
    tags = set(item.get("tags", []))
    source_file = str(item.get("sourceFile", ""))
    folded_id = item_id.casefold()
    folded_path = source_file.casefold()
    folded_tags = {tag.casefold() for tag in tags}

    excluded_ids = set(policy.get("excludePrototypeIds", []))
    if item_id in excluded_ids:
        return classification_result(
            "excluded",
            reason="prototype explicitly excluded by classification policy",
            signals=("config:excludePrototypeIds",),
        )
    def public(category_id: str, reason: str, *signals: str) -> dict[str, Any]:
        return classification_result(
            "public",
            category_id=category_id,
            reason=reason,
            signals=signals,
        )

    properties = item.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}
    slots = {str(slot).casefold() for slot in item.get("equipmentSlots", [])}
    # A weapon is identified by the mechanic that actually launches a shot,
    # not by its name or wearable storage slots. Nailguns use their own firing
    # component instead of Gun.
    has_gun = (
        "Gun" in component_types
        or "RMCFlamerAmmoProvider" in component_types
        or "Nailgun" in component_types
    )
    has_ammo = (
        "Projectile" in component_types
        or "ProjectileGrenade" in component_types
        or "CartridgeAmmo" in component_types
        or (
            "BallisticAmmoProvider" in component_types
            and "Gun" not in component_types
        )
        or is_ammunition_container(item_id, component_types, tags)
        or "MortarShell" in component_types
        or "RMCPacketGrenade" in tags
    )
    has_explosive = (
        ("Explosive" in component_types and "gastank" not in folded_tags)
        or "ExplodeOnTrigger" in component_types
        or "ProjectileGrenade" in component_types
        or "grenade" in folded_id
        or "grenade" in folded_tags
        or "handgrenade" in folded_tags
    )

    cm_armor = properties.get("CMArmor")
    armor_components = {
        key: value
        for key, value in properties.items()
        if key in {"Armor", "CMArmor", "RMCArmor"}
    }
    meaningful_armor = has_meaningful_armor(armor_components) or (
        isinstance(cm_armor, dict)
        and any(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value != 0
            for value in cm_armor.values()
        )
    )

    if is_technical_hidden_item(item):
        return public(
            "hidden",
            "runtime helper, projectile or internal item variant",
            "technical:hidden",
        )

    if is_miscellaneous_item(item):
        return public(
            "other",
            "ordinary supply, consumable, replacement part or utility object",
            "item:miscellaneous",
        )

    # Full-sized cargo/map crates are structures rather than portable ammo
    # boxes. They always live in "Другое"; their contents are separate cards.
    if is_shipping_crate(item):
        return public(
            "other",
            "full-sized cargo or map crate",
            "container:shipping-crate",
        )

    # Protection wins over incidental grenade/ammunition signals. This keeps
    # helmets and armored clothing out of "Боезапас".
    if meaningful_armor and slots.intersection({"outerclothing", "head"}):
        return public(
            "armor",
            "protective outer-clothing or helmet slot",
            "component:armor",
            "slot:armor-or-head",
        )

    if is_packaging_container(item) and is_utility_supply_box(item):
        return public("gear", "portable field-supply box", "container:utility-box")

    if (
        "Mortar" in component_types
        or "Stunbaton" in component_types
        or (
            "Flash" in component_types
            and "LimitedCharges" in component_types
            and "MeleeWeapon" in component_types
        )
        or is_dedicated_melee_weapon(item_id, component_types, tags)
    ):
        return public(
            "weapon",
            "dedicated melee, incapacitation or crew-served weapon",
            "component:weapon",
        )

    # Underbarrel launchers and shotguns still belong to attachments even when
    # they also contain a Gun component. Firearms win over their Clothing slots.
    if "Attachable" in component_types:
        return public("attachment", "dedicated attachment component", "Attachable")
    if has_gun:
        return public(
            "weapon",
            "item has a dedicated projectile-launching mechanic",
            "component:projectile-launcher",
        )

    is_flare = (
        "Flare" in component_types
        or "RMCFlare" in component_types
        or "flare" in folded_id
        or bool({"flare", "rmcflare"}.intersection(folded_tags))
    )
    if (
        is_flare
        or "SkillPamphlet" in component_types
        or "Whistle" in component_types
        or "synthresetkey" in folded_id
    ):
        return public(
            "gear",
            "field utility, signalling device or training item",
            "component:field-utility",
        )

    has_storage = "Storage" in component_types
    is_wearable_storage = has_storage and bool(slots.intersection(WEARABLE_STORAGE_SLOTS))
    is_patch = (
        "patch" in folded_id
        or any("patch" in tag for tag in folded_tags)
        or has_any_component(component_types, ("uniformaccessory", "patch"))
    )

    # Stethoscopes are uniform accessories mechanically, but their primary
    # purpose is medical and must win over the wearable signal.
    if has_any_component(component_types, ("stethoscope",)):
        return public("medicine", "medical diagnostic instrument", "component:medicine")

    # Real containers worn as belts, pouches or backpacks must stay equipment
    # even when their names mention grenades or ammunition. Ordinary objects
    # merely allowed in a belt/suit-storage slot do not pass this rule.
    if (
        is_patch
        or "Webbing" in component_types
        or "HelmetAccessory" in component_types
        or is_wearable_storage
    ):
        return public(
            "equipment",
            "wearable clothing, storage or installed uniform accessory",
            "component:wearable-equipment",
        )

    if is_packaging_container(item) and is_ammunition_or_magazine_box(item):
        return public(
            "ammunition",
            "portable ammunition or magazine box",
            "container:ammunition-box",
        )

    if has_ammo or has_explosive:
        return public(
            "ammunition",
            "ammunition, grenade or explosive item",
            "component:ammunition-or-explosive",
        )
    if (
        "/objects/weapons/throwable/packets" in folded_path
        and ("Storage" in component_types or "CMItemSlots" in component_types)
    ):
        return public(
            "ammunition",
            "grenade packet or ammunition box",
            "path:throwable-packet",
        )
    medical_object_path = "/entities/objects/medical/" in folded_path
    medical_box_path = "/catalog/fills/boxes/medical" in folded_path
    medical_delivery = (
        "Pill" in component_types
        or "Hypospray" in component_types
        or "Injector" in component_types
        or "Syringe" in component_types
        or "pillcanister" in folded_id
        or "packetpills" in folded_id
        or "syringecase" in folded_id
        or "surgicalcase" in folded_id
    )
    medical_solution = medical_object_path and (
        "CMRefillableSolution" in component_types
        or folded_id.startswith("cmbottle")
    )

    medical_path_id_signal = any(
        word in folded_id
        for word in (
            "firstaid",
            "aidkit",
            "medkit",
            "surgicaltray",
            "ivdrip",
            "medicaltent",
        )
    )
    field_medical_id_signal = any(
        word in folded_id
        for word in (
            "rollerbed",
            "stretcher",
            "surgicalbed",
            "oxygentank",
            "anesthetictank",
            "surgical",
            "scalpel",
            "hemostat",
            "retractor",
            "cautery",
            "bonesaw",
            "bonesetter",
            "woundclamp",
            "bonegel",
            "synthgraft",
        )
    )
    medical_mechanics = has_any_component(
        {
            component
            for component in component_types
            if not component.casefold().endswith("blocked")
        },
        (
            "surgerytool",
            "surgery",
            "healthanalyzer",
            "defibrillator",
            "dialysis",
            "cprdummy",
            "stasisbag",
            "bodybag",
            "healthscannable",
            "healthscanner",
            "ivdrip",
            "bloodpack",
            "stethoscope",
            "healing",
        ),
    )
    medical_container = (
        medical_object_path
        and (
            medical_path_id_signal
            or "Storage" in component_types
            or "CMItemSlots" in component_types
        )
    )
    if (
        medical_delivery
        or medical_solution
        or medical_mechanics
        or medical_container
        or medical_object_path
        or medical_box_path
        or field_medical_id_signal
    ):
        return public(
            "medicine",
            "medicine, medical device, treatment kit or surgical instrument",
            "component:medicine",
        )

    if is_packaging_container(item):
        return public(
            "other",
            "box or case published as a separate catalog item",
            "container:packaging",
        )

    strong_tool = (
        "Tool" in component_types
        or any(component.endswith("Tool") for component in component_types)
        or has_any_component(
            component_types,
            (
                "welder",
                "multitool",
                "entrenchingtool",
                "nailgun",
                "lightreplacer",
            ),
        )
        or "/entities/objects/tools/" in folded_path
    )
    if strong_tool:
        return public(
            "gear",
            "dedicated hand tool or single-purpose utility item",
            "component:tool",
        )

    advanced_field_device = (
        "WeaponMount" in component_types
        or has_any_component(component_types, ("sentry", "turret", "mortar", "weaponmount"))
        or has_any_component(
            component_types,
            (
                "scope",
                "binocular",
                "rangefinder",
                "spotting",
                "motiondetector",
                "motionsensor",
                "sensor",
                "nightvision",
                "togglevisor",
                "integratedvisor",
                "cycleablevisor",
                "targetinglaser",
                "overwatchcamera",
                "overwatch",
                "handcuff",
                "restrain",
            ),
        )
    )
    if advanced_field_device:
        return public(
            "gear",
            "advanced field device, weapon support or encryption component",
            "component:gear",
        )

    # Tools, complex field technology and single-purpose utility objects share
    # one broad section. This avoids an arbitrary border between a multitool,
    # binoculars, a turret and an encryption key.
    if (
        "WeaponMount" in component_types
        or has_any_component(component_types, ("sentry", "turret", "mortar", "weaponmount"))
        or "Tool" in component_types
        or any(component.endswith("Tool") for component in component_types)
        or has_any_component(
            component_types,
            (
                "welder",
                "multitool",
                "entrenchingtool",
                "nailgun",
                "foldingbarricade",
                "powercell",
                "battery",
                "circuitboard",
                "lightreplacer",
                "lightbulb",
                "lighttube",
                "generator",
                "machineboard",
            ),
        )
        or "/entities/objects/tools/" in folded_path
        or "engineerkit" in folded_id
        or any(component.casefold().endswith("electronics") for component in component_types)
        or any(
            word in folded_id
            for word in (
                "battery",
                "powercell",
                "lightbulb",
                "lighttube",
                "circuitboard",
            )
        )
    ):
        return public(
            "gear",
            "tool, field technology, replacement part or single-purpose utility item",
            "component:gear-or-tool",
        )

    if has_any_component(
        component_types,
        (
            "handheldlight",
            "flare",
            "flash",
            "detector",
            "scanner",
        ),
    ) or any(
        word in folded_id
        for word in ("whistle", "ziptie", "bedroll")
    ):
        return public(
            "gear",
            "single-purpose field item",
            "component:gear",
        )

    # Clothing is intentionally late: the game also gives this component to
    # tools, lights, ammo boxes and other objects merely compatible with a
    # wearable slot. Their actual mechanics were classified above.
    is_standard_wearable = (
        "Clothing" in component_types
        and bool(slots.intersection(WEARABLE_EQUIPMENT_SLOTS))
    )
    if is_standard_wearable:
        return public(
            "equipment",
            "clothing assigned to a real wearable equipment slot",
            "component:wearable-equipment",
        )

    return public(
        "other",
        "no stronger universal functional rule matched",
        "fallback:other",
    )

