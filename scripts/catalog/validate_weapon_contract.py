"""Check newly built item catalogs against the damage calculator data contract.

Read-only: run after Build catalog and Build map data, before publication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.catalog.ballistics import weapon_ballistics


def validate_weapon_contract(catalog: dict) -> int:
    count = 0
    for item_id in catalog["publicCatalog"]["itemIds"]:
        item = catalog["items"][item_id]
        expected = weapon_ballistics(item.get("properties", {}))
        if expected is None:
            continue
        stats = item.get("weaponStats", {})
        if stats.get("ballistics") != expected:
            raise RuntimeError(f"{item_id}: missing or stale ballistics; rebuild from game sources")
        for field in ("scatter", "recoil"):
            grips = {"wielded": expected[field], "unwielded": expected[field + "Unwielded"]}
            if stats.get(field) != grips:
                raise RuntimeError(f"{item_id}: {field} does not contain both normalized grips")
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    print(f"Weapon contracts checked: {validate_weapon_contract(catalog)}")


if __name__ == "__main__":
    main()
