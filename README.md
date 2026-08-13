# SSMC Wiki Data

Репозиторий собирает игровые прототипы из
[`MetalSage/space-stories-cm14`](https://github.com/MetalSage/space-stories-cm14)
в стабильные JSON и PNG для веб-приложения.

## Как работает каталог

1. Источники из `config/equipment-sources.yml` открывают выбранные торговые
   автоматы и карго-каталоги.
2. Графовый обход рекурсивно раскрывает ящики, кейсы, наборы, установленные
   предметы, магазины, патроны и projectile-прототипы.
3. Независимые extractors собирают факты: стрельбу, защиту, растворы,
   хранилища, слоты одежды и другие механики.
4. Классификатор назначает объяснимую автоматическую категорию.
5. `config/catalog-overrides.json` при необходимости меняет финальную категорию.
6. Из фактов формируются компактные характеристики карточек и PNG-спрайты.
7. Валидатор проверяет схему, ссылки, категории, overrides и изображения.

Категории: `Оружие`, `Боезапас`, `Обвесы`, `Броня`, `Экипировка`,
`Медицина`, `Снаряжение`, `Другое`, `Скрытые`.

`Скрытые` — обычный раздел каталога. Автоматически он не назначается и может
появиться только через override. Предметы из него не удаляются из JSON.

## Архитектура

```text
scripts/
├── catalog/                 каталог предметов
│   ├── extractors/          независимые модули фактов
│   ├── tests/               unit-тесты каталога
│   ├── prototypes.py        YAML и наследование
│   ├── sources.py           автоматы и карго
│   ├── graph.py             рекурсивное обнаружение
│   ├── relations.py         содержимое и совместимость
│   ├── facts.py             единая модель фактов
│   ├── classification.py    автоматические категории
│   ├── overrides.py         финальные ручные решения
│   ├── characteristics.py   нормализованные характеристики
│   ├── sprites.py           рендер RSI/PNG
│   ├── builder.py           сборка документов
│   └── validation.py        инварианты результата
├── chemistry/               независимый химический конвейер
└── common/                  общий JSON/YAML infrastructure

data/
├── catalog/
│   ├── catalog.json
│   ├── index.json
│   └── sprites/
└── chemistry/
    ├── catalog.json
    ├── index.json
    └── guides.json
```

`data/catalog/index.json` хранит технический граф и полные факты.
`data/catalog/catalog.json` — компактный публичный документ для приложения.

## Overrides

Формат `config/catalog-overrides.json`:

```json
{
  "schemaVersion": 2,
  "items": {
    "SomePrototype": {
      "category": "Медицина"
    },
    "InternalVariant": {
      "category": "Скрытые"
    }
  }
}
```

Карточка сохраняет `automaticCategory`, `finalCategory`, `edited` и источник
решения. Неизвестные ID, категории и поля останавливают сборку.

## Запуск

Основной способ — workflows в `.github/workflows/`.

Локальная сборка каталога:

```bash
python -m scripts.catalog.build \
  --game-source game-source \
  --config config/equipment-sources.yml \
  --overrides config/catalog-overrides.json \
  --index-output data/catalog/index.json \
  --output data/catalog/catalog.json \
  --sprites-output data/catalog/sprites \
  --commit "$(git -C game-source rev-parse HEAD)" \
  --locale ru-RU
```

Проверки:

```bash
ruff check scripts/
pytest scripts/
python -m scripts.catalog.validate \
  --catalog data/catalog/catalog.json \
  --index data/catalog/index.json \
  --config config/equipment-sources.yml \
  --overrides config/catalog-overrides.json \
  --sprites data/catalog/sprites
```

Сгенерированные файлы в `data/` вручную не редактируются.
