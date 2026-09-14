from pathlib import Path

import yaml

from scripts.chemistry.index import SOURCE_ROOTS

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github/workflows"


def workflow(name):
    return yaml.load((WORKFLOWS / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_all_builders_allow_the_same_pinned_game_commit():
    for name in ("build-catalog.yml", "build-maps.yml", "build-mobs.yml", "build-chemistry-catalog.yml"):
        document = workflow(name)
        assert document["on"]["workflow_dispatch"]["inputs"]["game_ref"]["default"] == "master"
        steps = next(iter(document["jobs"].values()))["steps"]
        checkout = next(step for step in steps if step.get("with", {}).get("path") == "game-source")
        assert checkout["with"]["ref"] == "${{ inputs.game_ref }}"


def test_chemistry_checkout_covers_every_index_source():
    steps = next(iter(workflow("build-chemistry-catalog.yml")["jobs"].values()))["steps"]
    paths = next(step["with"]["sparse-checkout"] for step in steps if "sparse-checkout" in step.get("with", {})).splitlines()
    assert all(root["path"] in paths for root in SOURCE_ROOTS)
    assert "Resources/Prototypes/Reagents" in paths


def test_both_item_builders_check_app_fields_before_publication():
    for name, catalog in (("build-catalog.yml", "data/catalog/catalog.json"), ("build-maps.yml", "data/maps/static-items.json")):
        steps = next(iter(workflow(name)["jobs"].values()))["steps"]
        check = next(i for i, step in enumerate(steps) if "scripts.catalog.validate_weapon_contract" in step.get("run", ""))
        save = next(i for i, step in enumerate(steps) if "git push" in step.get("run", ""))
        assert check < save
        assert catalog in steps[check]["run"]
