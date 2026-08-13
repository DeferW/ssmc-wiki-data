from __future__ import annotations

from collections.abc import Callable
from typing import Any

from scripts.catalog.extractors.core import extract_core
from scripts.catalog.extractors.medical import extract_medical
from scripts.catalog.extractors.mechanics import extract_mechanics

Extractor = Callable[[dict[str, Any]], dict[str, Any]]

# Adding a new independent fact module only requires registering it here.
EXTRACTORS: tuple[Extractor, ...] = (
    extract_core,
    extract_mechanics,
    extract_medical,
)


def extract_facts(resolved: dict[str, Any]) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for extractor in EXTRACTORS:
        extracted = extractor(resolved)
        overlap = facts.keys() & extracted.keys()
        if overlap:
            raise RuntimeError(f"Fact extractors produced duplicate fields: {sorted(overlap)}")
        facts.update(extracted)
    return facts
