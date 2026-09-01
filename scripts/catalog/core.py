from __future__ import annotations

from scripts.common.prototypes import EntityPrototype as EntityPrototype
from scripts.common.items.categories import (
    PUBLIC_CATEGORY_IDS_BY_LABEL as PUBLIC_CATEGORY_IDS_BY_LABEL,
    PUBLIC_CATEGORY_LABELS as PUBLIC_CATEGORY_LABELS,
    PUBLIC_CATEGORY_ORDER as PUBLIC_CATEGORY_ORDER,
)


PHYSICAL_CONTENT_RELATION_TYPES = {
    "contains",
    "slotItem",
    "bundleItem",
    "loadedWith",
    "installedAttachment",
    "fires",
    "variant",
    "mountedWeapon",
    "mappedVariant",
}


PUBLIC_PROPERTY_COMPONENTS = {
    # Weapons and ammunition.
    "AimedShot",
    "AimedShotEffect",
    "BallisticAmmoProvider",
    "CartridgeAmmo",
    "CMArmorPiercing",
    "CMItemSlots",
    "Gun",
    "GunDamageModifier",
    "GunToggleableAmmo",
    "HoloTargeting",
    "MagazineAmmoProvider",
    "Overheat",
    "Projectile",
    "ProjectileSpread",
    "ProjectileBatteryAmmoProvider",
    "RevolverAmmoProvider",
    "RMCFlamerAmmoProvider",
    "RMCFlamerTank",
    "RMCProjectileAccuracy",
    "RMCProjectileDamageFalloff",
    "RMCSelectiveFire",
    "RMCWeaponAccuracy",
    "RMCWeaponDamageFalloff",
    "WieldDelay",
    "WieldableSpeedModifiers",
    # Attachments and melee.
    "AttachableSizeMods",
    "AttachableSpeedMods",
    "AttachableWeaponMeleeMods",
    "AttachableWeaponRangedMods",
    "AttachableWieldDelayMods",
    "MeleeWeapon",
    # Protection, medicine and useful containers.
    "Armor",
    "CMArmor",
    "RMCArmor",
    "RMCArmorSpeedTier",
    "RMCArmorVariant",
    "ClothingSpeedModifier",
    "ExplosionResistance",
    "FixedItemSizeStorage",
    "IgnoreContentsSize",
    "Item",
    "LimitedStorage",
    "SolutionContainerManager",
    "Storage",
    # Communications. Headsets are useful because of their installed keys and
    # channels, not merely because they occupy the ears slot.
    "EncryptionKey",
    "EncryptionKeyHolder",
    "Headset",
    "HeadsetMultiBroadcast",
    "RMCHeadset",
    "RMCStaticDefaultChannel",
    # Training manuals and language pamphlets.
    "SkillPamphlet",
}


SLOT_LABELS = {
    "rmc-aslot-barrel": "Дуло",
    "rmc-aslot-rail": "Верхняя планка",
    "rmc-aslot-stock": "Приклад",
    "rmc-aslot-underbarrel": "Подствольный слот",
}


NON_MECHANICAL_COMPONENTS = {
    "Appearance",
    "ContainerContainer",
    "GenericVisualizer",
    "Icon",
    "ItemCamouflage",
    "PointLight",
    "Sprite",
    "Tag",
    "Transform",
}
