from __future__ import annotations

import json
from typing import Any

from scripts.catalog.prototypes import PrototypeResolver


def relation_key(relation: dict[str, Any]) -> str:
    return json.dumps(relation, ensure_ascii=False, sort_keys=True)


def content_relations(item_id: str, resolved: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only relations that make another prototype relevant to this item."""
    components = resolved["components"]
    relations: list[dict[str, Any]] = []

    def add(target: Any, relation_type: str, **metadata: Any) -> None:
        if isinstance(target, str) and target:
            relations.append({"from": item_id, "to": target, "type": relation_type, **metadata})

    contents = components.get("StorageFill", {}).get("contents")
    if isinstance(contents, list):
        for position, entry in enumerate(contents):
            if not isinstance(entry, dict):
                continue
            metadata = {"position": position, "quantity": entry.get("amount", 1)}
            for key, output in (("maxAmount", "maxQuantity"), ("prob", "probability"), ("orGroup", "group")):
                if key in entry:
                    metadata[output] = entry[key]
            add(entry.get("id"), "contains", **metadata)

    containers = components.get("ContainerFill", {}).get("containers")
    if isinstance(containers, dict):
        for container_name, entries in containers.items():
            if not isinstance(entries, list):
                continue
            for position, entry in enumerate(entries):
                if isinstance(entry, str):
                    add(entry, "contains", container=str(container_name), position=position, quantity=1)
                elif isinstance(entry, dict):
                    add(
                        entry.get("id"),
                        "contains",
                        container=str(container_name),
                        position=position,
                        quantity=entry.get("amount", 1),
                    )

    cm_slots = components.get("CMItemSlots", {})
    add(cm_slots.get("startingItem"), "slotItem", quantity=cm_slots.get("count", 1))
    starting_items = cm_slots.get("startingItems")
    if isinstance(starting_items, list):
        for position, target in enumerate(starting_items):
            add(target, "slotItem", position=position, quantity=1)

    item_slots = components.get("ItemSlots", {}).get("slots")
    if isinstance(item_slots, dict):
        for slot_name, slot in item_slots.items():
            if isinstance(slot, dict):
                add(slot.get("startingItem"), "loadedWith", slot=str(slot_name), quantity=1)

    attachment_slots = components.get("AttachableHolder", {}).get("slots")
    if isinstance(attachment_slots, dict):
        for slot_name, slot in attachment_slots.items():
            if isinstance(slot, dict):
                add(
                    slot.get("startingAttachable"),
                    "installedAttachment",
                    slot=str(slot_name),
                    quantity=1,
                )

    bundle = components.get("CMVendorBundle", {}).get("bundle")
    if isinstance(bundle, list):
        for position, target in enumerate(bundle):
            add(target, "bundleItem", position=position, quantity=1)

    variants = components.get("RMCArmorVariant", {}).get("types")
    if isinstance(variants, dict):
        for variant, target in variants.items():
            add(target, "variant", variant=str(variant), quantity=1)

    mapping = components.get("CMVendorMapToSquad", {}).get("map")
    if isinstance(mapping, dict):
        for variant, target in mapping.items():
            add(target, "mappedVariant", variant=str(variant), quantity=1)

    add(
        components.get("WeaponMount", {}).get("fixedWeaponPrototype"),
        "mountedWeapon",
        quantity=1,
    )

    for provider_type in (
        "BallisticAmmoProvider",
        "RevolverAmmoProvider",
        "ProjectileBatteryAmmoProvider",
        "BasicEntityAmmoProvider",
    ):
        provider = components.get(provider_type, {})
        if isinstance(provider, dict):
            metadata: dict[str, Any] = {"provider": provider_type}
            if isinstance(provider.get("capacity"), int):
                metadata["quantity"] = provider["capacity"]
            add(provider.get("proto"), "loadedWith", **metadata)

    add(components.get("CartridgeAmmo", {}).get("proto"), "fires", quantity=1)
    add(components.get("RefillableByBulletBox", {}).get("bulletType"), "refillableBy")
    return relations


def _matches(
    rule: Any,
    candidate_id: str,
    tags: set[str],
    component_types: set[str],
) -> bool:
    if not isinstance(rule, dict):
        return False
    return bool(
        candidate_id in rule.get("entities", [])
        or tags.intersection(value for value in rule.get("tags", []) if isinstance(value, str))
        or component_types.intersection(
            value for value in rule.get("components", []) if isinstance(value, str)
        )
    )


def compatibility_relations(
    item_ids: set[str], resolver: PrototypeResolver
) -> list[dict[str, Any]]:
    """Derive compatibility after discovery; these edges never expand discovery."""
    candidates: dict[str, tuple[set[str], set[str]]] = {}
    attachments: set[str] = set()
    magazines: set[str] = set()
    for item_id in item_ids:
        components = resolver.resolve(item_id)["components"]
        raw_tags = components.get("Tag", {}).get("tags", [])
        tags = {tag for tag in raw_tags if isinstance(tag, str)} if isinstance(raw_tags, list) else set()
        types = set(components)
        candidates[item_id] = tags, types
        if "Attachable" in types:
            attachments.add(item_id)
        if "BallisticAmmoProvider" in types and "Gun" not in types:
            magazines.add(item_id)

    result: list[dict[str, Any]] = []
    for host_id in sorted(item_ids):
        components = resolver.resolve(host_id)["components"]
        slots = components.get("AttachableHolder", {}).get("slots")
        if isinstance(slots, dict):
            for slot_name, slot in slots.items():
                if not isinstance(slot, dict):
                    continue
                for candidate_id in sorted(attachments):
                    tags, types = candidates[candidate_id]
                    if _matches(slot.get("whitelist"), candidate_id, tags, types) and not _matches(
                        slot.get("blacklist"), candidate_id, tags, types
                    ):
                        result.append(
                            {
                                "from": host_id,
                                "to": candidate_id,
                                "type": "compatibleAttachment",
                                "slot": str(slot_name),
                            }
                        )
        slots = components.get("ItemSlots", {}).get("slots")
        if isinstance(slots, dict):
            for slot_name, slot in slots.items():
                if not isinstance(slot, dict):
                    continue
                for candidate_id in sorted(magazines):
                    tags, types = candidates[candidate_id]
                    if _matches(slot.get("whitelist"), candidate_id, tags, types) and not _matches(
                        slot.get("blacklist"), candidate_id, tags, types
                    ):
                        result.append(
                            {
                                "from": host_id,
                                "to": candidate_id,
                                "type": "compatibleMagazine",
                                "slot": str(slot_name),
                            }
                        )
    return result

