from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

MIN_XENO_CASTES = 20

EXPECTED_ARMOR_KEYS = {
    "xenoArmor",
    "frontalArmor",
    "sideArmor",
    "explosionArmor",
    "immuneToArmorPiercing",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_thresholds(thresholds: Any, label: str) -> None:
    if not isinstance(thresholds, dict):
        raise RuntimeError(f"{label}: thresholds must be an object")
    dead = thresholds.get("dead")
    critical = thresholds.get("critical")
    if not isinstance(dead, int) or dead <= 0:
        raise RuntimeError(f"{label}: invalid dead threshold: {dead!r}")
    if critical is not None:
        if not isinstance(critical, int) or critical <= 0:
            raise RuntimeError(f"{label}: invalid critical threshold: {critical!r}")
        if critical >= dead:
            raise RuntimeError(
                f"{label}: critical threshold must be below dead: "
                f"{critical} >= {dead}"
            )


def validate(data: dict[str, Any]) -> None:
    if data.get("schemaVersion") != 1:
        raise RuntimeError(f"Unexpected schemaVersion: {data.get('schemaVersion')}")

    marine = data.get("marine")
    if not isinstance(marine, dict):
        raise RuntimeError("Missing marine entry")
    if not isinstance(marine.get("sourcePrototypeId"), str):
        raise RuntimeError("Marine entry has no sourcePrototypeId")
    validate_thresholds(marine.get("thresholds"), "marine")

    xeno_castes = data.get("xenoCastes")
    if not isinstance(xeno_castes, dict) or not xeno_castes:
        raise RuntimeError("No xeno castes found")
    if len(xeno_castes) < MIN_XENO_CASTES:
        raise RuntimeError(
            f"Suspiciously few xeno castes: {len(xeno_castes)} < {MIN_XENO_CASTES}"
        )

    for caste_id, caste in xeno_castes.items():
        if not isinstance(caste, dict):
            raise RuntimeError(f"Xeno caste is not an object: {caste_id}")
        if caste.get("id") != caste_id:
            raise RuntimeError(f"Xeno caste id mismatch: {caste_id}")
        if not isinstance(caste.get("name"), str) or not caste["name"]:
            raise RuntimeError(f"Xeno caste has no name: {caste_id}")
        source_file = caste.get("sourceFile")
        if not isinstance(source_file, str) or "Mobs/Xeno/" not in source_file:
            raise RuntimeError(f"Xeno caste has an unexpected sourceFile: {caste_id}")
        validate_thresholds(caste.get("thresholds"), caste_id)
        if caste.get("maturedThresholds") is not None:
            validate_thresholds(caste["maturedThresholds"], f"{caste_id} (matured)")

        armor = caste.get("armor")
        if not isinstance(armor, dict) or set(armor) != EXPECTED_ARMOR_KEYS:
            raise RuntimeError(f"Xeno caste has invalid armor keys: {caste_id}")
        for key in ("xenoArmor", "frontalArmor", "sideArmor", "explosionArmor"):
            if not isinstance(armor[key], int) or armor[key] < 0:
                raise RuntimeError(f"Xeno caste has invalid {key}: {caste_id}")
        if not isinstance(armor["immuneToArmorPiercing"], bool):
            raise RuntimeError(
                f"Xeno caste has invalid immuneToArmorPiercing: {caste_id}"
            )

    counts = data.get("counts")
    expected_counts = {"xenoCastes": len(xeno_castes)}
    if counts != expected_counts:
        raise RuntimeError(f"Count mismatch: stored={counts}, actual={expected_counts}")

    print(f'Marine thresholds: {marine["thresholds"]}')
    print(f"Xeno castes: {len(xeno_castes)}")
    print("Mob catalog validation passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate mob catalog output")
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    validate(read_json(args.catalog))


if __name__ == "__main__":
    main()
