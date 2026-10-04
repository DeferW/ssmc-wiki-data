"""Game rules mirrored from C#, audited against game commit 024d853a.

YAML only stores values that differ from the component defaults, and explosion
size is derived by the engine at runtime. Keep this file in sync with the
sources named next to each value when the game changes them.
"""
from __future__ import annotations

import math

# Content.Shared/_RMC14/Mortar/MortarComponent.cs: MinimumRange, MaximumRange.
# Content.Server/_RMC14/Mortar/MortarSystem.cs compares the straight-line
# distance between the mortar and the target with these bounds.
MORTAR_DEFAULTS = {"minimumRange": 15, "maximumRange": 65}

# Content.Shared/_RMC14/OrbitalCannon/OrbitalCannonExplosion.cs field defaults.
OB_STEP_DEFAULTS = {"fireRange": 18, "times": 1, "timesPer": 1, "spread": 0}

# Content.Shared/_RMC14/Areas/RoofingEntityComponent.cs: every Can* flag is a
# C# bool, so an omitted flag means the roof blocks that support. Names on the
# right match AREA_SUPPORT_FIELDS in scripts/maps/core.py.
ROOF_SUPPORT_FIELDS = {
    "canCAS": "CAS",
    "canFulton": "fulton",
    "canLase": "lasing",
    "canMortarPlace": "mortarPlacement",
    "canMortarFire": "mortarFire",
    "canMedevac": "medevac",
    "canParadrop": "paradropping",
    "canOrbitalBombard": "OB",
    "canSupplyDrop": "supplyDrop",
}


def radius_to_intensity(radius: float, slope: float, max_intensity: float = 0) -> float:
    """Content.Server/Explosion/EntitySystems/ExplosionSystem.cs: RadiusToIntensity."""
    cone_volume = slope * math.pi / 3 * radius**3
    if max_intensity <= 0 or slope * radius < max_intensity:
        return cone_volume
    h = slope * radius - max_intensity
    return cone_volume - h * math.pi / 3 * (h / slope) ** 2


def intensity_to_radius(total: float, slope: float, max_intensity: float) -> float:
    """Content.Server/Explosion/EntitySystems/ExplosionSystem.cs: IntensityToRadius.

    The engine's own estimate of how far an explosion reaches on open ground;
    walls and airtight tiles shorten the real shape.
    """
    r0 = max_intensity / slope
    v0 = radius_to_intensity(r0, slope)
    if total <= v0:
        return (3 * total / (slope * math.pi)) ** (1 / 3)
    return r0 * (math.sqrt(12 * total / v0 - 3) / 6 + 0.5)
