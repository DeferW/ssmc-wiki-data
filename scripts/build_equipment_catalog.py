from __future__ import annotations

import argparse
import copy
import json
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
    "weapon-support": "Оружейные системы",
    "attachment": "Обвесы",
    "explosive": "Взрывчатка",
    "magazine-or-ammo-container": "Боеприпасы",
    "cartridge": "Боеприпасы",
    "vehicle-ammunition": "Боеприпасы для техники",
    "armor": "Броня и защита",
    "melee": "Ближний бой",
    "medical": "Медицина",
    "medicine": "Медикаменты",
    "engineering": "Инженерия",
    "material": "Материалы",
    "tool": "Инструменты",
    "clothing": "Одежда",
    "container": "Разгрузка и хранение",
    "electronics": "Электроника и связь",
    "lighting": "Освещение",
    "food": "Провизия",
    "training": "Инструкции и обучение",
    "reagent": "Реагенты и топливо",
    "office": "Канцелярия",
    "janitorial": "Хозяйственные принадлежности",
    "misc": "Снаряжение",
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
    if "RMCArmor" in components:
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


def sprite_summary(components: dict[str, Any]) -> dict[str, Any] | None:
    sprite = components.get("Sprite")
    if not isinstance(sprite, dict):
        return None
    result: dict[str, Any] = {}
    if isinstance(sprite.get("sprite"), str):
        result["sprite"] = sprite["sprite"]
    if isinstance(sprite.get("state"), str):
        result["state"] = sprite["state"]
    layers = sprite.get("layers")
    if isinstance(layers, list):
        clean_layers = [
            copy.deepcopy(layer) for layer in layers if isinstance(layer, dict)
        ]
        if clean_layers:
            apply_static_preview_states(components, clean_layers)
            result["layers"] = clean_layers
            if "state" not in result:
                for layer in clean_layers:
                    state = layer.get("state")
                    if isinstance(state, str):
                        result["state"] = state
                        break
    return result or None


def texture_path(game_source: Path, sprite_path: str) -> Path:
    normalized = sprite_path.replace("\\", "/").lstrip("/")
    if normalized.startswith("Textures/"):
        normalized = normalized[len("Textures/") :]
    return game_source / "Resources/Textures" / normalized


def first_rsi_state(meta: dict[str, Any]) -> str | None:
    states = meta.get("states")
    if not isinstance(states, list):
        return None
    for state in states:
        if isinstance(state, dict) and isinstance(state.get("name"), str):
            return state["name"]
    return None


def load_sprite_frame(
    game_source: Path,
    sprite_path: str,
    state: str | None,
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

    selected_state = state or first_rsi_state(meta)
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


def render_sprite_preview(
    game_source: Path,
    summary: dict[str, Any],
) -> Image.Image:
    base_sprite = summary.get("sprite")
    layers = summary.get("layers")
    render_layers: list[dict[str, Any]] = []

    if isinstance(layers, list):
        for layer in layers:
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


def public_category(item: dict[str, Any]) -> str:
    types = item.get("types", [])
    if not isinstance(types, list):
        return "Прочее"
    for item_type in (
        "attachment",
        "weapon",
        "weapon-support",
        "melee",
        "explosive",
        "vehicle-ammunition",
        "magazine-or-ammo-container",
        "cartridge",
        "armor",
        "container",
        "medicine",
        "medical",
        "tool",
        "engineering",
        "electronics",
        "lighting",
        "food",
        "clothing",
        "material",
        "training",
        "reagent",
        "office",
        "janitorial",
        "misc",
    ):
        if item_type in types:
            return PUBLIC_CATEGORY_LABELS[item_type]
    return "Прочее"


def is_case_item(item: dict[str, Any]) -> bool:
    name = str(item.get("name", "")).casefold()
    prototype_id = str(item.get("id", ""))
    component_types = set(item.get("componentTypes", []))
    return (
        "StorageFill" in component_types
        and ("кейс" in name or "case" in prototype_id.casefold())
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
    if is_case_item(item):
        return True
    return item_id in generated_wrapper_ids


def build_public_catalog(
    trade_entries: list[dict[str, Any]],
    items: dict[str, Any],
    relations: list[dict[str, Any]],
    transport_container_ids: set[str],
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

    public_candidates: set[str] = set()
    queue = deque(
        entry["itemId"]
        for entry in trade_entries
        if isinstance(entry.get("itemId"), str)
    )
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
    sort_key = lambda value: (items[value]["name"].casefold(), value)
    for item_id in sorted(public_ids, key=sort_key):
        category = public_category(items[item_id])
        items[item_id]["category"] = category
        items[item_id]["public"] = True
        categories[category].append(item_id)

    return {
        "itemIds": sorted(public_ids, key=sort_key),
        "categories": dict(sorted(categories.items())),
        "unwrappedCaseIds": sorted(
            item_id for item_id in unwrapped_transport_ids if is_case_item(items[item_id])
        ),
        "unwrappedTransportIds": sorted(unwrapped_transport_ids),
        "aliases": {
            item_id: canonical_id
            for item_id, canonical_id in sorted(aliases.items())
            if item_id != canonical_id
        },
    }


def render_public_sprites(
    game_source: Path,
    output_dir: Path,
    items: dict[str, Any],
    public_item_ids: list[str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected: set[str] = set()
    failures: list[str] = []

    for item_id in public_item_ids:
        item = items[item_id]
        summary = item.get("sprite")
        if not isinstance(summary, dict):
            failures.append(f"{item_id}: no Sprite component")
            continue
        filename = f"{item_id}.png"
        expected.add(filename)
        try:
            preview = render_sprite_preview(game_source, summary)
            preview.save(output_dir / filename, format="PNG", optimize=True)
            item["image"] = f"equipment-sprites/{filename}"
        except Exception as error:  # Collect every missing/broken sprite in one run.
            failures.append(f"{item_id}: {error}")

    for path in output_dir.glob("*.png"):
        if path.name not in expected:
            path.unlink()
    if failures:
        raise RuntimeError("Unable to render equipment sprites:\n" + "\n".join(failures))


def should_publish_component(component_type: str) -> bool:
    # Keep every gameplay-bearing component. This deliberately prefers a
    # slightly larger stable JSON over silently dropping a newly introduced
    # weapon/armor/medical statistic that the website may need tomorrow.
    if component_type in NON_MECHANICAL_COMPONENTS:
        return False
    if component_type.endswith("Visuals") or component_type.endswith("Visualizer"):
        return False
    return True


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


def build_catalog(
    prototypes: dict[str, EntityPrototype],
    config: dict[str, Any],
    localizer: Localizer,
    game_commit: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolver = PrototypeResolver(prototypes)
    vendor_ids = [entry["id"] for entry in config["vendors"]]
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
    )
    populate_compatibility_summaries(
        items,
        relations,
        set(public_catalog["itemIds"]),
        public_catalog["aliases"],
    )

    counts = {
        "indexedEntityPrototypes": len(prototypes),
        "vendors": len(vendor_ids),
        "cargoCatalogs": len(cargo_catalog_ids),
        "sources": len(vendors),
        "sections": sum(len(vendor["sections"]) for vendor in vendors.values()),
        "tradeEntries": len(trade_entries),
        "directItemPrototypes": len(availability_by_item),
        "catalogItems": len(items),
        "publicItems": len(public_catalog["itemIds"]),
        "relations": len(relations),
    }

    catalog = {
        "schemaVersion": 1,
        "gameCommit": game_commit,
        "source": "MetalSage/space-stories-cm14",
        "locale": "ru-RU",
        "configuredVendorIds": vendor_ids,
        "configuredCargoCatalogIds": cargo_catalog_ids,
        "configuredSourceIds": source_ids,
        "vendors": vendors,
        "tradeEntries": trade_entries,
        "items": items,
        "publicCatalog": public_catalog,
        "relations": relations,
        "counts": counts,
    }

    index = {
        "schemaVersion": 1,
        "gameCommit": game_commit,
        "source": "MetalSage/space-stories-cm14",
        "counts": {
            "indexedEntityPrototypes": len(prototypes),
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

    prototypes = read_entity_prototypes(args.game_source)
    config = read_config(args.config)
    locale_root = args.game_source / "Resources/Locale" / args.locale
    localizer = Localizer(read_fluent_messages(locale_root))
    index, catalog = build_catalog(
        prototypes=prototypes,
        config=config,
        localizer=localizer,
        game_commit=args.commit,
    )
    render_public_sprites(
        game_source=args.game_source,
        output_dir=args.sprites_output,
        items=catalog["items"],
        public_item_ids=catalog["publicCatalog"]["itemIds"],
    )
    write_json(args.index_output, index)
    write_json(args.output, catalog)

    counts = catalog["counts"]
    print(f"Indexed entity prototypes: {counts['indexedEntityPrototypes']}")
    print(f"Vendor sections: {counts['sections']}")
    print(f"Trade entries: {counts['tradeEntries']}")
    print(f"Catalog items: {counts['catalogItems']}")
    print(f"Public equipment items: {counts['publicItems']}")
    print(f"Relations: {counts['relations']}")


if __name__ == "__main__":
    main()
