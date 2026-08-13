from scripts.catalog.prototypes import normalize_parents, origin_from_path, parse_box2i


def test_normalize_parents_single_string():
    assert normalize_parents("Base") == ("Base",)


def test_normalize_parents_list_filters_non_strings():
    assert normalize_parents(["A", 2, "B"]) == ("A", "B")


def test_normalize_parents_other_types_return_empty_tuple():
    assert normalize_parents(None) == ()


def test_origin_from_path_stories():
    assert origin_from_path("Resources/Prototypes/_Stories/Reagents/foo.yml") == "stories"


def test_origin_from_path_rmc14():
    assert origin_from_path("Resources/Prototypes/_RMC14/Reagents/foo.yml") == "rmc14"


def test_origin_from_path_defaults_to_upstream():
    assert origin_from_path("Resources/Prototypes/Reagents/foo.yml") == "upstream"


def test_parse_box2i_from_string():
    assert parse_box2i("0,0,1,1") == (0, 0, 1, 1)


def test_parse_box2i_from_list():
    assert parse_box2i([0, 1, 2, 3]) == (0, 1, 2, 3)


def test_parse_box2i_wrong_length_returns_none():
    assert parse_box2i("0,0,1") is None


def test_parse_box2i_non_numeric_returns_none():
    assert parse_box2i("a,b,c,d") is None


def test_parse_box2i_unsupported_type_returns_none():
    assert parse_box2i(None) is None
