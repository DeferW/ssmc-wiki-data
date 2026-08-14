from scripts.mobs.sprites import sprite_path_from_component


def test_sprite_path_from_component_reads_sprite_field():
    assert sprite_path_from_component({"sprite": "_Stories/Mobs/Xenos/Warrior/warrior.rsi"}) == (
        "_Stories/Mobs/Xenos/Warrior/warrior.rsi"
    )


def test_sprite_path_from_component_missing_field_returns_none():
    assert sprite_path_from_component({"noRot": True}) is None


def test_sprite_path_from_component_non_dict_returns_none():
    assert sprite_path_from_component(None) is None
