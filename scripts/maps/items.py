from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.catalog.catalog import build_catalog
from scripts.catalog.classification import classify_item, equipment_slots
from scripts.catalog.config import read_config
from scripts.catalog.prototypes import (
    read_item_size_definitions,
    read_reagent_colors,
)
from scripts.catalog.sprites import render_public_sprites
from scripts.common.localization import Localizer, read_fluent_messages
from scripts.common.prototypes import EntityPrototype, PrototypeResolver


STATIC_ITEM_SCHEMA_VERSION = 1
STATIC_ITEM_CATALOG_PATH = "static-items.json"
STATIC_ITEM_SPRITE_PATH = "static-item-sprites"

def _tags(components: dict[str, Any]) -> set[str]:
    raw = components.get("Tag", {}).get("tags", [])
    return {value for value in raw if isinstance(value, str)} if isinstance(raw, list) else set()


def static_item_classification(
    prototype_id: str,
    resolved: dict[str, Any],
) -> dict[str, Any] | None:
    """Classify every concrete placed item without maintaining an allow-list."""
    if resolved.get("abstract") is True:
        return None
    components = resolved["components"]
    component_types = set(components)
    if "Item" not in component_types:
        return None
    tags = _tags(components)
    return classify_item(
        {
            "id": prototype_id,
            "name": str(resolved["fields"].get("name") or prototype_id),
            "sourceFile": resolved.get("sourceFile", ""),
            "componentTypes": sorted(component_types),
            "equipmentSlots": sorted(equipment_slots(components)),
            "tags": sorted(tags),
            "properties": components,
        },
        {},
    )


def build_static_item_catalog(
    game_source: Path,
    output_root: Path,
    prototype_ids: set[str],
    prototypes: dict[str, EntityPrototype],
    resolver: PrototypeResolver,
    game_commit: str,
) -> dict[str, Any]:
    localizer = Localizer(read_fluent_messages(game_source / "Resources/Locale/ru-RU"))
    selected_ids: set[str] = set()
    for prototype_id in sorted(prototype_ids):
        resolved = resolver.resolve(prototype_id)
        if static_item_classification(prototype_id, resolved) is not None:
            selected_ids.add(prototype_id)

    _, full_catalog = build_catalog(
        prototypes=prototypes,
        config=read_config(
            Path(__file__).resolve().parents[2] / "config/catalog-sources.yml"
        ),
        localizer=localizer,
        game_commit=game_commit,
        item_sizes=read_item_size_definitions(game_source),
        additional_item_ids=selected_ids,
    )
    items = {
        item_id: full_catalog["items"][item_id]
        for item_id in selected_ids
        if item_id in full_catalog["items"]
    }
    item_ids = sorted(
        items,
        key=lambda value: (str(items[value]["name"]).casefold(), value),
    )
    categories: dict[str, list[str]] = {}
    for item_id in item_ids:
        categories.setdefault(str(items[item_id]["category"]), []).append(item_id)
    render_public_sprites(
        game_source,
        output_root / STATIC_ITEM_SPRITE_PATH,
        items,
        item_ids,
        read_reagent_colors(game_source),
        image_prefix=STATIC_ITEM_SPRITE_PATH,
        strict=False,
    )
    catalog = {
        "schemaVersion": STATIC_ITEM_SCHEMA_VERSION,
        "gameCommit": game_commit,
        "source": "MetalSage/space-stories-cm14",
        "locale": "ru-RU",
        "items": dict(sorted(items.items())),
        "publicCatalog": {
            "itemIds": item_ids,
            "categories": {name: values for name, values in categories.items() if values},
        },
        "counts": {"items": len(item_ids)},
    }
    return catalog
