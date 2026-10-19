from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from scripts.mobs.constants import RMC_SIZES

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


def positive_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def validate_damage(damage: Any, label: str) -> None:
    if not isinstance(damage, dict) or not damage:
        raise RuntimeError(f"{label}: damage must be a non-empty object")
    for damage_type, amount in damage.items():
        if not isinstance(damage_type, str) or not positive_number(amount):
            raise RuntimeError(f"{label}: invalid damage entry {damage_type!r}: {amount!r}")


def validate_attacks(attacks: Any, caste_id: str) -> None:
    if not isinstance(attacks, dict) or set(attacks) != {"claw", "tail"}:
        raise RuntimeError(f"Xeno caste has invalid attacks keys: {caste_id}")
    claw = attacks["claw"]
    if claw is not None:
        if not isinstance(claw, dict):
            raise RuntimeError(f"Xeno caste has invalid claw attack: {caste_id}")
        validate_damage(claw.get("damage"), f"{caste_id} claw")
        if not positive_number(claw.get("attackRate")):
            raise RuntimeError(f"Xeno caste has invalid claw attackRate: {caste_id}")
    tail = attacks["tail"]
    if tail is not None:
        if not isinstance(tail, dict):
            raise RuntimeError(f"Xeno caste has invalid tail attack: {caste_id}")
        validate_damage(tail.get("damage"), f"{caste_id} tail")
        if not isinstance(tail.get("armorPiercing"), int) or tail["armorPiercing"] < 0:
            raise RuntimeError(f"Xeno caste has invalid tail armorPiercing: {caste_id}")
        if not positive_number(tail.get("cooldownSeconds")):
            raise RuntimeError(f"Xeno caste has invalid tail cooldownSeconds: {caste_id}")


def validate(data: dict[str, Any], sprites_path: Path) -> None:
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
        strain_name = caste.get("strainName")
        if strain_name is not None and (not isinstance(strain_name, str) or not strain_name):
            raise RuntimeError(f"Xeno caste has an invalid strainName: {caste_id}")
        if caste.get("size") not in RMC_SIZES:
            raise RuntimeError(f"Xeno caste has an unknown size: {caste_id}")
        if data.get("evasionSchemaVersion") == 1:
            if "evasion" not in caste:
                raise RuntimeError(f"Missing evasion field: {caste_id}")
            evasion = caste["evasion"]
            if evasion is not None:
                if not isinstance(evasion, dict) or any(
                    isinstance(evasion.get(key), bool)
                    or not isinstance(evasion.get(key), (int, float))
                    or not math.isfinite(evasion[key])
                    for key in ("base", "sizeModifier", "standing")
                ):
                    raise RuntimeError(f"Invalid evasion: {caste_id}")
                if evasion["standing"] != evasion["base"] + evasion["sizeModifier"]:
                    raise RuntimeError(f"Inconsistent evasion: {caste_id}")
        source_file = caste.get("sourceFile")
        if not isinstance(source_file, str) or "Mobs/Xeno/" not in source_file:
            raise RuntimeError(f"Xeno caste has an unexpected sourceFile: {caste_id}")
        validate_thresholds(caste.get("thresholds"), caste_id)
        if caste.get("maturedThresholds") is not None:
            validate_thresholds(caste["maturedThresholds"], f"{caste_id} (matured)")

        sprite = caste.get("sprite")
        if sprite is not None:
            if sprite != f"sprites/{caste_id}.png":
                raise RuntimeError(f"Xeno caste has an unexpected sprite path: {caste_id}")
            if not (sprites_path / f"{caste_id}.png").is_file():
                raise RuntimeError(f"Missing xeno sprite file: {caste_id}")

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

        if data.get("attacksSchemaVersion") == 1:
            validate_attacks(caste.get("attacks"), caste_id)

    counts = data.get("counts")
    expected_counts = {"xenoCastes": len(xeno_castes)}
    if counts != expected_counts:
        raise RuntimeError(f"Count mismatch: stored={counts}, actual={expected_counts}")

    expected_sprites = {
        f"{caste_id}.png"
        for caste_id, caste in xeno_castes.items()
        if caste.get("sprite") is not None
    }
    actual_sprites = {path.name for path in sprites_path.glob("*.png")}
    extra_sprites = sorted(actual_sprites - expected_sprites)
    if extra_sprites:
        raise RuntimeError("Unexpected extra sprite files: " + ", ".join(extra_sprites))

    print(f'Marine thresholds: {marine["thresholds"]}')
    print(f"Xeno castes: {len(xeno_castes)}")
    print("Mob catalog validation passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate mob catalog output")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--sprites", type=Path, required=True)
    args = parser.parse_args()
    validate(read_json(args.catalog), args.sprites)


if __name__ == "__main__":
    main()
