from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .core import (
    PUBLIC_CATEGORY_IDS_BY_LABEL,
    PUBLIC_CATEGORY_LABELS,
    PUBLIC_CATEGORY_ORDER,
)


def read_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Catalog config must be a mapping")
    vendors = data.get("vendors")
    cargo_catalogs = data.get("cargoCatalogs", [])
    if not isinstance(vendors, list) or not vendors:
        raise RuntimeError("Catalog config has no vendors")
    if not isinstance(cargo_catalogs, list):
        raise RuntimeError("Catalog cargoCatalogs must be a list")
    sources = [*vendors, *cargo_catalogs]
    ids = [entry.get("id") for entry in sources if isinstance(entry, dict)]
    if len(ids) != len(sources) or any(not isinstance(item, str) for item in ids):
        raise RuntimeError("Every configured source must have a string id")
    if len(set(ids)) != len(ids):
        raise RuntimeError("Duplicate source id in catalog config")
    if "vendorDiscoveryPrefixes" in data:
        raise RuntimeError(
            "Automatic vendor discovery is disabled; list every source under vendors"
        )
    policy = data.get("classification", {})
    if not isinstance(policy, dict):
        raise RuntimeError("Catalog classification policy must be a mapping")
    for key in ("excludePrototypeIds", "includePrototypeIds"):
        value = policy.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise RuntimeError(f"classification.{key} must be a list of ids")
    for key in ("categoryOverrides", "canonicalPrototypeIds"):
        value = policy.get(key, {})
        if not isinstance(value, dict) or any(
            not isinstance(item_id, str) or not isinstance(target, str)
            for item_id, target in value.items()
        ):
            raise RuntimeError(f"classification.{key} must map ids to strings")
    unknown_categories = set(policy.get("categoryOverrides", {}).values()) - set(
        PUBLIC_CATEGORY_LABELS
    )
    if unknown_categories:
        raise RuntimeError(
            "Unknown classification category ids: "
            + ", ".join(sorted(unknown_categories))
        )
    return data


def read_catalog_overrides(path: Path) -> dict[str, Any]:
    """Read explicit editorial category decisions.

    `Скрытые` is a regular category. There is deliberately no boolean visibility
    switch: the application receives every catalog card and decides what to show.
    """
    if not path.is_file():
        return {"schemaVersion": 2, "items": {}}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid catalog overrides JSON: {path}: {error}") from error
    if not isinstance(document, dict) or document.get("schemaVersion") != 2:
        raise RuntimeError("Catalog overrides must use schemaVersion 2")
    if set(document) != {"schemaVersion", "items"}:
        raise RuntimeError("Catalog overrides may contain only schemaVersion and items")
    raw_items = document.get("items")
    if not isinstance(raw_items, dict):
        raise RuntimeError("Catalog overrides items must be an object")

    normalized_items: dict[str, dict[str, str]] = {}
    for item_id, raw_override in raw_items.items():
        if not isinstance(item_id, str) or not item_id:
            raise RuntimeError("Catalog override item IDs must be non-empty strings")
        if not isinstance(raw_override, dict) or set(raw_override) != {"category"}:
            raise RuntimeError(
                f"Catalog override for {item_id} must contain only category"
            )
        category = raw_override["category"]
        if category not in PUBLIC_CATEGORY_IDS_BY_LABEL:
            raise RuntimeError(
                f"Unknown catalog category override for {item_id}: {category}"
            )
        normalized_items[item_id] = {"category": category}
    return {"schemaVersion": 2, "items": normalized_items}


def apply_catalog_overrides(
    catalog: dict[str, Any],
    index: dict[str, Any],
    document: dict[str, Any],
) -> None:
    """Apply editorial categories after automatic classification."""
    items = catalog["items"]
    public_catalog = catalog["publicCatalog"]
    candidate_ids = set(public_catalog["candidateItemIds"])
    public_ids = set(public_catalog["itemIds"])
    overrides = document["items"]

    for item_id in overrides:
        if item_id not in items:
            raise RuntimeError(f"Catalog override references unknown item: {item_id}")
        if item_id not in candidate_ids or item_id not in public_ids:
            raise RuntimeError(
                f"Catalog override target is not a published candidate: {item_id}"
            )

    edited_ids: list[str] = []
    for item_id, override in sorted(overrides.items()):
        item = items[item_id]
        automatic_category = item["category"]
        category = override["category"]
        category_id = PUBLIC_CATEGORY_IDS_BY_LABEL[category]
        classification = item.get("classification")
        if not isinstance(classification, dict):
            raise RuntimeError(f"Catalog item has no classification: {item_id}")
        classification["automaticCategory"] = automatic_category
        classification["automaticCategoryId"] = classification.get("categoryId")
        classification["category"] = category
        classification["categoryId"] = category_id
        classification["overriddenByAdministrator"] = True
        item["category"] = category
        item["types"] = [category_id]
        if category != automatic_category:
            item["edited"] = True
            edited_ids.append(item_id)

    sort_key = lambda value: (items[value]["name"].casefold(), value)
    ordered_public_ids = sorted(public_ids, key=sort_key)
    categories = {
        PUBLIC_CATEGORY_LABELS[category_id]: []
        for category_id in PUBLIC_CATEGORY_ORDER
    }
    for item_id in ordered_public_ids:
        categories[items[item_id]["category"]].append(item_id)

    public_catalog["itemIds"] = ordered_public_ids
    public_catalog["categories"] = categories
    public_catalog["aliases"] = {
        alias_id: canonical_id
        for alias_id, canonical_id in public_catalog["aliases"].items()
        if canonical_id in public_ids
    }
    hidden_ids = list(categories[PUBLIC_CATEGORY_LABELS["hidden"]])
    catalog["overrides"] = {
        "schemaVersion": 2,
        "appliedItemIds": sorted(overrides),
        "editedItemIds": edited_ids,
    }
    catalog["counts"]["editedItems"] = len(edited_ids)
    catalog["counts"]["hiddenItems"] = len(hidden_ids)
    index["counts"]["editedItems"] = len(edited_ids)
    index["counts"]["hiddenItems"] = len(hidden_ids)
