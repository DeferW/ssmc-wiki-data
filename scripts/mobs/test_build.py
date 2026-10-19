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


def test_evasion_is_generated_for_any_new_prototype():
    from scripts.mobs.build import evasion_from_components
    assert evasion_from_components({}) is None
    assert evasion_from_components({"Evasion": {}})["standing"] == 0
    assert evasion_from_components({"Evasion": {"evasion": 20}, "RMCSize": {"size": "Small"}}) == {
        "base": 20, "sizeModifier": 10, "standing": 30,
    }
    assert evasion_from_components({"Evasion": {}, "RMCSize": {"size": "Big"}})["standing"] == -10
    assert evasion_from_components({"Evasion": {}, "RMCSize": {"size": "SmallXeno"}})["standing"] == 0


def test_damage_from_specifier_splits_groups_evenly():
    from scripts.mobs.build import damage_from_specifier
    groups = {"Brute": ["Blunt", "Slash", "Piercing"]}
    assert damage_from_specifier({"groups": {"Brute": 22.5}}, groups) == {
        "Blunt": 7.5, "Slash": 7.5, "Piercing": 7.5,
    }
    assert damage_from_specifier({"types": {"Slash": 10}, "groups": {"Brute": 3}}, groups) == {
        "Slash": 11, "Blunt": 1, "Piercing": 1,
    }
    assert damage_from_specifier(None, groups) == {}


def test_damage_from_specifier_unknown_group_raises():
    from scripts.mobs.build import damage_from_specifier
    with pytest.raises(RuntimeError, match="Unknown damage group"):
        damage_from_specifier({"groups": {"Mystery": 5}}, {"Brute": ["Blunt"]})


def tail_stab_actions():
    # Mirrors xeno_offense_actions.yml: Tail Slam (Defender) inherits the stab
    # event; the lance Alt action raises it with useAltTailStab.
    stab_event = {"yamlTag": "!type:XenoTailStabEvent", "value": {}}
    alt_event = {"yamlTag": "!type:XenoTailStabEvent", "value": {"useAltTailStab": True}}
    return {
        "ActionXenoTailStab": make_prototype("ActionXenoTailStab", components=[
            {"type": "Action", "useDelay": 10},
            {"type": "WorldTargetAction", "event": stab_event},
        ]),
        "ActionXenoTailSlam": make_prototype("ActionXenoTailSlam", parents=["ActionXenoTailStab"]),
        "ActionXenoTailStabLanceAlt": make_prototype("ActionXenoTailStabLanceAlt", parents=["ActionXenoTailStab"], components=[
            {"type": "Action", "useDelay": 3},
            {"type": "WorldTargetAction", "event": alt_event},
        ]),
        "ActionXenoTailFountain": make_prototype("ActionXenoTailFountain", components=[{"type": "Action", "useDelay": 5}]),
    }


def test_attacks_read_claw_and_granted_tail_stab():
    # Mirrors drone.yml: MeleeWeapon Brute 22.5 (attackRate inherited default),
    # XenoTailStab Brute 30, ActionXenoTailStab granted with useDelay 10.
    from scripts.mobs.build import attacks_from_components
    resolver = PrototypeResolver(tail_stab_actions())
    groups = {"Brute": ["Blunt", "Slash", "Piercing"]}
    components = {
        "MeleeWeapon": {"damage": {"groups": {"Brute": 22.5}}},
        "XenoTailStab": {"tailDamage": {"groups": {"Brute": 30}}},
        "Xeno": {"actionIds": ["ActionXenoRest", "ActionXenoTailStab"]},
    }
    attacks = attacks_from_components(components, resolver, groups)
    assert attacks["claw"] == {"damage": {"Blunt": 7.5, "Slash": 7.5, "Piercing": 7.5}, "attackRate": 1.0}
    assert attacks["tail"] == {"damage": {"Blunt": 10, "Slash": 10, "Piercing": 10}, "armorPiercing": 0, "cooldownSeconds": 10}


def test_attacks_skip_tail_without_granted_action_and_lance_alt():
    from scripts.mobs.build import attacks_from_components, tail_stab_action_id
    resolver = PrototypeResolver(tail_stab_actions())
    groups = {"Brute": ["Blunt"]}
    components = {
        "MeleeWeapon": {"damage": {"groups": {"Brute": 12}}, "attackRate": 1.4},
        "XenoTailStab": {"tailDamage": {"groups": {"Brute": 30}}},
        "Xeno": {"actionIds": ["ActionXenoRest", "ActionXenoTailFountain"]},
    }
    attacks = attacks_from_components(components, resolver, groups)
    assert attacks["claw"]["attackRate"] == 1.4
    assert attacks["tail"] is None
    assert tail_stab_action_id({"Xeno": {"actionIds": ["ActionXenoTailStabLanceAlt", "ActionXenoTailSlam"]}}, resolver) == "ActionXenoTailSlam"
