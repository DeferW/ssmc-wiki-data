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
        raise RuntimeError("Equipment config must be a mapping")
    vendors = data.get("vendors")
    cargo_catalogs = data.get("cargoCatalogs", [])
    if not isinstance(vendors, list) or not vendors:
        raise RuntimeError("Equipment config has no vendors")
    if not isinstance(cargo_catalogs, list):
        raise RuntimeError("Equipment cargoCatalogs must be a list")
    sources = [*vendors, *cargo_catalogs]
    ids = [entry.get("id") for entry in sources if isinstance(entry, dict)]
    if len(ids) != len(sources) or any(not isinstance(item, str) for item in ids):
        raise RuntimeError("Every configured source must have a string id")
    if len(set(ids)) != len(ids):
        raise RuntimeError("Duplicate source id in equipment config")
    if "vendorDiscoveryPrefixes" in data:
        raise RuntimeError(
            "Automatic vendor discovery is disabled; list every source under vendors"
        )
    policy = data.get("classification", {})
    if not isinstance(policy, dict):
        raise RuntimeError("Equipment classification policy must be a mapping")
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
            "Unknown classification category overrides: "
            + ", ".join(sorted(unknown_categories))
        )
    return data


def read_catalog_overrides(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schemaVersion": 1, "items": {}}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid catalog overrides JSON: {path}: {error}") from error
    if not isinstance(document, dict) or document.get("schemaVersion") != 1:
        raise RuntimeError("Catalog overrides must use schemaVersion 1")
    if set(document) != {"schemaVersion", "items"}:
        raise RuntimeError(
            "Catalog overrides may contain only schemaVersion and items"
        )
    raw_items = document.get("items")
    if not isinstance(raw_items, dict):
        raise RuntimeError("Catalog overrides items must be an object")

    normalized_items: dict[str, dict[str, Any]] = {}
    for item_id, raw_override in raw_items.items():
        if not isinstance(item_id, str) or not item_id:
            raise RuntimeError("Catalog override item IDs must be non-empty strings")
        if not isinstance(raw_override, dict) or not raw_override:
            raise RuntimeError(f"Catalog override for {item_id} must be a non-empty object")
        unknown_fields = set(raw_override) - {"category", "hidden"}
        if unknown_fields:
            raise RuntimeError(
                f"Unknown catalog override fields for {item_id}: "
                + ", ".join(sorted(unknown_fields))
            )
        normalized: dict[str, Any] = {}
        if "category" in raw_override:
            category = raw_override["category"]
            if category not in PUBLIC_CATEGORY_IDS_BY_LABEL:
                raise RuntimeError(
                    f"Unknown catalog category override for {item_id}: {category}"
                )
            normalized["category"] = category
        if "hidden" in raw_override:
            hidden = raw_override["hidden"]
            if not isinstance(hidden, bool):
                raise RuntimeError(
                    f"Catalog hidden override for {item_id} must be boolean"
                )
            normalized["hidden"] = hidden
        normalized_items[item_id] = normalized
    return {"schemaVersion": 1, "items": normalized_items}


def prune_hidden_catalog_references(
    items: dict[str, Any],
    public_item_ids: set[str],
    hidden_item_ids: set[str],
) -> None:
    """Prevent hidden cards from resurfacing through public detail links."""
    if not hidden_item_ids:
        return

    def keep_ids(values: Any) -> Any:
        if not isinstance(values, list):
            return values
        return [value for value in values if value not in hidden_item_ids]

    for item_id in public_item_ids:
        item = items[item_id]
        for key in ("containsItemIds", "compatibleWeaponIds"):
            if key in item:
                item[key] = keep_ids(item[key])

        for key in ("attachmentSlots", "magazineSlots"):
            slots = item.get(key)
            if not isinstance(slots, list):
                continue
            for slot in slots:
                if not isinstance(slot, dict):
                    continue
                for id_key in (
                    "compatibleItemIds",
                    "installedItemIds",
                    "loadedItemIds",
                ):
                    if id_key in slot:
                        slot[id_key] = keep_ids(slot[id_key])

        attachable_to = item.get("attachableTo")
        if isinstance(attachable_to, list):
            for slot in attachable_to:
                if isinstance(slot, dict) and "weaponIds" in slot:
                    slot["weaponIds"] = keep_ids(slot["weaponIds"])

        storage_stats = item.get("storageStats")
        if isinstance(storage_stats, dict) and "acceptedItemIds" in storage_stats:
            storage_stats["acceptedItemIds"] = keep_ids(
                storage_stats["acceptedItemIds"]
            )

        loadouts = item.get("loadoutVariants")
        if isinstance(loadouts, list):
            for loadout in loadouts:
                if isinstance(loadout, dict) and "contentItemIds" in loadout:
                    loadout["contentItemIds"] = keep_ids(loadout["contentItemIds"])

        paths = item.get("ammunitionPaths")
        if isinstance(paths, list):
            item["ammunitionPaths"] = [
                path
                for path in paths
                if isinstance(path, dict)
                and path.get("magazineId") not in hidden_item_ids
            ]

        weapon_stats = item.get("weaponStats")
        if isinstance(weapon_stats, dict) and isinstance(
            weapon_stats.get("ammunition"), list
        ):
            weapon_stats["ammunition"] = [
                entry
                for entry in weapon_stats["ammunition"]
                if isinstance(entry, dict)
                and entry.get("magazineId") not in hidden_item_ids
                and entry.get("ammoId") not in hidden_item_ids
            ]


def apply_catalog_overrides(
    catalog: dict[str, Any],
    index: dict[str, Any],
    document: dict[str, Any],
) -> None:
    """Apply administrator decisions after automatic catalog generation."""
    items = catalog["items"]
    public_catalog = catalog["publicCatalog"]
    base_public_ids = set(public_catalog["itemIds"])
    candidate_ids = set(public_catalog["candidateItemIds"])
    overrides = document["items"]

    for item_id in overrides:
        if item_id not in items:
            raise RuntimeError(f"Catalog override references unknown item: {item_id}")
        if item_id not in candidate_ids:
            raise RuntimeError(
                f"Catalog override target is not a publication candidate: {item_id}"
            )
        if item_id not in base_public_ids:
            raise RuntimeError(
                f"Catalog override target is not automatically public: {item_id}"
            )

    hidden_ids = {
        item_id
        for item_id, override in overrides.items()
        if override.get("hidden") is True
    }
    category_override_ids: list[str] = []
    for item_id, override in sorted(overrides.items()):
        item = items[item_id]
        category = override.get("category")
        if isinstance(category, str):
            category_id = PUBLIC_CATEGORY_IDS_BY_LABEL[category]
            item["category"] = category
            item["types"] = [category_id]
            classification = item.get("classification")
            if not isinstance(classification, dict):
                raise RuntimeError(f"Catalog override target has no classification: {item_id}")
            classification["category"] = category
            classification["categoryId"] = category_id
            classification["overriddenByAdministrator"] = True
            category_override_ids.append(item_id)
        if item_id in hidden_ids:
            item["public"] = False
            item["hiddenByAdministrator"] = True
        else:
            item.pop("hiddenByAdministrator", None)

    sort_key = lambda value: (items[value]["name"].casefold(), value)
    final_public_ids = sorted(base_public_ids - hidden_ids, key=sort_key)
    categories = {
        PUBLIC_CATEGORY_LABELS[category_id]: []
        for category_id in PUBLIC_CATEGORY_ORDER
    }
    for item_id in final_public_ids:
        categories[items[item_id]["category"]].append(item_id)

    public_catalog["itemIds"] = final_public_ids
    public_catalog["categories"] = categories
    public_catalog["hiddenItemIds"] = sorted(hidden_ids, key=sort_key)
    public_catalog["aliases"] = {
        alias_id: canonical_id
        for alias_id, canonical_id in public_catalog["aliases"].items()
        if canonical_id in set(final_public_ids)
    }
    prune_hidden_catalog_references(items, set(final_public_ids), hidden_ids)

    catalog["overrides"] = {
        "schemaVersion": 1,
        "appliedItemIds": sorted(overrides),
        "categoryItemIds": category_override_ids,
        "hiddenItemIds": sorted(hidden_ids),
    }
    catalog["counts"]["publicItems"] = len(final_public_ids)
    catalog["counts"]["hiddenItems"] = len(hidden_ids)
    index["counts"]["publicItems"] = len(final_public_ids)
    index["counts"]["hiddenItems"] = len(hidden_ids)
