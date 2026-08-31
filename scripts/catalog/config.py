from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

def read_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Catalog config must be a mapping")
    if data.get("schemaVersion") != 3:
        raise RuntimeError("Catalog config must use schemaVersion 3")
    vendors = data.get("vendors")
    cargo_catalogs = data.get("cargoCatalogs", [])
    if not isinstance(vendors, list) or not vendors:
        raise RuntimeError("Catalog config has no vendors")
    if not isinstance(cargo_catalogs, list):
        raise RuntimeError("Catalog cargoCatalogs must be a list")
    sources = [*vendors, *cargo_catalogs]
    ids = [entry.get("id") for entry in sources if isinstance(entry, dict)]
    if len(ids) != len(sources) or any(not isinstance(item, str) for item in ids):
        raise RuntimeError("Every configured source must have a string id")
    if len(set(ids)) != len(ids):
        raise RuntimeError("Duplicate source id in catalog config")
    if "vendorDiscoveryPrefixes" in data:
        raise RuntimeError(
            "Automatic vendor discovery is disabled; list every source under vendors"
        )
    policy = data.get("classification", {})
    if not isinstance(policy, dict):
        raise RuntimeError("Catalog classification policy must be a mapping")
    unknown_policy_keys = set(policy) - {
        "excludePrototypeIds",
    }
    if unknown_policy_keys:
        raise RuntimeError(
            "Unknown catalog classification options: "
            + ", ".join(sorted(unknown_policy_keys))
        )
    for key in ("excludePrototypeIds",):
        value = policy.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise RuntimeError(f"classification.{key} must be a list of ids")
    return data
