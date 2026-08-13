from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Iterable

from .prototypes import parse_box as parse_box2i


def box_cells(boxes: Iterable[tuple[int, int, int, int]]) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for left, bottom, right, top in boxes:
        for y in range(bottom, top + 1):
            for x in range(left, right + 1):
                cells.add((x, y))
    return cells


def shape_cells(boxes: Iterable[tuple[int, int, int, int]]) -> set[tuple[int, int]]:
    cells = box_cells(boxes)
    if not cells:
        return set()
    min_x = min(x for x, _ in cells)
    min_y = min(y for _, y in cells)
    return {(x - min_x, y - min_y) for x, y in cells}


def packing_capacity(
    grid_boxes: Iterable[tuple[int, int, int, int]],
    item_boxes: Iterable[tuple[int, int, int, int]],
) -> int:
    """Repeat RMC's non-rotating, first-available grid insertion for one size."""
    valid = box_cells(grid_boxes)
    shape = shape_cells(item_boxes)
    if not valid or not shape:
        return 0
    min_x = min(x for x, _ in valid)
    max_x = max(x for x, _ in valid)
    min_y = min(y for _, y in valid)
    max_y = max(y for _, y in valid)
    occupied: set[tuple[int, int]] = set()
    count = 0
    while True:
        placed: set[tuple[int, int]] | None = None
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                candidate = {(x + offset_x, y + offset_y) for offset_x, offset_y in shape}
                if candidate.issubset(valid) and not candidate.intersection(occupied):
                    placed = candidate
                    break
            if placed is not None:
                break
        if placed is None:
            return count
        occupied.update(placed)
        count += 1


def storage_whitelist_matches(rule: Any, item: dict[str, Any]) -> bool:
    if not isinstance(rule, dict):
        return True
    component_types = set(item.get("componentTypes", []))
    tags = set(item.get("tags", []))
    size = str(item.get("itemSize", "Small"))
    require_all = bool(rule.get("requireAll", False))
    checks: list[bool] = []
    components = rule.get("components")
    if isinstance(components, list) and components:
        component_checks = [str(component) in component_types for component in components]
        checks.extend(component_checks if require_all else [any(component_checks)])
    sizes = rule.get("sizes")
    if isinstance(sizes, list) and sizes:
        checks.append(size in {str(value) for value in sizes})
    allowed_tags = rule.get("tags")
    if isinstance(allowed_tags, list) and allowed_tags:
        tag_checks = [str(tag) in tags for tag in allowed_tags]
        checks.extend(tag_checks if require_all else [any(tag_checks)])
    if not checks:
        return require_all
    return all(checks) if require_all else any(checks)


def default_storage_max_size(
    container_size: str,
    item_sizes: dict[str, dict[str, Any]],
) -> str:
    ordered = sorted(
        item_sizes,
        key=lambda size_id: (item_sizes[size_id].get("weight", 1), size_id),
    )
    if container_size not in ordered:
        return "Normal" if "Normal" in item_sizes else ordered[-1]
    index = ordered.index(container_size)
    return ordered[max(0, index - 1)]


def parse_vector2i(value: Any, default: tuple[int, int]) -> tuple[int, int]:
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return default
    if len(parts) != 2:
        return default
    try:
        return int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return default


def populate_storage_statistics(
    items: dict[str, Any],
    public_item_ids: set[str],
    item_sizes: dict[str, dict[str, Any]],
) -> None:
    """Normalize grid storage into actual item counts instead of raw cell area."""
    ordered_sizes = sorted(
        item_sizes,
        key=lambda size_id: (item_sizes[size_id].get("weight", 1), size_id),
    )
    for item_id in sorted(public_item_ids):
        item = items[item_id]
        properties = item.get("properties", {})
        storage = properties.get("Storage")
        cm_slots = properties.get("CMItemSlots")
        stats: dict[str, Any] = {}

        if isinstance(cm_slots, dict):
            count = cm_slots.get("count", 1)
            if isinstance(count, int) and count > 0:
                stats["exactPlaces"] = count
            starting_item = cm_slots.get("startingItem")
            if isinstance(starting_item, str):
                stats["acceptedItemIds"] = [starting_item]

        if isinstance(storage, dict):
            grid_boxes = [
                box
                for value in storage.get("grid", [])
                if (box := parse_box2i(value)) is not None
            ]
            if grid_boxes:
                stats["gridCells"] = len(box_cells(grid_boxes))
                max_size = storage.get("maxItemSize")
                if not isinstance(max_size, str):
                    max_size = default_storage_max_size(
                        str(item.get("itemSize", "Small")), item_sizes
                    )
                stats["maxItemSize"] = max_size

                fixed = properties.get("FixedItemSizeStorage")
                fixed_dimensions: tuple[int, int] | None = None
                if isinstance(fixed, dict):
                    fixed_dimensions = parse_vector2i(fixed.get("size"), (2, 2))
                    width, height = fixed_dimensions
                    fixed_boxes = [(0, 0, max(width - 1, 0), max(height - 1, 0))]
                    stats["fixedItemDimensions"] = [width, height]
                    stats["exactPlaces"] = packing_capacity(grid_boxes, fixed_boxes)

                whitelist = storage.get("whitelist")
                blacklist = storage.get("blacklist")
                ignore = properties.get("IgnoreContentsSize")
                ignore_items = ignore.get("items") if isinstance(ignore, dict) else None
                allowed_sizes: set[str] = set()
                accepted_item_ids: list[str] = []
                for candidate_id, candidate in items.items():
                    if candidate_id == item_id:
                        continue
                    if whitelist is not None and not storage_whitelist_matches(whitelist, candidate):
                        continue
                    if blacklist is not None and storage_whitelist_matches(blacklist, candidate):
                        continue
                    candidate_size = str(candidate.get("itemSize", "Small"))
                    max_weight = item_sizes.get(max_size, {}).get("weight", 1)
                    candidate_weight = item_sizes.get(candidate_size, {}).get("weight", 1)
                    bypasses_size = isinstance(ignore_items, dict) and storage_whitelist_matches(
                        ignore_items, candidate
                    )
                    if candidate_weight > max_weight and not bypasses_size:
                        continue
                    allowed_sizes.add(candidate_size)
                    if len(accepted_item_ids) < 80:
                        accepted_item_ids.append(candidate_id)

                if whitelist is None:
                    max_weight = item_sizes.get(max_size, {}).get("weight", 1)
                    allowed_sizes = {
                        size_id
                        for size_id in ordered_sizes
                        if item_sizes[size_id].get("weight", 1) <= max_weight
                    }
                capacities = []
                for size_id in ordered_sizes:
                    if size_id not in allowed_sizes:
                        continue
                    if fixed_dimensions is not None:
                        count = stats.get("exactPlaces", 0)
                    else:
                        count = packing_capacity(
                            grid_boxes,
                            item_sizes[size_id].get("boxes", []),
                        )
                    if isinstance(count, int) and count > 0:
                        capacities.append({"size": size_id, "count": count})
                if capacities:
                    stats["capacities"] = capacities
                if accepted_item_ids:
                    stats["acceptedItemIds"] = sorted(accepted_item_ids)
                if isinstance(whitelist, dict):
                    stats["whitelist"] = copy.deepcopy(whitelist)
                if isinstance(blacklist, dict):
                    stats["blacklist"] = copy.deepcopy(blacklist)
                if isinstance(ignore_items, dict):
                    stats["sizeExceptions"] = copy.deepcopy(ignore_items)

        limited = properties.get("LimitedStorage")
        if isinstance(limited, dict) and isinstance(limited.get("limits"), list):
            special_limits: list[dict[str, Any]] = []
            for limit in limited["limits"]:
                if not isinstance(limit, dict):
                    continue
                count = limit.get("count", 1)
                whitelist = limit.get("whitelist")
                blacklist = limit.get("blacklist")
                global_limit = whitelist is None and not blacklist
                if global_limit and isinstance(count, int) and count > 0:
                    current = stats.get("exactPlaces")
                    stats["exactPlaces"] = min(current, count) if isinstance(current, int) else count
                else:
                    special_limits.append(copy.deepcopy(limit))
            if special_limits:
                stats["limits"] = special_limits
        if stats:
            item["storageStats"] = stats


def populate_armor_statistics(
    items: dict[str, Any],
    public_item_ids: set[str],
) -> None:
    protection_fields = (
        "xenoArmor",
        "frontalArmor",
        "sideArmor",
        "melee",
        "bullet",
        "bio",
        "explosionArmor",
    )
    for item_id in sorted(public_item_ids):
        item = items[item_id]
        if not item.get("facts", {}).get("signals", {}).get("armor"):
            continue
        properties = item.get("properties", {})
        cm_armor = properties.get("CMArmor", {})
        if not isinstance(cm_armor, dict):
            cm_armor = {}
        stats: dict[str, Any] = {
            "slots": list(item.get("equipmentSlots", [])),
            "protection": {
                field: cm_armor.get(field, 0) for field in protection_fields
            },
            "immuneToArmorPiercing": bool(cm_armor.get("immuneToAP", False)),
            "hardArmor": "CMHardArmor" in item.get("componentTypes", []),
            "bulkyArmor": "RMCBulkyArmor" in item.get("componentTypes", []),
        }
        speed_tier = properties.get("RMCArmorSpeedTier", {})
        if isinstance(speed_tier, dict) and isinstance(speed_tier.get("speedTier"), str):
            stats["speedTier"] = speed_tier["speedTier"]
        movement = properties.get("ClothingSpeedModifier")
        if isinstance(movement, dict) and movement:
            stats["movement"] = copy.deepcopy(movement)
        explosion = properties.get("ExplosionResistance")
        if isinstance(explosion, dict) and explosion:
            stats["explosionResistance"] = copy.deepcopy(explosion)
        generic = properties.get("Armor")
        if isinstance(generic, dict) and generic:
            stats["genericArmor"] = copy.deepcopy(generic)
        item["armorStats"] = stats


def populate_attachment_statistics(
    items: dict[str, Any],
    public_item_ids: set[str],
) -> None:
    modifier_components = (
        "AttachableWeaponRangedMods",
        "AttachableWeaponMeleeMods",
        "AttachableSpeedMods",
        "AttachableWieldDelayMods",
        "AttachableSizeMods",
    )
    for item_id in sorted(public_item_ids):
        item = items[item_id]
        if "Attachable" not in item.get("componentTypes", []):
            continue
        properties = item.get("properties", {})
        modifiers = {
            component: copy.deepcopy(properties[component])
            for component in modifier_components
            if isinstance(properties.get(component), dict)
            and properties[component]
        }
        special_components = sorted(
            component
            for component in item.get("componentTypes", [])
            if component.startswith("Attachable")
            and component
            not in {
                "Attachable",
                "AttachableVisuals",
                *modifier_components,
            }
        )
        stats: dict[str, Any] = {
            "compatibleWith": copy.deepcopy(item.get("attachableTo", [])),
            "modifiers": modifiers,
            "effects": special_components,
        }
        item["attachmentStats"] = stats


def populate_weapon_statistics(
    items: dict[str, Any],
    relations: list[dict[str, Any]],
    public_item_ids: set[str],
) -> None:
    """Create stable, website-ready firearm statistics from the entity graph."""
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relations:
        outgoing[str(relation.get("from", ""))].append(relation)

    def number(value: Any) -> int | float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return value

    def projectile_summary(
        projectile_id: str,
        damage_multiplier: int | float | None,
    ) -> dict[str, Any] | None:
        projectile = items.get(projectile_id)
        if not isinstance(projectile, dict):
            return None
        properties = projectile.get("properties", {})
        projectile_component = properties.get("Projectile", {})
        if not isinstance(projectile_component, dict):
            projectile_component = {}
        result: dict[str, Any] = {
            "projectileId": projectile_id,
            "name": projectile.get("name", projectile_id),
        }
        damage = projectile_component.get("damage")
        if isinstance(damage, dict):
            damage_types = damage.get("types")
            if isinstance(damage_types, dict) and damage_types:
                result["damage"] = copy.deepcopy(damage_types)
                if damage_multiplier is not None:
                    result["effectiveDamage"] = {
                        damage_type: round(value * damage_multiplier, 4)
                        for damage_type, value in damage_types.items()
                        if isinstance(value, (int, float)) and not isinstance(value, bool)
                    }
        armor_piercing = properties.get("CMArmorPiercing", {})
        if isinstance(armor_piercing, dict):
            amount = number(armor_piercing.get("amount"))
            if amount is not None:
                result["armorPiercing"] = amount
        accuracy = properties.get("RMCProjectileAccuracy")
        if isinstance(accuracy, dict) and accuracy:
            result["accuracy"] = copy.deepcopy(accuracy)
        falloff = properties.get("RMCProjectileDamageFalloff")
        if isinstance(falloff, dict) and falloff:
            result["damageFalloff"] = copy.deepcopy(falloff)
        return result

    for weapon_id in sorted(public_item_ids):
        item = items[weapon_id]
        properties = item.get("properties", {})
        gun = properties.get("Gun")
        if not isinstance(gun, dict):
            continue
        selective = properties.get("RMCSelectiveFire", {})
        if not isinstance(selective, dict):
            selective = {}
        stats: dict[str, Any] = {}

        modes = selective.get("baseFireModes", gun.get("availableModes"))
        if isinstance(modes, list) and modes:
            stats["fireModes"] = [str(mode) for mode in modes]
        selected_mode = gun.get("selectedMode")
        if isinstance(selected_mode, str):
            stats["defaultFireMode"] = selected_mode

        fire_rate = number(selective.get("baseFireRate"))
        if fire_rate is None:
            fire_rate = number(gun.get("fireRate"))
        if fire_rate is not None:
            stats["shotsPerSecond"] = fire_rate
            stats["roundsPerMinute"] = round(fire_rate * 60, 2)
        burst_size = number(gun.get("shotsPerBurst"))
        if burst_size is not None and burst_size > 0:
            stats["burstSize"] = burst_size
        gun_parameters = {
            key: value
            for key, value in gun.items()
            if isinstance(value, (str, int, float, bool))
            and not key.casefold().startswith("sound")
            and key not in {"selectedMode", "fireRate", "shotsPerBurst"}
        }
        if gun_parameters:
            stats["gunParameters"] = copy.deepcopy(gun_parameters)

        melee = properties.get("MeleeWeapon")
        if isinstance(melee, dict) and melee:
            melee_stats: dict[str, Any] = {}
            for source_key, output_key in (
                ("attackRate", "attacksPerSecond"),
                ("angle", "angle"),
                ("range", "range"),
            ):
                value = number(melee.get(source_key))
                if value is not None:
                    melee_stats[output_key] = value
            damage = melee.get("damage")
            if isinstance(damage, dict) and isinstance(damage.get("types"), dict):
                melee_stats["damage"] = copy.deepcopy(damage["types"])
            if melee_stats:
                stats["melee"] = melee_stats

        iff = properties.get("GunIFF")
        if isinstance(iff, dict):
            stats["iffEnabled"] = bool(iff.get("enabled", True))
        skill_requirements = properties.get("GunRequiresSkills")
        if isinstance(skill_requirements, dict) and skill_requirements:
            stats["skillRequirements"] = copy.deepcopy(skill_requirements)
        dual_wielding = properties.get("GunDualWielding")
        if isinstance(dual_wielding, dict) and dual_wielding:
            stats["dualWielding"] = copy.deepcopy(dual_wielding)
        wield_delay = properties.get("WieldDelay")
        if isinstance(wield_delay, dict) and wield_delay:
            stats["wieldDelay"] = copy.deepcopy(wield_delay)
        wield_speed = properties.get("WieldableSpeedModifiers")
        if isinstance(wield_speed, dict) and wield_speed:
            stats["wieldedMovement"] = copy.deepcopy(wield_speed)

        for output_key, source_keys in {
            "recoil": ("recoilWielded", "recoilUnwielded"),
            "scatter": ("scatterWielded", "scatterUnwielded"),
        }.items():
            values = {
                "wielded": number(selective.get(source_keys[0])),
                "unwielded": number(selective.get(source_keys[1])),
            }
            values = {key: value for key, value in values.items() if value is not None}
            if values:
                stats[output_key] = values

        accuracy_component = properties.get("RMCWeaponAccuracy", {})
        if isinstance(accuracy_component, dict):
            accuracy = {
                "wieldedMultiplier": number(accuracy_component.get("accuracyMultiplier")),
                "unwieldedMultiplier": number(
                    accuracy_component.get("accuracyMultiplierUnwielded")
                ),
            }
            accuracy = {key: value for key, value in accuracy.items() if value is not None}
            if accuracy:
                stats["accuracy"] = accuracy

        modifier = properties.get("GunDamageModifier", {})
        damage_multiplier: int | float | None = None
        if isinstance(modifier, dict):
            damage_multiplier = number(modifier.get("multiplier"))
            if damage_multiplier is not None:
                stats["damageMultiplier"] = damage_multiplier
        armor_piercing = properties.get("CMArmorPiercing", {})
        if isinstance(armor_piercing, dict):
            amount = number(armor_piercing.get("amount"))
            if amount is not None:
                stats["weaponArmorPiercing"] = amount
        weapon_falloff = properties.get("RMCWeaponDamageFalloff")
        if isinstance(weapon_falloff, dict) and weapon_falloff:
            stats["weaponDamageFalloff"] = copy.deepcopy(weapon_falloff)
        if isinstance(selective.get("modifiers"), dict):
            stats["fireModeModifiers"] = copy.deepcopy(selective["modifiers"])

        provider_type = None
        provider: dict[str, Any] = {}
        for candidate_type in (
            "BallisticAmmoProvider",
            "RevolverAmmoProvider",
            "ProjectileBatteryAmmoProvider",
            "MagazineAmmoProvider",
            "RMCFlamerAmmoProvider",
        ):
            candidate = properties.get(candidate_type)
            if isinstance(candidate, dict):
                provider_type = candidate_type
                provider = candidate
                break
        if provider_type is not None:
            provider_summary: dict[str, Any] = {"type": provider_type}
            for source_key, output_key in (
                ("capacity", "capacity"),
                ("fireCost", "fireCost"),
                ("proto", "startingAmmoId"),
                ("cycleable", "cycleable"),
                ("mayTransfer", "mayTransfer"),
            ):
                value = provider.get(source_key)
                if isinstance(value, (str, int, float, bool)):
                    provider_summary[output_key] = value
            whitelist = provider.get("whitelist")
            if isinstance(whitelist, dict):
                accepted_tags = whitelist.get("tags")
                if isinstance(accepted_tags, list):
                    provider_summary["acceptedTags"] = sorted(
                        str(tag) for tag in accepted_tags if isinstance(tag, str)
                    )
            stats["ammoProvider"] = provider_summary

        paths = item.get("ammunitionPaths", [])
        if not isinstance(paths, list):
            paths = []
        loaded_targets = {
            str(relation["to"])
            for relation in outgoing.get(weapon_id, [])
            if relation.get("type") == "loadedWith"
        }
        accepted_tags = set(
            stats.get("ammoProvider", {}).get("acceptedTags", [])
        )
        compatible_loose_ammo = {
            candidate_id
            for candidate_id, candidate in items.items()
            if accepted_tags.intersection(candidate.get("tags", []))
            and (
                "CartridgeAmmo" in candidate.get("componentTypes", [])
                or "ProjectileGrenade" in candidate.get("componentTypes", [])
                or "Explosive" in candidate.get("componentTypes", [])
            )
        }
        loaded_targets.update(compatible_loose_ammo)
        ammunition: list[dict[str, Any]] = []
        for path in paths:
            if not isinstance(path, dict):
                continue
            magazine_id = str(path.get("magazineId", ""))
            magazine = items.get(magazine_id, {})
            magazine_provider = magazine.get("properties", {}).get("BallisticAmmoProvider", {})
            entry: dict[str, Any] = {
                "magazineId": magazine_id,
                "magazineName": magazine.get("name", magazine_id),
                "cartridgeIds": list(path.get("cartridgeIds", [])),
            }
            if isinstance(magazine_provider, dict):
                capacity = number(magazine_provider.get("capacity"))
                if capacity is not None:
                    entry["capacity"] = capacity
            projectile_entries = [
                summary
                for projectile_id in path.get("projectileIds", [])
                if (
                    summary := projectile_summary(
                        str(projectile_id), damage_multiplier
                    )
                ) is not None
            ]
            if projectile_entries:
                entry["projectiles"] = projectile_entries
            ammunition.append(entry)
        for ammo_id in sorted(loaded_targets):
            ammo_item = items.get(ammo_id, {})
            component_types = set(ammo_item.get("componentTypes", []))
            if (
                "BallisticAmmoProvider" in component_types
                and "CartridgeAmmo" not in component_types
                and "Projectile" not in component_types
            ):
                continue
            direct_entry: dict[str, Any] = {
                "directFeed": True,
                "ammoId": ammo_id,
                "ammoName": ammo_item.get("name", ammo_id),
            }
            capacity = number(stats.get("ammoProvider", {}).get("capacity"))
            if capacity is not None:
                direct_entry["capacity"] = capacity
            projectile_ids: set[str] = set()
            if "Projectile" in component_types:
                projectile_ids.add(ammo_id)
            if "CartridgeAmmo" in component_types:
                direct_entry["cartridgeIds"] = [ammo_id]
                projectile_ids.update(
                    str(relation["to"])
                    for relation in outgoing.get(ammo_id, [])
                    if relation.get("type") == "fires"
                )
            projectile_entries = [
                summary
                for projectile_id in sorted(projectile_ids)
                if (
                    summary := projectile_summary(
                        projectile_id, damage_multiplier
                    )
                ) is not None
            ]
            if projectile_entries:
                direct_entry["projectiles"] = projectile_entries
            ammunition.append(direct_entry)
        if ammunition:
            stats["ammunition"] = ammunition
        item["weaponStats"] = stats
