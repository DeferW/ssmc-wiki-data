from __future__ import annotations

from typing import Any

import yaml


class GameYamlLoader(yaml.SafeLoader):
    """YAML loader that accepts and preserves SS14 custom tags."""


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


def normalize_parents(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []
