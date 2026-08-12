from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from equipment_catalog.catalog import build_catalog
from equipment_catalog.config import (
    apply_catalog_overrides,
    read_catalog_overrides,
    read_config,
)
from equipment_catalog.localization import Localizer, read_fluent_messages
from equipment_catalog.prototypes import (
    read_entity_prototypes,
    read_item_size_definitions,
    read_reagent_colors,
)
from equipment_catalog.reporting import (
    build_review_section,
    print_previous_catalog_comparison,
    write_json,
)
from equipment_catalog.sprites import render_public_sprites


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the SSMC equipment catalog from live game sources"
    )
    parser.add_argument("--game-source", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--index-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sprites-output", type=Path, required=True)
    parser.add_argument(
        "--overrides",
        type=Path,
        help=(
            "Administrator overrides JSON; defaults to "
            "catalog-overrides.json next to --config"
        ),
    )
    parser.add_argument("--commit", required=True)
    parser.add_argument("--locale", default="ru-RU")
    args = parser.parse_args()

    previous_catalog: dict[str, Any] | None = None
    if args.output.is_file():
        try:
            loaded_previous = json.loads(args.output.read_text(encoding="utf-8"))
            if isinstance(loaded_previous, dict):
                previous_catalog = loaded_previous
        except (OSError, json.JSONDecodeError):
            previous_catalog = None

    prototypes = read_entity_prototypes(args.game_source)
    reagent_colors = read_reagent_colors(args.game_source)
    item_sizes = read_item_size_definitions(args.game_source)
    config = read_config(args.config)
    locale_root = args.game_source / "Resources/Locale" / args.locale
    localizer = Localizer(read_fluent_messages(locale_root))
    index, catalog = build_catalog(
        prototypes=prototypes,
        config=config,
        localizer=localizer,
        game_commit=args.commit,
        item_sizes=item_sizes,
    )
    overrides_path = args.overrides or args.config.parent / "catalog-overrides.json"
    overrides = read_catalog_overrides(overrides_path)
    apply_catalog_overrides(catalog, index, overrides)
    catalog["review"] = build_review_section(catalog)
    render_public_sprites(
        game_source=args.game_source,
        output_dir=args.sprites_output,
        items=catalog["items"],
        public_item_ids=catalog["publicCatalog"]["itemIds"],
        reagent_colors=reagent_colors,
    )
    write_json(args.index_output, index)
    write_json(args.output, catalog)
    print_previous_catalog_comparison(previous_catalog, catalog)

    counts = catalog["counts"]
    source_counts = index["counts"]
    print(f"Indexed entity prototypes: {source_counts['indexedEntityPrototypes']}")
    print(f"Vendor sections: {source_counts['sections']}")
    print(f"Trade entries: {source_counts['tradeEntries']}")
    print(f"Catalog items: {counts['catalogItems']}")
    print(f"Public equipment items: {counts['publicItems']}")
    print(f"Administrator-hidden items: {counts['hiddenItems']}")
    print(f"Excluded non-equipment items: {counts['excludedItems']}")
    print(f"Internal relations: {source_counts['relations']}")


if __name__ == "__main__":
    main()
