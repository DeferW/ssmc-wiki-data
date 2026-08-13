from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def build_review_section(catalog: dict[str, Any]) -> dict[str, Any]:
    items = catalog["items"]
    public_catalog = catalog["publicCatalog"]

    def entry(item_id: str) -> dict[str, Any]:
        item = items[item_id]
        classification = item.get("classification", {})
        return {
            "id": item_id,
            "name": item.get("name", item_id),
            "reason": classification.get("reason", ""),
            "signals": classification.get("signals", []),
        }

    return {
        "policy": "catalog-v4-functional",
        "excluded": [
            entry(item_id) for item_id in public_catalog["excludedItemIds"]
        ],
    }


def print_previous_catalog_comparison(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> None:
    if not isinstance(previous, dict):
        print("Previous catalog comparison: unavailable")
        return
    previous_public = set(previous.get("publicCatalog", {}).get("itemIds", []))
    current_public = set(current["publicCatalog"]["itemIds"])
    current_excluded = set(current["publicCatalog"]["excludedItemIds"])
    previous_items = previous.get("items", {})
    current_items = current["items"]
    category_changes = sorted(
        item_id
        for item_id in previous_public & current_public
        if previous_items.get(item_id, {}).get("category")
        != current_items.get(item_id, {}).get("category")
    )
    print(f"New public items: {len(current_public - previous_public)}")
    print(f"Removed public items: {len(previous_public - current_public)}")
    print(
        "Previously public items now excluded: "
        f"{len(previous_public & current_excluded)}"
    )
    print(f"Public category changes: {len(category_changes)}")
