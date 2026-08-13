from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import yaml


class GameYamlLoader(yaml.SafeLoader):
    """Safe YAML loader that preserves SS14-specific tagged values."""


def _construct_tagged_value(
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
    return {"yamlTag": f"!{tag_suffix}", "value": value}


GameYamlLoader.add_multi_constructor("!", _construct_tagged_value)


def iter_documents(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as stream:
        for document in yaml.load_all(stream, Loader=GameYamlLoader):
            if document is None:
                continue
            values = document if isinstance(document, list) else [document]
            yield from (value for value in values if isinstance(value, dict))


def normalize_parents(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    return ()
