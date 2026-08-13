from __future__ import annotations

from typing import Any


def _solution_summary(components: dict[str, Any]) -> list[dict[str, Any]]:
    manager = components.get("SolutionContainerManager")
    if not isinstance(manager, dict) or not isinstance(manager.get("solutions"), dict):
        return []
    result: list[dict[str, Any]] = []
    for solution_id, solution in manager["solutions"].items():
        if not isinstance(solution, dict):
            continue
        reagents: list[dict[str, Any]] = []
        raw_reagents = solution.get("reagents")
        if isinstance(raw_reagents, list):
            for reagent in raw_reagents:
                if isinstance(reagent, dict) and isinstance(reagent.get("ReagentId"), str):
                    reagents.append({"id": reagent["ReagentId"], "amount": reagent.get("Quantity")})
        elif isinstance(raw_reagents, dict):
            reagents.extend(
                {"id": reagent_id, "amount": amount}
                for reagent_id, amount in raw_reagents.items()
                if isinstance(reagent_id, str)
            )
        result.append(
            {
                "id": str(solution_id),
                "maxVolume": solution.get("maxVol"),
                "reagents": reagents,
            }
        )
    return result


def extract_medical(resolved: dict[str, Any]) -> dict[str, Any]:
    components = resolved["components"]
    item_id = resolved["id"].casefold()
    source_file = resolved["sourceFile"].casefold()
    component_names = " ".join(
        component.casefold()
        for component in components
        if not component.casefold().endswith("blocked")
    )
    solutions = _solution_summary(components)
    medical_terms = (
        "healing",
        "healthanalyzer",
        "surgery",
        "defibrillator",
        "hypospray",
        "injector",
        "syringe",
        "pill",
        "bloodpack",
        "stasisbag",
        "bodybag",
        "dialysis",
        "stethoscope",
    )
    medical_id_terms = (
        "firstaid",
        "medkit",
        "surgical",
        "autoinjector",
        "pill",
        "syringe",
        "scalpel",
        "hemostat",
        "cautery",
        "bonesetter",
        "bonegel",
        "synthgraft",
        "defibrillator",
    )
    medical = bool(
        any(term in component_names for term in medical_terms)
        or any(term in item_id for term in medical_id_terms)
        or "/objects/medical/" in source_file
    )
    return {"solutions": solutions, "medicalFunction": medical}
