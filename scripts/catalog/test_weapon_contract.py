import copy

import pytest

from scripts.catalog.statistics import populate_weapon_statistics
from scripts.catalog.validate_weapon_contract import validate_weapon_contract


def catalog():
    items = {"NewGun": {"properties": {"Gun": {}, "RMCSelectiveFire": {}}}}
    populate_weapon_statistics(items, [], {"NewGun"})
    return {"items": items, "publicCatalog": {"itemIds": ["NewGun"]}}


def test_generated_weapon_contract():
    assert validate_weapon_contract(catalog()) == 1


@pytest.mark.parametrize("field", ["ballistics", "scatter", "recoil"])
def test_missing_generated_fields_block_publication(field):
    result = copy.deepcopy(catalog())
    del result["items"]["NewGun"]["weaponStats"][field]
    with pytest.raises(RuntimeError, match="NewGun"):
        validate_weapon_contract(result)
