from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml
from PIL import Image, ImageChops, ImageColor


class GameYamlLoader(yaml.SafeLoader):
    """YAML loader that preserves SS14 custom tags as plain JSON values."""


def construct_tagged_value(
    loader: GameYamlLoader,
    tag_suffix: str,
    node: yaml.Node,
) -> Any:
    if isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_scalar(node)
    return {"yamlTag": f"!{tag_suffix}", "value": value}


GameYamlLoader.add_multi_constructor("!", construct_tagged_value)


FTL_MESSAGE_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_-]*)\s*=\s*(.*)$")
FTL_ATTRIBUTE_RE = re.compile(r"^\s+\.([A-Za-z0-9_-]+)\s*=\s*(.*)$")
FTL_REFERENCE_RE = re.compile(r"^\{\s*([A-Za-z0-9_-]+)(?:\.([A-Za-z0-9_-]+))?\s*\}$")


ROOT_RELATION_TYPES = {
    "contains",
    "slotItem",
    "loadedWith",
    "installedAttachment",
    "bundleItem",
    "variant",
    "fires",
    "refillableBy",
    "mountedWeapon",
    "mappedVariant",
}


HIERARCHICAL_RELATION_TYPES = ROOT_RELATION_TYPES - {"refillableBy"}


CASE_CONTENT_RELATION_TYPES = {"contains", "bundleItem", "variant"}


PHYSICAL_CONTENT_RELATION_TYPES = {
    "contains",
    "slotItem",
    "bundleItem",
    "variant",
    "mountedWeapon",
    "mappedVariant",
}


PUBLIC_CATEGORY_LABELS = {
    "weapon": "Оружие",
    "ammunition": "Боеприпасы и взрывчатка",
    "attachment": "Обвесы",
    "melee": "Ближний бой",
    "armor": "Броня",
    "equipment": "Экипировка",
    "medicine": "Медицина",
    "gear": "Снаряжение",
    "other": "Другое",
}


PUBLIC_CATEGORY_ORDER = (
    "weapon",
    "ammunition",
    "attachment",
    "melee",
    "armor",
    "equipment",
    "medicine",
    "gear",
    "other",
)


WEARABLE_EQUIPMENT_SLOTS = {
    "innerclothing",
    "jumpsuit",
    "head",
    "eyes",
    "gloves",
    "hands",
    "shoes",
    "feet",
    "mask",
    "mouth",
    "ears",
    "ear",
    "neck",
    "pocket",
    "pockets",
    "belt",
    "back",
}


WEARABLE_STORAGE_SLOTS = {
    "innerclothing",
    "pocket",
    "pockets",
    "belt",
    "back",
}


PUBLIC_PROPERTY_COMPONENTS = {
    # Weapons and ammunition.
    "BallisticAmmoProvider",
    "CartridgeAmmo",
    "CMArmorPiercing",
    "Gun",
    "GunDamageModifier",
    "MagazineAmmoProvider",
    "Projectile",
    "ProjectileBatteryAmmoProvider",
    "RevolverAmmoProvider",
    "RMCFlamerAmmoProvider",
    "RMCFlamerTank",
    "RMCProjectileAccuracy",
    "RMCProjectileDamageFalloff",
    "RMCSelectiveFire",
    "RMCWeaponAccuracy",
    "RMCWeaponDamageFalloff",
    "WieldDelay",
    "WieldableSpeedModifiers",
    # Attachments and melee.
    "AttachableSizeMods",
    "AttachableSpeedMods",
    "AttachableWeaponMeleeMods",
    "AttachableWeaponRangedMods",
    "AttachableWieldDelayMods",
    "MeleeWeapon",
    # Protection, medicine and useful containers.
    "Armor",
    "CMArmor",
    "RMCArmor",
    "RMCArmorSpeedTier",
    "RMCArmorVariant",
    "ClothingSpeedModifier",
    "ExplosionResistance",
    "FixedItemSizeStorage",
    "IgnoreContentsSize",
    "LimitedStorage",
    "SolutionContainerManager",
    "Storage",
}


SOURCE_CATEGORY_HINTS = {
    "ammunition": "magazine-or-ammo-container",
    "armor-piercing ammunition": "magazine-or-ammo-container",
    "extended ammunition": "magazine-or-ammo-container",
    "special ammunition": "magazine-or-ammo-container",
    "restricted firearm ammunition": "magazine-or-ammo-container",
    "primary ammunition": "magazine-or-ammo-container",
    "sidearm ammunition": "magazine-or-ammo-container",
    "magazine boxes": "magazine-or-ammo-container",
    "ammunition boxes": "magazine-or-ammo-container",
    "боеприпасы": "magazine-or-ammo-container",
    "боеприпасы специалиста по оружию": "magazine-or-ammo-container",
    "vehicle ammunition": "vehicle-ammunition",
    "боеприпасы для техники": "vehicle-ammunition",
    "attachments": "attachment",
    "обвесы": "attachment",
    "armor": "armor",
    "броня": "armor",
    "clothing": "clothing",
    "одежда": "clothing",
    "food": "food",
    "еда": "food",
    "medicine": "medical",
    "medical": "medical",
    "медицина": "medical",
    "engineering": "engineering",
    "инженерия": "engineering",
    "explosives": "explosive",
    "взрывчатка": "explosive",
    "research": "material",
    "исследование": "material",
    "mortar": "magazine-or-ammo-container",
    "мортира": "magazine-or-ammo-container",
    "reagent tanks": "reagent",
    "резервуары для реагентов": "reagent",
    "weapons": "weapon",
    "primary firearms": "weapon",
    "sidearms": "weapon",
    "оружие": "weapon",
}


SLOT_LABELS = {
    "rmc-aslot-barrel": "Дуло",
    "rmc-aslot-rail": "Верхняя планка",
    "rmc-aslot-stock": "Приклад",
    "rmc-aslot-underbarrel": "Подствольный слот",
}


CORE_COMPONENTS = {
    "Armor",
    "BallisticAmmoProvider",
    "CartridgeAmmo",
    "CMArmorPiercing",
    "CMItemSlots",
    "ContainerFill",
    "Damageable",
    "Gun",
    "GunDamageModifier",
    "Item",
    "ItemSlots",
    "MeleeWeapon",
    "Projectile",
    "RMCArmor",
    "RMCArmorVariant",
    "RMCFlamerAmmoProvider",
    "RMCFlamerTank",
    "RMCProjectileAccuracy",
    "RMCProjectileDamageFalloff",
    "RMCSelectiveFire",
    "RMCWeaponAccuracy",
    "RMCWeaponDamageFalloff",
    "SolutionContainerManager",
    "Stack",
    "Storage",
    "StorageFill",
}


NON_MECHANICAL_COMPONENTS = {
    "Appearance",
    "ContainerContainer",
    "GenericVisualizer",
    "Icon",
    "ItemCamouflage",
    "PointLight",
    "Sprite",
    "Tag",
    "Transform",
}


@dataclass(frozen=True)
class EntityPrototype:
    id: str
    parents: tuple[str, ...]
    abstract: bool
    source_file: str
    origin: str
    fields: dict[str, Any]
    components: tuple[dict[str, Any], ...]


def normalize_parents(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def origin_from_path(path: str) -> str:
    if "/_Stories/" in path:
        return "stories"
    if "/_RMC14/" in path:
        return "rmc14"
    return "upstream"


def iter_prototype_documents(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as stream:
        for document in yaml.load_all(stream, Loader=GameYamlLoader):
            if document is None:
                continue
            values = document if isinstance(document, list) else [document]
            for value in values:
                if isinstance(value, dict):
                    yield value


def read_entity_prototypes(game_source: Path) -> dict[str, EntityPrototype]:
    root = game_source / "Resources/Prototypes"
    if not root.is_dir():
        raise FileNotFoundError(f"Missing prototype directory: {root}")

    result: dict[str, EntityPrototype] = {}
    files = sorted([*root.rglob("*.yml"), *root.rglob("*.yaml")])

    for path in files:
        source_file = path.relative_to(game_source).as_posix()
        for raw in iter_prototype_documents(path):
            if raw.get("type") != "entity":
                continue
            prototype_id = raw.get("id")
            if not isinstance(prototype_id, str) or not prototype_id:
                continue
            if prototype_id in result:
                previous = result[prototype_id].source_file
                raise RuntimeError(
                    f"Duplicate entity prototype {prototype_id}: "
                    f"{previous}, {source_file}"
                )

            raw_components = raw.get("components", [])
            components: list[dict[str, Any]] = []
            if isinstance(raw_components, list):
                components = [
                    copy.deepcopy(component)
                    for component in raw_components
                    if isinstance(component, dict)
                    and isinstance(component.get("type"), str)
                ]

            fields = {
                key: copy.deepcopy(value)
                for key, value in raw.items()
                if key not in {"type", "id", "parent", "abstract", "components"}
            }
            result[prototype_id] = EntityPrototype(
                id=prototype_id,
                parents=normalize_parents(raw.get("parent")),
                abstract=bool(raw.get("abstract", False)),
                source_file=source_file,
                origin=origin_from_path(source_file),
                fields=fields,
                components=tuple(components),
            )

    if not result:
        raise RuntimeError("No entity prototypes found")
    return result


def read_reagent_colors(game_source: Path) -> dict[str, str]:
    """Read reagent colors used by runtime-filled bottle/injector visuals."""
    root = game_source / "Resources/Prototypes"
    result: dict[str, str] = {}
    for path in sorted([*root.rglob("*.yml"), *root.rglob("*.yaml")]):
        for raw in iter_prototype_documents(path):
            if raw.get("type") != "reagent":
                continue
            reagent_id = raw.get("id")
            color = raw.get("color")
            if isinstance(reagent_id, str) and isinstance(color, str):
                result[reagent_id] = color
    return result


class PrototypeResolver:
    """Resolve entity inheritance with component-level SS14 semantics."""

    def __init__(self, prototypes: dict[str, EntityPrototype]):
        self.prototypes = prototypes
        self.cache: dict[str, dict[str, Any]] = {}
        self.active: list[str] = []

    def resolve(self, prototype_id: str) -> dict[str, Any]:
        cached = self.cache.get(prototype_id)
        if cached is not None:
            return cached

        prototype = self.prototypes.get(prototype_id)
        if prototype is None:
            raise RuntimeError(f"Unknown entity prototype: {prototype_id}")
        if prototype_id in self.active:
            start = self.active.index(prototype_id)
            cycle = self.active[start:] + [prototype_id]
            raise RuntimeError("Entity inheritance cycle: " + " -> ".join(cycle))

        self.active.append(prototype_id)
        fields: dict[str, Any] = {}
        components: dict[str, dict[str, Any]] = {}

        for parent_id in prototype.parents:
            if parent_id not in self.prototypes:
                raise RuntimeError(
                    f"Unknown parent {parent_id} used by {prototype_id}"
                )
            parent = self.resolve(parent_id)
            fields.update(copy.deepcopy(parent["fields"]))
            for component_type, component in parent["components"].items():
                merged_parent = copy.deepcopy(components.get(component_type, {}))
                merged_parent.update(copy.deepcopy(component))
                components[component_type] = merged_parent

        # Prototype fields and individual component fields replace the matching
        # inherited field as a whole. Nested maps are intentionally not merged:
        # Empty weapon variants rely on replacing ItemSlots.slots so an inherited
        # startingItem does not survive.
        fields.update(copy.deepcopy(prototype.fields))
        for raw_component in prototype.components:
            component_type = raw_component["type"]
            merged = copy.deepcopy(components.get(component_type, {}))
            merged.update(
                {
                    key: copy.deepcopy(value)
                    for key, value in raw_component.items()
                    if key != "type"
                }
            )
            components[component_type] = merged

        self.active.pop()
        resolved = {
            "id": prototype_id,
            "parents": list(prototype.parents),
            "abstract": prototype.abstract,
            "sourceFile": prototype.source_file,
            "origin": prototype.origin,
            "fields": fields,
            "components": components,
        }
        self.cache[prototype_id] = resolved
        return resolved


def read_fluent_messages(locale_root: Path) -> dict[str, str]:
    if not locale_root.is_dir():
        raise FileNotFoundError(f"Missing locale directory: {locale_root}")

    messages: dict[str, str] = {}
    for path in sorted(locale_root.rglob("*.ftl")):
        current_key: str | None = None
        current_attribute: str | None = None
        parts: list[str] = []

        def flush() -> None:
            nonlocal parts
            if current_key is None:
                parts = []
                return
            key = current_key
            if current_attribute is not None:
                key += "." + current_attribute
            value = " ".join(part.strip() for part in parts if part.strip())
            if value and key not in messages:
                messages[key] = value
            parts = []

        for line in path.read_text(encoding="utf-8-sig").splitlines():
            message_match = FTL_MESSAGE_RE.match(line)
            if message_match:
                flush()
                current_key = message_match.group(1)
                current_attribute = None
                parts = [message_match.group(2)]
                continue

            attribute_match = FTL_ATTRIBUTE_RE.match(line)
            if attribute_match and current_key is not None:
                flush()
                current_attribute = attribute_match.group(1)
                parts = [attribute_match.group(2)]
                continue

            if current_key is not None and line.startswith((" ", "\t")):
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    parts.append(stripped)
                continue

            if not line.strip():
                flush()
                current_key = None
                current_attribute = None

        flush()

    return messages


class Localizer:
    def __init__(self, messages: dict[str, str]):
        self.messages = messages

    def resolve_key(self, key: str, active: tuple[str, ...] = ()) -> str | None:
        if key in active:
            return None
        value = self.messages.get(key)
        if value is None:
            return None
        reference = FTL_REFERENCE_RE.match(value.strip())
        if reference:
            target = reference.group(1)
            if reference.group(2):
                target += "." + reference.group(2)
            return self.resolve_key(target, active + (key,))
        return value

    def entity_text(
        self,
        prototype_id: str,
        attribute: str | None,
        fallback: Any,
    ) -> str:
        key = f"ent-{prototype_id}"
        if attribute:
            key += "." + attribute
        localized = self.resolve_key(key)
        if localized:
            return localized
        if isinstance(fallback, str) and fallback.strip():
            fallback_reference = FTL_REFERENCE_RE.match(fallback.strip())
            if fallback_reference:
                target = fallback_reference.group(1)
                if fallback_reference.group(2):
                    target += "." + fallback_reference.group(2)
                resolved = self.resolve_key(target)
                if resolved:
                    return resolved
            return fallback
        return prototype_id if attribute is None else ""


def read_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Equipment config must be a mapping")
    vendors = data.get("vendors")
    cargo_catalogs = data.get("cargoCatalogs", [])
    if not isinstance(vendors, list) or not vendors:
        raise RuntimeError("Equipment config has no vendors")
    if not isinstance(cargo_catalogs, list):
        raise RuntimeError("Equipment cargoCatalogs must be a list")
    sources = [*vendors, *cargo_catalogs]
    ids = [entry.get("id") for entry in sources if isinstance(entry, dict)]
    if len(ids) != len(sources) or any(not isinstance(item, str) for item in ids):
        raise RuntimeError("Every configured source must have a string id")
    if len(set(ids)) != len(ids):
        raise RuntimeError("Duplicate source id in equipment config")
    discovery_prefixes = data.get("vendorDiscoveryPrefixes", [])
    if not isinstance(discovery_prefixes, list) or any(
        not isinstance(prefix, str) or not prefix
        for prefix in discovery_prefixes
    ):
        raise RuntimeError("vendorDiscoveryPrefixes must be a list of strings")
    policy = data.get("classification", {})
    if not isinstance(policy, dict):
        raise RuntimeError("Equipment classification policy must be a mapping")
    for key in ("excludePrototypeIds", "includePrototypeIds"):
        value = policy.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise RuntimeError(f"classification.{key} must be a list of ids")
    for key in ("categoryOverrides", "canonicalPrototypeIds"):
        value = policy.get(key, {})
        if not isinstance(value, dict) or any(
            not isinstance(item_id, str) or not isinstance(target, str)
            for item_id, target in value.items()
        ):
            raise RuntimeError(f"classification.{key} must map ids to strings")
    unknown_categories = set(policy.get("categoryOverrides", {}).values()) - set(
        PUBLIC_CATEGORY_LABELS
    )
    if unknown_categories:
        raise RuntimeError(
            "Unknown classification category overrides: "
            + ", ".join(sorted(unknown_categories))
        )
    return data


def capitalize_first(value: str) -> str:
    """Uppercase the first visible letter without changing the rest of a name."""
    for index, character in enumerate(value):
        if character.isdigit():
            return value
        if character.isalpha():
            return value[:index] + character.upper() + value[index + 1 :]
    return value


def catalog_display_name(base_name: str, suffix: str) -> str:
    ignored_prefixes = (
        "empty",
        "filled",
        "loaded",
        "folded",
        "assembled",
        "пуст",
        "заполн",
        "заряж",
        "слож",
        "собран",
    )
    qualifiers = [
        part.strip()
        for part in suffix.split(",")
        if part.strip()
        and not part.strip().casefold().startswith(ignored_prefixes)
    ]
    if not qualifiers:
        return base_name
    return f"{base_name} ({', '.join(qualifiers)})"


def relation_key(relation: dict[str, Any]) -> str:
    return json.dumps(relation, ensure_ascii=False, sort_keys=True)


def add_relation(
    relations: list[dict[str, Any]],
    known: set[str],
    relation: dict[str, Any],
) -> bool:
    key = relation_key(relation)
    if key in known:
        return False
    known.add(key)
    relations.append(relation)
    return True


def content_relations(
    prototype_id: str,
    resolved: dict[str, Any],
) -> list[dict[str, Any]]:
    components = resolved["components"]
    result: list[dict[str, Any]] = []

    storage_fill = components.get("StorageFill", {})
    contents = storage_fill.get("contents")
    if isinstance(contents, list):
        for position, entry in enumerate(contents):
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                continue
            relation: dict[str, Any] = {
                "from": prototype_id,
                "to": entry["id"],
                "type": "contains",
                "position": position,
                "quantity": entry.get("amount", 1),
            }
            for key in ("maxAmount", "prob", "orGroup"):
                if key in entry:
                    relation[key] = entry[key]
            result.append(relation)

    container_fill = components.get("ContainerFill", {})
    containers = container_fill.get("containers")
    if isinstance(containers, dict):
        for container_name, entries in containers.items():
            if not isinstance(entries, list):
                continue
            for position, entry in enumerate(entries):
                if isinstance(entry, str):
                    result.append(
                        {
                            "from": prototype_id,
                            "to": entry,
                            "type": "contains",
                            "container": str(container_name),
                            "position": position,
                            "quantity": 1,
                        }
                    )

    cm_slots = components.get("CMItemSlots", {})
    starting_item = cm_slots.get("startingItem")
    count = cm_slots.get("count", 1)
    if isinstance(starting_item, str):
        result.append(
            {
                "from": prototype_id,
                "to": starting_item,
                "type": "slotItem",
                "quantity": count if isinstance(count, int) else 1,
            }
        )
    starting_items = cm_slots.get("startingItems")
    if isinstance(starting_items, list):
        for position, entry in enumerate(starting_items):
            if isinstance(entry, str):
                result.append(
                    {
                        "from": prototype_id,
                        "to": entry,
                        "type": "slotItem",
                        "position": position,
                        "quantity": 1,
                    }
                )

    item_slots = components.get("ItemSlots", {}).get("slots")
    if isinstance(item_slots, dict):
        for slot_name, slot in item_slots.items():
            if not isinstance(slot, dict):
                continue
            item = slot.get("startingItem")
            if isinstance(item, str):
                result.append(
                    {
                        "from": prototype_id,
                        "to": item,
                        "type": "loadedWith",
                        "slot": str(slot_name),
                        "quantity": 1,
                    }
                )

    attachment_slots = components.get("AttachableHolder", {}).get("slots")
    if isinstance(attachment_slots, dict):
        for slot_name, slot in attachment_slots.items():
            if not isinstance(slot, dict):
                continue
            item = slot.get("startingAttachable")
            if isinstance(item, str):
                result.append(
                    {
                        "from": prototype_id,
                        "to": item,
                        "type": "installedAttachment",
                        "slot": str(slot_name),
                        "quantity": 1,
                    }
                )

    bundle = components.get("CMVendorBundle", {}).get("bundle")
    if isinstance(bundle, list):
        for position, item in enumerate(bundle):
            if isinstance(item, str):
                result.append(
                    {
                        "from": prototype_id,
                        "to": item,
                        "type": "bundleItem",
                        "position": position,
                        "quantity": 1,
                    }
                )

    variants = components.get("RMCArmorVariant", {}).get("types")
    if isinstance(variants, dict):
        for variant_name, item in variants.items():
            if isinstance(item, str):
                result.append(
                    {
                        "from": prototype_id,
                        "to": item,
                        "type": "variant",
                        "variant": str(variant_name),
                        "quantity": 1,
                    }
                )

    squad_mapping = components.get("CMVendorMapToSquad", {}).get("map")
    if isinstance(squad_mapping, dict):
        for squad_name, item in squad_mapping.items():
            if isinstance(item, str):
                result.append(
                    {
                        "from": prototype_id,
                        "to": item,
                        "type": "mappedVariant",
                        "variant": str(squad_name),
                        "quantity": 1,
                    }
                )

    fixed_weapon = components.get("WeaponMount", {}).get("fixedWeaponPrototype")
    if isinstance(fixed_weapon, str):
        result.append(
            {
                "from": prototype_id,
                "to": fixed_weapon,
                "type": "mountedWeapon",
                "quantity": 1,
            }
        )

    provider = components.get("BallisticAmmoProvider", {})
    ammo = provider.get("proto")
    if isinstance(ammo, str):
        relation = {
            "from": prototype_id,
            "to": ammo,
            "type": "loadedWith",
        }
        capacity = provider.get("capacity")
        if isinstance(capacity, int):
            relation["quantity"] = capacity
        result.append(relation)

    for provider_type in (
        "RevolverAmmoProvider",
        "ProjectileBatteryAmmoProvider",
        "BasicEntityAmmoProvider",
    ):
        provider = components.get(provider_type, {})
        ammo = provider.get("proto")
        if not isinstance(ammo, str):
            continue
        relation = {
            "from": prototype_id,
            "to": ammo,
            "type": "loadedWith",
            "provider": provider_type,
        }
        capacity = provider.get("capacity")
        if isinstance(capacity, int):
            relation["quantity"] = capacity
        result.append(relation)

    cartridge = components.get("CartridgeAmmo", {})
    projectile = cartridge.get("proto")
    if isinstance(projectile, str):
        result.append(
            {
                "from": prototype_id,
                "to": projectile,
                "type": "fires",
                "quantity": 1,
            }
        )

    bullet_box = components.get("RefillableByBulletBox", {}).get("bulletType")
    if isinstance(bullet_box, str):
        result.append(
            {
                "from": prototype_id,
                "to": bullet_box,
                "type": "refillableBy",
            }
        )

    return result


def whitelist_matches(
    whitelist: Any,
    candidate_id: str,
    candidate_tags: set[str],
    candidate_components: set[str],
) -> bool:
    if not isinstance(whitelist, dict):
        return False
    entities = whitelist.get("entities", [])
    if isinstance(entities, list) and candidate_id in entities:
        return True
    tags = whitelist.get("tags", [])
    if isinstance(tags, list) and candidate_tags.intersection(
        item for item in tags if isinstance(item, str)
    ):
        return True
    components = whitelist.get("components", [])
    if isinstance(components, list) and candidate_components.intersection(
        item for item in components if isinstance(item, str)
    ):
        return True
    return False


def add_compatibility_relations(
    item_ids: set[str],
    resolver: PrototypeResolver,
    relations: list[dict[str, Any]],
    relation_keys: set[str],
) -> None:
    candidate_data: dict[str, tuple[set[str], set[str]]] = {}
    attachments: set[str] = set()
    magazines: set[str] = set()

    for item_id in item_ids:
        resolved = resolver.resolve(item_id)
        components = resolved["components"]
        tags = components.get("Tag", {}).get("tags", [])
        tag_set = {item for item in tags if isinstance(item, str)} if isinstance(tags, list) else set()
        component_set = set(components)
        candidate_data[item_id] = (tag_set, component_set)
        if "Attachable" in component_set:
            attachments.add(item_id)
        if "BallisticAmmoProvider" in component_set and "Gun" not in component_set:
            magazines.add(item_id)

    for weapon_id in sorted(item_ids):
        components = resolver.resolve(weapon_id)["components"]

        attachment_slots = components.get("AttachableHolder", {}).get("slots")
        if isinstance(attachment_slots, dict):
            for slot_name, slot in attachment_slots.items():
                if not isinstance(slot, dict):
                    continue
                whitelist = slot.get("whitelist")
                blacklist = slot.get("blacklist")
                for attachment_id in sorted(attachments):
                    tags, component_types = candidate_data[attachment_id]
                    if not whitelist_matches(
                        whitelist, attachment_id, tags, component_types
                    ):
                        continue
                    if whitelist_matches(
                        blacklist, attachment_id, tags, component_types
                    ):
                        continue
                    add_relation(
                        relations,
                        relation_keys,
                        {
                            "from": weapon_id,
                            "to": attachment_id,
                            "type": "compatibleAttachment",
                            "slot": str(slot_name),
                        },
                    )

        item_slots = components.get("ItemSlots", {}).get("slots")
        if isinstance(item_slots, dict):
            for slot_name, slot in item_slots.items():
                if not isinstance(slot, dict):
                    continue
                whitelist = slot.get("whitelist")
                blacklist = slot.get("blacklist")
                for magazine_id in sorted(magazines):
                    tags, component_types = candidate_data[magazine_id]
                    if not whitelist_matches(
                        whitelist, magazine_id, tags, component_types
                    ):
                        continue
                    if whitelist_matches(
                        blacklist, magazine_id, tags, component_types
                    ):
                        continue
                    add_relation(
                        relations,
                        relation_keys,
                        {
                            "from": weapon_id,
                            "to": magazine_id,
                            "type": "compatibleMagazine",
                            "slot": str(slot_name),
                        },
                    )


def has_meaningful_armor(components: dict[str, Any]) -> bool:
    """Ignore the empty Armor marker inherited by backpacks and satchels."""
    cm_armor = components.get("CMArmor")
    if isinstance(cm_armor, dict) and any(
        isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0
        for key, value in cm_armor.items()
        if key
        in {
            "xenoArmor",
            "frontalArmor",
            "sideArmor",
            "melee",
            "bullet",
            "bio",
            "explosionArmor",
        }
    ):
        return True
    if isinstance(cm_armor, dict) and cm_armor.get("immuneToAP") is True:
        return True
    if any(
        component_type in components
        for component_type in ("CMHardArmor", "RMCBulkyArmor", "SquadArmor")
    ):
        return True
    armor = components.get("Armor")
    if not isinstance(armor, dict):
        return False
    modifiers = armor.get("modifiers")
    if isinstance(modifiers, dict) and modifiers:
        return True
    modifier_sets = armor.get("modifierSets")
    return isinstance(modifier_sets, list) and bool(modifier_sets)


def equipment_slots(components: dict[str, Any]) -> set[str]:
    clothing = components.get("Clothing")
    if not isinstance(clothing, dict):
        return set()
    slots = clothing.get("slots")
    if isinstance(slots, str):
        return {slots}
    if isinstance(slots, list):
        return {str(slot) for slot in slots if isinstance(slot, str)}
    return set()


def is_public_armor(components: dict[str, Any]) -> bool:
    """Armor is only protective outer clothing or a protective helmet."""
    if not has_meaningful_armor(components):
        return False
    slots = {slot.casefold() for slot in equipment_slots(components)}
    return bool(slots.intersection({"outerclothing", "head"}))


def is_ammunition_container(
    prototype_id: str,
    component_types: set[str],
    tags: set[str],
) -> bool:
    if "RMCAmmoBox" in tags or "RMCBoxShotgunShells" in tags:
        return True
    if prototype_id.startswith((
        "RMCBoxMagazine",
        "RMCBoxBullets",
        "RMCBoxShells",
        "RMCBoxShotgun",
        "RMCBox458SOCOM",
    )):
        return True
    return "RMCFlamerTank" in component_types


def is_dedicated_melee_weapon(
    prototype_id: str,
    component_types: set[str],
    tags: set[str],
) -> bool:
    if "MeleeWeapon" not in component_types:
        return False
    melee_words = ("knife", "machete", "bayonet", "sword", "blade")
    signals = {prototype_id.casefold(), *(tag.casefold() for tag in tags)}
    return "Sharp" in component_types or any(
        word in signal for signal in signals for word in melee_words
    )


def source_category_hint(section_name: str) -> str | None:
    normalized = re.sub(r"\s+", " ", section_name.strip().casefold())
    direct = SOURCE_CATEGORY_HINTS.get(normalized)
    if direct:
        return direct
    for fragment, category in SOURCE_CATEGORY_HINTS.items():
        if fragment in normalized:
            return category
    return None


def has_any_component(component_types: set[str], fragments: tuple[str, ...]) -> bool:
    return any(
        fragment.casefold() in component_type.casefold()
        for component_type in component_types
        for fragment in fragments
    )


def infer_types(
    prototype_id: str,
    components: dict[str, Any],
    tags: set[str],
    source_hints: set[str] | None = None,
) -> list[str]:
    result: set[str] = set()
    component_types = set(components)
    source_hints = source_hints or set()
    folded_id = prototype_id.casefold()

    if (
        "Attachable" not in component_types
        and ("Gun" in component_types or "RMCFlamerAmmoProvider" in component_types)
    ):
        result.add("weapon")
    if "Attachable" in component_types:
        result.add("attachment")
    if "Projectile" in component_types:
        result.add("projectile")
    if "CartridgeAmmo" in component_types:
        result.add("cartridge")
    if "BallisticAmmoProvider" in component_types and "Gun" not in component_types:
        result.add("magazine-or-ammo-container")
    if is_ammunition_container(prototype_id, component_types, tags):
        result.add("magazine-or-ammo-container")
    if "Storage" in component_types or "CMItemSlots" in component_types:
        result.add("container")
    if has_meaningful_armor(components):
        result.add("armor")
    if "Explosive" in component_types or any("Grenade" in tag for tag in tags):
        result.add("explosive")
    if is_dedicated_melee_weapon(prototype_id, component_types, tags):
        result.add("melee")
    if "Tool" in component_types or any(
        component_type.endswith("Tool") for component_type in component_types
    ):
        result.add("tool")
    if "Clothing" in component_types or has_any_component(
        component_types, ("uniformaccessory", "helmetaccessory")
    ):
        result.add("clothing")
    if has_any_component(
        component_types,
        ("healing", "healthanalyzer", "surgery", "defibrillator", "hypospray"),
    ):
        result.add("medical")
    if (
        has_any_component(
            component_types,
            ("pill", "injector", "hypospray", "syringe", "injectablesolution"),
        )
        or any(
            word in folded_id
            for word in ("pill", "tablet", "autoinjector", "syringe")
        )
    ):
        result.add("medicine")
    if has_any_component(component_types, ("edible",)):
        result.add("food")
    if has_any_component(
        component_types,
        (
            "radio",
            "headset",
            "binocular",
            "motiondetector",
            "camera",
            "computer",
            "encryption",
            "visor",
        ),
    ):
        result.add("electronics")
    if "Flash" in component_types:
        result.add("electronics")
    if has_any_component(component_types, ("light", "flashlight", "flare")):
        result.add("lighting")
    if "Stack" in component_types or any(
        word in folded_id for word in ("sheet", "plank", "sandbag", "plastic", "phoron")
    ):
        result.add("material")
    if any(word in folded_id for word in ("pamphlet", "manual", "guidebook")):
        result.add("training")
    if has_any_component(component_types, ("crayon", "stamp")) or any(
        word in folded_id for word in ("crayon", "stamp")
    ):
        result.add("office")
    if has_any_component(component_types, ("mop", "broom", "janitor")) or any(
        word in folded_id
        for word in ("cleaner", "wetsign", "mop", "broom", "janitor")
    ):
        result.add("janitorial")
    if has_any_component(component_types, ("cprdummy", "healthscannable")):
        result.add("medical")
    if has_any_component(
        component_types,
        ("welder", "construction", "powercell", "generator", "barricade"),
    ):
        result.add("engineering")
    if "WeaponMount" in component_types or has_any_component(
        component_types, ("sentry", "mortar")
    ):
        result.add("weapon-support")
    if (
        "vehicle-ammunition" in source_hints
        and (
            "magazine-or-ammo-container" in result
            or "cartridge" in result
            or "explosive" in result
        )
    ):
        result.add("vehicle-ammunition")
    if not result:
        result.update(source_hints)
    if not result:
        result.add("misc")
    return sorted(result)


def layer_map_names(layer: dict[str, Any]) -> set[str]:
    value = layer.get("map")
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def apply_static_preview_states(
    components: dict[str, Any],
    layers: list[dict[str, Any]],
) -> None:
    """Choose the spawn-time state for layers normally updated by game systems."""
    magazine_visuals = components.get("MagazineVisuals")
    if not isinstance(magazine_visuals, dict):
        return
    mag_state = magazine_visuals.get("magState")
    steps = magazine_visuals.get("steps")
    if not isinstance(mag_state, str) or not isinstance(steps, int) or steps <= 0:
        return
    full_state = f"{mag_state}-{max(steps - 1, 0)}"
    for layer in layers:
        if "enum.GunVisualLayers.Mag" in layer_map_names(layer):
            layer["state"] = full_state
            layer["visible"] = True


def apply_closed_container_preview(layers: list[dict[str, Any]]) -> None:
    """Mirror the closed item icon used by vendors, not the opened UI state."""
    for layer in layers:
        maps = {name.casefold() for name in layer_map_names(layer)}
        if any("openlayer" in name or "emptylayer" in name for name in maps):
            layer["visible"] = False
        if any("closedlayer" in name for name in maps):
            layer["visible"] = True


def solution_preview_summary(components: dict[str, Any]) -> dict[str, Any] | None:
    visuals = components.get("SolutionContainerVisuals")
    manager = components.get("SolutionContainerManager")
    if not isinstance(visuals, dict) or not isinstance(manager, dict):
        return None
    solutions = manager.get("solutions")
    if not isinstance(solutions, dict) or not solutions:
        return None
    solution_name = visuals.get("solutionName")
    if not isinstance(solution_name, str) or solution_name not in solutions:
        solution_name = next(iter(solutions))
    solution = solutions.get(solution_name)
    if not isinstance(solution, dict):
        return None
    raw_reagents = solution.get("reagents")
    reagents: list[dict[str, Any]] = []
    if isinstance(raw_reagents, list):
        for entry in raw_reagents:
            if not isinstance(entry, dict):
                continue
            reagent_id = entry.get("ReagentId")
            quantity = entry.get("Quantity")
            if isinstance(reagent_id, str) and isinstance(quantity, (int, float)):
                reagents.append({"id": reagent_id, "quantity": quantity})
    elif isinstance(raw_reagents, dict):
        for reagent_id, quantity in raw_reagents.items():
            if isinstance(reagent_id, str) and isinstance(quantity, (int, float)):
                reagents.append({"id": reagent_id, "quantity": quantity})
    volume = sum(
        float(entry["quantity"])
        for entry in reagents
        if isinstance(entry.get("quantity"), (int, float))
    )
    max_volume = solution.get("maxVol")
    if not isinstance(max_volume, (int, float)) or max_volume <= 0:
        max_volume = volume
    result = {
        "layerMap": str(
            visuals.get("layer", "enum.SolutionContainerLayers.Fill")
        ),
        "fillBaseName": visuals.get("fillBaseName"),
        "emptySpriteName": visuals.get("emptySpriteName"),
        "maxFillLevels": visuals.get("maxFillLevels", 1),
        "changeColor": visuals.get("changeColor", True),
        "fillFraction": min(max(volume / max_volume, 0), 1) if max_volume else 0,
        "reagents": reagents,
    }
    return result


def sprite_summary(components: dict[str, Any]) -> dict[str, Any] | None:
    sprite = components.get("Sprite")
    if not isinstance(sprite, dict):
        sprite = components.get("Icon")
    if not isinstance(sprite, dict):
        sprite = {}
    result: dict[str, Any] = {}
    if isinstance(sprite.get("sprite"), str):
        result["sprite"] = sprite["sprite"]
    elif isinstance(sprite.get("texture"), str):
        result["sprite"] = sprite["texture"]
    if isinstance(sprite.get("state"), str):
        result["state"] = sprite["state"]
    if "sprite" not in result:
        item_sprite = components.get("Item", {}).get("sprite")
        if isinstance(item_sprite, str):
            result["sprite"] = item_sprite
    layers = sprite.get("layers")
    if isinstance(layers, list):
        clean_layers = [
            copy.deepcopy(layer) for layer in layers if isinstance(layer, dict)
        ]
        if clean_layers:
            if (
                "StorageFill" in components
                or "ContainerFill" in components
                or "Storage" in components
            ):
                apply_closed_container_preview(clean_layers)
            apply_static_preview_states(components, clean_layers)
            result["layers"] = clean_layers
            if "state" not in result:
                for layer in clean_layers:
                    state = layer.get("state")
                    if isinstance(state, str):
                        result["state"] = state
                        break
    solution_preview = solution_preview_summary(components)
    if solution_preview:
        result["solutionPreview"] = solution_preview
    if (
        "StorageFill" in components
        or "ContainerFill" in components
        or "Storage" in components
    ):
        # Vending UIs show the spawn/closed appearance. Runtime visualizers can
        # otherwise leave a crate or grenade box on its open state in the wiki.
        result["preferClosed"] = True
    return result or None


def texture_path(game_source: Path, sprite_path: str) -> Path:
    normalized = sprite_path.replace("\\", "/").lstrip("/")
    if normalized.startswith("Textures/"):
        normalized = normalized[len("Textures/") :]
    return game_source / "Resources/Textures" / normalized


def first_rsi_state(
    meta: dict[str, Any],
    sprite_path: str = "",
    requested: str | None = None,
    prefer_closed: bool = False,
) -> str | None:
    states = meta.get("states")
    if not isinstance(states, list):
        return None
    names = [
        state["name"]
        for state in states
        if isinstance(state, dict) and isinstance(state.get("name"), str)
    ]
    stem = Path(sprite_path).stem.casefold()
    folded = {name.casefold(): name for name in names}
    if prefer_closed and isinstance(requested, str) and (
        "open" in requested.casefold() or "empty" in requested.casefold()
    ):
        closed_candidates: list[str] = []
        requested_folded = requested.casefold()
        closed_candidates.extend(
            (
                requested_folded.replace("opened", "closed").replace("empty", "closed"),
                requested_folded.replace("open", "closed").replace("empty", "closed"),
                re.sub(r"(?:^|[-_])(?:open(?:ed)?|empty)(?:$|[-_])", "", requested_folded).strip("-_"),
            )
        )
        closed_candidates.extend(("closed", "icon", "item", "default", stem, "base", "idle", "full"))
        for candidate in closed_candidates:
            if candidate and candidate in folded:
                return folded[candidate]
    if requested in names:
        return requested
    preferred = (
        ("closed", "icon", "item", "default", stem, "base", "idle", "full")
        if prefer_closed
        else ("icon", "item", "default", stem, "base", "idle", "closed", "full")
    )
    for candidate in preferred:
        if candidate and candidate in folded:
            return folded[candidate]
    non_equipped = [
        name
        for name in names
        if not any(
            marker in name.casefold()
            for marker in (
                "inhand",
                "equipped",
                "-left",
                "-right",
                "-front",
                "-back",
            )
        )
    ]
    return (non_equipped or names or [None])[0]


def load_sprite_frame(
    game_source: Path,
    sprite_path: str,
    state: str | None,
    prefer_closed: bool = False,
) -> Image.Image:
    source = texture_path(game_source, sprite_path)
    if source.suffix.lower() != ".rsi":
        if not source.is_file():
            raise FileNotFoundError(f"Missing sprite texture: {source}")
        return Image.open(source).convert("RGBA")

    meta_path = source / "meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"Missing RSI metadata: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    if not isinstance(meta, dict):
        raise RuntimeError(f"Invalid RSI metadata: {meta_path}")

    selected_state = first_rsi_state(
        meta,
        sprite_path,
        state,
        prefer_closed=prefer_closed,
    )
    if not selected_state:
        raise RuntimeError(f"RSI has no states: {meta_path}")
    state_path = source / f"{selected_state}.png"
    if not state_path.is_file():
        raise FileNotFoundError(f"Missing RSI state {selected_state}: {meta_path}")
    sheet = Image.open(state_path).convert("RGBA")

    size = meta.get("size", {})
    width = size.get("x") if isinstance(size, dict) else None
    height = size.get("y") if isinstance(size, dict) else None
    if not isinstance(width, int) or not isinstance(height, int):
        width, height = sheet.height, sheet.height
    return sheet.crop((0, 0, min(width, sheet.width), min(height, sheet.height)))


def tint_sprite_layer(image: Image.Image, color_value: Any) -> Image.Image:
    if not isinstance(color_value, str):
        return image
    try:
        red, green, blue, alpha = ImageColor.getcolor(color_value, "RGBA")
    except ValueError as error:
        raise RuntimeError(f"Unsupported sprite layer color: {color_value}") from error

    rgb = ImageChops.multiply(
        image.convert("RGB"),
        Image.new("RGB", image.size, (red, green, blue)),
    )
    source_alpha = image.getchannel("A")
    if alpha != 255:
        source_alpha = ImageChops.multiply(
            source_alpha,
            Image.new("L", image.size, alpha),
        )
    return Image.merge("RGBA", (*rgb.split(), source_alpha))


def layer_offset_pixels(layer: dict[str, Any], width: int, height: int) -> tuple[int, int]:
    value = layer.get("offset")
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return 0, 0
    if len(parts) != 2:
        return 0, 0
    try:
        x = float(parts[0])
        y = float(parts[1])
    except (TypeError, ValueError):
        return 0, 0
    return round(x * width), round(-y * height)


def mixed_reagent_color(
    reagents: list[dict[str, Any]],
    reagent_colors: dict[str, str],
) -> str | None:
    weighted: list[tuple[tuple[int, int, int, int], float]] = []
    for entry in reagents:
        reagent_id = entry.get("id")
        quantity = entry.get("quantity")
        color = reagent_colors.get(str(reagent_id))
        if not isinstance(quantity, (int, float)) or quantity <= 0 or not color:
            continue
        try:
            weighted.append((ImageColor.getcolor(color, "RGBA"), float(quantity)))
        except ValueError:
            continue
    total = sum(quantity for _, quantity in weighted)
    if total <= 0:
        return None
    channels = tuple(
        round(sum(color[index] * quantity for color, quantity in weighted) / total)
        for index in range(4)
    )
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def apply_solution_preview(
    summary: dict[str, Any],
    layers: list[dict[str, Any]],
    reagent_colors: dict[str, str],
) -> None:
    preview = summary.get("solutionPreview")
    if not isinstance(preview, dict):
        return
    fraction = preview.get("fillFraction")
    max_levels = preview.get("maxFillLevels")
    if not isinstance(fraction, (int, float)):
        return
    if not isinstance(max_levels, int) or max_levels <= 0:
        max_levels = 1
    level = min(max(math.ceil(float(fraction) * max_levels), 0), max_levels)
    map_name = str(preview.get("layerMap", "enum.SolutionContainerLayers.Fill"))
    color = mixed_reagent_color(preview.get("reagents", []), reagent_colors)
    for layer in layers:
        maps = layer_map_names(layer)
        if map_name not in maps and "enum.SolutionContainerLayers.Fill" not in maps:
            continue
        if level <= 0:
            empty_state = preview.get("emptySpriteName")
            if isinstance(empty_state, str):
                layer["state"] = empty_state
                layer["visible"] = True
            else:
                layer["visible"] = False
            continue
        fill_base = preview.get("fillBaseName")
        if isinstance(fill_base, str):
            layer["state"] = f"{fill_base}{level}"
        layer["visible"] = True
        if preview.get("changeColor", True) and color:
            layer["color"] = color
        else:
            layer.pop("color", None)


def render_sprite_preview(
    game_source: Path,
    summary: dict[str, Any],
    reagent_colors: dict[str, str],
) -> Image.Image:
    base_sprite = summary.get("sprite")
    layers = summary.get("layers")
    render_layers: list[dict[str, Any]] = []

    if isinstance(layers, list):
        prepared_layers = [copy.deepcopy(layer) for layer in layers if isinstance(layer, dict)]
        apply_solution_preview(summary, prepared_layers, reagent_colors)
        for layer in prepared_layers:
            if not isinstance(layer, dict) or layer.get("visible") is False:
                continue
            layer_sprite = layer.get("sprite", base_sprite)
            layer_state = layer.get("state")
            if isinstance(layer_sprite, str):
                # A layer without a state is an initially empty visualizer slot.
                # Reusing Sprite.state here produced unrelated duplicate artwork.
                if not isinstance(layer_state, str):
                    continue
                rendered = copy.deepcopy(layer)
                rendered["sprite"] = layer_sprite
                rendered["state"] = layer_state
                render_layers.append(rendered)
            elif isinstance(layer.get("texture"), str):
                rendered = copy.deepcopy(layer)
                rendered["sprite"] = layer["texture"]
                rendered["state"] = None
                render_layers.append(rendered)

    if not render_layers and isinstance(base_sprite, str):
        state = summary.get("state")
        render_layers.append(
            {
                "sprite": base_sprite,
                "state": state if isinstance(state, str) else None,
            }
        )
    if not render_layers:
        raise RuntimeError("Sprite component has no renderable texture")

    images: list[tuple[Image.Image, dict[str, Any]]] = []
    for layer in render_layers:
        image = load_sprite_frame(
            game_source,
            layer["sprite"],
            layer.get("state"),
            prefer_closed=summary.get("preferClosed") is True,
        )
        image = tint_sprite_layer(image, layer.get("color"))
        images.append((image, layer))
    width = max(image.width for image, _ in images)
    height = max(image.height for image, _ in images)
    preview = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for image, layer in images:
        offset_x, offset_y = layer_offset_pixels(layer, width, height)
        x = (width - image.width) // 2 + offset_x
        y = (height - image.height) // 2 + offset_y
        preview.alpha_composite(image, (x, y))
    return preview


def classification_result(
    status: str,
    *,
    category_id: str | None = None,
    reason: str,
    signals: Iterable[str] = (),
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "confidence": "high" if status == "public" else "none",
        "reason": reason,
        "signals": sorted(set(signals)),
    }
    if category_id is not None:
        result["categoryId"] = category_id
        result["category"] = PUBLIC_CATEGORY_LABELS[category_id]
    return result


def classify_item(
    item: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Assign exactly one wiki category from reusable mechanical signals."""
    item_id = str(item.get("id", ""))
    component_types = set(item.get("componentTypes", []))
    tags = set(item.get("tags", []))
    source_file = str(item.get("sourceFile", ""))
    folded_id = item_id.casefold()
    folded_path = source_file.casefold()
    folded_tags = {tag.casefold() for tag in tags}

    excluded_ids = set(policy.get("excludePrototypeIds", []))
    category_overrides = policy.get("categoryOverrides", {})
    if item_id in excluded_ids:
        return classification_result(
            "excluded",
            reason="prototype explicitly excluded by classification policy",
            signals=("config:excludePrototypeIds",),
        )
    override = category_overrides.get(item_id)
    if isinstance(override, str):
        return classification_result(
            "public",
            category_id=override,
            reason="category explicitly assigned by classification policy",
            signals=("config:categoryOverrides",),
        )

    def public(category_id: str, reason: str, *signals: str) -> dict[str, Any]:
        return classification_result(
            "public",
            category_id=category_id,
            reason=reason,
            signals=signals,
        )

    properties = item.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}
    slots = {str(slot).casefold() for slot in item.get("equipmentSlots", [])}
    has_gun = "Gun" in component_types or "RMCFlamerAmmoProvider" in component_types
    has_ammo = (
        "CartridgeAmmo" in component_types
        or (
            "BallisticAmmoProvider" in component_types
            and "Gun" not in component_types
        )
        or is_ammunition_container(item_id, component_types, tags)
        or "MortarShell" in component_types
        or "RMCPacketGrenade" in tags
    )
    has_explosive = (
        ("Explosive" in component_types and "gastank" not in folded_tags)
        or "ExplodeOnTrigger" in component_types
        or "ProjectileGrenade" in component_types
        or "grenade" in folded_id
        or "grenade" in folded_tags
        or "handgrenade" in folded_tags
    )

    # Underbarrel launchers and shotguns still belong to attachments even when
    # they also contain a Gun component.
    if "Attachable" in component_types:
        return public("attachment", "dedicated attachment component", "Attachable")
    if has_gun:
        return public("weapon", "dedicated firearm component", "Gun")
    if has_ammo or has_explosive:
        return public(
            "ammunition",
            "ammunition, grenade or explosive item",
            "component:ammunition-or-explosive",
        )
    if (
        "/objects/weapons/throwable/packets" in folded_path
        and ("Storage" in component_types or "CMItemSlots" in component_types)
    ):
        return public(
            "ammunition",
            "grenade packet or ammunition box",
            "path:throwable-packet",
        )
    cm_armor = properties.get("CMArmor")
    armor_components = {
        key: value
        for key, value in properties.items()
        if key in {"Armor", "CMArmor", "RMCArmor"}
    }
    meaningful_armor = has_meaningful_armor(armor_components) or (
        isinstance(cm_armor, dict)
        and any(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value != 0
            for value in cm_armor.values()
        )
    )
    if meaningful_armor and slots.intersection({"outerclothing", "head"}):
        return public(
            "armor",
            "protective outer-clothing or helmet slot",
            "component:armor",
            "slot:armor-or-head",
        )

    medical_object_path = "/entities/objects/medical/" in folded_path
    medical_box_path = "/catalog/fills/boxes/medical" in folded_path
    medical_delivery = (
        "Pill" in component_types
        or "Hypospray" in component_types
        or "Injector" in component_types
        or "Syringe" in component_types
        or "pillcanister" in folded_id
        or "packetpills" in folded_id
    )
    medical_solution = medical_object_path and (
        "CMRefillableSolution" in component_types
        or folded_id.startswith("cmbottle")
    )

    medical_path_id_signal = any(
        word in folded_id
        for word in (
            "firstaid",
            "aidkit",
            "medkit",
            "surgicaltray",
            "ivdrip",
            "medicaltent",
        )
    )
    field_medical_id_signal = any(
        word in folded_id
        for word in (
            "rollerbed",
            "stretcher",
            "surgicalbed",
            "oxygentank",
            "anesthetictank",
            "surgical",
            "scalpel",
            "hemostat",
            "retractor",
            "cautery",
            "bonesaw",
            "bonesetter",
            "woundclamp",
            "bonegel",
            "synthgraft",
        )
    )
    medical_mechanics = has_any_component(
        {
            component
            for component in component_types
            if not component.casefold().endswith("blocked")
        },
        (
            "surgerytool",
            "surgery",
            "healthanalyzer",
            "defibrillator",
            "dialysis",
            "cprdummy",
            "stasisbag",
            "bodybag",
            "healthscannable",
            "healthscanner",
            "ivdrip",
            "bloodpack",
            "stethoscope",
            "healing",
        ),
    )
    medical_container = (
        medical_object_path
        and (
            medical_path_id_signal
            or "Storage" in component_types
            or "CMItemSlots" in component_types
        )
    )
    if (
        medical_delivery
        or medical_solution
        or medical_mechanics
        or medical_container
        or medical_object_path
        or medical_box_path
        or field_medical_id_signal
    ):
        return public(
            "medicine",
            "medicine, medical device, treatment kit or surgical instrument",
            "component:medicine",
        )

    if is_dedicated_melee_weapon(item_id, component_types, tags):
        return public(
            "melee",
            "dedicated melee weapon outside medical use",
            "MeleeWeapon",
            "sharp-signal",
        )

    strong_tool = (
        "Tool" in component_types
        or any(component.endswith("Tool") for component in component_types)
        or has_any_component(
            component_types,
            (
                "welder",
                "multitool",
                "entrenchingtool",
                "nailgun",
                "lightreplacer",
            ),
        )
        or "/entities/objects/tools/" in folded_path
    )
    if strong_tool:
        return public(
            "gear",
            "dedicated hand tool or single-purpose utility item",
            "component:tool",
        )

    is_patch = (
        "patch" in folded_id
        or any("patch" in tag for tag in folded_tags)
        or has_any_component(component_types, ("uniformaccessory", "patch"))
    )
    is_headset = (
        "headset" in folded_id
        or has_any_component(component_types, ("headset",))
    )
    has_storage = "Storage" in component_types or "CMItemSlots" in component_types
    is_wearable_storage = has_storage and bool(slots.intersection(WEARABLE_STORAGE_SLOTS))
    is_standard_wearable = (
        "Clothing" in component_types
        and bool(slots.intersection(WEARABLE_EQUIPMENT_SLOTS))
    )

    # Patches and radio headsets are equipment even when their prototypes use
    # accessory components instead of an ordinary Clothing slot.
    if is_patch or is_headset:
        return public(
            "equipment",
            "patch or radio headset",
            "component:wearable-equipment",
        )

    advanced_field_device = (
        "WeaponMount" in component_types
        or has_any_component(component_types, ("sentry", "turret", "mortar", "weaponmount"))
        or "encryption" in folded_id
        or has_any_component(
            component_types,
            ("encryption",),
        )
        or has_any_component(
            component_types,
            (
                "scope",
                "binocular",
                "rangefinder",
                "spotting",
                "motiondetector",
                "motionsensor",
                "sensor",
                "nightvision",
                "togglevisor",
                "integratedvisor",
                "cycleablevisor",
                "targetinglaser",
                "overwatchcamera",
                "overwatch",
                "handcuff",
                "restrain",
            ),
        )
    )
    if advanced_field_device:
        return public(
            "gear",
            "advanced field device, weapon support or encryption component",
            "component:gear",
        )

    # Clothing and wearable storage belong together. Medical pouches are
    # already caught by the higher-priority medical rule.
    if is_wearable_storage or is_standard_wearable:
        return public(
            "equipment",
            "standard wearable or wearable storage",
            "component:wearable-equipment",
        )

    # Tools, complex field technology and single-purpose utility objects share
    # one broad section. This avoids an arbitrary border between a multitool,
    # binoculars, a turret and an encryption key.
    if (
        "WeaponMount" in component_types
        or has_any_component(component_types, ("sentry", "turret", "mortar", "weaponmount"))
        or "Tool" in component_types
        or any(component.endswith("Tool") for component in component_types)
        or has_any_component(
            component_types,
            (
                "welder",
                "multitool",
                "entrenchingtool",
                "nailgun",
                "foldingbarricade",
                "powercell",
                "battery",
                "circuitboard",
                "lightreplacer",
                "lightbulb",
                "lighttube",
                "generator",
                "machineboard",
            ),
        )
        or "/entities/objects/tools/" in folded_path
        or "engineerkit" in folded_id
        or any(component.casefold().endswith("electronics") for component in component_types)
        or any(
            word in folded_id
            for word in (
                "battery",
                "powercell",
                "lightbulb",
                "lighttube",
                "circuitboard",
                "encryptionkey",
                "encryption",
            )
        )
    ):
        return public(
            "gear",
            "tool, field technology, replacement part or single-purpose utility item",
            "component:gear-or-tool",
        )

    if (
        "Clothing" in component_types
        or slots
        or "/entities/clothing/" in folded_path
    ):
        return public(
            "gear",
            "non-standard wearable or installed clothing accessory",
            "component:installed-accessory",
        )

    if has_any_component(
        component_types,
        (
            "radio",
            "camera",
            "handheldlight",
            "flare",
            "flash",
            "detector",
            "scanner",
        ),
    ) or any(
        word in folded_id
        for word in ("whistle", "ziptie", "bedroll", "gasmask")
    ):
        return public(
            "gear",
            "single-purpose field item",
            "component:gear",
        )

    return public(
        "other",
        "no stronger universal functional rule matched",
        "fallback:other",
    )


def is_case_item(item: dict[str, Any]) -> bool:
    name = str(item.get("name", "")).casefold()
    prototype_id = str(item.get("id", ""))
    component_types = set(item.get("componentTypes", []))
    return (
        "StorageFill" in component_types
        and (
            "кейс" in name
            or "case" in prototype_id.casefold()
            or (
                prototype_id.startswith("RMCKit")
                and "RemoveOnlyStorage" in component_types
            )
        )
    )


def is_state_variant(item: dict[str, Any]) -> bool:
    signal = f"{item.get('id', '')} {item.get('suffix', '')}".casefold()
    return any(
        marker in signal
        for marker in (
            "empty",
            "filled",
            "loaded",
            "assembled",
            "пуст",
            "заполн",
            "заряж",
            "собран",
        )
    )


def normalized_identity_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def state_alias_groups(
    candidate_ids: set[str],
    items: dict[str, Any],
    relations: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Collapse load-state prototypes without merging merely similar models."""
    parent: dict[str, str] = {item_id: item_id for item_id in candidate_ids}

    def find(item_id: str) -> str:
        while parent[item_id] != item_id:
            parent[item_id] = parent[parent[item_id]]
            item_id = parent[item_id]
        return item_id

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for item_id in sorted(candidate_ids):
        item = items[item_id]
        ancestors = list(item.get("parents", []))
        visited: set[str] = set()
        while ancestors:
            ancestor_id = ancestors.pop(0)
            if ancestor_id in visited:
                continue
            visited.add(ancestor_id)
            ancestor = items.get(ancestor_id)
            if not isinstance(ancestor, dict):
                continue
            ancestors.extend(ancestor.get("parents", []))
            same_text = (
                normalized_identity_text(item.get("name"))
                == normalized_identity_text(ancestor.get("name"))
                and normalized_identity_text(item.get("description"))
                == normalized_identity_text(ancestor.get("description"))
            )
            load_state_weapon = (
                "weapon" in item.get("types", [])
                and "weapon" in ancestor.get("types", [])
                and (is_state_variant(item) or is_state_variant(ancestor))
            )
            load_state_container = (
                "container" in item.get("types", [])
                and "container" in ancestor.get("types", [])
                and (is_state_variant(item) or is_state_variant(ancestor))
            )
            stack_variant = (
                "Stack" in item.get("componentTypes", [])
                and "Stack" in ancestor.get("componentTypes", [])
            )
            if (
                ancestor_id in candidate_ids
                and same_text
                and (load_state_weapon or load_state_container or stack_variant)
            ):
                union(item_id, ancestor_id)

    for relation in relations:
        if relation.get("type") != "variant":
            continue
        source = relation.get("from")
        target = relation.get("to")
        if source not in candidate_ids or target not in candidate_ids:
            continue
        source_item = items[source]
        target_item = items[target]
        if (
            normalized_identity_text(source_item.get("name"))
            == normalized_identity_text(target_item.get("name"))
        ):
            union(source, target)

    variant_siblings: dict[str, list[str]] = defaultdict(list)
    for relation in relations:
        if relation.get("type") == "variant" and relation.get("to") in candidate_ids:
            variant_siblings[str(relation.get("from"))].append(str(relation["to"]))
    for siblings in variant_siblings.values():
        by_text: dict[tuple[str, str], list[str]] = defaultdict(list)
        for item_id in siblings:
            item = items[item_id]
            by_text[
                (
                    normalized_identity_text(item.get("name")),
                    normalized_identity_text(item.get("description")),
                )
            ].append(item_id)
        for members in by_text.values():
            for member in members[1:]:
                union(members[0], member)

    stack_families: dict[tuple[str, str, tuple[str, ...]], list[str]] = defaultdict(list)
    for item_id in sorted(candidate_ids):
        item = items[item_id]
        if "Stack" not in item.get("componentTypes", []):
            continue
        key = (
            normalized_identity_text(item.get("name")),
            normalized_identity_text(item.get("description")),
            tuple(sorted(item.get("parents", []))),
        )
        stack_families[key].append(item_id)
    for members in stack_families.values():
        for member in members[1:]:
            union(members[0], member)

    outgoing_weight: dict[str, int] = defaultdict(int)
    for relation in relations:
        if relation.get("type") in ROOT_RELATION_TYPES:
            outgoing_weight[str(relation.get("from"))] += 1

    groups: dict[str, list[str]] = defaultdict(list)
    for item_id in sorted(candidate_ids):
        groups[find(item_id)].append(item_id)

    aliases: dict[str, str] = {}
    canonical_groups: dict[str, list[str]] = {}
    for members in groups.values():
        plain_containers = [
            item_id
            for item_id in members
            if "container" in items[item_id].get("types", [])
            and "armor" not in items[item_id].get("types", [])
            and "weapon" not in items[item_id].get("types", [])
            and not is_state_variant(items[item_id])
        ]
        if plain_containers:
            canonical = min(plain_containers, key=lambda item_id: (len(item_id), item_id))
        else:
            canonical = max(
                members,
                key=lambda item_id: (
                    outgoing_weight[item_id],
                    not any(
                        marker in f"{item_id} {items[item_id].get('suffix', '')}".casefold()
                        for marker in ("empty", "пуст")
                    ),
                    len(items[item_id].get("componentTypes", [])),
                    -len(item_id),
                    item_id,
                ),
            )
        canonical_groups[canonical] = sorted(members)
        for member in members:
            aliases[member] = canonical
    return aliases, canonical_groups


def is_hidden_transport(
    item_id: str,
    item: dict[str, Any],
    explicit_transport_ids: set[str],
    generated_wrapper_ids: set[str],
) -> bool:
    if item_id in explicit_transport_ids or item_id.startswith("RMCCrate"):
        return True
    folded = f"{item_id} {item.get('name', '')}".casefold()
    component_types = set(item.get("componentTypes", []))
    packaging = any(
        marker in folded
        for marker in ("box", "crate", "case", "kit", "ящик", "короб")
    )
    lighting_supply = any(
        marker in folded
        for marker in ("flashlight", "flare", "фонар", "флаер", "сигнальн")
    )
    if "StorageFill" in component_types and packaging and lighting_supply:
        return True
    return item_id in generated_wrapper_ids


def build_public_catalog(
    trade_entries: list[dict[str, Any]],
    items: dict[str, Any],
    relations: list[dict[str, Any]],
    transport_container_ids: set[str],
    classification_policy: dict[str, Any],
) -> dict[str, Any]:
    physical_contents: dict[str, list[str]] = defaultdict(list)
    generated_wrapper_ids: set[str] = set()
    for relation in relations:
        if relation.get("type") in PHYSICAL_CONTENT_RELATION_TYPES:
            physical_contents[relation["from"]].append(relation["to"])
        if relation.get("type") == "mountedWeapon":
            generated_wrapper_ids.add(relation["from"])
        if relation.get("type") == "bundleItem":
            generated_wrapper_ids.add(relation["from"])
        if relation.get("type") == "mappedVariant":
            generated_wrapper_ids.add(relation["from"])
        if (
            relation.get("type") == "variant"
            and "RMCArmorVariant"
            in items.get(str(relation.get("from", "")), {}).get("componentTypes", [])
        ):
            generated_wrapper_ids.add(relation["from"])

    public_candidates: set[str] = set()
    seed_ids: list[str] = []
    for entry in trade_entries:
        item_id = entry.get("itemId")
        if isinstance(item_id, str):
            seed_ids.append(item_id)
        stock = entry.get("stock")
        stock_id = stock.get("itemId") if isinstance(stock, dict) else None
        if isinstance(stock_id, str):
            seed_ids.append(stock_id)
    queue = deque(seed_ids)
    visited: set[str] = set()
    unwrapped_transport_ids: set[str] = set()
    while queue:
        item_id = queue.popleft()
        if item_id in visited:
            continue
        visited.add(item_id)
        item = items[item_id]
        hidden = is_hidden_transport(
            item_id,
            item,
            transport_container_ids,
            generated_wrapper_ids,
        )
        if hidden:
            unwrapped_transport_ids.add(item_id)
        else:
            public_candidates.add(item_id)
        # Every physical container is recursive. Useful bags/pouches remain
        # public while their actual contents receive their own cards.
        queue.extend(physical_contents.get(item_id, []))

    aliases, alias_groups = state_alias_groups(
        public_candidates,
        items,
        relations,
    )
    configured_aliases = classification_policy.get("canonicalPrototypeIds", {})
    for alias_id, canonical_id in sorted(configured_aliases.items()):
        if alias_id not in public_candidates:
            continue
        if canonical_id not in public_candidates:
            raise RuntimeError(
                f"Configured canonical item {canonical_id} is not a public candidate "
                f"for alias {alias_id}"
            )
        aliases[alias_id] = canonical_id
    public_ids = {aliases[item_id] for item_id in public_candidates}
    for canonical_id, members in alias_groups.items():
        if len(members) > 1:
            items[canonical_id]["aliases"] = [
                member for member in members if member != canonical_id
            ]
            for member in members:
                items[member]["canonicalItemId"] = canonical_id
            if (
                "container" in items[canonical_id].get("types", [])
                and "armor" not in items[canonical_id].get("types", [])
                and "weapon" not in items[canonical_id].get("types", [])
            ):
                loadouts = []
                for member in members:
                    content_ids = sorted(set(physical_contents.get(member, [])))
                    if not content_ids:
                        continue
                    loadouts.append(
                        {
                            "itemId": member,
                            "suffix": items[member].get("suffix", ""),
                            "contentItemIds": content_ids,
                        }
                    )
                if loadouts:
                    items[canonical_id]["loadoutVariants"] = loadouts

    categories: dict[str, list[str]] = defaultdict(list)
    excluded_ids: list[str] = []
    sort_key = lambda value: (items[value]["name"].casefold(), value)
    for item_id in sorted(public_ids, key=sort_key):
        classification = classify_item(items[item_id], classification_policy)
        items[item_id]["classification"] = classification
        status = classification["status"]
        if status == "excluded":
            excluded_ids.append(item_id)
            continue
        category = classification["category"]
        items[item_id]["category"] = category
        items[item_id]["types"] = [classification["categoryId"]]
        items[item_id]["public"] = True
        categories[category].append(item_id)

    published_ids = [
        item_id
        for item_id in sorted(public_ids, key=sort_key)
        if items[item_id].get("public") is True
    ]

    return {
        "itemIds": published_ids,
        "categories": {
            PUBLIC_CATEGORY_LABELS[category_id]: categories.get(
                PUBLIC_CATEGORY_LABELS[category_id], []
            )
            for category_id in PUBLIC_CATEGORY_ORDER
        },
        "excludedItemIds": excluded_ids,
        "candidateItemIds": sorted(public_ids, key=sort_key),
        "unwrappedCaseIds": sorted(
            item_id for item_id in unwrapped_transport_ids if is_case_item(items[item_id])
        ),
        "unwrappedTransportIds": sorted(unwrapped_transport_ids),
        "aliases": {
            item_id: canonical_id
            for item_id, canonical_id in sorted(aliases.items())
            if item_id != canonical_id and canonical_id in set(published_ids)
        },
    }


def render_public_sprites(
    game_source: Path,
    output_dir: Path,
    items: dict[str, Any],
    public_item_ids: list[str],
    reagent_colors: dict[str, str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected: set[str] = set()
    failures: list[str] = []
    solution_images: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for item_id in public_item_ids:
        item = items[item_id]
        summary = item.get("sprite")
        if not isinstance(summary, dict):
            failures.append(f"{item_id}: no Sprite component")
            continue
        filename = f"{item_id}.png"
        expected.add(filename)
        try:
            preview = render_sprite_preview(game_source, summary, reagent_colors)
            preview.save(output_dir / filename, format="PNG", optimize=True)
            item["image"] = f"equipment-sprites/{filename}"
            solution = summary.get("solutionPreview")
            if isinstance(solution, dict) and solution.get("reagents"):
                signature = json.dumps(
                    solution.get("reagents"), ensure_ascii=False, sort_keys=True
                )
                digest = hashlib.sha256(preview.tobytes()).hexdigest()
                solution_images[digest].append((item_id, signature))
        except Exception as error:  # Collect every missing/broken sprite in one run.
            failures.append(f"{item_id}: {error}")

    for path in output_dir.glob("*.png"):
        if path.name not in expected:
            path.unlink()
    if failures:
        raise RuntimeError("Unable to render equipment sprites:\n" + "\n".join(failures))
    ambiguous = [
        sorted(item_id for item_id, _ in entries)
        for entries in solution_images.values()
        if len({signature for _, signature in entries}) > 1
    ]
    if ambiguous:
        raise RuntimeError(
            "Different filled solutions rendered as identical sprites:\n"
            + "\n".join(", ".join(group) for group in ambiguous)
        )


def should_publish_component(component_type: str) -> bool:
    if component_type in NON_MECHANICAL_COMPONENTS:
        return False
    if component_type.endswith("Visuals") or component_type.endswith("Visualizer"):
        return False
    if component_type in PUBLIC_PROPERTY_COMPONENTS:
        return True
    return component_type.startswith(
        (
            "Attachable",
            "Gun",
            "RMCProjectile",
            "RMCWeapon",
        )
    )


def build_card(
    prototype_id: str,
    resolved: dict[str, Any],
    localizer: Localizer,
    availability: list[dict[str, Any]],
    reachable_vendors: set[str],
    source_hints: set[str],
) -> dict[str, Any]:
    components = resolved["components"]
    raw_tags = components.get("Tag", {}).get("tags", [])
    tags = {item for item in raw_tags if isinstance(item, str)} if isinstance(raw_tags, list) else set()
    fields = resolved["fields"]

    properties = {
        component_type: copy.deepcopy(component)
        for component_type, component in sorted(components.items())
        if should_publish_component(component_type)
    }

    base_name = capitalize_first(
        localizer.entity_text(prototype_id, None, fields.get("name"))
    )
    suffix = localizer.entity_text(
        prototype_id, "suffix", fields.get("suffix")
    )
    card: dict[str, Any] = {
        "id": prototype_id,
        "name": catalog_display_name(base_name, suffix),
        "baseName": base_name,
        "description": localizer.entity_text(
            prototype_id, "desc", fields.get("description")
        ),
        "suffix": suffix,
        "origin": resolved["origin"],
        "sourceFile": resolved["sourceFile"],
        "parents": resolved["parents"],
        "abstract": resolved["abstract"],
        "types": infer_types(prototype_id, components, tags, source_hints),
        "sourceCategoryHints": sorted(source_hints),
        "tags": sorted(tags),
        "componentTypes": sorted(components),
        "equipmentSlots": sorted(equipment_slots(components)),
        "properties": properties,
        "availability": availability,
        "directlyVended": bool(availability),
        "reachableFromVendors": sorted(reachable_vendors),
    }
    sprite = sprite_summary(components)
    if sprite:
        card["sprite"] = sprite
    return card


def slot_label(slot: Any) -> str:
    raw = str(slot or "")
    if raw in SLOT_LABELS:
        return SLOT_LABELS[raw]
    folded = raw.casefold()
    if "barrel" in folded or "muzzle" in folded:
        return "Дуло"
    if "rail" in folded or "optic" in folded or "sight" in folded:
        return "Верхняя планка"
    if "stock" in folded:
        return "Приклад"
    if "under" in folded:
        return "Подствольный слот"
    return raw


def populate_compatibility_summaries(
    items: dict[str, Any],
    relations: list[dict[str, Any]],
    public_item_ids: set[str],
    aliases: dict[str, str],
) -> None:
    attachment_slots: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    attachment_weapons: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    magazine_slots: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    magazine_weapons: dict[str, set[str]] = defaultdict(set)
    installed: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    loaded: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def canonical(item_id: str) -> str:
        return aliases.get(item_id, item_id)

    for relation in relations:
        raw_source = str(relation.get("from", ""))
        raw_target = str(relation.get("to", ""))
        source = canonical(raw_source)
        target = canonical(raw_target)
        relation_type = relation.get("type")
        canonical_relation = dict(relation)
        canonical_relation["from"] = source
        canonical_relation["to"] = target
        outgoing[source].append(canonical_relation)
        raw_slot = str(relation.get("slot", ""))
        if (
            relation_type == "compatibleAttachment"
            and source in public_item_ids
            and target in public_item_ids
        ):
            attachment_slots[source][raw_slot].add(target)
            attachment_weapons[target][raw_slot].add(source)
        elif (
            relation_type == "compatibleMagazine"
            and source in public_item_ids
            and target in public_item_ids
        ):
            magazine_slots[source][raw_slot].add(target)
            magazine_weapons[target].add(source)
        elif relation_type == "installedAttachment":
            installed[source][raw_slot].add(target)
        elif relation_type == "loadedWith":
            loaded[source][raw_slot].add(target)

    for weapon_id, slots in attachment_slots.items():
        items[weapon_id]["attachmentSlots"] = [
            {
                "id": raw_slot,
                "name": slot_label(raw_slot),
                "compatibleItemIds": sorted(attachment_ids),
                "installedItemIds": sorted(installed[weapon_id].get(raw_slot, set())),
            }
            for raw_slot, attachment_ids in sorted(slots.items())
        ]
    for attachment_id, slots in attachment_weapons.items():
        items[attachment_id]["attachableTo"] = [
            {
                "slotId": raw_slot,
                "slotName": slot_label(raw_slot),
                "weaponIds": sorted(weapon_ids),
            }
            for raw_slot, weapon_ids in sorted(slots.items())
        ]
    for weapon_id, slots in magazine_slots.items():
        items[weapon_id]["magazineSlots"] = [
            {
                "id": raw_slot,
                "name": "Магазин" if "magazine" in raw_slot.casefold() else raw_slot,
                "compatibleItemIds": sorted(magazine_ids),
                "loadedItemIds": sorted(loaded[weapon_id].get(raw_slot, set())),
            }
            for raw_slot, magazine_ids in sorted(slots.items())
        ]
    for magazine_id, weapon_ids in magazine_weapons.items():
        items[magazine_id]["compatibleWeaponIds"] = sorted(weapon_ids)

    # Materialize the magazine -> cartridge -> projectile path so a future
    # damage/falloff calculator does not have to rediscover the graph.
    for weapon_id in sorted(set(attachment_slots) | set(magazine_slots)):
        paths: list[dict[str, Any]] = []
        magazines = {
            magazine_id
            for values in magazine_slots.get(weapon_id, {}).values()
            for magazine_id in values
        }
        if not magazines:
            magazines = {
                str(relation["to"])
                for relation in outgoing.get(weapon_id, [])
                if relation.get("type") == "loadedWith"
                and "BallisticAmmoProvider"
                in items.get(str(relation.get("to")), {}).get("componentTypes", [])
                and "Gun"
                not in items.get(str(relation.get("to")), {}).get("componentTypes", [])
            }
        for magazine_id in sorted(magazines):
            cartridges = sorted(
                {
                    str(relation["to"])
                    for relation in outgoing.get(magazine_id, [])
                    if relation.get("type") == "loadedWith"
                }
            )
            projectiles = sorted(
                {
                    str(relation["to"])
                    for cartridge_id in cartridges
                    for relation in outgoing.get(cartridge_id, [])
                    if relation.get("type") == "fires"
                }
            )
            paths.append(
                {
                    "magazineId": magazine_id,
                    "cartridgeIds": cartridges,
                    "projectileIds": projectiles,
                }
            )
        if paths:
            items[weapon_id]["ammunitionPaths"] = paths


def populate_content_summaries(
    items: dict[str, Any],
    relations: list[dict[str, Any]],
    public_item_ids: set[str],
    aliases: dict[str, str],
) -> None:
    """Expose only the forward 'contains' view; never an incoming provenance view."""
    contents: dict[str, set[str]] = defaultdict(set)
    for relation in relations:
        if relation.get("type") not in PHYSICAL_CONTENT_RELATION_TYPES:
            continue
        source = aliases.get(str(relation.get("from", "")), str(relation.get("from", "")))
        target = aliases.get(str(relation.get("to", "")), str(relation.get("to", "")))
        if source in public_item_ids and target in public_item_ids and source != target:
            contents[source].add(target)
    for source, target_ids in contents.items():
        items[source]["containsItemIds"] = sorted(
            target_ids,
            key=lambda item_id: (items[item_id]["name"].casefold(), item_id),
        )


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
        if item.get("category") != PUBLIC_CATEGORY_LABELS["armor"]:
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
        if item.get("category") != PUBLIC_CATEGORY_LABELS["attachment"]:
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
            provider = magazine.get("properties", {}).get("BallisticAmmoProvider", {})
            entry: dict[str, Any] = {
                "magazineId": magazine_id,
                "magazineName": magazine.get("name", magazine_id),
                "cartridgeIds": list(path.get("cartridgeIds", [])),
            }
            if isinstance(provider, dict):
                capacity = number(provider.get("capacity"))
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
            capacity = number(provider.get("capacity"))
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


def build_catalog(
    prototypes: dict[str, EntityPrototype],
    config: dict[str, Any],
    localizer: Localizer,
    game_commit: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolver = PrototypeResolver(prototypes)
    required_vendor_ids = [entry["id"] for entry in config["vendors"]]
    discovery_prefixes = tuple(config.get("vendorDiscoveryPrefixes", []))
    discovered_vendor_ids = sorted(
        prototype_id
        for prototype_id in prototypes
        if discovery_prefixes
        and prototype_id.startswith(discovery_prefixes)
        and not prototypes[prototype_id].abstract
        and isinstance(
            resolver.resolve(prototype_id)["components"].get("CMAutomatedVendor"),
            dict,
        )
    )
    vendor_ids = list(dict.fromkeys([*required_vendor_ids, *discovered_vendor_ids]))
    cargo_catalog_ids = [entry["id"] for entry in config.get("cargoCatalogs", [])]
    source_ids = [*vendor_ids, *cargo_catalog_ids]
    vendors: dict[str, Any] = {}
    trade_entries: list[dict[str, Any]] = []
    availability_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reachable_vendors: dict[str, set[str]] = defaultdict(set)
    source_hints_by_item: dict[str, set[str]] = defaultdict(set)
    transport_container_ids: set[str] = set()
    item_ids: set[str] = set()
    queue: deque[str] = deque()

    for vendor_id in vendor_ids:
        vendor = resolver.resolve(vendor_id)
        component = vendor["components"].get("CMAutomatedVendor")
        if not isinstance(component, dict):
            raise RuntimeError(f"Vendor {vendor_id} has no CMAutomatedVendor")
        sections = component.get("sections")
        if not isinstance(sections, list) or not sections:
            raise RuntimeError(f"Vendor {vendor_id} has no sections")

        vendor_sections: list[dict[str, Any]] = []
        for section_index, raw_section in enumerate(sections):
            if not isinstance(raw_section, dict):
                continue
            raw_entries = raw_section.get("entries")
            if not isinstance(raw_entries, list):
                continue
            section_name = raw_section.get("name")
            if not isinstance(section_name, str):
                section_name = f"Section {section_index + 1}"
            section_key = f"{vendor_id}:{section_index}"
            section_trade_keys: list[str] = []
            category_hint = source_category_hint(section_name)

            for entry_index, raw_entry in enumerate(raw_entries):
                if not isinstance(raw_entry, dict):
                    continue
                item_id = raw_entry.get("id")
                if not isinstance(item_id, str):
                    raise RuntimeError(
                        f"Vendor entry without id: {vendor_id}/{section_name}/{entry_index}"
                    )
                if item_id not in prototypes:
                    raise RuntimeError(
                        f"Vendor {vendor_id} references unknown item {item_id}"
                    )
                trade_key = f"{vendor_id}:{section_index}:{entry_index}"
                item = resolver.resolve(item_id)
                display_name = raw_entry.get("name")
                if not isinstance(display_name, str):
                    display_name = localizer.entity_text(
                        item_id, None, item["fields"].get("name")
                    )

                trade: dict[str, Any] = {
                    "key": trade_key,
                    "vendorId": vendor_id,
                    "sectionKey": section_key,
                    "sectionName": section_name,
                    "position": entry_index,
                    "itemId": item_id,
                    "name": display_name,
                    "amount": raw_entry.get("amount"),
                    "spawn": raw_entry.get("spawn", 1),
                }
                stock_item = raw_entry.get("box")
                if isinstance(stock_item, str):
                    if stock_item not in prototypes:
                        raise RuntimeError(
                            f"Trade {trade_key} references unknown stock item {stock_item}"
                        )
                    trade["stock"] = {
                        "itemId": stock_item,
                        "amount": raw_entry.get("boxAmount"),
                        "slots": raw_entry.get("boxSlots"),
                    }
                for key in (
                    "points",
                    "recommended",
                    "multiplier",
                    "max",
                    "linkedEntries",
                ):
                    if key in raw_entry:
                        trade[key] = copy.deepcopy(raw_entry[key])

                trade_entries.append(trade)
                section_trade_keys.append(trade_key)
                availability = {
                    "vendorId": vendor_id,
                    "sectionKey": section_key,
                    "sectionName": section_name,
                    "tradeKey": trade_key,
                }
                availability_by_item[item_id].append(availability)
                if vendor_id not in reachable_vendors[item_id]:
                    reachable_vendors[item_id].add(vendor_id)
                if category_hint:
                    source_hints_by_item[item_id].add(category_hint)
                if item_id not in item_ids:
                    item_ids.add(item_id)
                    queue.append(item_id)
                if isinstance(stock_item, str):
                    availability_by_item[stock_item].append(
                        {
                            "vendorId": vendor_id,
                            "sectionKey": section_key,
                            "sectionName": section_name,
                            "tradeKey": trade_key,
                            "stockForItemId": item_id,
                        }
                    )
                    reachable_vendors[stock_item].add(vendor_id)
                    if category_hint:
                        source_hints_by_item[stock_item].add(category_hint)
                    if stock_item not in item_ids:
                        item_ids.add(stock_item)
                        queue.append(stock_item)

            vendor_sections.append(
                {
                    "key": section_key,
                    "name": section_name,
                    "position": section_index,
                    "hasBoxes": bool(raw_section.get("hasBoxes", False)),
                    "tradeKeys": section_trade_keys,
                }
            )

        vendors[vendor_id] = {
            "id": vendor_id,
            "name": localizer.entity_text(
                vendor_id, None, vendor["fields"].get("name")
            ),
            "description": localizer.entity_text(
                vendor_id, "desc", vendor["fields"].get("description")
            ),
            "sourceFile": vendor["sourceFile"],
            "sections": vendor_sections,
        }

    for catalog_id in cargo_catalog_ids:
        catalog_source = resolver.resolve(catalog_id)
        component = catalog_source["components"].get("RequisitionsComputer")
        if not isinstance(component, dict):
            raise RuntimeError(
                f"Cargo catalog {catalog_id} has no RequisitionsComputer"
            )
        categories = component.get("categories")
        if not isinstance(categories, list) or not categories:
            raise RuntimeError(f"Cargo catalog {catalog_id} has no categories")

        catalog_sections: list[dict[str, Any]] = []
        for section_index, raw_section in enumerate(categories):
            if not isinstance(raw_section, dict):
                continue
            section_name = raw_section.get("name")
            if not isinstance(section_name, str):
                section_name = f"Section {section_index + 1}"
            raw_entries = raw_section.get("entries")
            if not isinstance(raw_entries, list):
                continue
            section_key = f"{catalog_id}:cargo:{section_index}"
            section_trade_keys: list[str] = []
            category_hint = source_category_hint(section_name)

            for entry_index, raw_entry in enumerate(raw_entries):
                if not isinstance(raw_entry, dict):
                    continue
                payload_ids: list[tuple[str, bool]] = []
                crate_id = raw_entry.get("crate")
                if isinstance(crate_id, str):
                    payload_ids.append((crate_id, True))
                    transport_container_ids.add(crate_id)
                extras = raw_entry.get("entities")
                if isinstance(extras, list):
                    payload_ids.extend(
                        (item_id, False)
                        for item_id in extras
                        if isinstance(item_id, str)
                    )

                for payload_index, (item_id, is_transport) in enumerate(payload_ids):
                    if item_id not in prototypes:
                        raise RuntimeError(
                            f"Cargo catalog {catalog_id} references unknown item {item_id}"
                        )
                    kind = "crate" if is_transport else f"entity{payload_index}"
                    trade_key = (
                        f"{catalog_id}:cargo:{section_index}:{entry_index}:{kind}"
                    )
                    item = resolver.resolve(item_id)
                    trade: dict[str, Any] = {
                        "key": trade_key,
                        "vendorId": catalog_id,
                        "sourceType": "cargo",
                        "sectionKey": section_key,
                        "sectionName": section_name,
                        "position": entry_index,
                        "itemId": item_id,
                        "name": localizer.entity_text(
                            item_id, None, item["fields"].get("name")
                        ),
                        "transportContainer": is_transport,
                    }
                    if "cost" in raw_entry:
                        trade["cost"] = copy.deepcopy(raw_entry["cost"])
                    trade_entries.append(trade)
                    section_trade_keys.append(trade_key)
                    availability_by_item[item_id].append(
                        {
                            "vendorId": catalog_id,
                            "sourceType": "cargo",
                            "sectionKey": section_key,
                            "sectionName": section_name,
                            "tradeKey": trade_key,
                        }
                    )
                    reachable_vendors[item_id].add(catalog_id)
                    if category_hint:
                        source_hints_by_item[item_id].add(category_hint)
                    if item_id not in item_ids:
                        item_ids.add(item_id)
                        queue.append(item_id)

            catalog_sections.append(
                {
                    "key": section_key,
                    "name": section_name,
                    "position": section_index,
                    "tradeKeys": section_trade_keys,
                }
            )

        vendors[catalog_id] = {
            "id": catalog_id,
            "type": "cargo",
            "name": localizer.entity_text(
                catalog_id, None, catalog_source["fields"].get("name")
            ),
            "description": localizer.entity_text(
                catalog_id, "desc", catalog_source["fields"].get("description")
            ),
            "sourceFile": catalog_source["sourceFile"],
            "sections": catalog_sections,
        }

    relations: list[dict[str, Any]] = []
    relation_keys: set[str] = set()
    outgoing: dict[str, list[str]] = defaultdict(list)

    while queue:
        item_id = queue.popleft()
        resolved = resolver.resolve(item_id)
        for relation in content_relations(item_id, resolved):
            target = relation["to"]
            if target not in prototypes:
                raise RuntimeError(
                    f"{item_id} has {relation['type']} relation to unknown entity {target}"
                )
            if add_relation(relations, relation_keys, relation):
                outgoing[item_id].append(target)
            changed = False
            for vendor_id in reachable_vendors[item_id]:
                if vendor_id not in reachable_vendors[target]:
                    reachable_vendors[target].add(vendor_id)
                    changed = True
            before_hints = len(source_hints_by_item[target])
            source_hints_by_item[target].update(source_hints_by_item[item_id])
            if len(source_hints_by_item[target]) != before_hints:
                changed = True
            if target not in item_ids:
                item_ids.add(target)
                queue.append(target)
            elif changed:
                queue.append(target)

    # Source propagation can revisit a node after its relations were added. The
    # relation set de-duplicates those visits while the vendor provenance flows.
    provenance_queue = deque(sorted(item_ids))
    while provenance_queue:
        source = provenance_queue.popleft()
        for target in outgoing.get(source, []):
            before = len(reachable_vendors[target])
            reachable_vendors[target].update(reachable_vendors[source])
            before_hints = len(source_hints_by_item[target])
            source_hints_by_item[target].update(source_hints_by_item[source])
            if (
                len(reachable_vendors[target]) != before
                or len(source_hints_by_item[target]) != before_hints
            ):
                provenance_queue.append(target)

    add_compatibility_relations(item_ids, resolver, relations, relation_keys)

    items: dict[str, Any] = {}
    for item_id in sorted(item_ids):
        items[item_id] = build_card(
            item_id,
            resolver.resolve(item_id),
            localizer,
            availability_by_item.get(item_id, []),
            reachable_vendors[item_id],
            source_hints_by_item[item_id],
        )

    relations.sort(
        key=lambda item: (
            item["from"],
            item["type"],
            item["to"],
            str(item.get("slot", "")),
            int(item.get("position", -1)),
        )
    )
    trade_entries.sort(key=lambda item: item["key"])

    public_catalog = build_public_catalog(
        trade_entries,
        items,
        relations,
        transport_container_ids,
        config.get("classification", {}),
    )
    populate_compatibility_summaries(
        items,
        relations,
        set(public_catalog["itemIds"]),
        public_catalog["aliases"],
    )
    populate_content_summaries(
        items,
        relations,
        set(public_catalog["itemIds"]),
        public_catalog["aliases"],
    )
    populate_weapon_statistics(
        items,
        relations,
        set(public_catalog["itemIds"]),
    )
    populate_armor_statistics(items, set(public_catalog["itemIds"]))
    populate_attachment_statistics(items, set(public_catalog["itemIds"]))

    source_counts = {
        "indexedEntityPrototypes": len(prototypes),
        "vendors": len(vendor_ids),
        "cargoCatalogs": len(cargo_catalog_ids),
        "sources": len(vendors),
        "sections": sum(len(vendor["sections"]) for vendor in vendors.values()),
        "tradeEntries": len(trade_entries),
        "directItemPrototypes": len(availability_by_item),
        "catalogItems": len(items),
        "publicItems": len(public_catalog["itemIds"]),
        "excludedItems": len(public_catalog["excludedItemIds"]),
        "relations": len(relations),
    }

    # The public catalog intentionally carries no vending/crate provenance and
    # no reverse containment graph. Those diagnostics live in the index only.
    provenance_keys = {
        "origin",
        "sourceFile",
        "parents",
        "abstract",
        "sourceCategoryHints",
        "availability",
        "directlyVended",
        "reachableFromVendors",
    }
    for item in items.values():
        for key in provenance_keys:
            item.pop(key, None)

    counts = {
        "catalogItems": len(items),
        "publicItems": len(public_catalog["itemIds"]),
        "excludedItems": len(public_catalog["excludedItemIds"]),
    }

    catalog = {
        "schemaVersion": 3,
        "gameCommit": game_commit,
        "source": "MetalSage/space-stories-cm14",
        "locale": "ru-RU",
        "items": items,
        "publicCatalog": public_catalog,
        "counts": counts,
    }

    index = {
        "schemaVersion": 3,
        "gameCommit": game_commit,
        "source": "MetalSage/space-stories-cm14",
        "configuredVendorIds": vendor_ids,
        "configuredCargoCatalogIds": cargo_catalog_ids,
        "configuredSourceIds": source_ids,
        "vendors": vendors,
        "tradeEntries": trade_entries,
        "relations": relations,
        "counts": {
            **source_counts,
            "catalogEntityPrototypes": len(item_ids),
            "resolvedEntityPrototypes": len(resolver.cache),
        },
        "entries": {
            prototype_id: {
                "parents": list(prototype.parents),
                "abstract": prototype.abstract,
                "origin": prototype.origin,
                "sourceFile": prototype.source_file,
            }
            for prototype_id, prototype in sorted(prototypes.items())
            if prototype_id in item_ids
        },
    }
    return index, catalog


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def build_review_section(catalog: dict[str, Any]) -> dict[str, Any]:
    items = catalog["items"]
    public_catalog = catalog["publicCatalog"]

    def entry(item_id: str) -> dict[str, Any]:
        item = items[item_id]
        classification = item.get("classification", {})
        return {
            "id": item_id,
            "name": item.get("name", item_id),
            "reason": classification.get("reason", ""),
            "signals": classification.get("signals", []),
        }

    return {
        "policy": "universal-functional-v3",
        "excluded": [
            entry(item_id) for item_id in public_catalog["excludedItemIds"]
        ],
    }


def print_previous_catalog_comparison(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> None:
    if not isinstance(previous, dict):
        print("Previous catalog comparison: unavailable")
        return
    previous_public = set(previous.get("publicCatalog", {}).get("itemIds", []))
    current_public = set(current["publicCatalog"]["itemIds"])
    current_excluded = set(current["publicCatalog"]["excludedItemIds"])
    previous_items = previous.get("items", {})
    current_items = current["items"]
    category_changes = sorted(
        item_id
        for item_id in previous_public & current_public
        if previous_items.get(item_id, {}).get("category")
        != current_items.get(item_id, {}).get("category")
    )
    print(f"New public items: {len(current_public - previous_public)}")
    print(f"Removed public items: {len(previous_public - current_public)}")
    print(
        "Previously public items now excluded: "
        f"{len(previous_public & current_excluded)}"
    )
    print(f"Public category changes: {len(category_changes)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the SSMC equipment catalog from live game sources"
    )
    parser.add_argument("--game-source", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--index-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sprites-output", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--locale", default="ru-RU")
    args = parser.parse_args()

    previous_catalog: dict[str, Any] | None = None
    if args.output.is_file():
        try:
            loaded_previous = json.loads(args.output.read_text(encoding="utf-8"))
            if isinstance(loaded_previous, dict):
                previous_catalog = loaded_previous
        except (OSError, json.JSONDecodeError):
            previous_catalog = None

    prototypes = read_entity_prototypes(args.game_source)
    reagent_colors = read_reagent_colors(args.game_source)
    config = read_config(args.config)
    locale_root = args.game_source / "Resources/Locale" / args.locale
    localizer = Localizer(read_fluent_messages(locale_root))
    index, catalog = build_catalog(
        prototypes=prototypes,
        config=config,
        localizer=localizer,
        game_commit=args.commit,
    )
    catalog["review"] = build_review_section(catalog)
    render_public_sprites(
        game_source=args.game_source,
        output_dir=args.sprites_output,
        items=catalog["items"],
        public_item_ids=catalog["publicCatalog"]["itemIds"],
        reagent_colors=reagent_colors,
    )
    write_json(args.index_output, index)
    write_json(args.output, catalog)
    print_previous_catalog_comparison(previous_catalog, catalog)

    counts = catalog["counts"]
    source_counts = index["counts"]
    print(f"Indexed entity prototypes: {source_counts['indexedEntityPrototypes']}")
    print(f"Vendor sections: {source_counts['sections']}")
    print(f"Trade entries: {source_counts['tradeEntries']}")
    print(f"Catalog items: {counts['catalogItems']}")
    print(f"Public equipment items: {counts['publicItems']}")
    print(f"Excluded non-equipment items: {counts['excludedItems']}")
    print(f"Internal relations: {source_counts['relations']}")


if __name__ == "__main__":
    main()
