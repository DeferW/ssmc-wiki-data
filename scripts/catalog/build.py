from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from scripts.catalog.builder import build_catalog
from scripts.catalog.config import read_config, read_overrides
from scripts.catalog.localization import Localizer, read_fluent_messages
from scripts.catalog.prototypes import (
    PrototypeResolver,
    read_item_sizes,
    read_prototypes,
    read_reagent_colors,
)
from scripts.catalog.sprites import render_public_sprites
from scripts.catalog.validation import validate
from scripts.common.io import replace_directory, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the SSMC equipment catalog")
    parser.add_argument("--game-source", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--index-output", type=Path, required=True)
    parser.add_argument("--sprites-output", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--locale", default="ru-RU")
    args = parser.parse_args()

    config = read_config(args.config)
    overrides = read_overrides(args.overrides)
    prototypes = read_prototypes(args.game_source)
    resolver = PrototypeResolver(prototypes)
    locale_root = args.game_source / "Resources/Locale" / args.locale
    localizer = Localizer(read_fluent_messages(locale_root))
    index, catalog = build_catalog(
        resolver=resolver,
        config=config,
        overrides=overrides,
        localizer=localizer,
        item_sizes=read_item_sizes(args.game_source),
        game_commit=args.commit,
        locale=args.locale,
    )

    args.sprites_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="catalog-sprites-", dir=args.sprites_output.parent
    ) as temporary:
        staging = Path(temporary)
        render_public_sprites(
            game_source=args.game_source,
            output_dir=staging,
            items=catalog["items"],
            public_item_ids=list(catalog["items"]),
            reagent_colors=read_reagent_colors(args.game_source),
        )
        validate(catalog, index, config, overrides, staging)
        replace_directory(staging, args.sprites_output)

    write_json(args.index_output, index)
    write_json(args.output, catalog)
    print(f"Catalog items: {catalog['counts']['items']}")
    print(f"Edited categories: {catalog['counts']['edited']}")
    print(f"Hidden category: {catalog['counts']['hiddenCategory']}")
    print(f"Relations: {index['counts']['relations']}")


if __name__ == "__main__":
    main()

