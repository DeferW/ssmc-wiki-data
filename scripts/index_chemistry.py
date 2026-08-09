from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


class GameYamlLoader(yaml.SafeLoader):
    """YAML loader that accepts SS14 tags such as !type:HealthChange."""


def construct_tagged_value(
    loader: GameYamlLoader,
    tag_suffix: str,
    node: yaml.Node,
) -> Any:
    if isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(
            node,
            deep=True,
        )
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(
            node,
            deep=True,
        )
    else:
        value = loader.construct_scalar(node)

    return {
        "yamlTag": f"!{tag_suffix}",
        "value": value,
    }


SOURCE_ROOTS = [
    {
        "path": "Resources/Prototypes/_RMC14/Reagents",
        "origin": "rmc14",
        "prototypeType": "reagent",
    },
    {
        "path": "Resources/Prototypes/_Stories/Reagents",
        "origin": "stories",
        "prototypeType": "reagent",
    },
    {
        "path": "Resources/Prototypes/_RMC14/Recipes/Reactions",
        "origin": "rmc14",
        "prototypeType": "reaction",
    },
    {
        "path": "Resources/Prototypes/_Stories/Recipes/Reactions",
        "origin": "stories",
        "prototypeType": "reaction",
    },
]


def normalize_parents(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]

    if isinstance(value, list):
        return [
            item
            for item in value
            if isinstance(item, str)
        ]

    return []


def read_file(
    game_source: Path,
    path: Path,
    expected_type: str,
    origin: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    with path.open(
        "r",
        encoding="utf-8-sig",
    ) as stream:
        documents = yaml.load_all(
            stream,
            Loader=GameYamlLoader,
        )

        for document in documents:
            if document is None:
                continue

            prototypes = (
                document
                if isinstance(document, list)
                else [document]
            )

            for prototype in prototypes:
                if not isinstance(prototype, dict):
                    continue

                prototype_type = prototype.get("type")
                prototype_id = prototype.get("id")

                if prototype_type != expected_type:
                    continue

                if not isinstance(prototype_id, str):
                    continue

                entries.append({
                    "type": prototype_type,
                    "id": prototype_id,
                    "origin": origin,
                    "sourceFile": path.relative_to(
                        game_source
                    ).as_posix(),
                    "parents": normalize_parents(
                        prototype.get("parent")
                    ),
                    "abstract": bool(
                        prototype.get("abstract", False)
                    ),
                    "definition": {
                        key: value
                        for key, value in prototype.items()
                        if key not in {
                            "type",
                            "id",
                            "parent",
                            "abstract",
                        }
                    },
                })

    return entries


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--game-source",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--commit",
        default="unknown",
    )

    args = parser.parse_args()

    entries: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}

    for source in SOURCE_ROOTS:
        root = args.game_source / source["path"]

        if not root.is_dir():
            raise FileNotFoundError(
                f"Missing source directory: {root}"
            )

        files = sorted([
            *root.rglob("*.yml"),
            *root.rglob("*.yaml"),
        ])

        source_counts[source["path"]] = len(files)

        for path in files:
            entries.extend(read_file(
                game_source=args.game_source,
                path=path,
                expected_type=source["prototypeType"],
                origin=source["origin"],
            ))

    entries.sort(key=lambda entry: (
        entry["type"],
        entry["origin"],
        entry["id"],
        entry["sourceFile"],
    ))

    duplicates: dict[str, list[str]] = {}

    for entry in entries:
        key = f'{entry["type"]}:{entry["id"]}'
        duplicates.setdefault(key, []).append(
            entry["sourceFile"]
        )

    duplicates = {
        key: paths
        for key, paths in duplicates.items()
        if len(paths) > 1
    }

    result = {
        "schemaVersion": 1,
        "source": {
            "repository": "MetalSage/space-stories-cm14",
            "branch": "master",
            "commit": args.commit,
        },
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "sourceFileCounts": source_counts,
        "prototypeCounts": {
            "reagents": sum(
                entry["type"] == "reagent"
                for entry in entries
            ),
            "reactions": sum(
                entry["type"] == "reaction"
                for entry in entries
            ),
        },
        "duplicates": duplicates,
        "entries": entries,
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(
        f'Indexed {result["prototypeCounts"]["reagents"]} reagents'
    )
    print(
        f'Indexed {result["prototypeCounts"]["reactions"]} reactions'
    )
    print(f"Duplicate IDs: {len(duplicates)}")


if __name__ == "__main__":
    main()
