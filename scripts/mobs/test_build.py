import pytest

from scripts.mobs.build import (
    EXCLUDED_XENO_CASTE_IDS,
    apply_bulwark_passive,
    armor_from_component,
    capitalize_first,
    invert_thresholds,
    is_xeno_mob_source_file,
    matured_thresholds,
    rmc_size,
    strain_name,
)
from scripts.common.localization import Localizer
from scripts.common.prototypes import EntityPrototype, PrototypeResolver


def test_invert_thresholds_basic():
    assert invert_thresholds({0: "Alive", 150: "Critical", 200: "Dead"}) == {
        "critical": 150,
        "dead": 200,
    }


def test_invert_thresholds_dead_only_is_allowed():
    # Parasite/larva-style castes have no Critical state, they just die outright.
    assert invert_thresholds({0: "Alive", 35: "Dead"}) == {
        "critical": None,
        "dead": 35,
    }


def test_invert_thresholds_missing_dead_raises():
    with pytest.raises(RuntimeError, match="Dead"):
        invert_thresholds({0: "Alive", 150: "Critical"})


def test_invert_thresholds_unknown_state_raises():
    with pytest.raises(RuntimeError, match="Unknown"):
        invert_thresholds({0: "Alive", 100: "Paralyzed", 200: "Dead"})


def test_invert_thresholds_duplicate_state_raises():
    with pytest.raises(RuntimeError, match="Duplicate"):
        invert_thresholds({100: "Dead", 200: "Dead"})


def test_is_xeno_mob_source_file_accepts_known_directories():
    assert is_xeno_mob_source_file(
        "Resources/Prototypes/_RMC14/Entities/Mobs/Xeno/warrior.yml"
    )
    assert is_xeno_mob_source_file(
        "Resources/Prototypes/_Stories/Entities/Mobs/Xeno/crusher.yml"
    )


def test_is_xeno_mob_source_file_rejects_other_paths():
    assert not is_xeno_mob_source_file(
        "Resources/Prototypes/_RMC14/Entities/Mobs/Species/base.yml"
    )


def test_armor_from_component_reads_known_fields():
    component = {"xenoArmor": 20, "explosionArmor": 40}
    assert armor_from_component(component) == {
        "xenoArmor": 20,
        "frontalArmor": 0,
        "sideArmor": 0,
        "explosionArmor": 40,
        "immuneToArmorPiercing": False,
    }


def test_armor_from_component_defaults_bare_component():
    # base_xeno.yml sets a bare `type: CMArmor` with no fields at all.
    assert armor_from_component({}) == {
        "xenoArmor": 0,
        "frontalArmor": 0,
        "sideArmor": 0,
        "explosionArmor": 0,
        "immuneToArmorPiercing": False,
    }


def test_matured_thresholds_none_when_absent():
    assert matured_thresholds(None) is None


def test_matured_thresholds_reads_queen_style_component():
    component = {"critThreshold": 1000, "deadThreshold": 1100}
    assert matured_thresholds(component) == {"critical": 1000, "dead": 1100}


def test_matured_thresholds_missing_fields_raises():
    with pytest.raises(RuntimeError):
        matured_thresholds({"critThreshold": 1000})


def test_capitalize_first_uppercases_first_letter():
    assert capitalize_first("воин") == "Воин"


def test_apply_bulwark_passive_adds_unconditional_frontal_and_side_bonus():
    # Real data: STXenoWarriorBulwark's base CMArmor has frontalArmor=0,
    # sideArmor=0, but it also carries a bare `type: BulwarkPassive` (no field
    # overrides), whose component defaults are PassiveFrontalBonus=10,
    # PassiveSideBonus=10 -- applied with no Active/toggle guard at all.
    armor = {"xenoArmor": 30, "frontalArmor": 0, "sideArmor": 0, "explosionArmor": 50, "immuneToArmorPiercing": False}
    result = apply_bulwark_passive(armor, {"BulwarkPassive": {}})
    assert result == {"xenoArmor": 30, "frontalArmor": 10, "sideArmor": 10, "explosionArmor": 50, "immuneToArmorPiercing": False}


def test_apply_bulwark_passive_noop_when_component_absent():
    armor = {"xenoArmor": 20, "frontalArmor": 0, "sideArmor": 0, "explosionArmor": 0, "immuneToArmorPiercing": False}
    assert apply_bulwark_passive(armor, {}) == armor


def test_apply_bulwark_passive_respects_explicit_overrides():
    armor = {"xenoArmor": 30, "frontalArmor": 0, "sideArmor": 0, "explosionArmor": 50, "immuneToArmorPiercing": False}
    result = apply_bulwark_passive(armor, {"BulwarkPassive": {"passiveFrontalBonus": 5, "passiveSideBonus": 2}})
    assert result["frontalArmor"] == 5
    assert result["sideArmor"] == 2


def test_strain_name_resolves_the_localized_key():
    # Real data: STXenoWarriorBulwark carries `type: XenoStrain, name:
    # stories-xeno-bulwark-name`, and xeno-strains.ftl defines that key as
    # "Бастион" — a plain top-level Fluent message, not an `ent-...` entity
    # attribute reference.
    localizer = Localizer({"stories-xeno-bulwark-name": "Бастион"})
    components = {"XenoStrain": {"name": "stories-xeno-bulwark-name"}}
    assert strain_name(components, localizer) == "Бастион"


def test_strain_name_none_when_component_absent():
    # The default/base variant of a caste family has no XenoStrain component.
    localizer = Localizer({})
    assert strain_name({}, localizer) is None


def test_strain_name_none_when_key_unresolvable():
    localizer = Localizer({})
    components = {"XenoStrain": {"name": "missing-key"}}
    assert strain_name(components, localizer) is None


def test_rmc_size_reads_the_component_value():
    assert rmc_size({"RMCSize": {"size": "Big"}}) == "Big"


def test_rmc_size_defaults_to_xeno_when_component_absent():
    # RMCSizeComponent.Size defaults to Xeno in the C# component itself.
    assert rmc_size({}) == "Xeno"


def test_rmc_size_defaults_to_xeno_when_value_unrecognized():
    assert rmc_size({"RMCSize": {"size": "NotARealSize"}}) == "Xeno"


def make_prototype(prototype_id, parents=(), abstract=False, components=(), source_file="test.yml"):
    return EntityPrototype(
        id=prototype_id,
        parents=tuple(parents),
        abstract=abstract,
        source_file=source_file,
        origin="rmc14",
        fields={},
        components=tuple(components),
    )


def test_prototype_resolver_merges_inherited_armor_and_thresholds():
    # Mirrors CMXenoBase (abstract, bare CMArmor default) -> CMXenoWarrior
    # (concrete, overrides xenoArmor/explosionArmor and adds its own thresholds).
    prototypes = {
        "CMXenoBase": make_prototype(
            "CMXenoBase",
            abstract=True,
            components=[{"type": "CMArmor"}],
        ),
        "CMXenoWarrior": make_prototype(
            "CMXenoWarrior",
            parents=["CMXenoBase"],
            components=[
                {"type": "MobThresholds", "thresholds": {0: "Alive", 500: "Critical", 600: "Dead"}},
                {"type": "CMArmor", "xenoArmor": 20, "explosionArmor": 40},
            ],
        ),
    }
    resolver = PrototypeResolver(prototypes)

    resolved_abstract = resolver.resolve("CMXenoBase")
    assert "MobThresholds" not in resolved_abstract["components"]

    resolved_concrete = resolver.resolve("CMXenoWarrior")
    assert resolved_concrete["components"]["CMArmor"] == {
        "xenoArmor": 20,
        "explosionArmor": 40,
    }
    assert resolved_concrete["components"]["MobThresholds"]["thresholds"] == {
        0: "Alive",
        500: "Critical",
        600: "Dead",
    }


def test_discovery_filter_includes_concrete_excludes_abstract():
    """The real build_mob_catalog.py discovery loop keeps only non-abstract xeno
    prototypes that resolve to having both MobThresholds and CMArmor — this test
    exercises exactly that filter against tiny in-memory fixtures instead of a
    full game-source checkout."""
    prototypes = {
        "CMXenoBase": make_prototype(
            "CMXenoBase",
            abstract=True,
            source_file="Resources/Prototypes/_RMC14/Entities/Mobs/Xeno/base_xeno.yml",
            components=[{"type": "CMArmor"}],
        ),
        "CMXenoWarrior": make_prototype(
            "CMXenoWarrior",
            parents=["CMXenoBase"],
            source_file="Resources/Prototypes/_RMC14/Entities/Mobs/Xeno/warrior.yml",
            components=[
                {"type": "MobThresholds", "thresholds": {0: "Alive", 500: "Critical", 600: "Dead"}},
                {"type": "CMArmor", "xenoArmor": 20},
            ],
        ),
        "CMXenoHive": make_prototype(
            "CMXenoHive",
            source_file="Resources/Prototypes/_RMC14/Entities/Mobs/Xeno/hive.yml",
            components=[{"type": "Structure"}],
        ),
        "RMCXenoRouny": make_prototype(
            "RMCXenoRouny",
            parents=["CMXenoBase"],
            source_file="Resources/Prototypes/_RMC14/Entities/Mobs/Xeno/rouny.yml",
            components=[
                {"type": "MobThresholds", "thresholds": {0: "Alive", 230: "Critical", 330: "Dead"}},
                {"type": "CMArmor"},
            ],
        ),
    }
    resolver = PrototypeResolver(prototypes)

    kept: list[str] = []
    for prototype in prototypes.values():
        if prototype.abstract or prototype.id in EXCLUDED_XENO_CASTE_IDS:
            continue
        if not is_xeno_mob_source_file(prototype.source_file):
            continue
        resolved = resolver.resolve(prototype.id)
        if "MobThresholds" in resolved["components"] and "CMArmor" in resolved["components"]:
            kept.append(prototype.id)

    assert kept == ["CMXenoWarrior"]
