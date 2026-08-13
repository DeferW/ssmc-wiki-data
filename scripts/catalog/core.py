from __future__ import annotations

from scripts.common.prototypes import EntityPrototype as EntityPrototype


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


PUBLIC_CATEGORY_LABELS = {
    "weapon": "Оружие",
    "ammunition": "Боезапас",
    "attachment": "Обвесы",
    "armor": "Броня",
    "equipment": "Экипировка",
    "medicine": "Медицина",
    "gear": "Снаряжение",
    "other": "Другое",
    "hidden": "Скрытые",
}


PUBLIC_CATEGORY_ORDER = (
    "weapon",
    "ammunition",
    "attachment",
    "armor",
    "equipment",
    "medicine",
    "gear",
    "other",
    "hidden",
)


PUBLIC_CATEGORY_IDS_BY_LABEL = {
    label: category_id for category_id, label in PUBLIC_CATEGORY_LABELS.items()
}


WEARABLE_EQUIPMENT_SLOTS = {
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
    "ears",
    "ear",
    "neck",
    "pocket",
    "pockets",
    "belt",
    "back",
}


WEARABLE_STORAGE_SLOTS = {
    "innerclothing",
    "pocket",
    "pockets",
    "belt",
    "back",
}


PUBLIC_PROPERTY_COMPONENTS = {
    # Weapons and ammunition.
    "BallisticAmmoProvider",
    "CartridgeAmmo",
    "CMArmorPiercing",
    "CMItemSlots",
    "Gun",
    "GunDamageModifier",
    "MagazineAmmoProvider",
    "Projectile",
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
}


SOURCE_CATEGORY_HINTS = {
    "ammunition": "magazine-or-ammo-container",
    "armor-piercing ammunition": "magazine-or-ammo-container",
    "extended ammunition": "magazine-or-ammo-container",
    "special ammunition": "magazine-or-ammo-container",
    "restricted firearm ammunition": "magazine-or-ammo-container",
    "primary ammunition": "magazine-or-ammo-container",
    "sidearm ammunition": "magazine-or-ammo-container",
    "magazine boxes": "magazine-or-ammo-container",
    "ammunition boxes": "magazine-or-ammo-container",
    "боеприпасы": "magazine-or-ammo-container",
    "боеприпасы специалиста по оружию": "magazine-or-ammo-container",
    "vehicle ammunition": "vehicle-ammunition",
    "боеприпасы для техники": "vehicle-ammunition",
    "attachments": "attachment",
    "обвесы": "attachment",
    "armor": "armor",
    "броня": "armor",
    "clothing": "clothing",
    "одежда": "clothing",
    "food": "food",
    "еда": "food",
    "medicine": "medical",
    "medical": "medical",
    "медицина": "medical",
    "engineering": "engineering",
    "инженерия": "engineering",
    "explosives": "explosive",
    "взрывчатка": "explosive",
    "research": "material",
    "исследование": "material",
    "mortar": "magazine-or-ammo-container",
    "мортира": "magazine-or-ammo-container",
    "reagent tanks": "reagent",
    "резервуары для реагентов": "reagent",
    "weapons": "weapon",
    "primary firearms": "weapon",
    "sidearms": "weapon",
    "оружие": "weapon",
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
