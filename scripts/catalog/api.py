from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from scripts.catalog.catalog import build_catalog
from scripts.catalog.config import read_config
from scripts.common.items.prototypes import read_item_size_definitions
from scripts.common.localization import Localizer, read_fluent_messages
from scripts.common.prototypes import EntityPrototype


def build_catalog_documents(
    *,
    game_source: Path,
    config_path: Path,
    prototypes: dict[str, EntityPrototype],
    game_commit: str,
    locale: str = "ru-RU",
    additional_item_ids: Iterable[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Stable entry point for consumers that need canonical catalog cards."""
    localizer = Localizer(
        read_fluent_messages(game_source / "Resources/Locale" / locale)
    )
    return build_catalog(
        prototypes=prototypes,
        config=read_config(config_path),
        localizer=localizer,
        game_commit=game_commit,
        item_sizes=read_item_size_definitions(game_source),
        additional_item_ids=set(additional_item_ids or ()),
    )
