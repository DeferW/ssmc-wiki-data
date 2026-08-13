from __future__ import annotations

import copy
from collections import defaultdict, deque
from typing import Any

from .classification import (
    classify_item,
    equipment_slots,
    infer_types,
    source_category_hint,
)
from .core import (
    EntityPrototype,
    NON_MECHANICAL_COMPONENTS,
    PHYSICAL_CONTENT_RELATION_TYPES,
    PUBLIC_CATEGORY_LABELS,
    PUBLIC_CATEGORY_ORDER,
    PUBLIC_PROPERTY_COMPONENTS,
    SLOT_LABELS,
)
from scripts.common.localization import Localizer
from .prototypes import PrototypeResolver
from .relations import add_compatibility_relations, add_relation, content_relations
from .sprites import sprite_summary
from .statistics import (
    populate_armor_statistics,
    populate_attachment_statistics,
    populate_communication_statistics,
    populate_solution_statistics,
    populate_storage_statistics,
    populate_weapon_statistics,
)


def capitalize_first(value: str) -> str:
    """Uppercase the first visible letter without changing the rest of a name."""
    for index, character in enumerate(value):
        if character.isdigit():
            return value
        if character.isalpha():
            return value[:index] + character.upper() + value[index + 1 :]
    return value


def catalog_display_name(base_name: str, suffix: str) -> str:
    ignored_prefixes = (
        "empty",
        "filled",
        "loaded",
        "folded",
        "assembled",
        "пуст",
        "заполн",
        "заряж",
        "слож",
        "собран",
    )
    qualifiers = [
        part.strip()
        for part in suffix.split(",")
        if part.strip()
        and not part.strip().casefold().startswith(ignored_prefixes)
    ]
    if not qualifiers:
        return base_name
    return f"{base_name} ({', '.join(qualifiers)})"


def build_public_catalog(
    trade_entries: list[dict[str, Any]],
    items: dict[str, Any],
    relations: list[dict[str, Any]],
    transport_container_ids: set[str],
    classification_policy: dict[str, Any],
) -> dict[str, Any]:
    physical_contents: dict[str, list[str]] = defaultdict(list)
    for relation in relations:
        if relation.get("type") in PHYSICAL_CONTENT_RELATION_TYPES:
            physical_contents[relation["from"]].append(relation["to"])

    public_candidates: set[str] = set()
    seed_ids: list[str] = []
    for entry in trade_entries:
        item_id = entry.get("itemId")
        if isinstance(item_id, str):
            seed_ids.append(item_id)
        stock = entry.get("stock")
        stock_id = stock.get("itemId") if isinstance(stock, dict) else None
        if isinstance(stock_id, str):
            seed_ids.append(stock_id)
    queue = deque(seed_ids)
    visited: set[str] = set()
    while queue:
        item_id = queue.popleft()
        if item_id in visited:
            continue
        visited.add(item_id)
        if item_id not in items:
            raise RuntimeError(f"Unknown item id reachable from public roots: {item_id}")
        public_candidates.add(item_id)
        # Every configured product and every reachable content item is public.
        # Boxes/crates are no longer silently replaced with their contents.
        queue.extend(physical_contents.get(item_id, []))

    # Admin review needs every reachable prototype as its own card. Automatic
    # canonical aliases used to hide filled/empty and wrapper variants before a
    # human could inspect them, which contradicts the all-items source policy.
    aliases = {item_id: item_id for item_id in public_candidates}
    alias_groups: dict[str, list[str]] = {}
    public_ids = {aliases[item_id] for item_id in public_candidates}
    for canonical_id, members in alias_groups.items():
        if len(members) > 1:
            items[canonical_id]["aliases"] = [
                member for member in members if member != canonical_id
            ]
            for member in members:
                items[member]["canonicalItemId"] = canonical_id
            if (
                "container" in items[canonical_id].get("types", [])
                and "armor" not in items[canonical_id].get("types", [])
                and "weapon" not in items[canonical_id].get("types", [])
            ):
                loadouts = []
                for member in members:
                    content_ids = sorted(set(physical_contents.get(member, [])))
                    if not content_ids:
                        continue
                    loadouts.append(
                        {
                            "itemId": member,
                            "suffix": items[member].get("suffix", ""),
                            "contentItemIds": content_ids,
                        }
                    )
                if loadouts:
                    items[canonical_id]["loadoutVariants"] = loadouts

    categories: dict[str, list[str]] = defaultdict(list)
    excluded_ids: list[str] = []
    sort_key = lambda value: (items[value]["name"].casefold(), value)
    for item_id in sorted(public_ids, key=sort_key):
        classification = classify_item(items[item_id], classification_policy)
        items[item_id]["classification"] = classification
        status = classification["status"]
        if status == "excluded":
            excluded_ids.append(item_id)
            continue
        category = classification["category"]
        items[item_id]["category"] = category
        items[item_id]["types"] = [classification["categoryId"]]
        items[item_id]["public"] = True
        categories[category].append(item_id)

    published_ids = [
        item_id
        for item_id in sorted(public_ids, key=sort_key)
        if items[item_id].get("public") is True
    ]

    return {
        "itemIds": published_ids,
        "categories": {
            PUBLIC_CATEGORY_LABELS[category_id]: categories.get(
                PUBLIC_CATEGORY_LABELS[category_id], []
            )
            for category_id in PUBLIC_CATEGORY_ORDER
        },
        "excludedItemIds": excluded_ids,
        "candidateItemIds": sorted(public_ids, key=sort_key),
        "unwrappedCaseIds": [],
        "unwrappedTransportIds": [],
        "aliases": {
            item_id: canonical_id
            for item_id, canonical_id in sorted(aliases.items())
            if item_id != canonical_id and canonical_id in set(published_ids)
        },
    }


def should_publish_component(component_type: str) -> bool:
    if component_type in NON_MECHANICAL_COMPONENTS:
        return False
    if component_type.endswith("Visuals") or component_type.endswith("Visualizer"):
        return False
    if component_type in PUBLIC_PROPERTY_COMPONENTS:
        return True
    return component_type.startswith(
        (
            "Attachable",
            "Gun",
            "RMCProjectile",
            "RMCWeapon",
        )
    )


def build_card(
    prototype_id: str,
    resolved: dict[str, Any],
    localizer: Localizer,
    availability: list[dict[str, Any]],
    reachable_vendors: set[str],
    source_hints: set[str],
) -> dict[str, Any]:
    components = resolved["components"]
    raw_tags = components.get("Tag", {}).get("tags", [])
    tags = {item for item in raw_tags if isinstance(item, str)} if isinstance(raw_tags, list) else set()
    fields = resolved["fields"]

    properties = {
        component_type: copy.deepcopy(component)
        for component_type, component in sorted(components.items())
        if should_publish_component(component_type)
    }

    base_name = capitalize_first(
        localizer.entity_text(prototype_id, None, fields.get("name"))
    )
    suffix = localizer.entity_text(
        prototype_id, "suffix", fields.get("suffix")
    )
    card: dict[str, Any] = {
        "id": prototype_id,
        "name": catalog_display_name(base_name, suffix),
        "baseName": base_name,
        "description": localizer.entity_text(
            prototype_id, "desc", fields.get("description")
        ),
        "suffix": suffix,
        "origin": resolved["origin"],
        "sourceFile": resolved["sourceFile"],
        "parents": resolved["parents"],
        "abstract": resolved["abstract"],
        "types": infer_types(prototype_id, components, tags, source_hints),
        "sourceCategoryHints": sorted(source_hints),
        "tags": sorted(tags),
        "componentTypes": sorted(components),
        "equipmentSlots": sorted(equipment_slots(components)),
        "properties": properties,
        "itemSize": str(components.get("Item", {}).get("size", "Small")),
        "itemShape": copy.deepcopy(components.get("Item", {}).get("shape")),
        "availability": availability,
        "directlyVended": bool(availability),
        "reachableFromVendors": sorted(reachable_vendors),
    }
    sprite = sprite_summary(components)
    if sprite:
        card["sprite"] = sprite
    return card


def slot_label(slot: Any) -> str:
    raw = str(slot or "")
    if raw in SLOT_LABELS:
        return SLOT_LABELS[raw]
    folded = raw.casefold()
    if "barrel" in folded or "muzzle" in folded:
        return "Дуло"
    if "rail" in folded or "optic" in folded or "sight" in folded:
        return "Верхняя планка"
    if "stock" in folded:
        return "Приклад"
    if "under" in folded:
        return "Подствольный слот"
    return raw


def populate_compatibility_summaries(
    items: dict[str, Any],
    relations: list[dict[str, Any]],
    public_item_ids: set[str],
    aliases: dict[str, str],
) -> None:
    attachment_slots: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    attachment_weapons: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    magazine_slots: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    magazine_weapons: dict[str, set[str]] = defaultdict(set)
    installed: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    loaded: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def canonical(item_id: str) -> str:
        return aliases.get(item_id, item_id)

    for relation in relations:
        raw_source = str(relation.get("from", ""))
        raw_target = str(relation.get("to", ""))
        source = canonical(raw_source)
        target = canonical(raw_target)
        relation_type = relation.get("type")
        canonical_relation = dict(relation)
        canonical_relation["from"] = source
        canonical_relation["to"] = target
        outgoing[source].append(canonical_relation)
        raw_slot = str(relation.get("slot", ""))
        if (
            relation_type == "compatibleAttachment"
            and source in public_item_ids
            and target in public_item_ids
        ):
            attachment_slots[source][raw_slot].add(target)
            attachment_weapons[target][raw_slot].add(source)
        elif (
            relation_type == "compatibleMagazine"
            and source in public_item_ids
            and target in public_item_ids
        ):
            magazine_slots[source][raw_slot].add(target)
            magazine_weapons[target].add(source)
        elif relation_type == "installedAttachment":
            installed[source][raw_slot].add(target)
        elif relation_type == "loadedWith":
            loaded[source][raw_slot].add(target)

    for weapon_id, slots in attachment_slots.items():
        items[weapon_id]["attachmentSlots"] = [
            {
                "id": raw_slot,
                "name": slot_label(raw_slot),
                "compatibleItemIds": sorted(attachment_ids),
                "installedItemIds": sorted(installed[weapon_id].get(raw_slot, set())),
            }
            for raw_slot, attachment_ids in sorted(slots.items())
        ]
    for attachment_id, slots in attachment_weapons.items():
        items[attachment_id]["attachableTo"] = [
            {
                "slotId": raw_slot,
                "slotName": slot_label(raw_slot),
                "weaponIds": sorted(weapon_ids),
            }
            for raw_slot, weapon_ids in sorted(slots.items())
        ]
    for weapon_id, slots in magazine_slots.items():
        items[weapon_id]["magazineSlots"] = [
            {
                "id": raw_slot,
                "name": "Магазин" if "magazine" in raw_slot.casefold() else raw_slot,
                "compatibleItemIds": sorted(magazine_ids),
                "loadedItemIds": sorted(loaded[weapon_id].get(raw_slot, set())),
            }
            for raw_slot, magazine_ids in sorted(slots.items())
        ]
    for magazine_id, weapon_ids in magazine_weapons.items():
        items[magazine_id]["compatibleWeaponIds"] = sorted(weapon_ids)

    # Materialize the magazine -> cartridge -> projectile path so a future
    # damage/falloff calculator does not have to rediscover the graph.
    for weapon_id in sorted(set(attachment_slots) | set(magazine_slots)):
        paths: list[dict[str, Any]] = []
        magazines = {
            magazine_id
            for values in magazine_slots.get(weapon_id, {}).values()
            for magazine_id in values
        }
        if not magazines:
            magazines = {
                str(relation["to"])
                for relation in outgoing.get(weapon_id, [])
                if relation.get("type") == "loadedWith"
                and "BallisticAmmoProvider"
                in items.get(str(relation.get("to")), {}).get("componentTypes", [])
                and "Gun"
                not in items.get(str(relation.get("to")), {}).get("componentTypes", [])
            }
        for magazine_id in sorted(magazines):
            cartridges = sorted(
                {
                    str(relation["to"])
                    for relation in outgoing.get(magazine_id, [])
                    if relation.get("type") == "loadedWith"
                }
            )
            projectiles = sorted(
                {
                    str(relation["to"])
                    for cartridge_id in cartridges
                    for relation in outgoing.get(cartridge_id, [])
                    if relation.get("type") == "fires"
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


def populate_content_summaries(
    items: dict[str, Any],
    relations: list[dict[str, Any]],
    public_item_ids: set[str],
    aliases: dict[str, str],
) -> None:
    """Expose the resolved item graph in the public catalog.

    `index.json` keeps the complete diagnostic edge list. Cards get their own
    normalized outgoing edges so the web app can show crates, headset keys,
    installed attachments, loaded ammunition and projectile chains without
    having to read the technical index.
    """
    contents: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relations:
        source = aliases.get(str(relation.get("from", "")), str(relation.get("from", "")))
        target = aliases.get(str(relation.get("to", "")), str(relation.get("to", "")))
        if source not in public_item_ids or target not in items or source == target:
            continue
        summary = {
            "type": relation.get("type"),
            "itemId": target,
        }
        for key in ("quantity", "position", "slot", "container", "variant", "provider"):
            if key in relation:
                summary[key] = copy.deepcopy(relation[key])
        outgoing[source].append(summary)
        if relation.get("type") in PHYSICAL_CONTENT_RELATION_TYPES:
            contents[source].add(target)
    for source, edges in outgoing.items():
        items[source]["relationships"] = sorted(
            edges,
            key=lambda edge: (
                str(edge.get("type", "")),
                int(edge.get("position", -1)),
                str(edge.get("slot", "")),
                str(edge.get("itemId", "")),
            ),
        )
    for source, target_ids in contents.items():
        items[source]["containsItemIds"] = sorted(
            target_ids,
            key=lambda item_id: (items[item_id]["name"].casefold(), item_id),
        )


def build_catalog(
    prototypes: dict[str, EntityPrototype],
    config: dict[str, Any],
    localizer: Localizer,
    game_commit: str,
    item_sizes: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolver = PrototypeResolver(prototypes)
    required_vendor_ids = [entry["id"] for entry in config["vendors"]]
    # Source scope is deliberately explicit. A newly added ColMarTech prototype
    # must be reviewed and added to config before it can affect the catalog.
    vendor_ids = list(dict.fromkeys(required_vendor_ids))
    cargo_catalog_ids = [entry["id"] for entry in config.get("cargoCatalogs", [])]
    source_ids = [*vendor_ids, *cargo_catalog_ids]
    vendors: dict[str, Any] = {}
    trade_entries: list[dict[str, Any]] = []
    availability_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reachable_vendors: dict[str, set[str]] = defaultdict(set)
    source_hints_by_item: dict[str, set[str]] = defaultdict(set)
    transport_container_ids: set[str] = set()
    item_ids: set[str] = set()
    queue: deque[str] = deque()

    for vendor_id in vendor_ids:
        vendor = resolver.resolve(vendor_id)
        component = vendor["components"].get("CMAutomatedVendor")
        if not isinstance(component, dict):
            raise RuntimeError(f"Vendor {vendor_id} has no CMAutomatedVendor")
        sections = component.get("sections")
        if not isinstance(sections, list) or not sections:
            raise RuntimeError(f"Vendor {vendor_id} has no sections")

        vendor_sections: list[dict[str, Any]] = []
        for section_index, raw_section in enumerate(sections):
            if not isinstance(raw_section, dict):
                continue
            raw_entries = raw_section.get("entries")
            if not isinstance(raw_entries, list):
                continue
            section_name = raw_section.get("name")
            if not isinstance(section_name, str):
                section_name = f"Section {section_index + 1}"
            section_key = f"{vendor_id}:{section_index}"
            section_trade_keys: list[str] = []
            category_hint = source_category_hint(section_name)

            for entry_index, raw_entry in enumerate(raw_entries):
                if not isinstance(raw_entry, dict):
                    continue
                item_id = raw_entry.get("id")
                if not isinstance(item_id, str):
                    raise RuntimeError(
                        f"Vendor entry without id: {vendor_id}/{section_name}/{entry_index}"
                    )
                if item_id not in prototypes:
                    raise RuntimeError(
                        f"Vendor {vendor_id} references unknown item {item_id}"
                    )
                trade_key = f"{vendor_id}:{section_index}:{entry_index}"
                item = resolver.resolve(item_id)
                display_name = raw_entry.get("name")
                if not isinstance(display_name, str):
                    display_name = localizer.entity_text(
                        item_id, None, item["fields"].get("name")
                    )

                trade: dict[str, Any] = {
                    "key": trade_key,
                    "vendorId": vendor_id,
                    "sectionKey": section_key,
                    "sectionName": section_name,
                    "position": entry_index,
                    "itemId": item_id,
                    "name": display_name,
                    "amount": raw_entry.get("amount"),
                    "spawn": raw_entry.get("spawn", 1),
                }
                stock_item = raw_entry.get("box")
                if isinstance(stock_item, str):
                    if stock_item not in prototypes:
                        raise RuntimeError(
                            f"Trade {trade_key} references unknown stock item {stock_item}"
                        )
                    trade["stock"] = {
                        "itemId": stock_item,
                        "amount": raw_entry.get("boxAmount"),
                        "slots": raw_entry.get("boxSlots"),
                    }
                for key in (
                    "points",
                    "recommended",
                    "multiplier",
                    "max",
                    "linkedEntries",
                ):
                    if key in raw_entry:
                        trade[key] = copy.deepcopy(raw_entry[key])

                trade_entries.append(trade)
                section_trade_keys.append(trade_key)
                availability = {
                    "vendorId": vendor_id,
                    "sourceType": "vendor",
                    "sectionKey": section_key,
                    "sectionName": section_name,
                    "tradeKey": trade_key,
                }
                for key in (
                    "amount",
                    "spawn",
                    "points",
                    "recommended",
                    "multiplier",
                    "max",
                    "linkedEntries",
                    "stock",
                ):
                    if key in trade and trade[key] is not None:
                        availability[key] = copy.deepcopy(trade[key])
                availability_by_item[item_id].append(availability)
                if vendor_id not in reachable_vendors[item_id]:
                    reachable_vendors[item_id].add(vendor_id)
                if category_hint:
                    source_hints_by_item[item_id].add(category_hint)
                if item_id not in item_ids:
                    item_ids.add(item_id)
                    queue.append(item_id)
                if isinstance(stock_item, str):
                    stock_availability = copy.deepcopy(availability)
                    stock_availability["stockForItemId"] = item_id
                    availability_by_item[stock_item].append(stock_availability)
                    reachable_vendors[stock_item].add(vendor_id)
                    if category_hint:
                        source_hints_by_item[stock_item].add(category_hint)
                    if stock_item not in item_ids:
                        item_ids.add(stock_item)
                        queue.append(stock_item)

            vendor_sections.append(
                {
                    "key": section_key,
                    "name": section_name,
                    "position": section_index,
                    "hasBoxes": bool(raw_section.get("hasBoxes", False)),
                    "tradeKeys": section_trade_keys,
                }
            )

        vendors[vendor_id] = {
            "id": vendor_id,
            "name": localizer.entity_text(
                vendor_id, None, vendor["fields"].get("name")
            ),
            "description": localizer.entity_text(
                vendor_id, "desc", vendor["fields"].get("description")
            ),
            "sourceFile": vendor["sourceFile"],
            "sections": vendor_sections,
        }

    for catalog_id in cargo_catalog_ids:
        catalog_source = resolver.resolve(catalog_id)
        component = catalog_source["components"].get("RequisitionsComputer")
        if not isinstance(component, dict):
            raise RuntimeError(
                f"Cargo catalog {catalog_id} has no RequisitionsComputer"
            )
        categories = component.get("categories")
        if not isinstance(categories, list) or not categories:
            raise RuntimeError(f"Cargo catalog {catalog_id} has no categories")

        catalog_sections: list[dict[str, Any]] = []
        for section_index, raw_section in enumerate(categories):
            if not isinstance(raw_section, dict):
                continue
            section_name = raw_section.get("name")
            if not isinstance(section_name, str):
                section_name = f"Section {section_index + 1}"
            raw_entries = raw_section.get("entries")
            if not isinstance(raw_entries, list):
                continue
            section_key = f"{catalog_id}:cargo:{section_index}"
            section_trade_keys: list[str] = []
            category_hint = source_category_hint(section_name)

            for entry_index, raw_entry in enumerate(raw_entries):
                if not isinstance(raw_entry, dict):
                    continue
                payload_ids: list[tuple[str, bool]] = []
                crate_id = raw_entry.get("crate")
                if isinstance(crate_id, str):
                    payload_ids.append((crate_id, True))
                    transport_container_ids.add(crate_id)
                extras = raw_entry.get("entities")
                if isinstance(extras, list):
                    payload_ids.extend(
                        (item_id, False)
                        for item_id in extras
                        if isinstance(item_id, str)
                    )

                for payload_index, (item_id, is_transport) in enumerate(payload_ids):
                    if item_id not in prototypes:
                        raise RuntimeError(
                            f"Cargo catalog {catalog_id} references unknown item {item_id}"
                        )
                    kind = "crate" if is_transport else f"entity{payload_index}"
                    trade_key = (
                        f"{catalog_id}:cargo:{section_index}:{entry_index}:{kind}"
                    )
                    item = resolver.resolve(item_id)
                    trade: dict[str, Any] = {
                        "key": trade_key,
                        "vendorId": catalog_id,
                        "sourceType": "cargo",
                        "sectionKey": section_key,
                        "sectionName": section_name,
                        "position": entry_index,
                        "itemId": item_id,
                        "name": localizer.entity_text(
                            item_id, None, item["fields"].get("name")
                        ),
                        "transportContainer": is_transport,
                    }
                    if "cost" in raw_entry:
                        trade["cost"] = copy.deepcopy(raw_entry["cost"])
                    trade_entries.append(trade)
                    section_trade_keys.append(trade_key)
                    availability = {
                        "vendorId": catalog_id,
                        "sourceType": "cargo",
                        "sectionKey": section_key,
                        "sectionName": section_name,
                        "tradeKey": trade_key,
                        "transportContainer": is_transport,
                    }
                    if "cost" in trade:
                        availability["cost"] = copy.deepcopy(trade["cost"])
                    availability_by_item[item_id].append(availability)
                    reachable_vendors[item_id].add(catalog_id)
                    if category_hint:
                        source_hints_by_item[item_id].add(category_hint)
                    if item_id not in item_ids:
                        item_ids.add(item_id)
                        queue.append(item_id)

            catalog_sections.append(
                {
                    "key": section_key,
                    "name": section_name,
                    "position": section_index,
                    "tradeKeys": section_trade_keys,
                }
            )

        vendors[catalog_id] = {
            "id": catalog_id,
            "type": "cargo",
            "name": localizer.entity_text(
                catalog_id, None, catalog_source["fields"].get("name")
            ),
            "description": localizer.entity_text(
                catalog_id, "desc", catalog_source["fields"].get("description")
            ),
            "sourceFile": catalog_source["sourceFile"],
            "sections": catalog_sections,
        }

    relations: list[dict[str, Any]] = []
    relation_keys: set[str] = set()
    outgoing: dict[str, list[str]] = defaultdict(list)

    while queue:
        item_id = queue.popleft()
        resolved = resolver.resolve(item_id)
        for relation in content_relations(item_id, resolved):
            target = relation["to"]
            if target not in prototypes:
                raise RuntimeError(
                    f"{item_id} has {relation['type']} relation to unknown entity {target}"
                )
            if add_relation(relations, relation_keys, relation):
                outgoing[item_id].append(target)
            changed = False
            for vendor_id in reachable_vendors[item_id]:
                if vendor_id not in reachable_vendors[target]:
                    reachable_vendors[target].add(vendor_id)
                    changed = True
            before_hints = len(source_hints_by_item[target])
            source_hints_by_item[target].update(source_hints_by_item[item_id])
            if len(source_hints_by_item[target]) != before_hints:
                changed = True
            if target not in item_ids:
                item_ids.add(target)
                queue.append(target)
            elif changed:
                queue.append(target)

    # Source propagation can revisit a node after its relations were added. The
    # relation set de-duplicates those visits while the vendor provenance flows.
    provenance_queue = deque(sorted(item_ids))
    while provenance_queue:
        source = provenance_queue.popleft()
        for target in outgoing.get(source, []):
            before = len(reachable_vendors[target])
            reachable_vendors[target].update(reachable_vendors[source])
            before_hints = len(source_hints_by_item[target])
            source_hints_by_item[target].update(source_hints_by_item[source])
            if (
                len(reachable_vendors[target]) != before
                or len(source_hints_by_item[target]) != before_hints
            ):
                provenance_queue.append(target)

    add_compatibility_relations(item_ids, resolver, relations, relation_keys)

    items: dict[str, Any] = {}
    for item_id in sorted(item_ids):
        items[item_id] = build_card(
            item_id,
            resolver.resolve(item_id),
            localizer,
            availability_by_item.get(item_id, []),
            reachable_vendors[item_id],
            source_hints_by_item[item_id],
        )

    relations.sort(
        key=lambda item: (
            item["from"],
            item["type"],
            item["to"],
            str(item.get("slot", "")),
            int(item.get("position", -1)),
        )
    )
    trade_entries.sort(key=lambda item: item["key"])

    public_catalog = build_public_catalog(
        trade_entries,
        items,
        relations,
        transport_container_ids,
        config.get("classification", {}),
    )
    populate_compatibility_summaries(
        items,
        relations,
        set(public_catalog["itemIds"]),
        public_catalog["aliases"],
    )
    populate_content_summaries(
        items,
        relations,
        set(public_catalog["itemIds"]),
        public_catalog["aliases"],
    )
    populate_communication_statistics(items, set(public_catalog["itemIds"]))
    populate_solution_statistics(items, set(public_catalog["itemIds"]))
    populate_weapon_statistics(
        items,
        relations,
        set(public_catalog["itemIds"]),
    )
    populate_armor_statistics(items, set(public_catalog["itemIds"]))
    populate_attachment_statistics(items, set(public_catalog["itemIds"]))
    populate_storage_statistics(
        items,
        set(public_catalog["itemIds"]),
        item_sizes,
    )

    source_counts = {
        "indexedEntityPrototypes": len(prototypes),
        "vendors": len(vendor_ids),
        "cargoCatalogs": len(cargo_catalog_ids),
        "sources": len(vendors),
        "sections": sum(len(vendor["sections"]) for vendor in vendors.values()),
        "tradeEntries": len(trade_entries),
        "directItemPrototypes": len(availability_by_item),
        "catalogItems": len(items),
        "publicItems": len(public_catalog["itemIds"]),
        "excludedItems": len(public_catalog["excludedItemIds"]),
        "relations": len(relations),
    }

    # Keep purchase offers and normalized card relationships in the public API.
    # Only parser/debug provenance stays exclusive to index.json.
    provenance_keys = {
        "origin",
        "sourceFile",
        "parents",
        "abstract",
        "sourceCategoryHints",
        "reachableFromVendors",
    }
    for item in items.values():
        item.pop("itemSize", None)
        item.pop("itemShape", None)
        properties = item.get("properties")
        if isinstance(properties, dict):
            properties.pop("Item", None)
        for key in provenance_keys:
            item.pop(key, None)

    counts = {
        "catalogItems": len(items),
        "publicItems": len(public_catalog["itemIds"]),
        "excludedItems": len(public_catalog["excludedItemIds"]),
    }

    public_sources = {
        source_id: {
            key: copy.deepcopy(value)
            for key, value in source.items()
            if key != "sourceFile"
        }
        for source_id, source in sorted(vendors.items())
    }

    catalog = {
        "schemaVersion": 4,
        "gameCommit": game_commit,
        "source": "MetalSage/space-stories-cm14",
        "locale": "ru-RU",
        "sources": public_sources,
        "items": items,
        "publicCatalog": public_catalog,
        "counts": counts,
    }

    index = {
        "schemaVersion": 3,
        "gameCommit": game_commit,
        "source": "MetalSage/space-stories-cm14",
        "configuredVendorIds": vendor_ids,
        "configuredCargoCatalogIds": cargo_catalog_ids,
        "configuredSourceIds": source_ids,
        "vendors": vendors,
        "tradeEntries": trade_entries,
        "relations": relations,
        "counts": {
            **source_counts,
            "catalogEntityPrototypes": len(item_ids),
            "resolvedEntityPrototypes": len(resolver.cache),
        },
        "entries": {
            prototype_id: {
                "parents": list(prototype.parents),
                "abstract": prototype.abstract,
                "origin": prototype.origin,
                "sourceFile": prototype.source_file,
            }
            for prototype_id, prototype in sorted(prototypes.items())
            if prototype_id in item_ids
        },
    }
    return index, catalog
