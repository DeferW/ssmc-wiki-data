"""Visibility of state variants, shared by vendor and map item catalogs."""

from __future__ import annotations

import copy
import re
from typing import Any


def components(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("_classificationComponents", item.get("properties", {}))


def mechanics(item: dict[str, Any], *, load_state: bool = False) -> dict[str, Any]:
    """Keep weapon/protection/capacity mechanics, ignoring initial load and presentation."""
    ignored = {
        "GunIDLock",
        "Sprite",
        "Appearance",
        "GenericVisualizer",
        "MagazineVisuals",
        "ItemCamouflage",
        "StorageFill",
        "ContainerFill",
        "RMCEmptyMag",
    }
    if load_state:
        # Spawn prefabs may replace entire slot dictionaries with their starting
        # loadout. These are configurations of the same frame, not new weapons.
        ignored.update({"ItemSlots", "AttachableHolder"})
    result = copy.deepcopy(
        {name: value for name, value in components(item).items() if name not in ignored}
    )
    for component_name, initial_field in [
        ("ItemSlots", "startingItem"),
        ("AttachableHolder", "startingAttachable"),
    ]:
        slots = result.get(component_name, {}).get("slots", {})
        if isinstance(slots, dict):
            for slot in slots.values():
                if isinstance(slot, dict):
                    slot.pop(initial_field, None)
                    if component_name == "ItemSlots" and "Gun" not in result:
                        slot.pop("locked", None)
    provider = result.get("BallisticAmmoProvider")
    if isinstance(provider, dict):
        provider.pop("proto", None)
    revolver = result.get("RevolverAmmoProvider")
    if isinstance(revolver, dict):
        revolver.pop("proto", None)
        chambers = revolver.get("chambers")
        if isinstance(chambers, list):
            revolver["chambers"] = [None] * len(chambers)
    for provider_name, initial_field in [("LightReplacer", "contents"), ("BulletBox", "amount")]:
        provider = result.get(provider_name)
        if isinstance(provider, dict):
            provider.pop(initial_field, None)
    battery = result.get("Battery")
    if isinstance(battery, dict):
        battery.pop("startingCharge", None)
    gun = result.get("Gun")
    if isinstance(gun, dict):
        gun.pop("selectedMode", None)
    return result


def hidden_variant_reasons(
    items: dict[str, dict[str, Any]], public_ids: set[str]
) -> dict[str, str]:
    hidden: dict[str, str] = {}
    for item_id in sorted(public_ids):
        item = items[item_id]
        types = set(item.get("componentTypes", []))
        if types.intersection({"EmptySandbag", "FullSandbag"}):
            continue
        if "RMCEmptyMag" in types:
            hidden[item_id] = "empty magazine state variant"
            continue
        if {"PDTBraceletHolderTarget", "StorageFill"}.issubset(types) and types.intersection(
            {"CMArmor", "CMHardArmor", "RMCArmor"}
        ):
            hidden[item_id] = "internal armor storage/fill variant"
            continue
        state = str(item.get("_prototypeSuffix", item.get("suffix", ""))).casefold()
        empty = bool(
            re.search(r"\b(empty|пустой|пустая|пустое|пустые)\b", state)
        ) or item_id.casefold().endswith("empty")
        loaded = "Gun" in types and bool(
            re.search(r"\b(filled|loaded|заполненн\w*|заряженн\w*)\b", state)
        )
        if not (empty or loaded):
            continue
        for parent_id in item.get("parents", []):
            parent = items.get(parent_id)
            if (
                parent_id not in public_ids
                or not parent
                or "Item" not in parent.get("componentTypes", [])
            ):
                continue
            if item.get("baseName", item.get("name")) != parent.get("baseName", parent.get("name")):
                continue
            if mechanics(item, load_state=True) == mechanics(parent, load_state=True):
                hidden[item_id] = f"load-state duplicate of {parent_id}"
                break

    # The secured child is the canonical card: it describes the ID-lock mechanic.
    # Only an actual inheritance relation with identical combat parameters qualifies.
    for item_id in sorted(public_ids):
        item = items[item_id]
        if item_id in hidden or not {"Gun", "GunIDLock"}.issubset(item.get("componentTypes", [])):
            continue
        for parent_id in item.get("parents", []):
            parent = items.get(parent_id)
            if (
                parent_id not in public_ids
                or not parent
                or "GunIDLock" in parent.get("componentTypes", [])
            ):
                continue
            if "Gun" in parent.get("componentTypes", []) and mechanics(item) == mechanics(parent):
                hidden[parent_id] = f"ID-lock state duplicate of {item_id}"
    return hidden
