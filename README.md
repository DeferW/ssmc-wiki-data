# SSMC Wiki Data

Полное руководство по архитектуре обоих репозиториев находится в
[`ssmc-wiki-app/docs/CONTRIBUTOR_GUIDE.md`](https://github.com/DeferW/ssmc-wiki-app/blob/main/docs/CONTRIBUTOR_GUIDE.md).

Сборщики данных для веб-приложения Space Stories Marine Corps. Репозиторий не
хранит вручную составленный список предметов: данные воспроизводимо строятся из
актуальных прототипов игры.

## Структура

```text
config/
  catalog-sources.yml       автоматы и каталоги карго — корни обхода
  catalog-overrides.json    только редакторские категории
scripts/
  common/                   общий YAML resolver и Fluent-локализация
  catalog/                  предметный каталог
  chemistry/                химия
  mobs/                     параметры людей и каст ксеноморфов
data/
  catalog/                  catalog.json, технический index.json, sprites/
  chemistry/                catalog.json, index.json, guides.json
  mobs/                     catalog.json
```

Модули не импортируют друг друга. Общий код находится только в
`scripts/common`, поэтому новый сборщик можно добавить отдельной папкой, не
связывая его с каталогом или химией.

## Как работает каталог

1. `config/catalog-sources.yml` задаёт торговые автоматы и компьютеры карго.
2. Сборщик читает их предложения и запускает обход графа прототипов.
3. Обход раскрывает ящики, кейсы, наборы, слоты, установленные обвесы,
   гарнитуры, магазины, патроны и снаряды до конечных предметов.
4. Для каждого предмета извлекаются только подходящие механические блоки:
   стрельба, защита, хранение, растворы, связь, обучение, совместимость и связи
   содержимого. Блок не зависит от итоговой категории — приложение само решает,
   что отображать на карточке.
5. Автоклассификатор назначает ровно один раздел.
6. `config/catalog-overrides.json` меняет разделы после автоклассификации. При
   реальном изменении карточка получает `edited: true`.
7. Генерируются публичный `catalog.json`, диагностический `index.json` и PNG.

Разделы: `Оружие`, `Боезапас`, `Обвесы`, `Броня`, `Экипировка`, `Медицина`,
`Снаряжение`, `Другое`, `Скрытые`.

`Скрытые` — обычный раздел, доступный приложению. Автоматически предмет туда
попасть не может; используется override вида:

```json
{
  "schemaVersion": 2,
  "items": {
    "PrototypeId": { "category": "Скрытые" }
  }
}
```

### Публичный и технический JSON

Приложение должно читать `data/catalog/catalog.json`. В нём есть:

- карточки и категории;
- источники и предложения покупки, включая стоимость заказов карго;
- содержимое и другие связи предметов, включая ключи гарнитур;
- все доступные нормализованные блоки характеристик независимо от раздела;
- спрайты и результат редакторских overrides.

`data/catalog/index.json` предназначен для диагностики сборщика: там находятся
полные торговые записи, сырой граф связей и происхождение прототипов. Контрактом
веб-приложения он не является.

## Файлы `scripts/catalog`

- `build.py` — CLI и полный сборочный конвейер.
- `catalog.py` — обход источников и графа, сборка карточек и JSON-документов.
- `classification.py` — механические признаки и правила категорий.
- `config.py` — строгая проверка sources/overrides и применение overrides.
- `core.py` — константы категорий, слотов и публикуемых компонентов.
- `prototypes.py` — специфичные для каталога парсеры размеров и реагентов;
  общий resolver переэкспортируется из `scripts/common`.
- `relations.py` — содержимое, загрузка, снаряды и совместимость.
- `statistics.py` — нормализованные характеристики карточек.
- `sprites.py` — рендер PNG из игровых RSI.
- `reporting.py` — запись JSON, review и сравнение со старой сборкой.
- `validate.py` — проверка публичного контракта и согласованности с index.
- `test_*.py` — модульные тесты.

## Локальный запуск

Из корня репозитория:

```bash
python -m pip install -r requirements.txt

python -m scripts.catalog.build \
  --game-source /path/to/space-stories-cm14 \
  --config config/catalog-sources.yml \
  --index-output data/catalog/index.json \
  --output data/catalog/catalog.json \
  --sprites-output data/catalog/sprites \
  --commit GAME_COMMIT \
  --locale ru-RU

python -m scripts.catalog.validate \
  --catalog data/catalog/catalog.json \
  --index data/catalog/index.json \
  --config config/catalog-sources.yml \
  --sprites data/catalog/sprites

python -m pytest scripts
```

GitHub Actions содержит отдельную ручную сборку для каждого модуля и общие PR
проверки. Публикующие workflows используют одну concurrency-группу, чтобы два
бота не пытались одновременно записать разные `data/` в ветку `main`.
