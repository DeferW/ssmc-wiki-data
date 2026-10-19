"""Build data/fire-zones/catalog.json: mortar range, orbital warheads and hive roofs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.common.localization import Localizer, read_fluent_messages
from scripts.common.prototypes import PrototypeResolver, read_entity_prototypes
from scripts.fire_zones.rules import (
    MORTAR_DEFAULTS,
    OB_STEP_DEFAULTS,
    ROOF_SUPPORT_FIELDS,
    intensity_to_radius,
)

SCHEMA_VERSION = 1
SOURCE = "MetalSage/space-stories-cm14"


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{label}: expected a number, got {value!r}")
    return float(value)


def _round(value: float) -> float:
    return round(value, 3)


def _name(localizer: Localizer, resolved: dict[str, Any]) -> str:
    text = localizer.entity_text(resolved["id"], None, resolved["fields"].get("name"))
    return text[:1].upper() + text[1:]


def _concrete_with(resolver: PrototypeResolver, component: str) -> list[dict[str, Any]]:
    result = []
    for prototype_id, prototype in sorted(resolver.prototypes.items()):
        if prototype.abstract:
            continue
        resolved = resolver.resolve(prototype_id)
        if component in resolved["components"]:
            result.append(resolved)
    return result


def explosion_parts(steps: Any, label: str) -> list[dict[str, Any]]:
    """Shapes one OrbitalCannonExplosion covers, as the system spawns them.

    OrbitalCannonSystem offsets every explosion of a step by a random vector up
    to ``spread`` tiles long, then queues the explosion and, when ``fire`` is
    set, a fire diamond of ``fireRange`` tiles.
    """
    if not isinstance(steps, list) or not steps:
        raise RuntimeError(f"{label}: OrbitalCannonExplosion has no steps")
    parts: list[dict[str, Any]] = []
    for index, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise RuntimeError(f"{label}: step {index} is not a mapping")
        step = {**OB_STEP_DEFAULTS, **raw}
        if step.get("type") is not None:
            radius = _round(intensity_to_radius(
                _number(step.get("total"), f"{label} step {index} total"),
                _number(step.get("slope"), f"{label} step {index} slope"),
                _number(step.get("max"), f"{label} step {index} max"),
            ))
            spread = _number(step["spread"], f"{label} step {index} spread")
            if spread > 0:
                count = int(step["times"]) * int(step["timesPer"])
                parts.append({"shape": "scatter", "spread": _round(spread), "radius": radius, "count": count})
            else:
                parts.append({"shape": "circle", "radius": radius})
        if step.get("fire") is not None:
            fire_range = _number(step["fireRange"], f"{label} step {index} fireRange")
            if fire_range > 0:
                parts.append({"shape": "diamond", "radius": _round(fire_range)})
    if not parts:
        raise RuntimeError(f"{label}: no explosion or fire steps")
    unique = {json.dumps(part, sort_keys=True): part for part in parts}
    return sorted(unique.values(), key=lambda part: (part["shape"], part["radius"]))


def build_mortars(resolver: PrototypeResolver, localizer: Localizer) -> list[dict[str, Any]]:
    mortars = []
    for resolved in _concrete_with(resolver, "Mortar"):
        component = {**MORTAR_DEFAULTS, **(resolved["components"]["Mortar"] or {})}
        mortars.append({
            "id": resolved["id"],
            "name": _name(localizer, resolved),
            "minRange": _number(component["minimumRange"], f"{resolved['id']} minimumRange"),
            "maxRange": _number(component["maximumRange"], f"{resolved['id']} maximumRange"),
        })
    return mortars


def build_orbital_warheads(resolver: PrototypeResolver, localizer: Localizer) -> list[dict[str, Any]]:
    warhead_ids: list[str] = []
    for cannon in _concrete_with(resolver, "OrbitalCannon"):
        for warhead_id in cannon["components"]["OrbitalCannon"].get("warheadTypes") or []:
            if warhead_id not in warhead_ids:
                warhead_ids.append(warhead_id)
    warheads = []
    for warhead_id in warhead_ids:
        warhead = resolver.resolve(warhead_id)
        explosion_id = (warhead["components"].get("OrbitalCannonWarhead") or {}).get("explosion")
        if not isinstance(explosion_id, str):
            raise RuntimeError(f"{warhead_id}: OrbitalCannonWarhead has no explosion")
        explosion = resolver.resolve(explosion_id)["components"].get("OrbitalCannonExplosion")
        if not isinstance(explosion, dict):
            raise RuntimeError(f"{explosion_id}: no OrbitalCannonExplosion component")
        warheads.append({
            "id": warhead_id,
            "name": _name(localizer, warhead),
            "explosionId": explosion_id,
            "parts": explosion_parts(explosion.get("steps"), explosion_id),
        })
    return warheads


def build_roofs(resolver: PrototypeResolver, localizer: Localizer) -> list[dict[str, Any]]:
    roofs = []
    for resolved in _concrete_with(resolver, "RoofingEntity"):
        component = resolved["components"]["RoofingEntity"] or {}
        allowed = {field: component.get(field, False) for field in ROOF_SUPPORT_FIELDS}
        for field, value in allowed.items():
            if not isinstance(value, bool):
                raise RuntimeError(f"{resolved['id']}: RoofingEntity.{field} is not a bool")
        roofs.append({
            "id": resolved["id"],
            "name": _name(localizer, resolved),
            "radius": _number(component.get("range"), f"{resolved['id']} RoofingEntity.range"),
            "blocks": sorted(ROOF_SUPPORT_FIELDS[field] for field, value in allowed.items() if not value),
        })
    return roofs


def build_catalog(game_source: Path, commit: str, locale: str) -> dict[str, Any]:
    resolver = PrototypeResolver(read_entity_prototypes(game_source))
    localizer = Localizer(read_fluent_messages(game_source / "Resources/Locale" / locale))
    mortars = build_mortars(resolver, localizer)
    warheads = build_orbital_warheads(resolver, localizer)
    roofs = build_roofs(resolver, localizer)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "source": SOURCE,
        "gameCommit": commit,
        "counts": {"mortars": len(mortars), "orbitalWarheads": len(warheads), "roofs": len(roofs)},
        "mortars": mortars,
        "orbitalWarheads": warheads,
        "roofs": roofs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SSMC fire zones from live game sources")
    parser.add_argument("--game-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--locale", default="ru-RU")
    args = parser.parse_args()

    catalog = build_catalog(args.game_source, args.commit, args.locale)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(catalog, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Fire zones: {catalog['counts']}")


if __name__ == "__main__":
    main()
