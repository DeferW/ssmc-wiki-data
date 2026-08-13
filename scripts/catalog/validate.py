from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

from scripts.catalog.core import (
    PHYSICAL_CONTENT_RELATION_TYPES,
    PUBLIC_CATEGORY_LABELS,
    PUBLIC_CATEGORY_ORDER,
)
from scripts.catalog.config import read_catalog_overrides


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return data


def configured_source_ids(path: Path) -> tuple[list[str], list[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Invalid catalog source config")

    def ids(key: str) -> list[str]:
        values = data.get(key, [])
        if not isinstance(values, list):
            raise RuntimeError(f"config.{key} must be a list")
        result = []
        for value in values:
            if not isinstance(value, dict) or not isinstance(value.get("id"), str):
                raise RuntimeError(f"Invalid source under config.{key}")
            result.append(value["id"])
        return result

    return ids("vendors"), ids("cargoCatalogs")


def fail_if(condition: bool, message: str) -> None:
    if condition:
        raise RuntimeError(message)


def validate(
    catalog: dict[str, Any],
    index: dict[str, Any],
    config_path: Path,
    sprites_path: Path,
    overrides: dict[str, Any],
) -> None:
    fail_if(catalog.get("schemaVersion") != 4, "Catalog must use schemaVersion 4")
    fail_if(index.get("schemaVersion") != 3, "Index must use schemaVersion 3")
    fail_if(catalog.get("gameCommit") != index.get("gameCommit"), "Commit mismatch")

    items = catalog.get("items")
    public_catalog = catalog.get("publicCatalog")
    sources = catalog.get("sources")
    relations = index.get("relations")
    trades = index.get("tradeEntries")
    fail_if(not isinstance(items, dict), "Catalog items must be an object")
    fail_if(not isinstance(public_catalog, dict), "Missing publicCatalog")
    fail_if(not isinstance(sources, dict), "Missing public sources")
    fail_if(not isinstance(relations, list), "Index relations must be a list")
    fail_if(not isinstance(trades, list), "Index tradeEntries must be a list")

    vendor_ids, cargo_ids = configured_source_ids(config_path)
    expected_sources = [*vendor_ids, *cargo_ids]
    fail_if(
        index.get("configuredVendorIds") != vendor_ids,
        "Configured vendor ids do not match index",
    )
    fail_if(
        index.get("configuredCargoCatalogIds") != cargo_ids,
        "Configured cargo ids do not match index",
    )
    fail_if(set(sources) != set(expected_sources), "Public source list is incomplete")

    public_ids = public_catalog.get("itemIds")
    candidate_ids = public_catalog.get("candidateItemIds")
    excluded_ids = public_catalog.get("excludedItemIds")
    categories = public_catalog.get("categories")
    for name, value in (
        ("itemIds", public_ids),
        ("candidateItemIds", candidate_ids),
        ("excludedItemIds", excluded_ids),
    ):
        fail_if(not isinstance(value, list), f"publicCatalog.{name} must be a list")
    fail_if(not isinstance(categories, dict), "publicCatalog.categories must be an object")
    expected_categories = [
        PUBLIC_CATEGORY_LABELS[category_id] for category_id in PUBLIC_CATEGORY_ORDER
    ]
    fail_if(list(categories) != expected_categories, "Category order or labels changed")
    flat_categories = [item_id for ids in categories.values() for item_id in ids]
    fail_if(Counter(flat_categories) != Counter(public_ids), "Categories do not partition items")
    fail_if(set(public_ids) | set(excluded_ids) != set(candidate_ids), "Candidate partition is invalid")
    fail_if(set(public_ids).intersection(excluded_ids), "Published and excluded ids overlap")

    for item_id in public_ids:
        item = items.get(item_id)
        fail_if(not isinstance(item, dict), f"Missing public item: {item_id}")
        for field in ("id", "name", "description", "category", "classification"):
            fail_if(field not in item, f"{item_id} has no {field}")
        fail_if(item.get("id") != item_id, f"Item id mismatch: {item_id}")
        category = item.get("category")
        fail_if(category not in categories, f"Unknown item category: {item_id}")
        fail_if(item_id not in categories[category], f"Category membership mismatch: {item_id}")
        if "Gun" in item.get("componentTypes", []):
            fail_if(not isinstance(item.get("weaponStats"), dict), f"Gun has no stats: {item_id}")
        if "Attachable" in item.get("componentTypes", []):
            fail_if(
                not isinstance(item.get("attachmentStats"), dict),
                f"Attachment has no stats: {item_id}",
            )
        for block in (
            "weaponStats",
            "armorStats",
            "attachmentStats",
            "storageStats",
            "solutionStats",
            "communicationStats",
            "skillStats",
        ):
            fail_if(block in item and not isinstance(item[block], dict), f"Invalid {block}: {item_id}")
        for offer in item.get("availability", []):
            fail_if(not isinstance(offer, dict), f"Invalid offer: {item_id}")
            fail_if(not isinstance(offer.get("tradeKey"), str), f"Offer has no key: {item_id}")

    for item_id in categories[PUBLIC_CATEGORY_LABELS["hidden"]]:
        fail_if(item_id not in overrides.get("items", {}), f"Hidden item lacks override: {item_id}")

    override_items = overrides.get("items")
    fail_if(overrides.get("schemaVersion") != 2, "Overrides must use schemaVersion 2")
    fail_if(not isinstance(override_items, dict), "Overrides items must be an object")
    edited_ids: list[str] = []
    for item_id, override in override_items.items():
        fail_if(item_id not in public_ids, f"Override target is not published: {item_id}")
        fail_if(not isinstance(override, dict), f"Invalid override: {item_id}")
        category = override.get("category")
        fail_if(items[item_id].get("category") != category, f"Override not applied: {item_id}")
        automatic = items[item_id].get("classification", {}).get("automaticCategory")
        if automatic != category:
            edited_ids.append(item_id)
            fail_if(items[item_id].get("edited") is not True, f"Missing edited marker: {item_id}")
        else:
            fail_if("edited" in items[item_id], f"Redundant edited marker: {item_id}")
    expected_override_summary = {
        "schemaVersion": 2,
        "appliedItemIds": sorted(override_items),
        "editedItemIds": sorted(edited_ids),
    }
    fail_if(catalog.get("overrides") != expected_override_summary, "Override summary mismatch")

    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relations:
        fail_if(not isinstance(relation, dict), "Invalid relation")
        source = relation.get("from")
        target = relation.get("to")
        fail_if(source not in items or target not in items, f"Dangling relation: {relation}")
        outgoing[str(source)].append(relation)
    for item_id in public_ids:
        card_edges = items[item_id].get("relationships", [])
        fail_if(not isinstance(card_edges, list), f"Invalid relationships: {item_id}")
        edge_pairs = {(edge.get("type"), edge.get("itemId")) for edge in card_edges}
        content_ids = set(items[item_id].get("containsItemIds", []))
        for relation in outgoing.get(item_id, []):
            pair = (relation.get("type"), relation.get("to"))
            fail_if(pair not in edge_pairs, f"Public relationship missing: {item_id} {pair}")
            if relation.get("type") in PHYSICAL_CONTENT_RELATION_TYPES:
                fail_if(relation.get("to") not in content_ids, f"Content link missing: {item_id} {pair}")

    trade_by_key = {
        trade.get("key"): trade for trade in trades if isinstance(trade, dict)
    }
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        item = items.get(trade.get("itemId"))
        fail_if(not isinstance(item, dict), f"Trade points to unknown item: {trade}")
        offers = [
            offer
            for offer in item.get("availability", [])
            if offer.get("tradeKey") == trade.get("key")
        ]
        fail_if(not offers, f"Trade offer missing from catalog: {trade.get('key')}")
        if trade.get("sourceType") == "cargo" and "cost" in trade:
            fail_if(offers[0].get("cost") != trade["cost"], f"Cargo cost lost: {trade.get('key')}")
    offer_keys = {
        offer.get("tradeKey")
        for item in items.values()
        for offer in item.get("availability", [])
        if isinstance(offer, dict)
    }
    fail_if(not offer_keys.issubset(trade_by_key), "Catalog has unknown offer keys")

    expected_pngs = set()
    for item_id in public_ids:
        sprite = items[item_id].get("sprite")
        if not isinstance(sprite, dict) or not isinstance(sprite.get("file"), str):
            continue
        filename = sprite["file"]
        expected_pngs.add(filename)
        path = sprites_path / filename
        fail_if(not path.is_file(), f"Missing sprite: {filename}")
        with Image.open(path) as image:
            fail_if(image.format != "PNG", f"Sprite is not PNG: {filename}")
    actual_pngs = {path.name for path in sprites_path.glob("*.png")}
    fail_if(actual_pngs != expected_pngs, "Sprite directory contains missing or stale files")

    counts = catalog.get("counts", {})
    fail_if(counts.get("catalogItems") != len(items), "Catalog item count mismatch")
    fail_if(counts.get("publicItems") != len(public_ids), "Public item count mismatch")
    fail_if(counts.get("excludedItems") != len(excluded_ids), "Excluded count mismatch")
    fail_if(counts.get("editedItems") != len(edited_ids), "Edited count mismatch")
    fail_if(
        counts.get("hiddenItems") != len(categories[PUBLIC_CATEGORY_LABELS["hidden"]]),
        "Hidden category count mismatch",
    )

    print(f"Sources: {len(sources)}")
    print(f"Trade entries: {len(trades)}")
    print(f"Catalog items: {len(items)}")
    print(f"Published items: {len(public_ids)}")
    print(f"Items in Скрытые: {len(categories[PUBLIC_CATEGORY_LABELS['hidden']])}")
    print(f"Relations: {len(relations)}")
    print("Catalog validation passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate catalog outputs")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--sprites", type=Path, required=True)
    parser.add_argument("--overrides", type=Path)
    args = parser.parse_args()
    overrides_path = args.overrides or args.config.parent / "catalog-overrides.json"
    validate(
        read_json(args.catalog),
        read_json(args.index),
        args.config,
        args.sprites,
        read_catalog_overrides(overrides_path),
    )


if __name__ == "__main__":
    main()
