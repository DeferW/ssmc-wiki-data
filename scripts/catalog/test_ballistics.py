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


def test_one_handed_defaults_and_overrides():
    defaults = weapon_ballistics({"Gun": {}, "RMCSelectiveFire": {}})
    assert defaults["scatterUnwielded"] == 10
    assert defaults["recoilUnwielded"] == 1
    assert defaults["modes"]["FullAuto"]["unwieldedMultiplier"] == 2
    explicit = weapon_ballistics({"Gun": {}, "RMCSelectiveFire": {
        "scatterUnwielded": 20, "recoilUnwielded": 4,
        "modifiers": {"FullAuto": {"unwieldedScatterMultiplier": 0}}
    }})
    assert explicit["scatterUnwielded"] == 20
    assert explicit["recoilUnwielded"] == 4
    assert explicit["modes"]["FullAuto"]["unwieldedMultiplier"] == 0
