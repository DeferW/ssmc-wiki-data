from scripts.catalog.ballistics import weapon_ballistics


def test_defaults_and_explicit_zero():
    result = weapon_ballistics({"Gun": {}, "RMCSelectiveFire": {"scatterWielded": 0}})
    assert result["scatter"] == 0
    assert result["modes"]["FullAuto"]["shotsToMax"] == 4
    assert result["modes"]["FullAuto"]["extraScatter"] == 26
    assert result["availableModes"] == ["SemiAuto"]


def test_empty_dictionary_does_not_restore_component_defaults():
    result = weapon_ballistics({"Gun": {}, "RMCSelectiveFire": {"modifiers": {}}})
    assert result["modes"]["FullAuto"]["extraScatter"] == 0
    assert result["modes"]["FullAuto"]["shotsToMax"] is None


def test_omitted_record_fields_use_record_defaults():
    result = weapon_ballistics({"Gun": {}, "RMCSelectiveFire": {
        "modifiers": {"FullAuto": {"maxScatterModifier": 13, "shotsToMaxScatter": 4}}
    }})
    assert result["modes"]["FullAuto"]["fireDelay"] == 0
    assert result["modes"]["FullAuto"]["scaleExtraScatter"] is False


def test_non_selective_guns_are_not_fabricated():
    assert weapon_ballistics({"Gun": {}}) is None
