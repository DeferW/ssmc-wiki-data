from __future__ import annotations


PUBLIC_CATEGORY_LABELS = {
    "weapon": "Оружие",
    "ammunition": "Боезапас",
    "attachment": "Обвесы",
    "armor": "Броня",
    "clothing": "Одежда",
    "equipment": "Экипировка",
    "medicine": "Медицина",
    "gear": "Снаряжение",
    "tools": "Инструменты",
    "electronics": "Электроника",
    "food": "Провизия",
    "household": "Быт",
    "materials": "Материалы",
    "containers": "Контейнеры",
    "other": "Другое",
    "hidden": "Скрытые",
}

PUBLIC_CATEGORY_ORDER = tuple(PUBLIC_CATEGORY_LABELS)
# Schema 4 snapshots published before the taxonomy extension remain readable.
LEGACY_CATEGORY_ORDER = (
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


def supported_category_order(labels: list[str]) -> bool:
    return labels in [
        [PUBLIC_CATEGORY_LABELS[key] for key in order]
        for order in (LEGACY_CATEGORY_ORDER, PUBLIC_CATEGORY_ORDER)
    ]


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
    "outerclothing",
}

WEARABLE_STORAGE_SLOTS = {
    "innerclothing",
    "pocket",
    "pockets",
    "belt",
    "back",
    "outerclothing",
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
