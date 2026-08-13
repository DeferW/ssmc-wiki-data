import json

import pytest

from scripts.catalog.config import Override, read_overrides
from scripts.catalog.models import CATEGORY_HIDDEN
from scripts.catalog.overrides import apply_overrides


def test_hidden_is_a_category_and_sets_edited():
    records = {
        "Item": {
            "automaticCategory": "Другое",
            "reason": "fallback",
            "signals": [],
        }
    }
    apply_overrides(records, {"Item": Override(CATEGORY_HIDDEN)})
    assert records["Item"]["finalCategory"] == CATEGORY_HIDDEN
    assert records["Item"]["edited"] is True
    assert records["Item"]["source"] == "override"


def test_matching_override_is_not_marked_edited():
    records = {
        "Item": {
            "automaticCategory": "Другое",
            "reason": "fallback",
            "signals": [],
        }
    }
    apply_overrides(records, {"Item": Override("Другое")})
    assert records["Item"]["edited"] is False


def test_legacy_hidden_field_is_rejected(tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text(
        json.dumps({"schemaVersion": 2, "items": {"Item": {"hidden": True}}}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Unknown override fields"):
        read_overrides(path)

