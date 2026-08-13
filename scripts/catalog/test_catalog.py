from scripts.catalog.catalog import (
    capitalize_first,
    cargo_payloads,
    catalog_display_name,
    is_direct_offer,
    should_publish_component,
)


def test_capitalize_first_uppercases_first_letter():
    assert capitalize_first("нож") == "Нож"


def test_capitalize_first_leaves_digit_led_names_untouched():
    assert capitalize_first("9mm пистолет") == "9mm пистолет"


def test_capitalize_first_skips_leading_punctuation():
    assert capitalize_first("«винтовка»") == "«Винтовка»"


def test_catalog_display_name_no_suffix_returns_base_name():
    assert catalog_display_name("Ящик", "") == "Ящик"


def test_catalog_display_name_ignores_load_state_qualifiers():
    assert catalog_display_name("Ящик", "empty") == "Ящик"
    assert catalog_display_name("Ящик", "пуст") == "Ящик"


def test_catalog_display_name_keeps_real_qualifiers():
    assert catalog_display_name("Ящик", "синий") == "Ящик (синий)"


def test_catalog_display_name_keeps_only_non_ignored_qualifiers():
    assert catalog_display_name("Ящик", "empty, синий") == "Ящик (синий)"


def test_catalog_display_name_does_not_repeat_base_name():
    assert catalog_display_name("Капельница", "Капельница") == "Капельница"


def test_catalog_display_name_removes_duplicate_qualifiers():
    assert catalog_display_name("Ящик", "синий, синий") == "Ящик (синий)"


def test_cargo_payloads_marks_bundle_members_without_duplicate_price_root():
    assert cargo_payloads({"crate": "Crate", "entities": ["IV"]}) == [
        {
            "itemId": "Crate",
            "transportContainer": True,
            "includedItemIds": ["IV"],
        },
        {
            "itemId": "IV",
            "transportContainer": False,
            "includedWithItemId": "Crate",
        },
    ]


def test_cargo_payloads_uses_first_entity_as_bundle_root_without_crate():
    assert cargo_payloads({"entities": ["First", "Second"]}) == [
        {
            "itemId": "First",
            "transportContainer": False,
            "includedItemIds": ["Second"],
        },
        {
            "itemId": "Second",
            "transportContainer": False,
            "includedWithItemId": "First",
        },
    ]


def test_direct_offer_excludes_packaging_and_bundle_members():
    assert is_direct_offer({"tradeKey": "direct"}) is True
    assert is_direct_offer({"tradeKey": "stock", "stockForItemId": "Item"}) is False
    assert is_direct_offer({"tradeKey": "bundle", "includedWithItemId": "Crate"}) is False


def test_should_publish_component_rejects_visuals():
    assert should_publish_component("SpriteVisuals") is False
    assert should_publish_component("SomeVisualizer") is False


def test_should_publish_component_accepts_weapon_prefixes():
    assert should_publish_component("AttachableSizeMods") is True
    assert should_publish_component("GunDamageModifier") is True


def test_should_publish_component_rejects_unrelated_component():
    assert should_publish_component("Appearance") is False
