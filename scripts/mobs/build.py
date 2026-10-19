from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.common.localization import Localizer, read_fluent_messages
from scripts.common.prototypes import PrototypeResolver, iter_prototype_documents, read_entity_prototypes
from scripts.mobs.constants import RMC_SIZES
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


def apply_bulwark_passive(armor: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """BulwarkPassiveSystem.OnGetArmor adds PassiveFrontalBonus/PassiveSideBonus
    to CMGetArmorEvent with no Active/toggle guard at all — a permanent trait
    of the Bulwark strain, unlike the Encased Plates ability, so it belongs in
    the caste's base armor numbers rather than a togglable ability."""
    passive = components.get("BulwarkPassive")
    if not isinstance(passive, dict):
        return armor
    armor = dict(armor)
    armor["frontalArmor"] += passive.get("passiveFrontalBonus", 10)
    armor["sideArmor"] += passive.get("passiveSideBonus", 10)
    return armor


def evasion_from_components(components: dict[str, Any]) -> dict[str, Any] | None:
    """Standing enemy baseline: EvasionSystem.OnSizeRefreshEvasion, 024d853a."""
    evasion = components.get("Evasion")
    if not isinstance(evasion, dict):
        return None
    base = evasion.get("evasion", 0)
    if isinstance(base, bool) or not isinstance(base, (int, float)):
        raise RuntimeError(f"Invalid Evasion.evasion: {base!r}")
    size_modifier = 0
    if isinstance(components.get("RMCSize"), dict):
        size = rmc_size(components)
        if size == "Small":
            size_modifier = 10
        elif size in ("Big", "Immobile"):
            size_modifier = -10
    return {"base": base, "sizeModifier": size_modifier, "standing": base + size_modifier}


def read_damage_groups(game_source: Path) -> dict[str, list[str]]:
    """damageGroup prototypes (Resources/Prototypes/Damage/groups.yml): a
    DamageSpecifier written as `groups: {Brute: 12}` is spread over the
    group's damage types when the game loads it."""
    root = game_source / "Resources/Prototypes"
    groups: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.yml")):
        for raw in iter_prototype_documents(path):
            if raw.get("type") != "damageGroup":
                continue
            group_id = raw.get("id")
            types = raw.get("damageTypes")
            if isinstance(group_id, str) and isinstance(types, list):
                groups[group_id] = [value for value in types if isinstance(value, str)]
    if "Brute" not in groups:
        raise RuntimeError("No Brute damageGroup prototype found")
    return groups


def damage_from_specifier(specifier: Any, groups: dict[str, list[str]]) -> dict[str, float]:
    """DamageSpecifier `types` + `groups`; a group amount is split evenly
    across its types (DamageSpecifier's group constructor)."""
    if not isinstance(specifier, dict):
        return {}
    result: dict[str, float] = {}
    raw_types = specifier.get("types")
    if isinstance(raw_types, dict):
        for damage_type, amount in raw_types.items():
            if isinstance(amount, (int, float)) and not isinstance(amount, bool):
                result[damage_type] = result.get(damage_type, 0) + amount
    raw_groups = specifier.get("groups")
    if isinstance(raw_groups, dict):
        for group_id, amount in raw_groups.items():
            if isinstance(amount, bool) or not isinstance(amount, (int, float)):
                continue
            types = groups.get(group_id)
            if not types:
                raise RuntimeError(f"Unknown damage group: {group_id}")
            share = amount / len(types)
            for damage_type in types:
                result[damage_type] = result.get(damage_type, 0) + share
    return {key: round(value, 4) for key, value in result.items() if value != 0}


# MeleeWeaponComponent.AttackRate default (attacks per second); xeno castes
# that swing faster or slower override it in their MeleeWeapon component.
DEFAULT_MELEE_ATTACK_RATE = 1.0


def is_tail_stab_action(resolver: PrototypeResolver, action_id: str) -> bool:
    """An action whose WorldTargetAction raises XenoTailStabEvent — the plain
    stab and its renamed children (Defender's Tail Slam, Corrosive, Lance).
    useAltTailStab marks the Praetorian lance's secondary mode, which uses
    a different component's stats."""
    if action_id not in resolver.prototypes:
        return False
    target = resolver.resolve(action_id)["components"].get("WorldTargetAction")
    event = target.get("event") if isinstance(target, dict) else None
    if not isinstance(event, dict) or event.get("yamlTag") != "!type:XenoTailStabEvent":
        return False
    value = event.get("value")
    return not (isinstance(value, dict) and value.get("useAltTailStab") is True)


def tail_stab_action_id(components: dict[str, Any], resolver: PrototypeResolver) -> str | None:
    """The tail stab action a caste is actually granted (Xeno.actionIds)."""
    xeno = components.get("Xeno")
    action_ids = xeno.get("actionIds") if isinstance(xeno, dict) else None
    if not isinstance(action_ids, list):
        return None
    for action_id in action_ids:
        if isinstance(action_id, str) and is_tail_stab_action(resolver, action_id):
            return action_id
    return None


def attacks_from_components(
    components: dict[str, Any],
    resolver: PrototypeResolver,
    groups: dict[str, list[str]],
) -> dict[str, Any]:
    """Base claw swing (MeleeWeapon) and tail stab (XenoTailStab + the granted
    action's useDelay). Situational buffs (pheromones, Empower, strain
    passives) are not included."""
    claw = None
    melee = components.get("MeleeWeapon")
    if isinstance(melee, dict):
        damage = damage_from_specifier(melee.get("damage"), groups)
        if damage:
            rate = melee.get("attackRate", DEFAULT_MELEE_ATTACK_RATE)
            claw = {
                "damage": damage,
                "attackRate": rate if isinstance(rate, (int, float)) and not isinstance(rate, bool) else DEFAULT_MELEE_ATTACK_RATE,
            }

    tail = None
    stab = components.get("XenoTailStab")
    action_id = tail_stab_action_id(components, resolver)
    if isinstance(stab, dict) and action_id is not None:
        damage = damage_from_specifier(stab.get("tailDamage"), groups)
        action = resolver.resolve(action_id)["components"].get("Action", {})
        cooldown = action.get("useDelay") if isinstance(action, dict) else None
        if damage and isinstance(cooldown, (int, float)) and cooldown > 0:
            piercing = stab.get("armorPiercing", 0)
            tail = {
                "damage": damage,
                "armorPiercing": piercing if isinstance(piercing, int) else 0,
                "cooldownSeconds": cooldown,
            }

    return {"claw": claw, "tail": tail}


def rmc_size(components: dict[str, Any]) -> str:
    """RMCSizeComponent.Size gates several mechanics (stopping power stun
    thresholds, RMCFocusedShootingSystem's bonus-damage tiers) by an ordered
    scale; the component itself defaults to Xeno when absent."""
    size_component = components.get("RMCSize")
    if isinstance(size_component, dict):
        size = size_component.get("size")
        if size in RMC_SIZES:
            return size
    return "Xeno"


def strain_name(components: dict[str, Any], localizer: Localizer) -> str | None:
    """XenoStrainComponent.name is a bare Fluent key (not an `{ent-...}`
    reference) naming the caste's strain, e.g. "stories-xeno-bulwark-name"
    -> "Бастион". Castes with no strain (the default/base variant) have no
    XenoStrain component at all."""
    strain = components.get("XenoStrain")
    if not isinstance(strain, dict):
        return None
    key = strain.get("name")
    if not isinstance(key, str):
        return None
    return localizer.resolve_key(key)


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
    damage_groups = read_damage_groups(args.game_source)

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
            "strainName": strain_name(components, localizer),
            "size": rmc_size(components),
            "evasion": evasion_from_components(components),
            "origin": prototype.origin,
            "sourceFile": prototype.source_file,
            "parents": list(prototype.parents),
            "thresholds": invert_thresholds(
                thresholds_component.get("thresholds", {})
            ),
            "maturedThresholds": matured_thresholds(components.get("XenoMaturing")),
            "armor": apply_bulwark_passive(armor_from_component(armor_component), components),
            "attacks": attacks_from_components(components, resolver, damage_groups),
            "sprite": None,
        }

    if not xeno_castes:
        raise RuntimeError("No xeno castes were discovered")

    render_mob_sprites(args.game_source, args.sprites_output, sprite_paths)
    for caste_id in sprite_paths:
        xeno_castes[caste_id]["sprite"] = f"sprites/{caste_id}.png"

    result = {
        "schemaVersion": 1,
        "evasionSchemaVersion": 1,
        "attacksSchemaVersion": 1,
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
        newline="\n",
    )

    print(f'Marine thresholds: {marine["thresholds"]}')
    print(f'Xeno castes: {len(xeno_castes)}')


if __name__ == "__main__":
    main()
