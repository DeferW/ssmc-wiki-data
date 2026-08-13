from __future__ import annotations

from pathlib import Path

import pytest

from scripts.catalog.config import read_catalog_overrides


EMPTY_OVERRIDES = {"schemaVersion": 2, "items": {}}


@pytest.mark.parametrize("contents", ["", "   \n", "{}", '{"schemaVersion": 2, "items": {}}'])
def test_empty_catalog_overrides_are_disabled(tmp_path: Path, contents: str):
    path = tmp_path / "catalog-overrides.json"
    path.write_text(contents, encoding="utf-8")

    assert read_catalog_overrides(path) == EMPTY_OVERRIDES


def test_missing_catalog_overrides_are_disabled(tmp_path: Path):
    assert read_catalog_overrides(tmp_path / "missing.json") == EMPTY_OVERRIDES


def test_nonempty_malformed_catalog_overrides_still_fail(tmp_path: Path):
    path = tmp_path / "catalog-overrides.json"
    path.write_text('{"items": {"Example": {"category": "Другое"}}}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="schemaVersion 2"):
        read_catalog_overrides(path)
