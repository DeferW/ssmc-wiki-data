from __future__ import annotations

import json
from typing import Any

from .prototypes import PrototypeResolver


def relation_key(relation: dict[str, Any]) -> str:
    return json.dumps(relation, ensure_ascii=False, sort_keys=True)


def add_relation(
    relations: list[dict[str, Any]],
    known: set[str],
    relation: dict[str, Any],
) -> bool:
    key = relation_key(relation)
    if key in known:
        return False
    known.add(key)
    relations.append(relation)
    return True


def content_relations(
    prototype_id: str,
    resolved: dict[str, Any],
) -> list[dict[str, Any]]:
    components = resolved["components"]
    result: list[dict[str, Any]] = []

    storage_fill = components.get("StorageFill", {})
    contents = storage_fill.get("contents")
    if isinstance(contents, list):
        for position, entry in enumerate(contents):
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                continue
            relation: dict[str, Any] = {
                "from": prototype_id,
                "to": entry["id"],
                "type": "contains",
                "position": position,
                "quantity": entry.get("amount", 1),
            }
            for key in ("maxAmount", "prob", "orGroup"):
                if key in entry:
                    relation[key] = entry[key]
            result.append(relation)

    container_fill = components.get("ContainerFill", {})
    containers = container_fill.get("containers")
    if isinstance(containers, dict):
        for container_name, entries in containers.items():
            if not isinstance(entries, list):
                continue
            for position, entry in enumerate(entries):
                if isinstance(entry, str):
                    result.append(
                        {
                            "from": prototype_id,
                            "to": entry,
                            "type": "contains",
                            "container": str(container_name),
                            "position": position,
                            "quantity": 1,
                        }
                    )

    cm_slots = components.get("CMItemSlots", {})
    starting_item = cm_slots.get("startingItem")
    count = cm_slots.get("count", 1)
    if isinstance(starting_item, str):
        result.append(
            {
                "from": prototype_id,
                "to": starting_item,
                "type": "slotItem",
                "quantity": count if isinstance(count, int) else 1,
            }
        )
    starting_items = cm_slots.get("startingItems")
    if isinstance(starting_items, list):
        for position, entry in enumerate(starting_items):
            if isinstance(entry, str):
                result.append(
                    {
                        "from": prototype_id,
                        "to": entry,
                        "type": "slotItem",
                        "position": position,
                        "quantity": 1,
                    }
                )

    item_slots = components.get("ItemSlots", {}).get("slots")
    if isinstance(item_slots, dict):
        for slot_name, slot in item_slots.items():
            if not isinstance(slot, dict):
                continue
            item = slot.get("startingItem")
            if isinstance(item, str):
                result.append(
                    {
                        "from": prototype_id,
                        "to": item,
                        "type": "loadedWith",
                        "slot": str(slot_name),
                        "quantity": 1,
                    }
                )

    attachment_slots = components.get("AttachableHolder", {}).get("slots")
    if isinstance(attachment_slots, dict):
        for slot_name, slot in attachment_slots.items():
            if not isinstance(slot, dict):
                continue
            item = slot.get("startingAttachable")
            if isinstance(item, str):
                result.append(
                    {
                        "from": prototype_id,
                        "to": item,
                        "type": "installedAttachment",
                        "slot": str(slot_name),
                        "quantity": 1,
                    }
                )

    bundle = components.get("CMVendorBundle", {}).get("bundle")
    if isinstance(bundle, list):
        for position, item in enumerate(bundle):
            if isinstance(item, str):
                result.append(
                    {
                        "from": prototype_id,
                        "to": item,
                        "type": "bundleItem",
                        "position": position,
                        "quantity": 1,
                    }
                )

    variants = components.get("RMCArmorVariant", {}).get("types")
    if isinstance(variants, dict):
        for variant_name, item in variants.items():
            if isinstance(item, str):
                result.append(
                    {
                        "from": prototype_id,
                        "to": item,
                        "type": "variant",
                        "variant": str(variant_name),
                        "quantity": 1,
                    }
                )

    squad_mapping = components.get("CMVendorMapToSquad", {}).get("map")
    if isinstance(squad_mapping, dict):
        for squad_name, item in squad_mapping.items():
            if isinstance(item, str):
                result.append(
                    {
                        "from": prototype_id,
                        "to": item,
                        "type": "mappedVariant",
                        "variant": str(squad_name),
                        "quantity": 1,
                    }
                )

    fixed_weapon = components.get("WeaponMount", {}).get("fixedWeaponPrototype")
    if isinstance(fixed_weapon, str):
        result.append(
            {
                "from": prototype_id,
                "to": fixed_weapon,
                "type": "mountedWeapon",
                "quantity": 1,
            }
        )

    provider = components.get("BallisticAmmoProvider", {})
    ammo = provider.get("proto")
    if isinstance(ammo, str):
        relation = {
            "from": prototype_id,
            "to": ammo,
            "type": "loadedWith",
        }
        capacity = provider.get("capacity")
        if isinstance(capacity, int):
            relation["quantity"] = capacity
        result.append(relation)

    for provider_type in (
        "RevolverAmmoProvider",
        "ProjectileBatteryAmmoProvider",
        "BasicEntityAmmoProvider",
    ):
        provider = components.get(provider_type, {})
        ammo = provider.get("proto")
        if not isinstance(ammo, str):
            continue
        relation = {
            "from": prototype_id,
            "to": ammo,
            "type": "loadedWith",
            "provider": provider_type,
        }
        capacity = provider.get("capacity")
        if isinstance(capacity, int):
            relation["quantity"] = capacity
        result.append(relation)

    cartridge = components.get("CartridgeAmmo", {})
    projectile = cartridge.get("proto")
    if isinstance(projectile, str):
        result.append(
            {
                "from": prototype_id,
                "to": projectile,
                "type": "fires",
                "quantity": 1,
            }
        )

    bullet_box = components.get("RefillableByBulletBox", {}).get("bulletType")
    if isinstance(bullet_box, str):
        result.append(
            {
                "from": prototype_id,
                "to": bullet_box,
                "type": "refillableBy",
            }
        )

    return result


def whitelist_matches(
    whitelist: Any,
    candidate_id: str,
    candidate_tags: set[str],
    candidate_components: set[str],
) -> bool:
    if not isinstance(whitelist, dict):
        return False
    entities = whitelist.get("entities", [])
    if isinstance(entities, list) and candidate_id in entities:
        return True
    tags = whitelist.get("tags", [])
    if isinstance(tags, list) and candidate_tags.intersection(
        item for item in tags if isinstance(item, str)
    ):
        return True
    components = whitelist.get("components", [])
    if isinstance(components, list) and candidate_components.intersection(
        item for item in components if isinstance(item, str)
    ):
        return True
    return False


def add_compatibility_relations(
    item_ids: set[str],
    resolver: PrototypeResolver,
    relations: list[dict[str, Any]],
    relation_keys: set[str],
) -> None:
    candidate_data: dict[str, tuple[set[str], set[str]]] = {}
    attachments: set[str] = set()
    magazines: set[str] = set()

    for item_id in item_ids:
        resolved = resolver.resolve(item_id)
        components = resolved["components"]
        tags = components.get("Tag", {}).get("tags", [])
        tag_set = {item for item in tags if isinstance(item, str)} if isinstance(tags, list) else set()
        component_set = set(components)
        candidate_data[item_id] = (tag_set, component_set)
        if "Attachable" in component_set:
            attachments.add(item_id)
        if "BallisticAmmoProvider" in component_set and "Gun" not in component_set:
            magazines.add(item_id)

    for weapon_id in sorted(item_ids):
        components = resolver.resolve(weapon_id)["components"]

        attachment_slots = components.get("AttachableHolder", {}).get("slots")
        if isinstance(attachment_slots, dict):
            for slot_name, slot in attachment_slots.items():
                if not isinstance(slot, dict):
                    continue
                whitelist = slot.get("whitelist")
                blacklist = slot.get("blacklist")
                for attachment_id in sorted(attachments):
                    tags, component_types = candidate_data[attachment_id]
                    if not whitelist_matches(
                        whitelist, attachment_id, tags, component_types
                    ):
                        continue
                    if whitelist_matches(
                        blacklist, attachment_id, tags, component_types
                    ):
                        continue
                    add_relation(
                        relations,
                        relation_keys,
                        {
                            "from": weapon_id,
                            "to": attachment_id,
                            "type": "compatibleAttachment",
                            "slot": str(slot_name),
                        },
                    )

        item_slots = components.get("ItemSlots", {}).get("slots")
        if isinstance(item_slots, dict):
            for slot_name, slot in item_slots.items():
                if not isinstance(slot, dict):
                    continue
                whitelist = slot.get("whitelist")
                blacklist = slot.get("blacklist")
                for magazine_id in sorted(magazines):
                    tags, component_types = candidate_data[magazine_id]
                    if not whitelist_matches(
                        whitelist, magazine_id, tags, component_types
                    ):
                        continue
                    if whitelist_matches(
                        blacklist, magazine_id, tags, component_types
                    ):
                        continue
                    add_relation(
                        relations,
                        relation_keys,
                        {
                            "from": weapon_id,
                            "to": magazine_id,
                            "type": "compatibleMagazine",
                            "slot": str(slot_name),
                        },
                    )
