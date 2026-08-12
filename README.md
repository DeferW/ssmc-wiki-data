# Сборщики данных SSMC Wiki

Репозиторий собирает данные из [`MetalSage/space-stories-cm14`](https://github.com/MetalSage/space-stories-cm14) и сохраняет готовые JSON и спрайты для вики.

## Навигация

- [Химия](#химия)
- [Снаряжение](#снаряжение)
- [Запуск сборки](#запуск-сборки)
- [Настройки](#настройки)
- [Результаты сборки](#результаты-сборки)
- [Ошибки](#ошибки)
- [Структура репозитория](#структура-репозитория)

## Химия

Workflow: [`.github/workflows/build-chemistry-catalog.yml`](.github/workflows/build-chemistry-catalog.yml)

Сборщик:

1. Загружает химические YAML, XML-руководства и локализацию `ru-RU` из ветки `master` игры.
2. Индексирует реагенты и реакции.
3. Разрешает наследование прототипов.
4. Связывает рецепты, ингредиенты и продукты.
5. Распределяет реагенты по разделам.
6. Проверяет итоговый каталог и сохраняет его в `data/`.

Разделы каталога:

- `ordnance` — боевая химия;
- `medicine` — медицина;
- `drinks` — напитки;
- `elements` — элементы;
- `other` — остальные вещества.

Основные скрипты:

- [`scripts/extract_guide_sections.py`](scripts/extract_guide_sections.py) — читает XML-руководства;
- [`scripts/index_chemistry.py`](scripts/index_chemistry.py) — индексирует YAML-прототипы;
- [`scripts/build_chemistry_catalog.py`](scripts/build_chemistry_catalog.py) — собирает итоговый каталог.

## Снаряжение

Workflow: [`.github/workflows/build-equipment-catalog.yml`](.github/workflows/build-equipment-catalog.yml)

Сборщик:

1. Загружает прототипы, локализацию и текстуры из ветки `master` игры.
2. Находит предметы через торговые автоматы и каталог карго.
3. Разрешает наследование и связи между прототипами.
4. Определяет названия, описания, характеристики и категории.
5. Применяет администраторские изменения из [`config/catalog-overrides.json`](config/catalog-overrides.json).
6. Создаёт PNG-спрайты публичных предметов.
7. Проверяет JSON, связи, категории и спрайты.

Основные файлы:

- [`config/equipment-sources.yml`](config/equipment-sources.yml) — источники и правила автоматической классификации;
- [`config/catalog-overrides.json`](config/catalog-overrides.json) — ручное скрытие предметов и смена категорий;
- [`scripts/build_equipment_catalog.py`](scripts/build_equipment_catalog.py) — сборка каталога;
- [`scripts/validate_equipment_catalog.py`](scripts/validate_equipment_catalog.py) — проверка результата.

Overrides применяются после автоматической классификации. Поэтому ручное решение имеет приоритет над правилами сборщика.

## Запуск сборки

### Вручную

1. Открыть вкладку **Actions** в GitHub.
2. Выбрать **Build chemistry catalog** или **Build equipment catalog**.
3. Нажать **Run workflow** и выбрать ветку `main`.
4. Дождаться зелёной отметки.

### После изменения снаряжения в админке

Админка обновляет `config/catalog-overrides.json`. Если в workflow снаряжения настроен `push`-триггер для этого файла, сборка запускается автоматически. Иначе запустите **Build equipment catalog** вручную.

При успешной сборке GitHub Actions создаёт коммит только при наличии изменений. Сообщение `Nothing changed` означает, что итоговые файлы не изменились.

## Настройки

### Добавить источник снаряжения

Откройте [`config/equipment-sources.yml`](config/equipment-sources.yml) и добавьте ID:

- в `vendors` — для торгового автомата;
- в `cargoCatalogs` — для каталога карго.

После изменения запустите сборку снаряжения.

### Скрыть предмет или сменить категорию

Используйте админ-режим сайта. Он записывает изменения в [`config/catalog-overrides.json`](config/catalog-overrides.json).

Формат записи:

```json
{
  "schemaVersion": 1,
  "items": {
    "PrototypeId": {
      "hidden": true
    },
    "AnotherPrototypeId": {
      "category": "Другое"
    }
  }
}
```

JSON не поддерживает комментарии и запятую после последнего поля объекта.

### Изменить автоматическую классификацию

В [`config/equipment-sources.yml`](config/equipment-sources.yml) доступны:

- `excludePrototypeIds` — исключить прототип;
- `includePrototypeIds` — принудительно включить;
- `categoryOverrides` — назначить категорию;
- `canonicalPrototypeIds` — заменить дублирующий ID каноническим.

Эти правила нужны для ошибок или особенностей игровых данных. Обычные ручные изменения делаются через `catalog-overrides.json`.

## Результаты сборки

Файлы в `data/` создаются автоматически. Не редактируйте их вручную.

| Файл | Назначение |
| --- | --- |
| [`data/chemistry-catalog.json`](data/chemistry-catalog.json) | готовый каталог химии для вики |
| [`data/chemistry-guides.json`](data/chemistry-guides.json) | данные XML-руководств |
| [`data/chemistry-index.json`](data/chemistry-index.json) | индекс реагентов и реакций |
| [`data/equipment-catalog.json`](data/equipment-catalog.json) | готовый каталог снаряжения |
| [`data/equipment-index.json`](data/equipment-index.json) | технический индекс снаряжения |
| [`data/equipment-sprites/`](data/equipment-sprites/) | PNG-спрайты публичных предметов |

## Ошибки

### `Invalid catalog overrides JSON`

Файл `config/catalog-overrides.json` содержит ошибку JSON. Откройте указанную в логе строку и проверьте кавычки, запятые и фигурные скобки.

### `Unknown ... ID` или неизвестная категория

В конфиге или overrides указан ID, которого нет в текущих игровых данных, либо неверное название категории. Исправьте указанную запись и повторите сборку.

### Workflow завершился без нового коммита

Если в логе есть `Nothing changed`, сборка прошла успешно, но результат совпал с уже опубликованными файлами.

При любой ошибке workflow не публикует частично собранные данные: предыдущая рабочая версия остаётся в репозитории.

## Структура репозитория

```text
.github/workflows/       GitHub Actions
config/                  источники и ручные overrides
scripts/                 сборщики и валидаторы
data/                    готовые JSON и спрайты
```
