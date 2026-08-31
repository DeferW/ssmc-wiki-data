from __future__ import annotations

from pathlib import Path

import pytest

from scripts.catalog.config import read_config


def write_source_config(tmp_path: Path, classification: str = "{}") -> Path:
    path = tmp_path / "catalog-sources.yml"
    path.write_text(
        "schemaVersion: 3\n"
        "vendors:\n"
        "  - id: TestVendor\n"
        "cargoCatalogs: []\n"
        f"classification: {classification}\n",
        encoding="utf-8",
    )
    return path


def test_catalog_source_config_requires_current_schema(tmp_path: Path):
    path = write_source_config(tmp_path)
    contents = path.read_text(encoding="utf-8").replace("3", "2", 1)
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(RuntimeError, match="schemaVersion 3"):
        read_config(path)


def test_catalog_source_config_rejects_unused_policy_options(tmp_path: Path):
    path = write_source_config(tmp_path, "{canonicalPrototypeIds: {Old: New}}")

    with pytest.raises(RuntimeError, match="Unknown catalog classification options"):
        read_config(path)
