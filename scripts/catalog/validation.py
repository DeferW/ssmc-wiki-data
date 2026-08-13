from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from scripts.catalog.config import CatalogConfig, Override
from scripts.catalog.models import AUTOMATIC_CATEGORIES, CATEGORY_HIDDEN, CATEGORY_ORDER


def validate(
    catalog: dict[str, Any],
    index: dict[str, Any],
    config: CatalogConfig,
    overrides: dict[str, Override],
    sprites: Path,
) -> None:
    if catalog.get("schemaVersion") != 4 or index.get("schemaVersion") != 4:
        raise RuntimeError("Unexpected catalog schema version")
    if catalog.get("source") != index.get("source"):
        raise RuntimeError("Catalog and index source mismatch")
    if catalog.get("categoryOrder") != list(CATEGORY_ORDER):
        raise RuntimeError("Unexpected category order")
    if index.get("configuredSources") != {
        "vendors": list(config.vendor_ids),
        "cargoCatalogs": list(config.cargo_catalog_ids),
    }:
        raise RuntimeError("Configured sources do not match the index")

    items = catalog.get("items")
    categories = catalog.get("categories")
    facts = index.get("facts")
    relations = index.get("relations")
    if not isinstance(items, dict) or not items:
        raise RuntimeError("Catalog is empty")
    if not isinstance(categories, dict) or list(categories) != list(CATEGORY_ORDER):
        raise RuntimeError("Invalid catalog categories")
    if not isinstance(facts, dict) or set(facts) != set(items):
        raise RuntimeError("Catalog facts do not match items")
    if not isinstance(relations, list):
        raise RuntimeError("Invalid relation collection")

    categorized = [item_id for category in CATEGORY_ORDER for item_id in categories[category]]
    if len(categorized) != len(set(categorized)) or set(categorized) != set(items):
        raise RuntimeError("Categories must partition all catalog items")

    for item_id, item in items.items():
        if item.get("id") != item_id or item.get("category") not in CATEGORY_ORDER:
            raise RuntimeError(f"Invalid item card: {item_id}")
        classification = item.get("classification")
        if not isinstance(classification, dict):
            raise RuntimeError(f"Missing classification: {item_id}")
        automatic = classification.get("automaticCategory")
        final = classification.get("finalCategory")
        if automatic not in AUTOMATIC_CATEGORIES:
            raise RuntimeError(f"Automatic classifier used a forbidden category: {item_id}")
        if final != item["category"]:
            raise RuntimeError(f"Final category mismatch: {item_id}")
        expected_override = overrides.get(item_id)
        if final == CATEGORY_HIDDEN and (
            expected_override is None or expected_override.category != CATEGORY_HIDDEN
        ):
            raise RuntimeError(f"Hidden category was assigned automatically: {item_id}")
        expected_edited = final != automatic
        if classification.get("edited") is not expected_edited:
            raise RuntimeError(f"Incorrect edited flag: {item_id}")
        if expected_override and final != expected_override.category:
            raise RuntimeError(f"Override was not applied: {item_id}")

        image = item.get("image")
        if isinstance(item.get("sprite"), dict):
            if image != f"sprites/{item_id}.png":
                raise RuntimeError(f"Invalid image path: {item_id}")
            path = sprites / f"{item_id}.png"
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"Missing sprite: {item_id}")
            with Image.open(path) as image_file:
                if image_file.convert("RGBA").getbbox() is None:
                    raise RuntimeError(f"Transparent sprite: {item_id}")
        elif image is not None:
            raise RuntimeError(f"Sprite-less item has image path: {item_id}")

    unknown_overrides = sorted(set(overrides) - set(items))
    if unknown_overrides:
        raise RuntimeError("Stale overrides: " + ", ".join(unknown_overrides))
    for relation in relations:
        if relation.get("from") not in items or relation.get("to") not in items:
            raise RuntimeError(f"Relation references missing items: {relation}")

    counts = catalog.get("counts", {})
    expected_counts = {
        "items": len(items),
        "edited": sum(item["classification"]["edited"] for item in items.values()),
        "hiddenCategory": len(categories[CATEGORY_HIDDEN]),
    }
    if counts != expected_counts:
        raise RuntimeError(f"Catalog counts mismatch: {counts} != {expected_counts}")
