from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from PIL import Image


HIERARCHICAL_RELATIONS = {
    "contains",
    "slotItem",
    "loadedWith",
    "installedAttachment",
    "bundleItem",
    "variant",
    "fires",
}


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return data


def configured_sources(path: Path) -> tuple[list[str], list[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("vendors"), list):
        raise RuntimeError("Invalid equipment config")
    vendor_ids = []
    for entry in data["vendors"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise RuntimeError("Invalid configured vendor")
        vendor_ids.append(entry["id"])
    cargo_ids = []
    cargo_catalogs = data.get("cargoCatalogs", [])
    if not isinstance(cargo_catalogs, list):
        raise RuntimeError("Invalid cargo catalog config")
    for entry in cargo_catalogs:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise RuntimeError("Invalid configured cargo catalog")
        cargo_ids.append(entry["id"])
    return vendor_ids, cargo_ids


def validate_no_hierarchical_cycles(relations: list[dict[str, Any]]) -> None:
    graph: dict[str, list[str]] = defaultdict(list)
    for relation in relations:
        if relation.get("type") in HIERARCHICAL_RELATIONS:
            graph[relation["from"]].append(relation["to"])

    state: dict[str, int] = {}
    active: list[str] = []

    def visit(node: str) -> None:
        status = state.get(node, 0)
        if status == 2:
            return
        if status == 1:
            start = active.index(node)
            raise RuntimeError(
                "Equipment relation cycle: " + " -> ".join(active[start:] + [node])
            )
        state[node] = 1
        active.append(node)
        for target in graph.get(node, []):
            visit(target)
        active.pop()
        state[node] = 2

    for node in sorted(graph):
        visit(node)


def sprite_has_green_tint(path: Path) -> bool:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        for y in range(rgba.height):
            for x in range(rgba.width):
                red, green, blue, alpha = pixels[x, y]
                if alpha and green >= red + 20 and green >= blue + 20:
                    return True
    return False


def validate(
    catalog: dict[str, Any],
    index: dict[str, Any],
    config: Path,
    sprites: Path,
) -> None:
    if catalog.get("schemaVersion") != 1:
        raise RuntimeError("Unexpected equipment catalog schema")
    if index.get("schemaVersion") != 1:
        raise RuntimeError("Unexpected equipment index schema")
    if catalog.get("gameCommit") != index.get("gameCommit"):
        raise RuntimeError("Catalog and index were built from different commits")

    expected_vendors, expected_cargo_catalogs = configured_sources(config)
    expected_sources = [*expected_vendors, *expected_cargo_catalogs]
    vendors = catalog.get("vendors")
    trades = catalog.get("tradeEntries")
    items = catalog.get("items")
    relations = catalog.get("relations")
    counts = catalog.get("counts")
    public_catalog = catalog.get("publicCatalog")

    if not isinstance(vendors, dict) or list(vendors) != expected_sources:
        raise RuntimeError(
            f"Unexpected sources: expected={expected_sources}, "
            f"actual={list(vendors) if isinstance(vendors, dict) else vendors}"
        )
    if not isinstance(trades, list) or not trades:
        raise RuntimeError("No equipment trade entries")
    if not isinstance(items, dict) or not items:
        raise RuntimeError("No equipment items")
    if not isinstance(relations, list):
        raise RuntimeError("Invalid equipment relations")
    if not isinstance(counts, dict):
        raise RuntimeError("Missing equipment counts")
    if not isinstance(public_catalog, dict):
        raise RuntimeError("Missing public equipment catalog")

    trade_keys: set[str] = set()
    direct_ids: set[str] = set()
    for trade in trades:
        if not isinstance(trade, dict):
            raise RuntimeError("Invalid trade entry")
        key = trade.get("key")
        item_id = trade.get("itemId")
        vendor_id = trade.get("vendorId")
        if not isinstance(key, str) or key in trade_keys:
            raise RuntimeError(f"Duplicate or invalid trade key: {key}")
        if item_id not in items:
            raise RuntimeError(f"Trade {key} references missing item {item_id}")
        if vendor_id not in vendors:
            raise RuntimeError(f"Trade {key} references missing vendor {vendor_id}")
        stock = trade.get("stock")
        if stock is not None:
            stock_id = stock.get("itemId") if isinstance(stock, dict) else None
            if stock_id not in index.get("entries", {}):
                raise RuntimeError(f"Trade {key} has unknown stock item {stock_id}")
        trade_keys.add(key)
        direct_ids.add(item_id)

    for item_id, item in items.items():
        if not isinstance(item, dict) or item.get("id") != item_id:
            raise RuntimeError(f"Invalid item card: {item_id}")
        if item_id not in index.get("entries", {}):
            raise RuntimeError(f"Catalog item missing from index: {item_id}")
        reachable = item.get("reachableFromVendors")
        if not isinstance(reachable, list) or not reachable:
            raise RuntimeError(f"Item has no source path: {item_id}")
        unknown_vendors = set(reachable) - set(vendors)
        if unknown_vendors:
            raise RuntimeError(
                f"Item {item_id} has unknown source vendors: {sorted(unknown_vendors)}"
            )

    public_ids = public_catalog.get("itemIds")
    unwrapped_cases = public_catalog.get("unwrappedCaseIds")
    unwrapped_transport = public_catalog.get("unwrappedTransportIds")
    aliases = public_catalog.get("aliases")
    categories = public_catalog.get("categories")
    if not isinstance(public_ids, list) or not public_ids:
        raise RuntimeError("Public equipment catalog is empty")
    if len(public_ids) != len(set(public_ids)):
        raise RuntimeError("Public equipment catalog contains duplicate items")
    if not isinstance(unwrapped_cases, list) or not unwrapped_cases:
        raise RuntimeError("No equipment cases were unwrapped")
    if not isinstance(unwrapped_transport, list) or not unwrapped_transport:
        raise RuntimeError("No transport containers were unwrapped")
    if not isinstance(aliases, dict):
        raise RuntimeError("Missing public item aliases")
    leaked_cases = sorted(set(public_ids).intersection(unwrapped_cases))
    if leaked_cases:
        raise RuntimeError(f"Cases leaked into public catalog: {leaked_cases}")
    leaked_transport = sorted(set(public_ids).intersection(unwrapped_transport))
    if leaked_transport:
        raise RuntimeError(
            f"Transport containers leaked into public catalog: {leaked_transport}"
        )
    leaked_cargo_crates = sorted(
        item_id for item_id in public_ids if item_id.startswith("RMCCrate")
    )
    if leaked_cargo_crates:
        raise RuntimeError(
            f"Cargo crates leaked into public catalog: {leaked_cargo_crates}"
        )
    for alias_id, canonical_id in aliases.items():
        if alias_id in public_ids:
            raise RuntimeError(f"Alias leaked into public catalog: {alias_id}")
        if canonical_id not in public_ids:
            raise RuntimeError(
                f"Alias {alias_id} has non-public canonical item {canonical_id}"
            )
    if not isinstance(categories, dict):
        raise RuntimeError("Missing public equipment categories")

    categorized_ids: list[str] = []
    for category, category_ids in categories.items():
        if not isinstance(category, str) or not isinstance(category_ids, list):
            raise RuntimeError("Invalid public equipment category")
        categorized_ids.extend(category_ids)
        for item_id in category_ids:
            if items.get(item_id, {}).get("category") != category:
                raise RuntimeError(
                    f"Public category mismatch for {item_id}: {category}"
                )
    if sorted(categorized_ids) != sorted(public_ids):
        raise RuntimeError("Public equipment categories do not match public items")

    for item_id in public_ids:
        if item_id not in items:
            raise RuntimeError(f"Public catalog references missing item: {item_id}")
        item = items[item_id]
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise RuntimeError(f"Public item has no name: {item_id}")
        for character in name:
            if character.isdigit():
                break
            if character.isalpha():
                if character != character.upper():
                    raise RuntimeError(
                        f"Public item name is not capitalized: {item_id}"
                    )
                break
        image = item.get("image")
        if image != f"equipment-sprites/{item_id}.png":
            raise RuntimeError(f"Public item has invalid image path: {item_id}")
        sprite_path = sprites / f"{item_id}.png"
        if not sprite_path.is_file() or sprite_path.stat().st_size == 0:
            raise RuntimeError(f"Public item sprite is missing: {item_id}")
        with Image.open(sprite_path) as image_file:
            if image_file.convert("RGBA").getbbox() is None:
                raise RuntimeError(f"Public item sprite is transparent: {item_id}")

    expected_categories = {
        "RMCAttachmentU7UnderbarrelShotgun": "Обвесы",
        "RMCAttachmentUnderbarrelExtinguisher": "Обвесы",
        "RMCAttachmentU1GrenadeLauncher": "Обвесы",
        "CMWrench": "Инструменты",
        "CMScrewdriver": "Инструменты",
        "CMEntrenchingTool": "Инструменты",
        "CMFireExtinguisherPortable": "Инструменты",
        "CMBackpackMarine": "Разгрузка и хранение",
        "RMCBackpackAmmo": "Разгрузка и хранение",
        "RMCBoxMagazinePistolM13": "Боеприпасы",
        "RMCBoxMagazineRifleM54CAP": "Боеприпасы",
        "RMCBoxBulletsRifle": "Боеприпасы",
        "RMCBoxShotgunBuckshot": "Боеприпасы",
        "CMM11Knife": "Ближний бой",
        "CMM2132Machete": "Ближний бой",
        "ArmorHelmetM10": "Броня и защита",
        "RMCArmorM3MediumPadded": "Броня и защита",
        "RMCML66DMount": "Оружейные системы",
    }
    for item_id, expected_category in expected_categories.items():
        actual_category = items.get(item_id, {}).get("category")
        if actual_category != expected_category:
            raise RuntimeError(
                f"Wrong category for {item_id}: "
                f"expected={expected_category}, actual={actual_category}"
            )

    for item_id in public_ids:
        item = items[item_id]
        if "Attachable" in item.get("componentTypes", []):
            if item.get("category") != "Обвесы":
                raise RuntimeError(f"Attachment categorized incorrectly: {item_id}")
        if "RMCAmmoBox" in item.get("tags", []):
            if item.get("category") not in {
                "Боеприпасы",
                "Боеприпасы для техники",
            }:
                raise RuntimeError(f"Ammo box categorized incorrectly: {item_id}")

    if "Прочее" in categories:
        raise RuntimeError("Public catalog contains a catch-all 'Прочее' category")

    if aliases.get("RMCWeaponPistolM13Empty") != "RMCWeaponPistolM13":
        raise RuntimeError("M10 empty/load-state variants were not collapsed")
    m10_public = {
        "RMCWeaponPistolM13",
        "RMCWeaponPistolM13Empty",
    }.intersection(public_ids)
    if m10_public != {"RMCWeaponPistolM13"}:
        raise RuntimeError(f"Unexpected public M10 variants: {sorted(m10_public)}")
    if "RMCML66DMountAssembled" in public_ids or "RMCML66DMountWeaponAssembledLoaded" in public_ids:
        raise RuntimeError("Assembled ML66D state wrapper leaked into public catalog")

    m54c = items.get("RMCWeaponRifleM54C", {})
    expected_slot_names = {"Дуло", "Верхняя планка", "Приклад", "Подствольный слот"}
    actual_slot_names = {
        slot.get("name")
        for slot in m54c.get("attachmentSlots", [])
        if isinstance(slot, dict)
    }
    if not expected_slot_names.issubset(actual_slot_names):
        raise RuntimeError(
            f"M54C attachment slots incomplete: {sorted(actual_slot_names)}"
        )
    if not m54c.get("magazineSlots") or not m54c.get("ammunitionPaths"):
        raise RuntimeError("M54C ammunition compatibility is incomplete")
    suppressor = items.get("RMCAttachmentSuppressor", {})
    if not suppressor.get("attachableTo"):
        raise RuntimeError("Suppressor has no reverse attachment compatibility")
    if "AttachableWeaponRangedMods" not in suppressor.get("properties", {}):
        raise RuntimeError("Attachment mechanical modifiers were not preserved")

    pill_pouch_id = "RMCPouchFirstAidPills"
    if pill_pouch_id not in public_ids:
        raise RuntimeError("Filled pill pouch is missing from public catalog")
    pill_packets = {
        relation.get("to")
        for relation in relations
        if relation.get("from") == pill_pouch_id
        and relation.get("type") == "contains"
    }
    if not pill_packets or not pill_packets.issubset(set(public_ids)):
        raise RuntimeError(
            f"Pill pouch contents were not recursively published: {sorted(pill_packets)}"
        )
    holster = items.get("RMCBeltHolsterPistol", {})
    loadouts = holster.get("loadoutVariants")
    if "RMCBeltHolsterPistol" not in public_ids or not isinstance(loadouts, list) or len(loadouts) < 2:
        raise RuntimeError("Filled holster variants were not merged with their loadouts")

    green_ap_magazines = {
        "CMMagazineSMGM63AP",
        "CMMagazineRifleM54CAP",
        "CMMagazineRifleM4SPRAP",
    }
    for item_id in green_ap_magazines:
        sprite_path = sprites / f"{item_id}.png"
        if not sprite_has_green_tint(sprite_path):
            raise RuntimeError(f"AP magazine lost its green sprite tint: {item_id}")

    distinct_box_sprites = {
        (sprites / "RMCBoxMagazinePistolM13.png").read_bytes(),
        (sprites / "RMCBoxMagazineSMGM63.png").read_bytes(),
        (sprites / "RMCBoxMagazineRifleM54C.png").read_bytes(),
        (sprites / "RMCBoxMagazineRifleM54CAP.png").read_bytes(),
    }
    if len(distinct_box_sprites) != 4:
        raise RuntimeError("Differently colored ammunition boxes rendered identically")

    relation_keys: set[str] = set()
    for relation in relations:
        if not isinstance(relation, dict):
            raise RuntimeError("Invalid relation entry")
        source = relation.get("from")
        target = relation.get("to")
        relation_type = relation.get("type")
        if source not in items or target not in items:
            raise RuntimeError(
                f"Relation references missing item: {source} -[{relation_type}]-> {target}"
            )
        key = json.dumps(relation, ensure_ascii=False, sort_keys=True)
        if key in relation_keys:
            raise RuntimeError(
                f"Duplicate relation: {source} -[{relation_type}]-> {target}"
            )
        relation_keys.add(key)

    validate_no_hierarchical_cycles(relations)

    index_counts = index.get("counts", {})
    if index_counts.get("catalogEntityPrototypes") != len(items):
        raise RuntimeError(
            "Equipment index catalog count does not match catalog items"
        )

    actual_counts = {
        "indexedEntityPrototypes": index_counts.get("indexedEntityPrototypes"),
        "vendors": len(expected_vendors),
        "cargoCatalogs": len(expected_cargo_catalogs),
        "sources": len(vendors),
        "sections": sum(len(vendor.get("sections", [])) for vendor in vendors.values()),
        "tradeEntries": len(trades),
        "directItemPrototypes": len(direct_ids),
        "catalogItems": len(items),
        "publicItems": len(public_ids),
        "relations": len(relations),
    }
    if counts != actual_counts:
        raise RuntimeError(
            f"Equipment count mismatch: stored={counts}, actual={actual_counts}"
        )

    required_cases = {
        "RMCGunCasePistolMK80",
        "RMCGunCasePistolSmart",
        "RMCMOU53Case",
        "RMCCaseXM88",
        "RMCGunCaseRifleM54CE2",
        "RMCM54CMK1Case",
        "RMCML66DCase",
        "RMCM2CCase",
        "RMCCaseFlamer",
        "RMCM85A1Case",
        "RMCGunCasePistolM13",
    }
    missing_cases = required_cases - set(items)
    if missing_cases:
        raise RuntimeError(f"Required gun cases missing: {sorted(missing_cases)}")
    cases_without_contents = sorted(
        case_id
        for case_id in required_cases
        if not any(
            relation.get("from") == case_id
            and relation.get("type") == "contains"
            for relation in relations
        )
    )
    if cases_without_contents:
        raise RuntimeError(f"Gun cases have no contents: {cases_without_contents}")

    empty_weapons = {
        "RMCWeaponPistolM77Empty",
        "RMCWeaponRevolverM44Empty",
        "CMWeaponPistolM1984Empty",
        "RMCWeaponPistolM13Empty",
        "RMCWeaponPistolM82FEmpty",
    }
    incorrectly_loaded = sorted(
        weapon_id
        for weapon_id in empty_weapons
        if any(
            relation.get("from") == weapon_id
            and relation.get("type") == "loadedWith"
            for relation in relations
        )
    )
    if incorrectly_loaded:
        raise RuntimeError(
            f"Empty weapons inherited starting ammunition: {incorrectly_loaded}"
        )

    print(f"Sources: {len(vendors)}")
    print(f"Sections: {actual_counts['sections']}")
    print(f"Trade entries: {len(trades)}")
    print(f"Direct item prototypes: {len(direct_ids)}")
    print(f"Catalog items: {len(items)}")
    print(f"Public equipment items: {len(public_ids)}")
    print(f"Relations: {len(relations)}")
    print("Equipment catalog validation passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate equipment catalog outputs")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--sprites", type=Path, required=True)
    args = parser.parse_args()
    validate(
        read_json(args.catalog),
        read_json(args.index),
        args.config,
        args.sprites,
    )


if __name__ == "__main__":
    main()
