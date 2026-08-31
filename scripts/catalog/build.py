from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.catalog.catalog import build_catalog
from scripts.catalog.config import read_config
from scripts.common.localization import Localizer, read_fluent_messages
from scripts.catalog.prototypes import (
    read_entity_prototypes,
    read_item_size_definitions,
    read_reagent_colors,
)
from scripts.catalog.reporting import (
    build_review_section,
    print_previous_catalog_comparison,
    write_json,
)
from scripts.catalog.sprites import render_public_sprites


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the SSMC catalog from live game sources"
    )
    parser.add_argument("--game-source", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--index-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sprites-output", type=Path, required=True)
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
    print(f"Published catalog items: {counts['publicItems']}")
    print(f"Items in Скрытые: {counts['hiddenItems']}")
    print(f"Excluded items: {counts['excludedItems']}")
    print(f"Internal relations: {source_counts['relations']}")


if __name__ == "__main__":
    main()
