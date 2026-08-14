from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.common.localization import Localizer, read_fluent_messages
from scripts.common.prototypes import PrototypeResolver, read_entity_prototypes
from scripts.mobs.sprites import render_mob_sprites, sprite_path_from_component

MARINE_BASE_PROTOTYPE_ID = "RMCBaseMobSpeciesOrganic"

XENO_SOURCE_PREFIXES = (
    "Resources/Prototypes/_RMC14/Entities/Mobs/Xeno/",
    "Resources/Prototypes/_Stories/Entities/Mobs/Xeno/",
)

KNOWN_THRESHOLD_STATES = {"Alive", "Critical", "Dead"}

# Cosmetic/event reskins and admin-only utility entities that share a real
# caste's stat block but aren't part of the normal hive roster on this server.
EXCLUDED_XENO_CASTE_IDS = {
    "RMCXenoQueenMagical",
    "RMCXenoQueenMaid",
    "RMCXenoParasitePrimeHiveAssign",
    "RMCXenoRouny",
    "RMCXenoWehny",
}


def capitalize_first(value: str) -> str:
    for index, character in enumerate(value):
        if character.isdigit():
            return value
        if character.isalpha():
            return value[:index] + character.upper() + value[index + 1 :]
    return value


def invert_thresholds(thresholds: dict[Any, Any]) -> dict[str, int | None]:
    by_state: dict[str, int] = {}
    for raw_amount, state in thresholds.items():
        if state not in KNOWN_THRESHOLD_STATES:
            raise RuntimeError(f"Unknown MobThresholds state: {state}")
        if state in by_state:
            raise RuntimeError(f"Duplicate MobThresholds state: {state}")
        by_state[state] = int(raw_amount)

    if "Dead" not in by_state:
        raise RuntimeError("MobThresholds is missing the required Dead state")
    return {"critical": by_state.get("Critical"), "dead": by_state["Dead"]}


def is_xeno_mob_source_file(source_file: str) -> bool:
    return source_file.startswith(XENO_SOURCE_PREFIXES)


def matured_thresholds(component: dict[str, Any] | None) -> dict[str, int] | None:
    """XenoMaturingSystem overwrites MobThresholds once a spawn-time timer elapses
    (e.g. the queen starts at 500/600 and permanently jumps to 1000/1100)."""
    if component is None:
        return None
    critical = component.get("critThreshold")
    dead = component.get("deadThreshold")
    if not isinstance(critical, (int, float)) or not isinstance(dead, (int, float)):
        raise RuntimeError("XenoMaturing is missing critThreshold/deadThreshold")
    return {"critical": int(critical), "dead": int(dead)}


def armor_from_component(component: dict[str, Any]) -> dict[str, Any]:
    return {
        "xenoArmor": component.get("xenoArmor", 0),
        "frontalArmor": component.get("frontalArmor", 0),
        "sideArmor": component.get("sideArmor", 0),
        "explosionArmor": component.get("explosionArmor", 0),
        "immuneToArmorPiercing": bool(component.get("immuneToAP", False)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the SSMC mob catalog from live game sources")
    parser.add_argument("--game-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sprites-output", required=True, type=Path)
    parser.add_argument("--locale", default="ru-RU")
    parser.add_argument("--commit", default="unknown")
    args = parser.parse_args()

    prototypes = read_entity_prototypes(args.game_source)
    resolver = PrototypeResolver(prototypes)
    locale_root = args.game_source / "Resources/Locale" / args.locale
    localizer = Localizer(read_fluent_messages(locale_root))

    marine_resolved = resolver.resolve(MARINE_BASE_PROTOTYPE_ID)
    marine_thresholds = marine_resolved["components"].get("MobThresholds")
    if marine_thresholds is None:
        raise RuntimeError(
            f"{MARINE_BASE_PROTOTYPE_ID} has no MobThresholds component"
        )
    marine = {
        "sourcePrototypeId": MARINE_BASE_PROTOTYPE_ID,
        "thresholds": invert_thresholds(marine_thresholds.get("thresholds", {})),
    }

    xeno_castes: dict[str, Any] = {}
    sprite_paths: dict[str, str] = {}
    for prototype in prototypes.values():
        if prototype.abstract:
            continue
        if prototype.id in EXCLUDED_XENO_CASTE_IDS:
            continue
        if not is_xeno_mob_source_file(prototype.source_file):
            continue

        resolved = resolver.resolve(prototype.id)
        components = resolved["components"]
        thresholds_component = components.get("MobThresholds")
        armor_component = components.get("CMArmor")
        if thresholds_component is None or armor_component is None:
            continue

        name = capitalize_first(
            localizer.entity_text(prototype.id, None, resolved["fields"].get("name"))
        )

        sprite_path = sprite_path_from_component(components.get("Sprite"))
        if sprite_path is not None:
            sprite_paths[prototype.id] = sprite_path

        xeno_castes[prototype.id] = {
            "id": prototype.id,
            "name": name,
            "origin": prototype.origin,
            "sourceFile": prototype.source_file,
            "parents": list(prototype.parents),
            "thresholds": invert_thresholds(
                thresholds_component.get("thresholds", {})
            ),
            "maturedThresholds": matured_thresholds(components.get("XenoMaturing")),
            "armor": armor_from_component(armor_component),
            "sprite": None,
        }

    if not xeno_castes:
        raise RuntimeError("No xeno castes were discovered")

    render_mob_sprites(args.game_source, args.sprites_output, sprite_paths)
    for caste_id in sprite_paths:
        xeno_castes[caste_id]["sprite"] = f"sprites/{caste_id}.png"

    result = {
        "schemaVersion": 1,
        "source": "MetalSage/space-stories-cm14",
        "gameCommit": args.commit,
        "locale": args.locale,
        "marine": marine,
        "xenoCastes": dict(sorted(xeno_castes.items())),
        "counts": {"xenoCastes": len(xeno_castes)},
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f'Marine thresholds: {marine["thresholds"]}')
    print(f'Xeno castes: {len(xeno_castes)}')


if __name__ == "__main__":
    main()
