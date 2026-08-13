from __future__ import annotations

from typing import Any

from scripts.catalog.config import Override


def apply_overrides(
    classifications: dict[str, dict[str, Any]],
    overrides: dict[str, Override],
) -> None:
    unknown = sorted(set(overrides) - set(classifications))
    if unknown:
        raise RuntimeError("Overrides reference items outside the catalog: " + ", ".join(unknown))
    for item_id, classification in classifications.items():
        automatic = classification["automaticCategory"]
        override = overrides.get(item_id)
        final = override.category if override else automatic
        classification["finalCategory"] = final
        classification["edited"] = final != automatic
        classification["source"] = "override" if override else "automatic"

