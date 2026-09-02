from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from scripts.catalog.api import build_catalog_documents
from scripts.catalog.relations import content_relations
from scripts.common.items.classification import classify_item, equipment_slots
from scripts.common.items.prototypes import (
    read_reagent_colors,
)
from scripts.common.items.sprites import render_public_sprites
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
    """Classify any concrete Item; map placement decides whether it is collectable."""
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


def collect_linked_item_ids(
    root_ids: set[str],
    prototypes: dict[str, EntityPrototype],
    resolver: PrototypeResolver,
) -> set[str]:
    """Follow the same physical item graph as the ordinary catalog builder."""
    linked_ids = set(root_ids)
    queue = deque(sorted(root_ids))
    while queue:
        source_id = queue.popleft()
        resolved = resolver.resolve(source_id)
        for relation in content_relations(source_id, resolved):
            target_id = relation.get("to")
            if not isinstance(target_id, str):
                continue
            if target_id not in prototypes:
                raise RuntimeError(
                    f"Map item {source_id} has {relation.get('type')} relation "
                    f"to unknown entity {target_id}"
                )
            if target_id in linked_ids:
                continue
            linked_ids.add(target_id)
            queue.append(target_id)
    return linked_ids


def build_static_item_catalog(
    game_source: Path,
    output_root: Path,
    prototype_ids: set[str],
    prototypes: dict[str, EntityPrototype],
    resolver: PrototypeResolver,
    game_commit: str,
    *,
    render_sprites: bool = True,
) -> dict[str, Any]:
    selected_ids: set[str] = set()
    for prototype_id in sorted(prototype_ids):
        resolved = resolver.resolve(prototype_id)
        if static_item_classification(prototype_id, resolved) is not None:
            selected_ids.add(prototype_id)

    # Publish the complete physical graph rooted at map items. This includes
    # container contents, installed attachments and the full ammunition chain:
    # weapon -> magazine -> cartridge -> projectile.
    registry_ids = collect_linked_item_ids(selected_ids, prototypes, resolver)

    _, full_catalog = build_catalog_documents(
        game_source=game_source,
        config_path=Path(__file__).resolve().parents[2] / "config/catalog-sources.yml",
        prototypes=prototypes,
        game_commit=game_commit,
        additional_item_ids=registry_ids,
    )
    items = {
        item_id: full_catalog["items"][item_id]
        for item_id in registry_ids
        if item_id in full_catalog["items"]
    }
    item_ids = sorted(
        items,
        key=lambda value: (str(items[value]["name"]).casefold(), value),
    )
    categories: dict[str, list[str]] = {}
    for item_id in item_ids:
        categories.setdefault(str(items[item_id]["category"]), []).append(item_id)
    if render_sprites:
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
