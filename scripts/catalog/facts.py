from __future__ import annotations

from collections import defaultdict
from typing import Any

from scripts.catalog.extractors import extract_facts
from scripts.catalog.prototypes import PrototypeResolver


def build_facts(
    item_ids: set[str],
    relations: list[dict[str, Any]],
    resolver: PrototypeResolver,
) -> dict[str, dict[str, Any]]:
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relations:
        outgoing[relation["from"]].append(relation)
        incoming[relation["to"]].append(relation)

    result: dict[str, dict[str, Any]] = {}
    for item_id in sorted(item_ids):
        facts = extract_facts(resolver.resolve(item_id))
        facts["relations"] = {
            "outgoing": outgoing.get(item_id, []),
            "incoming": incoming.get(item_id, []),
        }
        result[item_id] = facts

    # Semantic content signals are graph-derived and deliberately stop at guns.
    path_cache: dict[tuple[str, str], bool] = {}
    active: set[tuple[str, str]] = set()

    def reaches(item_id: str, signal: str) -> bool:
        cache_key = (item_id, signal)
        if cache_key in path_cache:
            return path_cache[cache_key]
        if cache_key in active:
            return False
        active.add(cache_key)
        facts = result[item_id]
        own = bool(
            facts["medicalFunction"]
            if signal == "medical"
            else facts["signals"][signal]
        )
        if signal in {"projectile", "explosive"} and facts["signals"]["gun"]:
            value = False
        else:
            allowed = (
                {"contains", "slotItem", "bundleItem"}
                if signal == "medical"
                else {"contains", "slotItem", "bundleItem", "loadedWith", "fires"}
            )
            value = own or any(
                relation["to"] in result
                and relation["type"] in allowed
                and reaches(relation["to"], signal)
                for relation in facts["relations"]["outgoing"]
            )
        active.remove(cache_key)
        path_cache[cache_key] = value
        return value

    for item_id in result:
        result[item_id]["signals"]["projectilePath"] = reaches(item_id, "projectile")
        result[item_id]["signals"]["explosivePayload"] = reaches(item_id, "explosive")
        result[item_id]["signals"]["medicalPayload"] = reaches(item_id, "medical")
    return result
