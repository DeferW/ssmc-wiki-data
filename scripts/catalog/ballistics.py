"""Normalize selective-fire defaults, audited against game commit 024d853a.

Source: Content.Shared/_RMC14/Weapons/Ranged/RMCSelectiveFireComponent.cs.
Called by the catalog builder for every discovered weapon, including map items.
"""
from __future__ import annotations

import copy

SOURCE_COMMIT = "024d853a184f956e0c08d876808ea7771a104a04"
DEFAULT_MODES = {
    "Burst": {"fireDelay": 0.1, "maxScatterModifier": 10.0,
              "useBurstScatterMult": True, "unwieldedScatterMultiplier": 2.0,
              "shotsToMaxScatter": 6},
    "FullAuto": {"fireDelay": 0.0, "maxScatterModifier": 26.0,
                 "useBurstScatterMult": True, "unwieldedScatterMultiplier": 2.0,
                 "shotsToMaxScatter": 4},
}


def weapon_ballistics(properties: dict) -> dict | None:
    selective = properties.get("RMCSelectiveFire")
    if not isinstance(selective, dict) or not isinstance(properties.get("Gun"), dict):
        return None
    gun = properties["Gun"]
    modifiers = selective.get("modifiers", DEFAULT_MODES)
    modes = {}
    for mode in ("SemiAuto", "Burst", "FullAuto"):
        raw = modifiers.get(mode) if isinstance(modifiers, dict) else None
        # DataRecord scalar defaults apply to omitted fields in YAML entries;
        # the component dictionary defaults apply only when the whole field is absent.
        modes[mode] = {
            "unwieldedMultiplier": raw.get("unwieldedScatterMultiplier", 0) if raw else 0,
            "extraScatter": raw.get("maxScatterModifier", 0) if raw else 0,
            "scaleExtraScatter": raw.get("useBurstScatterMult", False) if raw else False,
            "shotsToMax": raw.get("shotsToMaxScatter") if raw else None,
            "fireDelay": raw.get("fireDelay", 0) if raw else 0,
        }
    return {
        "schemaVersion": 1, "rulesCommit": SOURCE_COMMIT,
        "availableModes": copy.deepcopy(selective.get("baseFireModes", ["SemiAuto"])),
        "defaultMode": gun.get("selectedMode", "SemiAuto"),
        "scatterUnwielded": selective.get("scatterUnwielded", 10.0),
        "recoilUnwielded": selective.get("recoilUnwielded", 1.0),
        "scatter": selective.get("scatterWielded", 10.0),
        "increase": selective.get("scatterIncrease", 0.0),
        "decay": selective.get("scatterDecay", 0.0),
        "recoil": selective.get("recoilWielded", 1.0),
        "burstScatterMultiplier": selective.get("burstScatterMult", 4.0),
        "fireRate": selective.get("baseFireRate", 1.429),
        "burstRateMultiplier": selective.get("burstFireRateMultiplier", 2.0),
        "burstSize": gun.get("shotsPerBurst", 3),
        "modes": modes,
        "unsupported": [key for key in ("GunSpinup", "RMCGunGroupPenalty") if key in properties],
    }
