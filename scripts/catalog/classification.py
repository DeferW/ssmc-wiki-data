from __future__ import annotations

from typing import Any

from scripts.catalog.models import (
    CATEGORY_AMMUNITION,
    CATEGORY_ARMOR,
    CATEGORY_ATTACHMENT,
    CATEGORY_EQUIPMENT,
    CATEGORY_GEAR,
    CATEGORY_MEDICINE,
    CATEGORY_OTHER,
    CATEGORY_WEAPON,
    Classification,
)


ARMOR_SLOTS = {"outerclothing", "head"}
EQUIPMENT_SLOTS = {
    "innerclothing",
    "jumpsuit",
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


def _packaging(item_id: str, name: str, facts: dict[str, Any]) -> bool:
    if not facts["signals"]["storage"]:
        return False
    text = f"{item_id} {name}".casefold()
    return any(marker in text for marker in ("box", "crate", "case", "короб", "ящик", "кейс"))


def _dedicated_ammunition_package(item_id: str, name: str, facts: dict[str, Any]) -> bool:
    text = f"{item_id} {name} {facts.get('sourceFile', '')}".casefold()
    tags = {tag.casefold() for tag in facts["tags"]}
    return bool(
        "rmcammobox" in tags
        or facts["signals"]["explosivePayload"]
        or any(
            marker in text
            for marker in (
                "boxmagazine",
                "boxbullets",
                "boxshells",
                "boxshotgun",
                "crateammo",
                "cratemagazine",
                "/ammunition/boxes/",
                "/throwable/packets",
                "коробка патрон",
                "коробка магазинов",
                "ящик боеприпасов",
            )
        )
    )


def classify(item_id: str, name: str, facts: dict[str, Any]) -> Classification:
    """Assign one explainable automatic category from normalized facts."""
    signals = facts["signals"]
    slots = {slot.casefold() for slot in facts["wearableSlots"]}
    component_types = set(facts["componentTypes"])
    tags = {tag.casefold() for tag in facts["tags"]}
    folded_id = item_id.casefold()

    # An attachment can itself contain a Gun, so attachment wins over weapon.
    if signals["attachment"]:
        return Classification(CATEGORY_ATTACHMENT, "weapon attachment mechanics", ("Attachable",))
    if signals["gun"]:
        return Classification(CATEGORY_WEAPON, "item has firing mechanics", ("Gun",))

    packaging = _packaging(item_id, name, facts)
    dedicated_ammunition_package = packaging and _dedicated_ammunition_package(
        item_id, name, facts
    )

    # Payload propagates through dedicated ammo packaging, not generic gun cases.
    if (
        (signals["projectilePath"] and not packaging)
        or dedicated_ammunition_package
        or (signals["explosivePayload"] and not packaging)
        or signals["ammoProvider"]
        or signals["cartridge"]
        or "rmcammobox" in tags
    ):
        return Classification(
            CATEGORY_AMMUNITION,
            "ammunition, explosive, or a dedicated container holding it",
            tuple(
                signal
                for signal, enabled in (
                    ("projectile-path", signals["projectilePath"]),
                    ("explosive-payload", signals["explosivePayload"]),
                    ("ammo-provider", signals["ammoProvider"]),
                )
                if enabled
            ),
        )

    # Armor requires both a supported armor slot and actual non-zero protection.
    if signals["armor"] and slots and slots.issubset(ARMOR_SLOTS):
        return Classification(
            CATEGORY_ARMOR,
            "protective outer clothing or helmet",
            ("protection", *tuple(f"slot:{slot}" for slot in sorted(slots))),
        )

    # Medical purpose wins over ordinary wearable/storage mechanics (e.g. defibrillator).
    if facts["medicalFunction"] or signals["medicalPayload"]:
        return Classification(
            CATEGORY_MEDICINE,
            "medical function or dedicated medical contents",
            ("medical-function",) if facts["medicalFunction"] else ("medical-payload",),
        )

    # Generic shipping packages stay in Other after ammo/medical exceptions.
    if packaging:
        return Classification(CATEGORY_OTHER, "generic box, crate, or case", ("packaging",))

    # Visors, tools, boards and other strong utility signals win over wearability.
    if signals["utility"] or signals["melee"]:
        return Classification(
            CATEGORY_GEAR,
            "single-purpose tool or field device",
            ("utility",) if signals["utility"] else ("melee",),
        )

    decorative = bool(
        "patch" in folded_id
        or "glasses" in folded_id
        or "goggles" in folded_id
        or "headset" in folded_id
        or any("accessory" in component.casefold() for component in component_types)
    )
    if decorative or slots.intersection(EQUIPMENT_SLOTS) or signals["clothing"]:
        return Classification(
            CATEGORY_EQUIPMENT,
            "wearable, wearable storage, or clothing accessory",
            tuple(f"slot:{slot}" for slot in sorted(slots)) or ("clothing",),
        )

    return Classification(CATEGORY_OTHER, "no stronger category rule matched", ("fallback",))
