from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any

from scripts.catalog.characteristics import (
    populate_armor_statistics,
    populate_attachment_statistics,
    populate_storage_statistics,
    populate_weapon_statistics,
)
from scripts.catalog.classification import classify
from scripts.catalog.config import CatalogConfig, Override
from scripts.catalog.facts import build_facts
from scripts.catalog.graph import discover_items
from scripts.catalog.localization import Localizer
from scripts.catalog.models import (
    CATEGORY_AMMUNITION,
    CATEGORY_ARMOR,
    CATEGORY_ATTACHMENT,
    CATEGORY_EQUIPMENT,
    CATEGORY_GEAR,
    CATEGORY_HIDDEN,
    CATEGORY_MEDICINE,
    CATEGORY_ORDER,
    CATEGORY_OTHER,
    CATEGORY_WEAPON,
)
from scripts.catalog.overrides import apply_overrides
from scripts.catalog.prototypes import PrototypeResolver
from scripts.catalog.sources import discover_sources
from scripts.catalog.sprites import sprite_summary


def _capitalize(value: str) -> str:
    for index, character in enumerate(value):
        if character.isdigit():
            return value
        if character.isalpha():
            return value[:index] + character.upper() + value[index + 1 :]
    return value


def _display_name(base_name: str, suffix: str) -> str:
    ignored = ("empty", "filled", "loaded", "folded", "пуст", "заполн", "заряж", "слож")
    qualifiers = [
        part.strip()
        for part in suffix.split(",")
        if part.strip() and not part.strip().casefold().startswith(ignored)
    ]
    return f"{base_name} ({', '.join(qualifiers)})" if qualifiers else base_name


def _base_cards(
    item_ids: set[str],
    facts: dict[str, dict[str, Any]],
    resolver: PrototypeResolver,
    localizer: Localizer,
) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for item_id in sorted(item_ids):
        resolved = resolver.resolve(item_id)
        fields = resolved["fields"]
        base_name = _capitalize(localizer.entity_text(item_id, None, fields.get("name")))
        suffix = localizer.entity_text(item_id, "suffix", fields.get("suffix"))
        fact = facts[item_id]
        card: dict[str, Any] = {
            "id": item_id,
            "name": _display_name(base_name, suffix),
            "description": localizer.entity_text(item_id, "desc", fields.get("description")),
            "componentTypes": fact["componentTypes"],
            "tags": fact["tags"],
            "equipmentSlots": fact["wearableSlots"],
            "properties": copy.deepcopy(fact["properties"]),
            "itemSize": fact["itemSize"],
            "itemShape": copy.deepcopy(fact["itemShape"]),
            "facts": fact,
        }
        summary = sprite_summary(resolved["components"])
        if summary:
            card["sprite"] = summary
        cards[item_id] = card
    return cards


def _relation_summaries(
    items: dict[str, dict[str, Any]], relations: list[dict[str, Any]]
) -> None:
    contents: dict[str, set[str]] = defaultdict(set)
    attachment_slots: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    attachment_hosts: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    magazine_slots: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    magazine_hosts: dict[str, set[str]] = defaultdict(set)
    installed: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    loaded: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relations:
        source, target, relation_type = relation["from"], relation["to"], relation["type"]
        outgoing[source].append(relation)
        slot = str(relation.get("slot", ""))
        if relation_type in {"contains", "bundleItem"} and source != target:
            contents[source].add(target)
        elif relation_type == "compatibleAttachment":
            attachment_slots[source][slot].add(target)
            attachment_hosts[target][slot].add(source)
        elif relation_type == "compatibleMagazine":
            magazine_slots[source][slot].add(target)
            magazine_hosts[target].add(source)
        elif relation_type == "installedAttachment":
            installed[source][slot].add(target)
        elif relation_type == "loadedWith":
            loaded[source][slot].add(target)

    for item_id, target_ids in contents.items():
        items[item_id]["containsItemIds"] = sorted(target_ids)
    for item_id, slots in attachment_slots.items():
        items[item_id]["attachmentSlots"] = [
            {
                "id": slot,
                "compatibleItemIds": sorted(targets),
                "installedItemIds": sorted(installed[item_id].get(slot, set())),
            }
            for slot, targets in sorted(slots.items())
        ]
    for item_id, slots in attachment_hosts.items():
        items[item_id]["attachableTo"] = [
            {"slotId": slot, "weaponIds": sorted(hosts)}
            for slot, hosts in sorted(slots.items())
        ]
    for item_id, slots in magazine_slots.items():
        items[item_id]["magazineSlots"] = [
            {
                "id": slot,
                "compatibleItemIds": sorted(targets),
                "loadedItemIds": sorted(loaded[item_id].get(slot, set())),
            }
            for slot, targets in sorted(slots.items())
        ]
    for item_id, hosts in magazine_hosts.items():
        items[item_id]["compatibleWeaponIds"] = sorted(hosts)

    for weapon_id in sorted(magazine_slots):
        paths: list[dict[str, Any]] = []
        for magazine_id in sorted(
            target for targets in magazine_slots[weapon_id].values() for target in targets
        ):
            cartridges = sorted(
                {
                    relation["to"]
                    for relation in outgoing.get(magazine_id, [])
                    if relation["type"] == "loadedWith"
                }
            )
            projectiles = sorted(
                {
                    relation["to"]
                    for cartridge_id in cartridges
                    for relation in outgoing.get(cartridge_id, [])
                    if relation["type"] == "fires"
                }
            )
            paths.append(
                {
                    "magazineId": magazine_id,
                    "cartridgeIds": cartridges,
                    "projectileIds": projectiles,
                }
            )
        if paths:
            items[weapon_id]["ammunitionPaths"] = paths


def _classification_records(
    items: dict[str, dict[str, Any]], overrides: dict[str, Override]
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for item_id, item in items.items():
        automatic = classify(item_id, item["name"], item["facts"])
        records[item_id] = {
            "automaticCategory": automatic.category,
            "reason": automatic.reason,
            "signals": list(automatic.signals),
        }
    apply_overrides(records, overrides)
    return records


def _project_characteristics(item: dict[str, Any], category: str) -> dict[str, Any]:
    # Hidden cards keep the useful shape of their automatic category.
    if category == CATEGORY_HIDDEN:
        category = item["classification"]["automaticCategory"]
    result: dict[str, Any] = {}
    if item.get("containsItemIds"):
        result["contents"] = item["containsItemIds"]
    if category == CATEGORY_WEAPON:
        for source, target in (
            ("weaponStats", "weapon"),
            ("attachmentSlots", "attachmentSlots"),
            ("magazineSlots", "magazineSlots"),
        ):
            if item.get(source):
                result[target] = item[source]
    elif category == CATEGORY_AMMUNITION:
        mechanical = {
            key: value
            for key, value in item["properties"].items()
            if key
            in {
                "BallisticAmmoProvider",
                "CartridgeAmmo",
                "Projectile",
                "CMArmorPiercing",
                "RMCProjectileAccuracy",
                "RMCProjectileDamageFalloff",
            }
        }
        if mechanical:
            result["ammunition"] = mechanical
        if item.get("compatibleWeaponIds"):
            result["compatibleWeaponIds"] = item["compatibleWeaponIds"]
    elif category == CATEGORY_ATTACHMENT and item.get("attachmentStats"):
        result["attachment"] = item["attachmentStats"]
    elif category == CATEGORY_ARMOR and item.get("armorStats"):
        result["armor"] = item["armorStats"]
    elif category == CATEGORY_MEDICINE:
        medical_components = [
            component
            for component in item["componentTypes"]
            if any(
                marker in component.casefold()
                for marker in (
                    "heal",
                    "health",
                    "surg",
                    "defib",
                    "hypo",
                    "inject",
                    "syringe",
                    "pill",
                    "blood",
                    "stasis",
                    "dialysis",
                )
            )
            and not component.casefold().endswith("blocked")
        ]
        if medical_components:
            result["medicalFunctions"] = medical_components
        if item["facts"].get("solutions"):
            result["solutions"] = item["facts"]["solutions"]
    if category in {
        CATEGORY_EQUIPMENT,
        CATEGORY_MEDICINE,
        CATEGORY_GEAR,
        CATEGORY_OTHER,
        CATEGORY_AMMUNITION,
    } and item.get("storageStats"):
        result["storage"] = item["storageStats"]
    if item.get("equipmentSlots") and category in {
        CATEGORY_ARMOR,
        CATEGORY_EQUIPMENT,
        CATEGORY_MEDICINE,
        CATEGORY_GEAR,
    }:
        result["wearableSlots"] = item["equipmentSlots"]
    return result


def build_catalog(
    resolver: PrototypeResolver,
    config: CatalogConfig,
    overrides: dict[str, Override],
    localizer: Localizer,
    item_sizes: dict[str, dict[str, Any]],
    game_commit: str,
    locale: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    sources, source_entries = discover_sources(config, resolver, localizer)
    item_ids, relations = discover_items(source_entries, resolver)
    facts = build_facts(item_ids, relations, resolver)
    items = _base_cards(item_ids, facts, resolver, localizer)
    _relation_summaries(items, relations)

    classifications = _classification_records(items, overrides)
    for item_id, classification in classifications.items():
        items[item_id]["classification"] = classification
        items[item_id]["category"] = classification["finalCategory"]

    populate_weapon_statistics(items, relations, item_ids)
    populate_armor_statistics(items, item_ids)
    populate_attachment_statistics(items, item_ids)
    populate_storage_statistics(items, item_ids, item_sizes)

    categories = {category: [] for category in CATEGORY_ORDER}
    for item_id in sorted(items, key=lambda value: (items[value]["name"].casefold(), value)):
        item = items[item_id]
        categories[item["category"]].append(item_id)
        item["characteristics"] = _project_characteristics(item, item["category"])
        for internal in (
            "facts",
            "properties",
            "itemSize",
            "itemShape",
            "weaponStats",
            "armorStats",
            "attachmentStats",
            "storageStats",
            "ammunitionPaths",
            "attachmentSlots",
            "magazineSlots",
            "attachableTo",
            "compatibleWeaponIds",
            "containsItemIds",
        ):
            item.pop(internal, None)

    catalog = {
        "schemaVersion": 4,
        "source": {
            "repository": "MetalSage/space-stories-cm14",
            "commit": game_commit,
        },
        "locale": locale,
        "categoryOrder": list(CATEGORY_ORDER),
        "categories": categories,
        "items": items,
        "counts": {
            "items": len(items),
            "edited": sum(value["edited"] for value in classifications.values()),
            "hiddenCategory": len(categories[CATEGORY_HIDDEN]),
        },
    }
    index = {
        "schemaVersion": 4,
        "source": catalog["source"],
        "configuredSources": {
            "vendors": list(config.vendor_ids),
            "cargoCatalogs": list(config.cargo_catalog_ids),
        },
        "sources": sources,
        "sourceEntries": [
            {
                "key": entry.key,
                "sourceId": entry.source_id,
                "sourceType": entry.source_type,
                "section": entry.section,
                "itemId": entry.item_id,
                "position": entry.position,
                **entry.metadata,
            }
            for entry in source_entries
        ],
        "relations": relations,
        "facts": facts,
        "counts": {
            "indexedPrototypes": len(resolver.prototypes),
            "catalogItems": len(items),
            "relations": len(relations),
            "sourceEntries": len(source_entries),
        },
    }
    return index, catalog
