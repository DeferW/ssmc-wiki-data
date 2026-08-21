from __future__ import annotations

import argparse
from pathlib import Path

from scripts.common.prototypes import PrototypeResolver, read_entity_prototypes
from scripts.maps.core import (
    DEFAULT_MAX_ASSET_BYTES,
    DEFAULT_RENDER_SCALE,
    DEFAULT_TILE_SIZE,
    DEFAULT_WEBP_QUALITY,
    build_catalog,
    directory_size,
    discover_active_maps,
    package_render,
    resource_path,
    write_json,
    write_overlays,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build compact SSMC map manifests, overlays and lazy WebP tiles"
    )
    parser.add_argument("--game-source", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--assets-output", type=Path)
    parser.add_argument("--rendered-input", type=Path)
    parser.add_argument("--render-list-output", type=Path)
    parser.add_argument("--discovery-only", action="store_true")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tile-size", type=int, default=DEFAULT_TILE_SIZE)
    parser.add_argument("--render-scale", type=float, default=DEFAULT_RENDER_SCALE)
    parser.add_argument("--webp-quality", type=int, default=DEFAULT_WEBP_QUALITY)
    parser.add_argument("--max-assets-bytes", type=int, default=DEFAULT_MAX_ASSET_BYTES)
    args = parser.parse_args()

    prototypes = read_entity_prototypes(args.game_source)
    resolver = PrototypeResolver(prototypes)
    maps = discover_active_maps(args.game_source, prototypes, resolver)

    if args.render_list_output is not None:
        args.render_list_output.parent.mkdir(parents=True, exist_ok=True)
        args.render_list_output.write_text(
            "".join(
                str(resource_path(args.game_source, entry["mapPath"]).resolve()) + "\n"
                for entry in maps
            ),
            encoding="utf-8",
        )
    if args.discovery_only:
        print(f"Discovered active maps: {len(maps)}")
        return
    if args.output is None or args.assets_output is None:
        parser.error("--output and --assets-output are required unless --discovery-only is used")
    if args.tile_size < 128 or args.tile_size > 2048:
        parser.error("--tile-size must be between 128 and 2048")
    if not 0 < args.render_scale <= 1:
        parser.error("--render-scale must be greater than 0 and at most 1")
    if not 1 <= args.webp_quality <= 100:
        parser.error("--webp-quality must be between 1 and 100")

    write_overlays(args.game_source, args.assets_output, maps, prototypes, resolver)
    if args.rendered_input is not None:
        for entry in maps:
            package_render(
                args.rendered_input,
                args.assets_output,
                entry,
                tile_size=args.tile_size,
                scale=args.render_scale,
                quality=args.webp_quality,
            )

    assets_bytes = directory_size(args.assets_output, exclude={args.output})
    catalog = build_catalog(maps, args.commit, assets_bytes)
    write_json(args.output, catalog)
    if args.output.resolve().is_relative_to(args.assets_output.resolve()):
        published_bytes = directory_size(args.assets_output)
    else:
        published_bytes = assets_bytes + args.output.stat().st_size
    if published_bytes > args.max_assets_bytes:
        raise RuntimeError(
            f"Published map data exceeds budget: {published_bytes} > "
            f"{args.max_assets_bytes} bytes. Lower --render-scale or --webp-quality."
        )
    print(f"Active maps: {catalog['counts']['maps']}")
    print(f"Ships: {catalog['counts']['ships']}")
    print(f"Planets: {catalog['counts']['planets']}")
    print(f"Map asset bytes: {assets_bytes}")
    print(f"Published map bytes: {published_bytes}")


if __name__ == "__main__":
    main()
