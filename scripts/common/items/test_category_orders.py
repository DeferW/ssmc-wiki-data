from scripts.common.items.categories import supported_category_order


def test_category_validation_accepts_complete_old_and_new_snapshots_only():
    old = [
        "Оружие",
        "Боезапас",
        "Обвесы",
        "Броня",
        "Экипировка",
        "Медицина",
        "Снаряжение",
        "Другое",
        "Скрытые",
    ]
    new = [
        "Оружие",
        "Боезапас",
        "Обвесы",
        "Броня",
        "Одежда",
        "Экипировка",
        "Медицина",
        "Снаряжение",
        "Инструменты",
        "Электроника",
        "Провизия",
        "Быт",
        "Материалы",
        "Контейнеры",
        "Другое",
        "Скрытые",
    ]
    assert supported_category_order(old)
    assert supported_category_order(new)
    assert not supported_category_order(new[:-1])
    assert not supported_category_order([*old, "Unknown"])
    assert not supported_category_order(list(reversed(new)))
