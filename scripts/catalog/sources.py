from __future__ import annotations

from typing import Any

from scripts.catalog.config import CatalogConfig
from scripts.catalog.localization import Localizer
from scripts.catalog.models import SourceEntry
from scripts.catalog.prototypes import PrototypeResolver


def discover_sources(
    config: CatalogConfig,
    resolver: PrototypeResolver,
    localizer: Localizer,
) -> tuple[dict[str, Any], list[SourceEntry]]:
    sources: dict[str, Any] = {}
    entries: list[SourceEntry] = []

    for vendor_id in config.vendor_ids:
        vendor = resolver.resolve(vendor_id)
        component = vendor["components"].get("CMAutomatedVendor")
        if not isinstance(component, dict) or not isinstance(component.get("sections"), list):
            raise RuntimeError(f"Vendor {vendor_id} has no CMAutomatedVendor sections")
        sections: list[dict[str, Any]] = []
        for section_index, raw_section in enumerate(component["sections"]):
            if not isinstance(raw_section, dict):
                continue
            section_name = str(raw_section.get("name", f"Section {section_index + 1}"))
            section_entries: list[str] = []
            for position, raw in enumerate(raw_section.get("entries", [])):
                if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
                    continue
                item_id = raw["id"]
                if item_id not in resolver.prototypes:
                    raise RuntimeError(f"Vendor {vendor_id} references unknown item {item_id}")
                key = f"{vendor_id}:{section_index}:{position}"
                metadata = {
                    key: raw[key]
                    for key in ("amount", "spawn", "points", "recommended", "multiplier", "max")
                    if key in raw
                }
                entries.append(
                    SourceEntry(key, vendor_id, "vendor", section_name, item_id, position, metadata)
                )
                section_entries.append(key)
                stock_id = raw.get("box")
                if isinstance(stock_id, str):
                    if stock_id not in resolver.prototypes:
                        raise RuntimeError(f"Vendor {vendor_id} references unknown box {stock_id}")
                    stock_key = f"{key}:stock"
                    entries.append(
                        SourceEntry(
                            stock_key,
                            vendor_id,
                            "vendor-stock",
                            section_name,
                            stock_id,
                            position,
                            {"productId": item_id, "amount": raw.get("boxAmount")},
                        )
                    )
                    section_entries.append(stock_key)
            sections.append({"name": section_name, "position": section_index, "entries": section_entries})
        sources[vendor_id] = {
            "id": vendor_id,
            "type": "vendor",
            "name": localizer.entity_text(vendor_id, None, vendor["fields"].get("name")),
            "sections": sections,
        }

    for catalog_id in config.cargo_catalog_ids:
        catalog = resolver.resolve(catalog_id)
        component = catalog["components"].get("RequisitionsComputer")
        if not isinstance(component, dict) or not isinstance(component.get("categories"), list):
            raise RuntimeError(f"Cargo catalog {catalog_id} has no RequisitionsComputer categories")
        sections: list[dict[str, Any]] = []
        for section_index, raw_section in enumerate(component["categories"]):
            if not isinstance(raw_section, dict):
                continue
            section_name = str(raw_section.get("name", f"Section {section_index + 1}"))
            section_entries: list[str] = []
            for position, raw in enumerate(raw_section.get("entries", [])):
                if not isinstance(raw, dict):
                    continue
                payloads: list[tuple[str, str]] = []
                if isinstance(raw.get("crate"), str):
                    payloads.append((raw["crate"], "crate"))
                if isinstance(raw.get("entities"), list):
                    payloads.extend(
                        (item_id, "entity") for item_id in raw["entities"] if isinstance(item_id, str)
                    )
                for payload_index, (item_id, kind) in enumerate(payloads):
                    if item_id not in resolver.prototypes:
                        raise RuntimeError(f"Cargo catalog {catalog_id} references unknown item {item_id}")
                    key = f"{catalog_id}:{section_index}:{position}:{kind}:{payload_index}"
                    metadata = {"kind": kind}
                    if "cost" in raw:
                        metadata["cost"] = raw["cost"]
                    entries.append(
                        SourceEntry(key, catalog_id, "cargo", section_name, item_id, position, metadata)
                    )
                    section_entries.append(key)
            sections.append({"name": section_name, "position": section_index, "entries": section_entries})
        sources[catalog_id] = {
            "id": catalog_id,
            "type": "cargo",
            "name": localizer.entity_text(catalog_id, None, catalog["fields"].get("name")),
            "sections": sections,
        }
    return sources, entries

