from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXPECTED_GUIDE_SET = {"ordnance", "medicine", "drinks"}

EXPECTED_CATALOG_SECTIONS = {"ordnance", "medicine", "drinks", "elements", "other"}

EXPECTED_CLASSIFICATION_GUIDE = (
    "Resources/ServerInfo/Guidebook/_RMC14/Chemicals/RMCChemicals.xml"
)

REQUIRED_CHEMICAL_GROUPS = {
    "Elements", "Medicine", "Narcotics", "Pyrotechnic",
    "Toxins", "Foods", "Botanical", "Biological", "Unknown",
}

VALID_REAGENT_ORIGINS = {"rmc14", "stories"}
VALID_REACTION_ORIGINS = {"rmc14", "stories"}
VALID_DEPENDENCY_ORIGIN = "upstream-reference"


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return data


def validate(data: dict[str, Any]) -> None:
    reagents = data.get("reagents", {})
    dependencies = data.get("dependencies", {})
    reactions = data.get("reactions", {})
    guides = data.get("guides", {})
    catalog_sections = data.get("catalogSections", {})
    classification = data.get("classification", {})
    counts = data.get("counts", {})

    if not reagents:
        raise RuntimeError("No custom reagents found")

    if not reactions:
        raise RuntimeError("No custom reactions found")

    if set(guides) != EXPECTED_GUIDE_SET:
        raise RuntimeError(
            "Unexpected guide set: " + ", ".join(sorted(guides))
        )

    if set(catalog_sections) != EXPECTED_CATALOG_SECTIONS:
        raise RuntimeError(
            "Unexpected catalog section set: "
            + ", ".join(sorted(catalog_sections))
        )

    if classification.get("guideFile") != EXPECTED_CLASSIFICATION_GUIDE:
        raise RuntimeError(
            "RMCChemicals.xml is not connected to the catalog build"
        )

    actual_chemical_groups = set(classification.get("groupSections", {}))
    if actual_chemical_groups != REQUIRED_CHEMICAL_GROUPS:
        raise RuntimeError(
            "Unexpected RMCChemicals.xml groups: "
            + ", ".join(sorted(actual_chemical_groups))
        )

    invalid_reagents = sorted(
        reagent_id
        for reagent_id, reagent in reagents.items()
        if reagent.get("origin") not in VALID_REAGENT_ORIGINS
    )
    if invalid_reagents:
        raise RuntimeError(
            "Upstream reagents entered the custom catalog: "
            + ", ".join(invalid_reagents)
        )

    invalid_dependencies = sorted(
        reagent_id
        for reagent_id, reagent in dependencies.items()
        if reagent.get("origin") != VALID_DEPENDENCY_ORIGIN
    )
    if invalid_dependencies:
        raise RuntimeError(
            "Invalid dependency origins: "
            + ", ".join(invalid_dependencies)
        )

    invalid_reactions = sorted(
        reaction_id
        for reaction_id, reaction in reactions.items()
        if reaction.get("origin") not in VALID_REACTION_ORIGINS
    )
    if invalid_reactions:
        raise RuntimeError(
            "Upstream reactions entered the catalog: "
            + ", ".join(invalid_reactions)
        )

    known_reagents = set(reagents) | set(dependencies)
    missing_references: set[str] = set()

    for reaction in reactions.values():
        for field in ("reactants", "products"):
            for item in reaction.get(field, []):
                reagent_id = item.get("id")
                if reagent_id not in known_reagents:
                    missing_references.add(reagent_id)

    for entries in guides.values():
        for entry in entries:
            reagent_id = entry.get("id")
            if reagent_id not in known_reagents:
                missing_references.add(reagent_id)

    catalog_ids: list[str] = []
    for entries in catalog_sections.values():
        for entry in entries:
            reagent_id = entry.get("id")
            catalog_ids.append(reagent_id)
            if reagent_id not in known_reagents:
                missing_references.add(reagent_id)

    if missing_references:
        raise RuntimeError(
            "Unknown reagent references: "
            + ", ".join(sorted(missing_references))
        )

    duplicate_catalog_ids = sorted({
        reagent_id
        for reagent_id in catalog_ids
        if catalog_ids.count(reagent_id) > 1
    })
    if duplicate_catalog_ids:
        raise RuntimeError(
            "Reagents entered multiple catalog sections: "
            + ", ".join(duplicate_catalog_ids)
        )

    missing_custom_reagents = sorted(set(reagents) - set(catalog_ids))
    if missing_custom_reagents:
        raise RuntimeError(
            "Custom reagents missing from catalog sections: "
            + ", ".join(missing_custom_reagents)
        )

    expected_counts = {
        "customReagents": len(reagents),
        "upstreamDependencies": len(dependencies),
        "customReactions": len(reactions),
        "unlistedCustomReagents": len(data.get("unlistedReagents", [])),
    }

    if counts != expected_counts:
        raise RuntimeError(
            f"Count mismatch: stored={counts}, actual={expected_counts}"
        )

    print(f"Custom reagents: {len(reagents)}")
    print(f"Upstream dependencies: {len(dependencies)}")
    print(f"Custom reactions: {len(reactions)}")
    print(
        "Unlisted custom reagents: "
        f"{len(data.get('unlistedReagents', []))}"
    )
    print("Chemistry catalog validation passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate chemistry catalog output")
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    validate(read_json(args.catalog))


if __name__ == "__main__":
    main()
