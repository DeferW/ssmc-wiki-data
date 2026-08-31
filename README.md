# SSMC Wiki

SSMC Wiki — неофициальная модульная база данных и набор веб-инструментов для
**Space Stories Marine Corps**. Проект состоит из двух репозиториев:
[`ssmc-wiki-data`](https://github.com/DeferW/ssmc-wiki-data) собирает данные из
исходников игры, а [`ssmc-wiki-app`](https://github.com/DeferW/ssmc-wiki-app)
публикует сайт и работает с готовыми контрактами.

- [Планы и TODO](https://github.com/DeferW/ssmc-wiki-app/blob/main/docs/ROADMAP.md)
- [Руководство контрибьютора](https://github.com/DeferW/ssmc-wiki-app/blob/main/docs/CONTRIBUTOR_GUIDE.md)

## Роль репозитория

`ssmc-wiki-data` — набор воспроизводимых сборщиков. Он читает прототипы,
локализацию, ресурсы и явно заданную конфигурацию, разрешает игровые связи и
публикует устойчивые JSON-контракты с готовыми ассетами. Сгенерированные файлы
находятся в `data/` и не редактируются вручную.

## Общая архитектура

```text
исходники игры + config сборщика
            ↓
ssmc-wiki-data/scripts/<module>
read → resolve → normalize → validate → publish
            ↓
ssmc-wiki-data/data/<module-id>
публичный JSON-контракт + ассеты
            ↓ точная замена при deploy
ssmc-wiki-app/public/data → dist/data
            ↓
loader + types → логика модуля → UI
            ↓
GitHub Pages → пользователь
```

`data/<module-id>/` — граница между репозиториями. При deploy приложения свежий
`data/` полностью заменяет `public/data/`, поэтому удалённые сборщиком файлы не
остаются в публикации. Браузер получает сайт, JSON и ассеты с одного GitHub
Pages-адреса и не обращается к GitHub Raw при открытии модулей.

## Архитектура сборщика

```text
config/                    редактируемые настройки и выбор источников
scripts/common/            общие парсеры и устойчивые примитивы
scripts/<module_package>/  изолированный сборщик предметной области
data/<module-id>/          опубликованный JSON-контракт и ассеты
.github/workflows/         проверки и воспроизводимые сборки модулей
requirements.txt           runtime-зависимости Python
pyproject.toml             настройки тестов и статического анализа
```

Каждый сборщик владеет чтением источников, разрешением наследования и ссылок,
нормализацией предметной модели, сериализацией, валидатором, тестами и своей
выходной папкой. Общий код выносится в `scripts/common/` только когда у него есть
несколько реальных потребителей.

## Контракт и изменения

Публичной точкой входа обычно служит `data/<module-id>/catalog.json` с явной
`schemaVersion`. Приложение использует только публичные документы и ассеты;
диагностические индексы и промежуточные результаты могут меняться без обратной
совместимости.

Ломающее изменение типа, структуры или смысла поля получает новую
`schemaVersion`. Сначала здесь публикуется совместимый набор данных, затем
обновляется приложение. Сборка должна быть детерминированной: одинаковые
исходники, конфигурация и commit игры дают одинаковый результат.

## Локальная проверка

Требуются Python 3.11 или новее и зависимости проекта.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install pytest ruff
```

Перед pull request:

```powershell
python -m ruff check scripts
python -m pytest scripts
```

Параметры конкретного сборщика смотрите через его `--help` или workflow в
`.github/workflows/`. Сборщик должен записывать результат только в принадлежащую
ему папку `data/<module-id>/` и удалять из неё устаревшие файлы.
