from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from chemistry_yaml import GameYamlLoader, normalize_parents

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


# RMCChemicals.xml задаёт названия и состав химических групп. Здесь остаётся
# только привязка игровых групп к вкладкам интерфейса.
TAB_BY_CHEMICAL_GROUP: dict[str, str] = {
    "Elements": "elements",
    "Medicine": "medicine",
    "Pyrotechnic": "ordnance",
    "Narcotics": "other",
    "Toxins": "other",
    "Foods": "other",
    "Botanical": "other",
    "Biological": "other",
    "Unknown": "other",
}


# Группы, которых нет в RMCChemicals.xml, но которые встречаются в YAML.
FALLBACK_SECTION_BY_GROUP: dict[str, tuple[str, list[str]]] = {
    "Drinks": ("drinks", ["Напитки"]),
}


# У отдельных реагентов в игровых прототипах пока нет группы или метаболизма.
# Такие короткие исключения лучше держать здесь, а не зашивать в интерфейс вики.
AUTO_SECTION_BY_ID: dict[str, tuple[str, list[str]]] = {
    "RMCTableSalt": ("other", ["Продукты"]),
}


AUTO_SECTION_ORDER = {
    ("other", "Наркотики"): 10,
    ("other", "Токсины"): 20,
    ("other", "Биологические"): 30,
    ("other", "Ботанические"): 40,
    ("other", "Продукты"): 50,
    ("other", "Прочее"): 99,
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_chemical_group_sections(
    guides: dict[str, Any],
) -> tuple[str, dict[str, list[str]]]:
    classification_guide = guides.get("classificationGuide")
    if not isinstance(classification_guide, dict):
        raise RuntimeError("Missing RMCChemicals.xml classification guide")

    guide_path = classification_guide.get("path")
    entries = classification_guide.get("entries")
    if not isinstance(guide_path, str) or not guide_path.endswith(
        "/RMCChemicals.xml"
    ):
        raise RuntimeError("Invalid RMCChemicals.xml classification guide path")
    if not isinstance(entries, list):
        raise RuntimeError("Invalid RMCChemicals.xml classification entries")

    group_sections: dict[str, list[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "group":
            continue

        group_id = entry.get("id")
        section_path = entry.get("sectionPath")
        if not isinstance(group_id, str) or not isinstance(section_path, list):
            continue

        clean_path = [item for item in section_path if isinstance(item, str)]
        if clean_path and clean_path[0] == "Химикаты":
            clean_path = clean_path[1:]
        if not clean_path:
            raise RuntimeError(
                f"RMCChemicals.xml group has no section heading: {group_id}"
            )
        if group_id in group_sections:
            raise RuntimeError(
                f"Duplicate group in RMCChemicals.xml: {group_id}"
            )
        group_sections[group_id] = clean_path

    missing_groups = sorted(set(TAB_BY_CHEMICAL_GROUP) - set(group_sections))
    if missing_groups:
        raise RuntimeError(
            "RMCChemicals.xml is missing required groups: "
            + ", ".join(missing_groups)
        )

    return guide_path, group_sections


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


def automatic_section(
    prototype_id: str,
    record: dict[str, Any],
    chemical_group_sections: dict[str, list[str]],
) -> tuple[str, list[str], str]:
    explicit = AUTO_SECTION_BY_ID.get(prototype_id)
    if explicit is not None:
        return *explicit, "explicit-override"

    properties = record.get("properties", {})
    group = properties.get("group")
    if isinstance(group, str) and group in TAB_BY_CHEMICAL_GROUP:
        return (
            TAB_BY_CHEMICAL_GROUP[group],
            chemical_group_sections[group],
            "rmc-chemicals-guide",
        )
    if isinstance(group, str) and group in FALLBACK_SECTION_BY_GROUP:
        tab_id, section_path = FALLBACK_SECTION_BY_GROUP[group]
        return tab_id, section_path, "yaml-group-fallback"

    source_file = record.get("sourceFile", "")
    if source_file.endswith("/Reagents/explosives.yml"):
        return "ordnance", ["Прекурсоры"], "source-file-fallback"
    if "/Reagents/Consumable/Drink/" in source_file:
        return "drinks", ["Напитки"], "source-file-fallback"

    metabolisms = properties.get("metabolisms", {})
    metabolism_names = set(metabolisms) if isinstance(metabolisms, dict) else set()

    if "Narcotic" in metabolism_names:
        return "other", ["Наркотики"], "metabolism-fallback"
    if "Poison" in metabolism_names:
        return "other", ["Токсины"], "metabolism-fallback"
    if "Drink" in metabolism_names:
        return "drinks", ["Напитки"], "metabolism-fallback"
    if "Food" in metabolism_names:
        return "other", ["Продукты"], "metabolism-fallback"

    return "other", ["Прочее"], "unclassified-fallback"


def build_catalog_sections(
    expanded_guides: dict[str, list[dict[str, Any]]],
    custom_records: dict[str, dict[str, Any]],
    chemical_group_sections: dict[str, list[str]],
) -> dict[str, list[dict[str, Any]]]:
    sections = {
        "ordnance": [dict(entry) for entry in expanded_guides["ordnance"]],
        "medicine": [dict(entry) for entry in expanded_guides["medicine"]],
        "drinks": [dict(entry) for entry in expanded_guides["drinks"]],
        "elements": [],
        "other": [],
    }
    included_ids = {
        entry["id"]
        for entries in sections.values()
        for entry in entries
    }

    def remaining_sort_key(prototype_id: str) -> tuple[int, str]:
        tab_id, section_path, _included_by = automatic_section(
            prototype_id,
            custom_records[prototype_id],
            chemical_group_sections,
        )
        section_rank = AUTO_SECTION_ORDER.get(
            (tab_id, section_path[-1]),
            50,
        )
        return section_rank, custom_records[prototype_id]["name"].casefold()

    remaining_ids = sorted(
        set(custom_records) - included_ids,
        key=remaining_sort_key,
    )

    for prototype_id in remaining_ids:
        record = custom_records[prototype_id]
        tab_id, section_path, included_by = automatic_section(
            prototype_id,
            record,
            chemical_group_sections,
        )
        sections[tab_id].append({
            "id": prototype_id,
            "name": record["name"],
            "origin": record["origin"],
            "sectionPath": section_path,
            "includedBy": included_by,
        })

    catalog_ids = [
        entry["id"]
        for entries in sections.values()
        for entry in entries
    ]
    duplicate_ids = sorted({
        prototype_id
        for prototype_id in catalog_ids
        if catalog_ids.count(prototype_id) > 1
    })
    if duplicate_ids:
        raise RuntimeError(
            "Reagents entered multiple catalog sections: "
            + ", ".join(duplicate_ids)
        )

    expected_ids = set(custom_records)
    actual_custom_ids = set(catalog_ids) & expected_ids
    if actual_custom_ids != expected_ids:
        missing_ids = sorted(expected_ids - actual_custom_ids)
        raise RuntimeError(
            "Custom reagents missing from catalog sections: "
            + ", ".join(missing_ids)
        )

    return sections


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
    classification_guide_path, chemical_group_sections = (
        read_chemical_group_sections(guides)
    )

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

    catalog_sections = build_catalog_sections(
        expanded_guides,
        custom_records,
        chemical_group_sections,
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
        "catalogSections": catalog_sections,
        "classification": {
            "guideFile": classification_guide_path,
            "groupSections": chemical_group_sections,
        },
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
