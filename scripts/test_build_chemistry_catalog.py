import pytest

from build_chemistry_catalog import (
    automatic_section,
    localized,
    normalize_amounts,
    resolve_field,
)


def make_prototype(definition, parents=(), origin="rmc14"):
    return {"definition": definition, "parents": list(parents), "origin": origin}


def test_resolve_field_own_definition_wins():
    prototypes = {"Child": make_prototype({"name": "child-name"})}
    assert resolve_field("Child", "name", prototypes, {}) == "child-name"


def test_resolve_field_falls_back_to_parent():
    prototypes = {
        "Child": make_prototype({}, parents=["Parent"]),
        "Parent": make_prototype({"name": "parent-name"}),
    }
    assert resolve_field("Child", "name", prototypes, {}) == "parent-name"


def test_resolve_field_missing_field_returns_none():
    prototypes = {"Child": make_prototype({})}
    assert resolve_field("Child", "name", prototypes, {}) is None


def test_resolve_field_unknown_prototype_returns_none():
    assert resolve_field("Ghost", "name", {}, {}) is None


def test_resolve_field_later_parent_has_precedence():
    # SS14 multiple inheritance: later parents in the list win over earlier ones.
    prototypes = {
        "Child": make_prototype({}, parents=["First", "Second"]),
        "First": make_prototype({"name": "first-name"}),
        "Second": make_prototype({"name": "second-name"}),
    }
    assert resolve_field("Child", "name", prototypes, {}) == "second-name"


def test_resolve_field_detects_circular_inheritance():
    prototypes = {
        "A": make_prototype({}, parents=["B"]),
        "B": make_prototype({}, parents=["A"]),
    }
    with pytest.raises(RuntimeError, match="Circular reagent inheritance"):
        resolve_field("A", "name", prototypes, {})


def test_resolve_field_caches_results():
    cache = {}
    prototypes = {"Child": make_prototype({"name": "child-name"})}
    resolve_field("Child", "name", prototypes, cache)
    assert cache[("Child", "name")] == "child-name"


def test_localized_returns_translation():
    assert localized("chem-water-name", {"chem-water-name": "Вода"}) == "Вода"


def test_localized_falls_back_to_key_when_missing():
    assert localized("chem-unknown", {}) == "chem-unknown"


def test_localized_non_string_returns_none():
    assert localized(None, {}) is None
    assert localized(42, {}) is None


def test_normalize_amounts_uses_linked_reagent_name():
    records = {"Water": {"name": "Вода"}}
    result = normalize_amounts({"Water": 5}, records)
    assert result == [{"id": "Water", "name": "Вода", "amount": 5}]


def test_normalize_amounts_falls_back_to_id_when_unlinked():
    result = normalize_amounts({"Unknown": 3}, {})
    assert result == [{"id": "Unknown", "name": "Unknown", "amount": 3}]


def test_normalize_amounts_reads_catalyst_flag():
    result = normalize_amounts({"Acid": {"amount": 2, "catalyst": True}}, {})
    assert result == [{"id": "Acid", "name": "Acid", "amount": 2, "catalyst": True}]


def test_normalize_amounts_non_dict_returns_empty():
    assert normalize_amounts(None, {}) == []
    assert normalize_amounts([1, 2], {}) == []


CHEMICAL_GROUP_SECTIONS = {"Medicine": ["Медицина"], "Elements": ["Элементы"]}


def test_automatic_section_explicit_override_wins():
    tab_id, section_path, included_by = automatic_section(
        "RMCTableSalt", {"properties": {}, "sourceFile": ""}, CHEMICAL_GROUP_SECTIONS
    )
    assert (tab_id, included_by) == ("other", "explicit-override")
    assert section_path == ["Продукты"]


def test_automatic_section_uses_chemical_group():
    record = {"properties": {"group": "Medicine"}, "sourceFile": ""}
    tab_id, section_path, included_by = automatic_section("SomeReagent", record, CHEMICAL_GROUP_SECTIONS)
    assert tab_id == "medicine"
    assert section_path == ["Медицина"]
    assert included_by == "rmc-chemicals-guide"


def test_automatic_section_source_file_fallback():
    record = {"properties": {}, "sourceFile": "Resources/Prototypes/Reagents/explosives.yml"}
    tab_id, section_path, included_by = automatic_section("SomeReagent", record, CHEMICAL_GROUP_SECTIONS)
    assert (tab_id, section_path, included_by) == ("ordnance", ["Прекурсоры"], "source-file-fallback")


def test_automatic_section_metabolism_fallback():
    record = {"properties": {"metabolisms": {"Narcotic": {}}}, "sourceFile": ""}
    tab_id, section_path, included_by = automatic_section("SomeReagent", record, CHEMICAL_GROUP_SECTIONS)
    assert (tab_id, section_path, included_by) == ("other", ["Наркотики"], "metabolism-fallback")


def test_automatic_section_unclassified_fallback():
    record = {"properties": {}, "sourceFile": ""}
    tab_id, section_path, included_by = automatic_section("SomeReagent", record, CHEMICAL_GROUP_SECTIONS)
    assert (tab_id, section_path, included_by) == ("other", ["Прочее"], "unclassified-fallback")
