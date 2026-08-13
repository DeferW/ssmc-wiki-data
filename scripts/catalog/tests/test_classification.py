from scripts.catalog.classification import classify
from scripts.catalog.models import (
    CATEGORY_AMMUNITION,
    CATEGORY_ARMOR,
    CATEGORY_ATTACHMENT,
    CATEGORY_EQUIPMENT,
    CATEGORY_GEAR,
    CATEGORY_MEDICINE,
    CATEGORY_OTHER,
    CATEGORY_WEAPON,
)


def facts(**signals):
    base = {
        "gun": False,
        "attachment": False,
        "projectile": False,
        "cartridge": False,
        "ammoProvider": False,
        "explosive": False,
        "armor": False,
        "storage": False,
        "clothing": False,
        "utility": False,
        "melee": False,
        "projectilePath": False,
        "explosivePayload": False,
        "medicalPayload": False,
    }
    base.update(signals)
    return {
        "signals": base,
        "wearableSlots": [],
        "componentTypes": [],
        "tags": [],
        "medicalFunction": False,
    }


def test_attachment_wins_over_embedded_gun():
    value = facts(attachment=True, gun=True)
    assert classify("UnderbarrelGun", "Подствольник", value).category == CATEGORY_ATTACHMENT


def test_gun_is_weapon():
    assert classify("Rifle", "Винтовка", facts(gun=True)).category == CATEGORY_WEAPON


def test_projectile_container_is_ammunition():
    value = facts(storage=True, projectilePath=True)
    assert classify("AmmoBox", "Коробка патронов", value).category == CATEGORY_AMMUNITION


def test_generic_case_does_not_inherit_weapon_category():
    value = facts(storage=True, projectilePath=True)
    assert classify("GunCase", "Оружейный кейс", value).category == CATEGORY_OTHER


def test_defibrillator_is_medical_even_when_wearable():
    value = facts(storage=True)
    value["wearableSlots"] = ["back"]
    value["medicalFunction"] = True
    assert classify("Defibrillator", "Дефибриллятор", value).category == CATEGORY_MEDICINE


def test_armor_requires_protection_and_only_armor_slots():
    value = facts(armor=True, clothing=True)
    value["wearableSlots"] = ["outerClothing"]
    assert classify("Armor", "Броня", value).category == CATEGORY_ARMOR
    value["wearableSlots"] = ["outerClothing", "back"]
    assert classify("Armor", "Броня", value).category != CATEGORY_ARMOR


def test_visor_is_gear_before_wearable_equipment():
    value = facts(utility=True, clothing=True)
    value["wearableSlots"] = ["eyes"]
    assert classify("MedicalVisor", "Визор", value).category == CATEGORY_GEAR


def test_regular_wearable_is_equipment():
    value = facts(storage=True, clothing=True)
    value["wearableSlots"] = ["belt"]
    assert classify("Belt", "Пояс", value).category == CATEGORY_EQUIPMENT
