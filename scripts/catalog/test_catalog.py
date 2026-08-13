from scripts.catalog.catalog import capitalize_first, catalog_display_name, should_publish_component


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


def test_should_publish_component_rejects_visuals():
    assert should_publish_component("SpriteVisuals") is False
    assert should_publish_component("SomeVisualizer") is False


def test_should_publish_component_accepts_weapon_prefixes():
    assert should_publish_component("AttachableSizeMods") is True
    assert should_publish_component("GunDamageModifier") is True


def test_should_publish_component_rejects_unrelated_component():
    assert should_publish_component("Appearance") is False
