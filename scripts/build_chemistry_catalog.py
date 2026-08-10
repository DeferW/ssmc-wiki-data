from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


class GameYamlLoader(yaml.SafeLoader):
    """YAML loader that accepts SS14 custom tags."""


def construct_tagged_value(
    loader: GameYamlLoader,
    tag_suffix: str,
    node: yaml.Node,
) -> Any:
    if isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_scalar(node)

    return {
        "yamlTag": f"!{tag_suffix}",
        "value": value,
    }


GameYamlLoader.add_multi_constructor("!", construct_tagged_value)


FTL_MESSAGE_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9_-]*)\s*=\s*(.*)$"
)

RESOLVED_FIELDS = (
    "name",
    "desc",
    "physicalDesc",
    "group",
    "color",
    "flavor",
    "metabolisms",
    "plantMetabolism",
    "overdose",
    "criticalOverdose",
    "intensity",
    "duration",
    "radius",
    "burnColor",
    "explosive",
    "power",
    "falloffModifier",
    "intensityMod",
    "durationMod",
    "radiusMod",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_parents(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def read_upstream_reagents(game_source: Path) -> dict[str, dict[str, Any]]:
    root = game_source / "Resources/Prototypes/Reagents"
    if not root.is_dir():
        raise FileNotFoundError(f"Missing upstream reagent directory: {root}")

    result: dict[str, dict[str, Any]] = {}
    files = sorted([*root.rglob("*.yml"), *root.rglob("*.yaml")])

    for path in files:
        with path.open("r", encoding="utf-8-sig") as stream:
            for document in yaml.load_all(stream, Loader=GameYamlLoader):
                if document is None:
                    continue

                prototypes = document if isinstance(document, list) else [document]

                for prototype in prototypes:
                    if not isinstance(prototype, dict):
                        continue
                    if prototype.get("type") != "reagent":
                        continue

                    prototype_id = prototype.get("id")
                    if not isinstance(prototype_id, str):
                        continue
                    if prototype_id in result:
                        raise RuntimeError(
                            f"Duplicate upstream reagent ID: {prototype_id}"
                        )

                    result[prototype_id] = {
                        "id": prototype_id,
                        "origin": "upstream",
                        "sourceFile": path.relative_to(game_source).as_posix(),
                        "parents": normalize_parents(prototype.get("parent")),
                        "abstract": bool(prototype.get("abstract", False)),
                        "definition": {
                            key: value
                            for key, value in prototype.items()
                            if key not in {"type", "id", "parent", "abstract"}
                        },
                    }

    return result


def read_localization(locale_root: Path) -> dict[str, str]:
    if not locale_root.is_dir():
        raise FileNotFoundError(f"Missing locale directory: {locale_root}")

    messages: dict[str, str] = {}

    for path in sorted(locale_root.rglob("*.ftl")):
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        index = 0

        while index < len(lines):
            match = FTL_MESSAGE_RE.match(lines[index])
            if not match:
                index += 1
                continue

            key = match.group(1)
            parts = [match.group(2).strip()]
            index += 1

            while index < len(lines):
                line = lines[index]
                if FTL_MESSAGE_RE.match(line):
                    break
                if line.startswith((" ", "\t")):
                    stripped = line.strip()
                    if stripped and not stripped.startswith("."):
                        parts.append(stripped)
                    index += 1
                    continue
                if not line.strip():
                    index += 1
                    break
                break

            if key in messages:
                raise RuntimeError(f"Duplicate localization key: {key}")
            messages[key] = " ".join(part for part in parts if part)

    return messages


def custom_prototypes(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for entry in index["entries"]:
        if entry["type"] != "reagent":
            continue
        result[entry["id"]] = {
            "id": entry["id"],
            "origin": entry["origin"],
            "sourceFile": entry["sourceFile"],
            "parents": entry["parents"],
            "abstract": entry["abstract"],
            "definition": entry["definition"],
        }

    return result


def resolve_field(
    prototype_id: str,
    field: str,
    prototypes: dict[str, dict[str, Any]],
    cache: dict[tuple[str, str], Any],
    stack: tuple[str, ...] = (),
) -> Any:
    cache_key = (prototype_id, field)
    if cache_key in cache:
        return cache[cache_key]
    if prototype_id in stack:
        chain = " -> ".join((*stack, prototype_id))
        raise RuntimeError(f"Circular reagent inheritance: {chain}")

    prototype = prototypes.get(prototype_id)
    if prototype is None:
        cache[cache_key] = None
        return None

    definition = prototype["definition"]
    if field in definition:
        cache[cache_key] = definition[field]
        return definition[field]

    # Later parents have precedence in SS14 multiple inheritance.
    for parent_id in reversed(prototype["parents"]):
        value = resolve_field(
            parent_id,
            field,
            prototypes,
            cache,
            (*stack, prototype_id),
        )
        if value is not None:
            cache[cache_key] = value
            return value

    cache[cache_key] = None
    return None


def localized(value: Any, messages: dict[str, str]) -> str | None:
    if not isinstance(value, str):
        return None
    return messages.get(value, value)


def make_reagent_record(
    prototype_id: str,
    prototypes: dict[str, dict[str, Any]],
    messages: dict[str, str],
    cache: dict[tuple[str, str], Any],
    dependency: bool = False,
) -> dict[str, Any]:
    prototype = prototypes[prototype_id]
    resolved = {
        field: resolve_field(prototype_id, field, prototypes, cache)
        for field in RESOLVED_FIELDS
    }
    resolved = {key: value for key, value in resolved.items() if value is not None}

    name_key = resolved.get("name")
    desc_key = resolved.get("desc")
    physical_desc_key = resolved.get("physicalDesc")

    record = {
        "id": prototype_id,
        "origin": (
            "upstream-reference"
            if dependency and prototype["origin"] == "upstream"
            else prototype["origin"]
        ),
        "sourceFile": prototype["sourceFile"],
        "parents": prototype["parents"],
        "name": localized(name_key, messages) or prototype_id,
        "description": localized(desc_key, messages),
        "physicalDescription": localized(physical_desc_key, messages),
        "localizationKeys": {
            key: value
            for key, value in {
                "name": name_key,
                "description": desc_key,
                "physicalDescription": physical_desc_key,
            }.items()
            if isinstance(value, str)
        },
        "properties": {
            key: value
            for key, value in resolved.items()
            if key not in {"name", "desc", "physicalDesc"}
        },
        "definition": prototype["definition"],
    }
    return record


def normalize_amounts(
    values: Any,
    reagent_records: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(values, dict):
        return []

    result: list[dict[str, Any]] = []
    for reagent_id, raw in values.items():
        if not isinstance(reagent_id, str):
            continue

        if isinstance(raw, dict):
            amount = raw.get("amount")
            catalyst = bool(raw.get("catalyst", False))
        else:
            amount = raw
            catalyst = False

        linked = reagent_records.get(reagent_id)
        item: dict[str, Any] = {
            "id": reagent_id,
            "name": linked["name"] if linked else reagent_id,
            "amount": amount,
        }
        if catalyst:
            item["catalyst"] = True
        result.append(item)

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--guides", required=True, type=Path)
    parser.add_argument("--game-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--locale", default="ru-RU")
    args = parser.parse_args()

    index = read_json(args.index)
    guides = read_json(args.guides)

    index_commit = index["source"]["commit"]
    guide_commit = guides["source"]["commit"]
    if index_commit != guide_commit:
        raise RuntimeError(
            f"Source commit mismatch: index={index_commit}, guides={guide_commit}"
        )

    custom = custom_prototypes(index)
    upstream = read_upstream_reagents(args.game_source)
    collisions = sorted(set(custom) & set(upstream))
    if collisions:
        raise RuntimeError(
            "Custom/upstream reagent ID collision: " + ", ".join(collisions)
        )

    prototypes = {**upstream, **custom}
    locale_root = args.game_source / "Resources/Locale" / args.locale
    messages = read_localization(locale_root)
    cache: dict[tuple[str, str], Any] = {}

    reaction_entries = [
        entry for entry in index["entries"] if entry["type"] == "reaction"
    ]
    referenced_ids: set[str] = set()
    for entry in reaction_entries:
        definition = entry["definition"]
        for field in ("reactants", "products"):
            values = definition.get(field, {})
            if isinstance(values, dict):
                referenced_ids.update(
                    key for key in values if isinstance(key, str)
                )

    for guide_entries in guides["guides"].values():
        referenced_ids.update(
            entry["id"]
            for entry in guide_entries
            if entry["type"] == "reagent"
        )

    missing_references = sorted(referenced_ids - set(prototypes))
    if missing_references:
        raise RuntimeError(
            "Referenced reagents were not found: " + ", ".join(missing_references)
        )

    custom_records = {
        prototype_id: make_reagent_record(
            prototype_id,
            prototypes,
            messages,
            cache,
        )
        for prototype_id, prototype in sorted(custom.items())
        if not prototype["abstract"]
    }

    upstream_dependency_ids = sorted(
        prototype_id
        for prototype_id in referenced_ids
        if prototype_id in upstream
    )
    dependency_records = {
        prototype_id: make_reagent_record(
            prototype_id,
            prototypes,
            messages,
            cache,
            dependency=True,
        )
        for prototype_id in upstream_dependency_ids
    }
    all_records = {**dependency_records, **custom_records}

    reactions: dict[str, dict[str, Any]] = {}
    for entry in sorted(reaction_entries, key=lambda item: item["id"]):
        definition = entry["definition"]
        reactions[entry["id"]] = {
            "id": entry["id"],
            "origin": entry["origin"],
            "sourceFile": entry["sourceFile"],
            "reactants": normalize_amounts(
                definition.get("reactants"), all_records
            ),
            "products": normalize_amounts(
                definition.get("products"), all_records
            ),
            "conditions": {
                key: definition[key]
                for key in ("minTemp", "maxTemp", "priority")
                if key in definition
            },
            "effects": definition.get("effects", []),
            "definition": definition,
        }

    groups: dict[str, list[str]] = {}
    for prototype_id, record in custom_records.items():
        group = record["properties"].get("group")
        if isinstance(group, str):
            groups.setdefault(group, []).append(prototype_id)
    groups = {
        group: sorted(ids, key=lambda item: custom_records[item]["name"].casefold())
        for group, ids in sorted(groups.items())
    }

    expanded_guides: dict[str, list[dict[str, Any]]] = {}
    listed_custom_ids: set[str] = set()

    for guide_name, guide_entries in guides["guides"].items():
        expanded: list[dict[str, Any]] = []
        seen: set[str] = set()

        for entry in guide_entries:
            if entry["type"] == "reagent":
                ids = [entry["id"]]
                source_type = "reagent"
            else:
                ids = groups.get(entry["id"], [])
                source_type = "group"

            for prototype_id in ids:
                if prototype_id in seen:
                    continue
                seen.add(prototype_id)
                if prototype_id in custom_records:
                    listed_custom_ids.add(prototype_id)

                record = all_records.get(prototype_id)
                if record is None:
                    continue

                expanded.append({
                    "id": prototype_id,
                    "name": record["name"],
                    "origin": record["origin"],
                    "sectionPath": entry["sectionPath"],
                    "includedBy": source_type,
                    **(
                        {"group": entry["id"]}
                        if source_type == "group"
                        else {}
                    ),
                })

        expanded_guides[guide_name] = expanded

    unlisted = sorted(
        set(custom_records) - listed_custom_ids,
        key=lambda item: custom_records[item]["name"].casefold(),
    )

    unresolved_names = sorted(
        prototype_id
        for prototype_id, record in all_records.items()
        if record["name"] == prototype_id
    )
    if unresolved_names:
        raise RuntimeError(
            "Missing localized reagent names: " + ", ".join(unresolved_names)
        )

    result = {
        "schemaVersion": 1,
        "source": index["source"],
        "generatedAt": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "locale": args.locale,
        "counts": {
            "customReagents": len(custom_records),
            "upstreamDependencies": len(dependency_records),
            "customReactions": len(reactions),
            "unlistedCustomReagents": len(unlisted),
        },
        "guides": expanded_guides,
        "groups": groups,
        "reagents": custom_records,
        "dependencies": dependency_records,
        "reactions": reactions,
        "unlistedReagents": unlisted,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f'Custom reagents: {result["counts"]["customReagents"]}')
    print(f'Upstream dependencies: {result["counts"]["upstreamDependencies"]}')
    print(f'Custom reactions: {result["counts"]["customReactions"]}')
    print(f'Unlisted custom reagents: {result["counts"]["unlistedCustomReagents"]}')


if __name__ == "__main__":
    main()
