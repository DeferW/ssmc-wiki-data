from __future__ import annotations

from typing import Any


def extract_core(resolved: dict[str, Any]) -> dict[str, Any]:
    components = resolved["components"]
    raw_tags = components.get("Tag", {}).get("tags", [])
    tags = sorted(tag for tag in raw_tags if isinstance(tag, str)) if isinstance(raw_tags, list) else []
    clothing = components.get("Clothing", {})
    raw_slots = clothing.get("slots", []) if isinstance(clothing, dict) else []
    if isinstance(raw_slots, str):
        slots = [raw_slots]
    elif isinstance(raw_slots, list):
        slots = sorted(slot for slot in raw_slots if isinstance(slot, str))
    else:
        slots = []
    return {
        "componentTypes": sorted(components),
        "tags": tags,
        "wearableSlots": slots,
        "sourceFile": resolved["sourceFile"],
        "origin": resolved["origin"],
    }

