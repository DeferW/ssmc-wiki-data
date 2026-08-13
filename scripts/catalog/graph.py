from __future__ import annotations

from collections import deque
from typing import Any

from scripts.catalog.models import SourceEntry
from scripts.catalog.prototypes import PrototypeResolver
from scripts.catalog.relations import compatibility_relations, content_relations, relation_key


def discover_items(
    source_entries: list[SourceEntry],
    resolver: PrototypeResolver,
) -> tuple[set[str], list[dict[str, Any]]]:
    """Recursively follow ownership edges from configured catalog roots."""
    queue = deque(entry.item_id for entry in source_entries)
    discovered: set[str] = set()
    relations: list[dict[str, Any]] = []
    known_relations: set[str] = set()
    while queue:
        item_id = queue.popleft()
        if item_id in discovered:
            continue
        if item_id not in resolver.prototypes:
            raise RuntimeError(f"Unknown item reachable from configured sources: {item_id}")
        discovered.add(item_id)
        for relation in content_relations(item_id, resolver.resolve(item_id)):
            target = relation["to"]
            if target not in resolver.prototypes:
                raise RuntimeError(
                    f"{item_id} has {relation['type']} relation to unknown entity {target}"
                )
            key = relation_key(relation)
            if key not in known_relations:
                known_relations.add(key)
                relations.append(relation)
            if target not in discovered:
                queue.append(target)

    for relation in compatibility_relations(discovered, resolver):
        key = relation_key(relation)
        if key not in known_relations:
            known_relations.add(key)
            relations.append(relation)
    relations.sort(
        key=lambda relation: (
            relation["from"], relation["type"], relation["to"], str(relation.get("slot", ""))
        )
    )
    return discovered, relations
