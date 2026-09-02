from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


CATEGORY_ORDER = (
    "Оружие",
    "Боезапас",
    "Обвесы",
    "Броня",
    "Экипировка",
    "Медицина",
    "Снаряжение",
    "Другое",
    "Скрытые",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def effective_items(
    catalog: dict[str, Any],
    map_items: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    memberships: dict[str, set[str]] = defaultdict(set)
    for source, document in (("catalog", catalog), ("maps", map_items)):
        public_ids = document.get("publicCatalog", {}).get("itemIds", [])
        items = document.get("items", {})
        for item_id in public_ids:
            item = items.get(item_id)
            if not isinstance(item, dict):
                continue
            memberships[item_id].add(source)
            result[item_id] = {
                "id": item_id,
                "name": str(item.get("name") or item_id),
                "category": str(item.get("category") or "Другое"),
                "automaticCategory": str(item.get("category") or "Другое"),
            }

    override_items = overrides.get("items", {})
    if isinstance(override_items, dict):
        for item_id, override in override_items.items():
            if item_id not in result or not isinstance(override, dict):
                continue
            category = override.get("category")
            if isinstance(category, str) and category in CATEGORY_ORDER:
                result[item_id]["category"] = category
                result[item_id]["edited"] = category != result[item_id]["automaticCategory"]

    for item_id, entry in result.items():
        entry["source"] = "+".join(sorted(memberships[item_id]))
    return result


def category_counts(items: dict[str, dict[str, Any]]) -> Counter[str]:
    return Counter(str(item["category"]) for item in items.values())


def item_line(item: dict[str, Any]) -> str:
    edited = " · EDITED" if item.get("edited") else ""
    return f"- {item['name']} — `{item['id']}` · {item['source']}{edited}"


def append_full_list(lines: list[str], title: str, items: dict[str, dict[str, Any]]) -> None:
    lines.extend((f"## {title}", ""))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items.values():
        grouped[str(item["category"])].append(item)
    for category in CATEGORY_ORDER:
        entries = sorted(grouped.get(category, []), key=lambda item: (item["name"].casefold(), item["id"]))
        lines.extend((f"### {category} ({len(entries)})", ""))
        lines.extend(item_line(item) for item in entries)
        lines.append("")


def build_report(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]] | None,
) -> str:
    lines = [
        "# Аудит расширения каталога предметов карт",
        "",
        "Список учитывает основной каталог, каталог предметов карт и редакторские overrides приложения.",
        "`catalog+maps` означает, что предмет присутствует в обоих источниках.",
        "",
        f"Исходный объединённый каталог: **{len(before)} предметов**.",
        "",
    ]
    before_counts = category_counts(before)
    if after is None:
        lines.extend(("## Исходные количества", "", "| Категория | Предметов |", "|---|---:|"))
        lines.extend(f"| {category} | {before_counts[category]} |" for category in CATEGORY_ORDER)
        lines.append("")
        append_full_list(lines, "Полный исходный список", before)
        return "\n".join(lines)

    after_counts = category_counts(after)
    before_ids = set(before)
    after_ids = set(after)
    added = sorted(after_ids - before_ids, key=lambda item_id: (after[item_id]["name"].casefold(), item_id))
    removed = sorted(before_ids - after_ids, key=lambda item_id: (before[item_id]["name"].casefold(), item_id))
    category_changes = sorted(
        (
            item_id
            for item_id in before_ids & after_ids
            if before[item_id]["category"] != after[item_id]["category"]
        ),
        key=lambda item_id: (after[item_id]["name"].casefold(), item_id),
    )
    renamed = sorted(
        (
            item_id
            for item_id in before_ids & after_ids
            if before[item_id]["name"] != after[item_id]["name"]
        ),
        key=lambda item_id: item_id,
    )
    source_changes = sorted(
        (
            item_id
            for item_id in before_ids & after_ids
            if before[item_id]["source"] != after[item_id]["source"]
        ),
        key=lambda item_id: (after[item_id]["name"].casefold(), item_id),
    )

    lines.extend(
        (
            f"Новый объединённый каталог: **{len(after)} предметов**.",
            "",
            "## Итог",
            "",
            f"- Добавлено: **{len(added)}**.",
            f"- Удалено: **{len(removed)}**.",
            f"- Сменили категорию: **{len(category_changes)}**.",
            f"- Переименовано: **{len(renamed)}**.",
            f"- Уже существовали, но дополнительно вошли в каталог карт: **{len(source_changes)}**.",
            "",
            "| Категория | Было | Стало | Разница |",
            "|---|---:|---:|---:|",
        )
    )
    for category in CATEGORY_ORDER:
        delta = after_counts[category] - before_counts[category]
        lines.append(f"| {category} | {before_counts[category]} | {after_counts[category]} | {delta:+d} |")

    lines.extend(("", "## Добавленные предметы", ""))
    if added:
        grouped_added: dict[str, list[str]] = defaultdict(list)
        for item_id in added:
            grouped_added[str(after[item_id]["category"])].append(item_id)
        for category in CATEGORY_ORDER:
            category_ids = grouped_added.get(category, [])
            if not category_ids:
                continue
            lines.extend((f"### {category} ({len(category_ids)})", ""))
            lines.extend(item_line(after[item_id]) for item_id in category_ids)
            lines.append("")
    else:
        lines.extend(("Новых предметов нет.", ""))

    lines.extend(("## Уже существовавшие предметы, добавленные в каталог карт", ""))
    if source_changes:
        grouped_sources: dict[str, list[str]] = defaultdict(list)
        for item_id in source_changes:
            grouped_sources[str(after[item_id]["category"])].append(item_id)
        for category in CATEGORY_ORDER:
            category_ids = grouped_sources.get(category, [])
            if not category_ids:
                continue
            lines.extend((f"### {category} ({len(category_ids)})", ""))
            for item_id in category_ids:
                lines.append(
                    f"- {after[item_id]['name']} — `{item_id}`: "
                    f"{before[item_id]['source']} → {after[item_id]['source']}"
                )
            lines.append("")
    else:
        lines.extend(("Таких предметов нет.", ""))

    lines.extend(("## Удалённые предметы", ""))
    lines.extend(item_line(before[item_id]) for item_id in removed)
    if not removed:
        lines.append("Удалённых предметов нет.")
    lines.append("")

    lines.extend(("## Изменения категорий", ""))
    for item_id in category_changes:
        lines.append(
            f"- {after[item_id]['name']} — `{item_id}`: "
            f"{before[item_id]['category']} → {after[item_id]['category']}"
        )
    if not category_changes:
        lines.append("Изменений категорий нет.")
    lines.append("")

    lines.extend(("## Переименованные предметы", ""))
    for item_id in renamed:
        lines.append(f"- `{item_id}`: {before[item_id]['name']} → {after[item_id]['name']}")
    if not renamed:
        lines.append("Переименований нет.")
    lines.append("")

    append_full_list(lines, "Полный новый список", after)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare effective app catalogs before and after a map item rebuild")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    catalog = read_json(args.catalog)
    overrides = read_json(args.overrides)
    before = effective_items(catalog, read_json(args.before), overrides)
    after = effective_items(catalog, read_json(args.after), overrides) if args.after else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_report(before, after) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} ({len(before)} before, {len(after) if after else 0} after)")


if __name__ == "__main__":
    main()
