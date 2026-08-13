from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CATEGORY_WEAPON = "Оружие"
CATEGORY_AMMUNITION = "Боезапас"
CATEGORY_ATTACHMENT = "Обвесы"
CATEGORY_ARMOR = "Броня"
CATEGORY_EQUIPMENT = "Экипировка"
CATEGORY_MEDICINE = "Медицина"
CATEGORY_GEAR = "Снаряжение"
CATEGORY_OTHER = "Другое"
CATEGORY_HIDDEN = "Скрытые"

CATEGORY_ORDER = (
    CATEGORY_WEAPON,
    CATEGORY_AMMUNITION,
    CATEGORY_ATTACHMENT,
    CATEGORY_ARMOR,
    CATEGORY_EQUIPMENT,
    CATEGORY_MEDICINE,
    CATEGORY_GEAR,
    CATEGORY_OTHER,
    CATEGORY_HIDDEN,
)

AUTOMATIC_CATEGORIES = frozenset(CATEGORY_ORDER[:-1])
CATEGORY_ALIASES = {
    "Боеприпасы и взрывчатка": CATEGORY_AMMUNITION,
    "Ближний бой": CATEGORY_GEAR,
}

@dataclass(frozen=True)
class Prototype:
    id: str
    parents: tuple[str, ...]
    abstract: bool
    source_file: str
    origin: str
    fields: dict[str, Any]
    components: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class SourceEntry:
    key: str
    source_id: str
    source_type: str
    section: str
    item_id: str
    position: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Classification:
    category: str
    reason: str
    signals: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "reason": self.reason,
            "signals": list(self.signals),
        }


def normalized_category(value: str) -> str:
    return CATEGORY_ALIASES.get(value, value)
