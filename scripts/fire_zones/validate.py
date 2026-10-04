from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.fire_zones.build import SCHEMA_VERSION
from scripts.fire_zones.rules import ROOF_SUPPORT_FIELDS

SUPPORTS = set(ROOF_SUPPORT_FIELDS.values())
SHAPES = {"circle", "diamond", "scatter"}


def _positive(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise RuntimeError(f"{label}: expected a positive number, got {value!r}")


def _entry(entry: Any, label: str, seen: set[str]) -> None:
    if not isinstance(entry, dict):
        raise RuntimeError(f"{label}: entry is not an object")
    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not entry_id:
        raise RuntimeError(f"{label}: missing id")
    if entry_id in seen:
        raise RuntimeError(f"{label}: duplicate id {entry_id}")
    seen.add(entry_id)
    if not isinstance(entry.get("name"), str) or not entry["name"].strip():
        raise RuntimeError(f"{label} {entry_id}: missing name")


def validate(data: dict[str, Any]) -> None:
    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise RuntimeError(f"Unexpected schemaVersion: {data.get('schemaVersion')!r}")
    if not isinstance(data.get("gameCommit"), str) or not data["gameCommit"]:
        raise RuntimeError("Missing gameCommit")
    seen: set[str] = set()

    mortars = data.get("mortars")
    if not isinstance(mortars, list) or not mortars:
        raise RuntimeError("No mortars found")
    for mortar in mortars:
        _entry(mortar, "mortar", seen)
        _positive(mortar.get("minRange"), f"mortar {mortar['id']} minRange")
        _positive(mortar.get("maxRange"), f"mortar {mortar['id']} maxRange")
        if mortar["minRange"] >= mortar["maxRange"]:
            raise RuntimeError(f"mortar {mortar['id']}: minRange must be below maxRange")

    warheads = data.get("orbitalWarheads")
    if not isinstance(warheads, list) or len(warheads) < 3:
        raise RuntimeError("Expected at least the HE, incendiary and cluster orbital warheads")
    for warhead in warheads:
        _entry(warhead, "warhead", seen)
        parts = warhead.get("parts")
        if not isinstance(parts, list) or not parts:
            raise RuntimeError(f"warhead {warhead['id']}: no parts")
        for part in parts:
            if not isinstance(part, dict) or part.get("shape") not in SHAPES:
                raise RuntimeError(f"warhead {warhead['id']}: unknown part {part!r}")
            _positive(part.get("radius"), f"warhead {warhead['id']} radius")
            if part["shape"] == "scatter":
                _positive(part.get("spread"), f"warhead {warhead['id']} spread")
                _positive(part.get("count"), f"warhead {warhead['id']} count")

    roofs = data.get("roofs")
    if not isinstance(roofs, list) or not roofs:
        raise RuntimeError("No roofing entities found")
    for roof in roofs:
        _entry(roof, "roof", seen)
        _positive(roof.get("radius"), f"roof {roof['id']} radius")
        blocks = roof.get("blocks")
        if not isinstance(blocks, list) or not set(blocks) <= SUPPORTS or blocks != sorted(set(blocks)):
            raise RuntimeError(f"roof {roof['id']}: invalid blocks {blocks!r}")

    counts = data.get("counts")
    expected = {"mortars": len(mortars), "orbitalWarheads": len(warheads), "roofs": len(roofs)}
    if counts != expected:
        raise RuntimeError(f"counts {counts!r} do not match entries {expected!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate data/fire-zones/catalog.json")
    parser.add_argument("--catalog", required=True, type=Path)
    args = parser.parse_args()
    validate(json.loads(args.catalog.read_text(encoding="utf-8")))
    print(f"Fire zones are valid: {args.catalog}")


if __name__ == "__main__":
    main()
