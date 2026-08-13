from chemistry_yaml import normalize_parents


def test_normalize_parents_single_string():
    assert normalize_parents("BaseReagent") == ["BaseReagent"]


def test_normalize_parents_list_filters_non_strings():
    assert normalize_parents(["A", 1, "B", None]) == ["A", "B"]


def test_normalize_parents_other_types_return_empty():
    assert normalize_parents(None) == []
    assert normalize_parents(42) == []
    assert normalize_parents({}) == []
