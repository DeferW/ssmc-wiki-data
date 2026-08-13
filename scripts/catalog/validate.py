from __future__ import annotations

import argparse
from pathlib import Path

from scripts.catalog.config import read_config, read_overrides
from scripts.catalog.validation import validate
from scripts.common.io import read_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate generated catalog data")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--sprites", type=Path, required=True)
    args = parser.parse_args()
    catalog = read_json(args.catalog)
    index = read_json(args.index)
    validate(
        catalog,
        index,
        read_config(args.config),
        read_overrides(args.overrides),
        args.sprites,
    )
    print(f"Catalog validation passed: {catalog['counts']['items']} items")


if __name__ == "__main__":
    main()
