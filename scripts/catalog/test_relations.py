from scripts.catalog.relations import add_relation, relation_key, whitelist_matches


def test_relation_key_is_stable_regardless_of_key_order():
    a = {"from": "X", "to": "Y", "type": "contains"}
    b = {"type": "contains", "to": "Y", "from": "X"}
    assert relation_key(a) == relation_key(b)


def test_relation_key_differs_for_different_relations():
    a = {"from": "X", "to": "Y", "type": "contains"}
    b = {"from": "X", "to": "Z", "type": "contains"}
    assert relation_key(a) != relation_key(b)


def test_add_relation_appends_new_relation():
    relations = []
    known = set()
    added = add_relation(relations, known, {"from": "X", "to": "Y", "type": "contains"})
    assert added is True
    assert relations == [{"from": "X", "to": "Y", "type": "contains"}]


def test_add_relation_rejects_duplicate():
    relations = []
    known = set()
    add_relation(relations, known, {"from": "X", "to": "Y", "type": "contains"})
    added_again = add_relation(relations, known, {"from": "X", "to": "Y", "type": "contains"})
    assert added_again is False
    assert len(relations) == 1


def test_whitelist_matches_by_entity_id():
    assert whitelist_matches({"entities": ["RMCWeaponM13"]}, "RMCWeaponM13", set(), set()) is True


def test_whitelist_matches_by_tag():
    assert whitelist_matches({"tags": ["Rifle"]}, "x", {"Rifle"}, set()) is True


def test_whitelist_matches_by_component():
    assert whitelist_matches({"components": ["Gun"]}, "x", set(), {"Gun"}) is True


def test_whitelist_matches_no_overlap_returns_false():
    assert whitelist_matches({"tags": ["Rifle"]}, "x", {"Pistol"}, set()) is False


def test_whitelist_matches_non_dict_returns_false():
    assert whitelist_matches(None, "x", set(), set()) is False
