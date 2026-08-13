from __future__ import annotations

import copy
from typing import Any


ARMOR_FIELDS = (
    "xenoArmor",
    "frontalArmor",
    "sideArmor",
    "melee",
    "bullet",
    "bio",
    "explosionArmor",
)


def _meaningful_armor(components: dict[str, Any]) -> bool:
    cm_armor = components.get("CMArmor")
    if isinstance(cm_armor, dict) and (
        cm_armor.get("immuneToAP") is True
        or any(
            isinstance(cm_armor.get(field), (int, float))
            and not isinstance(cm_armor.get(field), bool)
            and cm_armor.get(field) != 0
            for field in ARMOR_FIELDS
        )
    ):
        return True
    armor = components.get("Armor")
    return bool(
        isinstance(armor, dict)
        and (armor.get("modifiers") or armor.get("modifierSets"))
    ) or any(component in components for component in ("CMHardArmor", "RMCBulkyArmor", "SquadArmor"))


def extract_mechanics(resolved: dict[str, Any]) -> dict[str, Any]:
    components = resolved["components"]
    types = set(components)
    item_id = resolved["id"]
    folded = item_id.casefold()
    properties = {
        component_type: copy.deepcopy(component)
        for component_type, component in components.items()
        if component_type
        in {
            "Gun",
            "GunIFF",
            "GunRequiresSkills",
            "GunDualWielding",
            "RMCSelectiveFire",
            "GunDamageModifier",
            "RMCWeaponAccuracy",
            "RMCWeaponDamageFalloff",
            "MeleeWeapon",
            "WieldDelay",
            "WieldableSpeedModifiers",
            "BallisticAmmoProvider",
            "RevolverAmmoProvider",
            "ProjectileBatteryAmmoProvider",
            "MagazineAmmoProvider",
            "RMCFlamerAmmoProvider",
            "CartridgeAmmo",
            "Projectile",
            "CMArmorPiercing",
            "RMCProjectileAccuracy",
            "RMCProjectileDamageFalloff",
            "Explosive",
            "ExplodeOnTrigger",
            "ProjectileGrenade",
            "AttachableWeaponRangedMods",
            "AttachableWeaponMeleeMods",
            "AttachableSpeedMods",
            "AttachableWieldDelayMods",
            "AttachableSizeMods",
            "Armor",
            "CMArmor",
            "RMCArmor",
            "RMCArmorSpeedTier",
            "ClothingSpeedModifier",
            "ExplosionResistance",
            "Storage",
            "CMItemSlots",
            "FixedItemSizeStorage",
            "LimitedStorage",
            "IgnoreContentsSize",
            "Item",
        }
    }
    explosive = bool(
        types.intersection({"Explosive", "ExplodeOnTrigger", "ProjectileGrenade", "MortarShell"})
        or "grenade" in folded
    )
    utility_fragments = (
        "tool",
        "welder",
        "binocular",
        "rangefinder",
        "detector",
        "scanner",
        "encryption",
        "visor",
        "sentry",
        "turret",
        "mortar",
        "circuitboard",
        "powercell",
        "generator",
        "flashlight",
    )
    utility = any(
        fragment in component_type.casefold()
        for component_type in types
        for fragment in utility_fragments
    ) or any(
        fragment in folded
        for fragment in (
            "knife",
            "machete",
            "bayonet",
            "binocular",
            "rangefinder",
            "motiondetector",
            "encryptionkey",
            "circuitboard",
            "powercell",
        )
    )
    return {
        "properties": properties,
        "signals": {
            "gun": "Gun" in types or "RMCFlamerAmmoProvider" in types,
            "attachment": "Attachable" in types,
            "projectile": "Projectile" in types,
            "cartridge": "CartridgeAmmo" in types,
            "ammoProvider": "BallisticAmmoProvider" in types and "Gun" not in types,
            "explosive": explosive,
            "armor": _meaningful_armor(components),
            "storage": bool(types.intersection({"Storage", "CMItemSlots"})),
            "clothing": "Clothing" in types,
            "utility": utility,
            "melee": "MeleeWeapon" in types,
        },
        "itemSize": str(components.get("Item", {}).get("size", "Small")),
        "itemShape": copy.deepcopy(components.get("Item", {}).get("shape")),
    }
