from scripts.catalog.statistics import (
    box_cells,
    default_storage_max_size,
    packing_capacity,
    parse_vector2i,
    shape_cells,
    storage_whitelist_matches,
)


def test_box_cells_single_1x1_box():
    assert box_cells([(0, 0, 0, 0)]) == {(0, 0)}


def test_box_cells_covers_full_rectangle():
    assert box_cells([(0, 0, 1, 1)]) == {(0, 0), (0, 1), (1, 0), (1, 1)}


def test_shape_cells_normalizes_to_origin():
    # A box that doesn't start at (0, 0) should be shifted so its minimum corner is (0, 0).
    assert shape_cells([(2, 3, 3, 4)]) == {(0, 0), (0, 1), (1, 0), (1, 1)}


def test_packing_capacity_fits_expected_count():
    grid = [(0, 0, 1, 1)]  # 2x2 grid = 4 cells
    item = [(0, 0, 0, 0)]  # 1x1 item
    assert packing_capacity(grid, item) == 4


def test_packing_capacity_item_bigger_than_grid():
    grid = [(0, 0, 0, 0)]  # 1x1 grid
    item = [(0, 0, 1, 1)]  # 2x2 item
    assert packing_capacity(grid, item) == 0


def test_packing_capacity_empty_grid_or_item_returns_zero():
    assert packing_capacity([], [(0, 0, 0, 0)]) == 0
    assert packing_capacity([(0, 0, 0, 0)], []) == 0


def test_parse_vector2i_from_string():
    assert parse_vector2i("3,4", default=(0, 0)) == (3, 4)


def test_parse_vector2i_from_list():
    assert parse_vector2i([3, 4], default=(0, 0)) == (3, 4)


def test_parse_vector2i_invalid_returns_default():
    assert parse_vector2i("not-a-vector", default=(1, 1)) == (1, 1)
    assert parse_vector2i(None, default=(1, 1)) == (1, 1)


def test_storage_whitelist_matches_true_when_no_rule():
    assert storage_whitelist_matches(None, {}) is True


def test_storage_whitelist_matches_by_component():
    rule = {"components": ["Gun"]}
    item = {"componentTypes": ["Gun"], "tags": []}
    assert storage_whitelist_matches(rule, item) is True


def test_storage_whitelist_matches_require_all():
    rule = {"requireAll": True, "components": ["Gun"], "sizes": ["Small"]}
    item = {"componentTypes": ["Gun"], "itemSize": "Normal", "tags": []}
    assert storage_whitelist_matches(rule, item) is False


def test_default_storage_max_size_picks_size_below_container():
    item_sizes = {
        "Small": {"weight": 1},
        "Normal": {"weight": 2},
        "Large": {"weight": 3},
    }
    assert default_storage_max_size("Large", item_sizes) == "Normal"


def test_default_storage_max_size_unknown_container_prefers_normal():
    item_sizes = {"Small": {"weight": 1}, "Normal": {"weight": 2}}
    assert default_storage_max_size("Unknown", item_sizes) == "Normal"
