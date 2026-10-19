from __future__ import annotations

import re
from typing import Any, Iterable

from .categories import (
    PUBLIC_CATEGORY_LABELS,
    SOURCE_CATEGORY_HINTS,
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
    if prototype_id.startswith(
        (
            "RMCBoxMagazine",
            "RMCBoxBullets",
            "RMCBoxShells",
            "RMCBoxShotgun",
            "RMCBox458SOCOM",
        )
    ):
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

    if "Attachable" not in component_types and (
        "Gun" in component_types or "RMCFlamerAmmoProvider" in component_types
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
    if has_any_component(
        component_types,
        ("pill", "injector", "hypospray", "syringe", "injectablesolution"),
    ) or any(word in folded_id for word in ("pill", "tablet", "autoinjector", "syringe")):
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
        word in folded_id for word in ("cleaner", "wetsign", "mop", "broom", "janitor")
    ):
        result.add("janitorial")
    if has_any_component(component_types, ("cprdummy", "healthscannable")):
        result.add("medical")
    if has_any_component(
        component_types,
        ("welder", "construction", "powercell", "generator", "barricade"),
    ):
        result.add("engineering")
    if "WeaponMount" in component_types or has_any_component(component_types, ("sentry", "mortar")):
        result.add("weapon-support")
    if "vehicle-ammunition" in source_hints and (
        "magazine-or-ammo-container" in result or "cartridge" in result or "explosive" in result
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


def is_technical_hidden_item(item: dict[str, Any], *, placed_on_map: bool = False) -> bool:
    """Only runtime helpers are hidden; load state and vendor availability are not roles."""
    components = set(item.get("componentTypes", []))
    return "CMVendorMapToSquad" in components or (
        "Item" not in components
        and bool(components.intersection({"Projectile", "RMCArmorVariant", "CMVendorBundle"}))
    )


def classify_item(
    item: dict[str, Any],
    policy: dict[str, Any],
    *,
    placed_on_map: bool = False,
) -> dict[str, Any]:
    """Classify primary purpose before incidental storage, clothing or combat mechanics.

    Component data is retained privately by build_card until classification finishes.
    State-variant visibility is resolved separately using inheritance and mechanics.
    """
    item_id = str(item.get("id", ""))
    components = set(item.get("componentTypes", []))
    tags = {str(tag).casefold() for tag in item.get("tags", [])}
    path = str(item.get("sourceFile", "")).replace("\\", "/").casefold()
    properties = item.get("_classificationComponents", item.get("properties", {}))
    if not isinstance(properties, dict):
        properties = {}
    slots = {str(slot).casefold() for slot in item.get("equipmentSlots", [])}
    contents = set(item.get("_contentCategories", []))

    def result(category: str, reason: str, *signals: str) -> dict[str, Any]:
        return classification_result("public", category_id=category, reason=reason, signals=signals)

    def has(*fragments: str) -> bool:
        return has_any_component(
            {
                component
                for component in components
                if not component.casefold().endswith(("blocked", "visible"))
            },
            fragments,
        )

    if item_id in set(policy.get("excludePrototypeIds", [])):
        return classification_result(
            "excluded",
            reason="prototype explicitly excluded by classification policy",
            signals=("config:excludePrototypeIds",),
        )
    if reason := item.get("_variantHiddenReason"):
        return result("hidden", str(reason), "variant:duplicate")
    if is_technical_hidden_item(item, placed_on_map=placed_on_map):
        return result(
            "hidden", "runtime helper without a portable item role", "technical:runtime-helper"
        )
    if "Attachable" in components:
        return result("attachment", "dedicated weapon attachment", "component:Attachable")

    armor = {
        key: value
        for key, value in properties.items()
        if key in {"Armor", "CMArmor", "RMCArmor", "CMHardArmor", "RMCBulkyArmor", "SquadArmor"}
    }
    if has_meaningful_armor(armor) and slots.intersection({"head", "outerclothing"}):
        return result("armor", "protective helmet or outer clothing", "role:protection")

    if any(
        part in path for part in ("/smokeables/", "/fun/", "/toys/", "/melee/kitchen")
    ) or tags.intersection({"cigarettecase", "toyrubberduck"}):
        return result("household", "smoking supplies and personal cases", "role:personal-supply")
    if "/tools/lighters" in path:
        return result(
            "household", "personal lighter with incidental welding mechanic", "source:lighter"
        )

    # These roles are stronger than incidental storage or a belt attachment slot.
    if "IdCard" in components:
        return result("equipment", "personal identification and access card", "component:IdCard")
    if "Cash" in components:
        return result("household", "currency, not a construction material", "component:Cash")
    if "GasTank" in components:
        return result("gear", "portable breathing or utility gas supply", "component:GasTank")
    if properties.get("ReagentTank", {}).get("tankType") == "Fuel":
        return result("gear", "portable welding or utility fuel supply", "role:fuel-supply")
    if (
        tags.intersection({"trashbag"})
        or "/specific/janitorial/" in path
        or "Mousetrap" in components
    ):
        return result("tools", "cleaning or waste collection supply", "role:maintenance-tool")
    if tags.intersection({"book", "folder", "clipboard"}) or "HandLabeler" in components:
        return result(
            "household", "reading or stationery item with incidental storage", "role:stationery"
        )

    # A wearable pouch remains equipment even if its contents are medicine, ammo or flares.
    # WebbingClothing accepts a webbing; StorageStoreSkillRequired restricts use.
    # Neither is a storage mechanism. Coats and uniforms can also have pockets.
    wearable_storage = (
        bool(slots.intersection(WEARABLE_STORAGE_SLOTS))
        and bool(components.intersection({"Storage", "CMItemSlots"}))
        and not slots.intersection({"innerclothing", "jumpsuit"})
        and not (
            "outerclothing" in slots
            and components.intersection({"UniformAccessoryHolder", "FoldableClothing"})
        )
    )
    if wearable_storage or "Webbing" in components:
        return result("equipment", "wearable storage, holster or webbing", "role:wearable-storage")

    if has("whistle"):
        return result("gear", "field signalling device", "component:Whistle")

    primary_slots = {
        "innerclothing",
        "jumpsuit",
        "head",
        "eyes",
        "gloves",
        "hands",
        "shoes",
        "feet",
        "mask",
        "mouth",
        "neck",
        "outerclothing",
    }
    gun = bool(components.intersection({"Gun", "RMCFlamerAmmoProvider", "Nailgun"}))
    utility_clothing = (
        "/objects/tools/" in path
        or "Drink" in components
        or {"MeleeWeapon", "Sharp"}.issubset(components)
    )
    if (
        not gun
        and not utility_clothing
        and (
            ("Clothing" in components and slots.intersection(primary_slots))
            or has("uniformaccessory", "helmetaccessory", "patch")
        )
    ):
        if not has("stethoscope"):
            return result("clothing", "clothing or uniform accessory", "role:clothing")

    if tags.intersection({"rmcsynthresetkey"}) or has("synthreset"):
        return result(
            "electronics", "synthetic diagnostic or reset device", "role:synthetic-device"
        )

    if tags.intersection({"cmrollerbed", "bodybag"}):
        return result(
            "medicine", "deployable patient transport or body bag", "role:patient-transport"
        )
    if "GrantParaDroppable" in components or tags.intersection({"rmcinflatablebarrier"}):
        return result("gear", "parachute or deployable field barrier", "role:field-utility")

    medical_components = {
        component for component in components if not component.casefold().endswith("blocked")
    }
    medical = "Pill" in components or has_any_component(
        medical_components,
        (
            "surgery",
            "scalpel",
            "healing",
            "defibrillator",
            "hypospray",
            "injector",
            "syringe",
            "healthanalyzer",
            "healthscanner",
            "healthscannable",
            "stethoscope",
            "dialysis",
            "bloodpack",
            "pillcanister",
            "ivdrip",
            "stasisbag",
            "bodybag",
            "cprdummy",
            "medicalupgrade",
            "rollerbed",
            "stretcher",
            "surgicalbed",
        ),
    )
    medical_source = "/objects/medical/" in path or "/fills/boxes/medical" in path
    solutions = properties.get("SolutionContainerManager", {}).get("solutions", {})
    filled_vessel = isinstance(solutions, dict) and any(
        isinstance(solution, dict) and solution.get("reagents") for solution in solutions.values()
    )
    if (
        medical_source
        and "SolutionContainerManager" in components
        and not filled_vessel
        and not medical
    ):
        return result("containers", "empty reusable solution vessel", "role:empty-vessel")
    if not gun and (
        medical or medical_source or tags.intersection({"cmfirstaidkit", "cmmedicalupgradekit"})
    ):
        return result("medicine", "treatment, diagnostic or medical supply", "role:medicine")

    if "/hydroponics/" in path and "Food" not in components:
        return result("tools", "agricultural tool or production supply", "source:hydroponics")

    # Combat blades share Utensil and Tool with tableware and repair tools.
    if (
        "MeleeWeapon" in components
        and "Sharp" in components
        and "SpaceGarbage" not in components
        and not tags.intersection({"kitchenknife", "botanyhatchet", "botanyhoe", "botanyshovel"})
    ):
        return result("weapon", "dedicated sharp melee weapon", "role:combat-blade")

    # Civilian roles override incidental melee, solution or tool components.
    household_tags = {
        "soap",
        "cigarette",
        "cigarettecase",
        "book",
        "pen",
        "write",
        "folder",
        "trashbag",
        "toyrubberduck",
        "kitchenknife",
        "utensil",
    }
    trash_item = "trash" in tags and not components.intersection({"Food", "Drink"})
    if (
        "Paper" in components
        or trash_item
        or tags.intersection(household_tags)
        or has(
            "utensil",
            "smokable",
            "lighter",
            "cigarette",
            "toy",
            "plushie",
            "stamp",
            "crayon",
            "soap",
            "smoking",
        )
    ):
        return result("household", "household, stationery or personal item", "role:household")
    if any(
        part in path for part in ("/cigarettes", "/smoking", "/toys/", "/fun/", "/paper", "/flags")
    ):
        return result("household", "household or personal item source", "source:household")

    if has(
        "sandbag",
        "barbedwire",
        "foldingbarricade",
        "sentry",
        "turret",
        "weaponmount",
        "mortar",
        "vehiclewheelitem",
    ):
        # Mortar shells are ammunition, not deployable mortars.
        if "MortarShell" not in components:
            return result(
                "gear",
                "field fortification, weapon support or vehicle repair",
                "role:field-equipment",
            )
    construction = properties.get("Construction", {})
    if isinstance(construction, dict) and any(
        word in str(construction.get("graph", "")).casefold()
        for word in ("sandbag", "barbedwire", "barricade")
    ):
        return result("gear", "field fortification construction recipe", "component:Construction")
    if "Material" in components and "Stack" in components:
        return result(
            "materials", "stackable construction material or raw resource", "role:material"
        )
    if "Stack" in components and tags.intersection({"cablecoil"}):
        return result("materials", "electrical construction cable", "tag:construction-resource")
    if has("ore", "extractable") and "Stack" in components:
        return result("materials", "raw resource stack", "role:raw-resource")

    if "/tools/janitor" in path:
        return result("tools", "cleaning and maintenance supplies", "source:maintenance")

    # Drink is also inherited by buckets, sprays and chemical beakers.
    if "Drink" in components and (has("spray", "bucket") or "bucket" in tags):
        if "Tool" in components:
            return result("gear", "field emergency fluid tool", "role:field-tool")
        return result("tools", "maintenance or agricultural fluid tool", "role:maintenance-tool")

    # Food crates and ration boxes must not inherit their engine's generic ammo-box tag.
    food_source = "/food/" in path or "/drinks/" in path
    edible = "Food" in components
    beverage = "Drink" in components and not any(
        part in path for part in ("/weapons/", "/tools/", "/hydroponics/")
    )
    if not gun and (edible or beverage or food_source):
        if not tags.intersection({"gastank"}):
            return result("food", "food, drink or ration supply", "role:food")

    if "PacifismAllowedGun" in components:
        return result(
            "tools", "utility device with incidental firing mechanic", "role:utility-tool"
        )
    if gun:
        return result("weapon", "dedicated projectile-launching mechanic", "role:firearm")
    if "Stunbaton" in components:
        return result("weapon", "dedicated incapacitation weapon", "component:Stunbaton")
    if has("powercell") or "Battery" in components and tags.intersection({"powercell"}):
        return result(
            "electronics", "electrical power supply, including riggable cells", "role:power-supply"
        )
    if is_shipping_crate(item):
        return result("containers", "full-sized cargo or storage crate", "role:shipping-container")
    ammo = bool(
        components.intersection(
            {
                "Projectile",
                "ProjectileGrenade",
                "CartridgeAmmo",
                "BallisticAmmoProvider",
                "MortarShell",
                "BulletBox",
                "RMCFlamerTank",
            }
        )
    )
    ammo = ammo or is_ammunition_container(item_id, components, set(item.get("tags", [])))
    ammo = ammo or any("magazine" in tag or "cartridge" in tag or "grenade" in tag for tag in tags)
    ammo = (
        ammo
        or ("Explosive" in components and "gastank" not in tags)
        or "ExplodeOnTrigger" in components
    )
    if ammo or (is_packaging_container(item) and is_ammunition_or_magazine_box(item)):
        return result(
            "ammunition", "ammunition, grenade or dedicated ammunition packaging", "role:ammunition"
        )

    if (
        "/hydroponics/" in path
        or "Shovel" in components
        or tags.intersection({"botanyhoe", "botanyshovel", "botanyhatchet", "hoe"})
    ):
        return result("tools", "agricultural or production tool", "role:production-tool")
    if has("tool", "welder", "fireextinguisher", "entrenching", "wirecutter") or tags.intersection(
        {"fireextinguisher", "cmfireextinguisherportable"}
    ):
        return result("gear", "field engineering or emergency tool", "role:field-tool")
    if has("janitor", "mop", "broom", "lightreplacer", "spray", "cleaner"):
        return result("tools", "cleaning or maintenance tool", "role:maintenance-tool")
    if is_dedicated_melee_weapon(item_id, components, set(item.get("tags", []))):
        return result("weapon", "dedicated melee weapon", "role:melee-weapon")

    if has(
        "headset",
        "radio",
        "encryption",
        "powercell",
        "battery",
        "handheldlight",
        "flash",
        "geiger",
        "detector",
        "scanner",
        "sensor",
        "binocular",
        "rangefinder",
        "scope",
        "camera",
        "megaphone",
        "machineboard",
        "circuitboard",
        "electronics",
        "pdtlocator",
        "visor",
        "nightvision",
        "computer",
        "laptop",
        "telephone",
        "recorder",
        "cassette",
        "crewmonitor",
        "pinpointer",
        "signaller",
    ):
        return result(
            "electronics",
            "electronic, optical, communication or lighting device",
            "role:electronics",
        )
    if has(
        "flare",
        "whistle",
        "skillpamphlet",
        "inflatable",
        "deployable",
        "fulton",
        "parachute",
        "handcuff",
        "restrain",
        "bedroll",
    ):
        return result(
            "gear", "field signalling, training or deployable utility", "role:field-utility"
        )
    # Source families fill gaps for props with no functional component. Keep
    # these fallbacks below actual game mechanics and above generic storage.
    source_roles = (
        ("/objects/weapons/melee/", "weapon"),
        ("/objects/weapons/guns/", "weapon"),
        ("/objects/shields/", "armor"),
        ("/objects/devices/", "electronics"),
        ("/objects/materials/", "materials"),
        ("/objects/decoration/", "household"),
        ("/structures/furniture/", "household"),
        ("/objects/fishing/", "tools"),
    )
    for fragment, category in source_roles:
        if fragment in path and not is_packaging_container(item):
            return {
                **result(category, "primary-purpose source family", f"source:{fragment}"),
                "confidence": "medium",
            }
    # Decorative props often intentionally have no usable device component.
    # Semantic source terms describe a whole family, never individual IDs.
    source_name = path.rsplit("/", 1)[-1].removesuffix(".yml").replace("_", " ")
    source_terms = (
        ("electronics", ("laptop", "computer", "recorder", "stock parts", "disk", "surveying")),
        ("tools", ("mining",)),
        ("gear", ("fuel canister",)),
        ("materials", ("ice crystal",)),
        (
            "household",
            (
                "bedsheet",
                "candle",
                "desk",
                "fan",
                "vase",
                "figurine",
                "magazine",
                "paper",
                "trash",
                "treasure",
                "basketball",
                "bandage props",
                "prop casing",
                "ordnancecasings",
            ),
        ),
    )
    for category, terms in source_terms:
        if any(re.search(rf"\b{re.escape(term)}\w*\b", source_name) for term in terms):
            return {
                **result(category, "semantic source family for a prop", "source:semantic-family"),
                "confidence": "medium",
            }
    if "/entities/clothing/" in path and "Clothing" in components:
        return {
            **result("clothing", "clothing source family", "source:clothing"),
            "confidence": "medium",
        }
    if "/objects/idcards/" in path:
        return {
            **result("equipment", "identification accessory source", "source:identification"),
            "confidence": "medium",
        }
    if "Clothing" in components and slots.intersection({"ears", "ear", "neck"}):
        return result("clothing", "personal clothing accessory", "role:clothing")
    if components.intersection(
        {"Storage", "CMItemSlots", "ItemSlots", "SolutionContainerManager"}
    ) or is_packaging_container(item):
        if contents and contents.issubset({"medicine"}):
            return result("medicine", "container of medical supplies", "contents:medicine")
        if contents and contents.issubset({"food"}):
            return result("food", "container of food or drinks", "contents:food")
        return result("containers", "general-purpose container or packaging", "role:container")
    if "Stack" in components and tags.intersection({"clothmade"}):
        return result("materials", "raw textile resource", "tag:material")
    return result("other", "no specific primary-purpose signal", "fallback:other")
