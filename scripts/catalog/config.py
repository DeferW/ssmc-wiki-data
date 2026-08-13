from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from scripts.catalog.models import CATEGORY_ORDER, normalized_category
from scripts.common.io import read_json


@dataclass(frozen=True)
class CatalogConfig:
    vendor_ids: tuple[str, ...]
    cargo_catalog_ids: tuple[str, ...]


@dataclass(frozen=True)
class Override:
    category: str


def _source_ids(value: Any, field: str, *, required: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or (required and not value):
        raise RuntimeError(f"{field} must be a non-empty list" if required else f"{field} must be a list")
    ids: list[str] = []
    for entry in value:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise RuntimeError(f"Every {field} entry must have a string id")
        ids.append(entry["id"])
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"Duplicate source id in {field}")
    return tuple(ids)


def read_config(path: Path) -> CatalogConfig:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Catalog config must be a mapping")
    if value.get("schemaVersion") != 4:
        raise RuntimeError("Catalog config must use schemaVersion 4")
    config = CatalogConfig(
        vendor_ids=_source_ids(value.get("vendors"), "vendors", required=True),
        cargo_catalog_ids=_source_ids(
            value.get("cargoCatalogs", []), "cargoCatalogs", required=False
        ),
    )
    if set(config.vendor_ids).intersection(config.cargo_catalog_ids):
        raise RuntimeError("A source ID cannot be both a vendor and a cargo catalog")
    return config


def read_overrides(path: Path) -> dict[str, Override]:
    if not path.is_file():
        return {}
    value = read_json(path)
    if value.get("schemaVersion") != 2:
        raise RuntimeError("Catalog overrides must use schemaVersion 2")
    raw_items = value.get("items")
    if not isinstance(raw_items, dict):
        raise RuntimeError("Catalog overrides items must be an object")

    result: dict[str, Override] = {}
    for item_id, raw in raw_items.items():
        if not isinstance(item_id, str) or not item_id or not isinstance(raw, dict):
            raise RuntimeError("Invalid catalog override entry")
        unknown = set(raw) - {"category"}
        if unknown:
            raise RuntimeError(
                f"Unknown override fields for {item_id}: {', '.join(sorted(unknown))}"
            )
        category = raw.get("category")
        if not isinstance(category, str):
            raise RuntimeError(f"Override {item_id} must assign a category")
        category = normalized_category(category)
        if category not in CATEGORY_ORDER:
            raise RuntimeError(f"Unknown category for {item_id}: {category}")
        result[item_id] = Override(category=category)
    return result
