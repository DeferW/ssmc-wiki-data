from __future__ import annotations

from typing import Any, cast

from scripts.common.prototypes import EntityPrototype, PrototypeResolver
from scripts.maps.items import collect_linked_item_ids


class StubResolver:
    def __init__(self, components: dict[str, dict[str, Any]]) -> None:
        self.components = components

    def resolve(self, prototype_id: str) -> dict[str, Any]:
        return {"components": self.components[prototype_id]}


def test_collect_linked_item_ids_follows_ammunition_and_installed_attachments() -> None:
    components = {
        "Weapon": {
            "ItemSlots": {"slots": {"gun_magazine": {"startingItem": "Magazine"}}},
            "AttachableHolder": {
                "slots": {"barrel": {"startingAttachable": "Suppressor"}}
            },
        },
        "Magazine": {"BallisticAmmoProvider": {"proto": "Cartridge", "capacity": 12}},
        "Cartridge": {"CartridgeAmmo": {"proto": "Projectile"}},
        "Projectile": {},
        "Suppressor": {},
        "Unrelated": {},
    }
    prototypes = cast(dict[str, EntityPrototype], {item_id: object() for item_id in components})
    resolver = cast(PrototypeResolver, StubResolver(components))

    assert collect_linked_item_ids({"Weapon"}, prototypes, resolver) == {
        "Weapon",
        "Magazine",
        "Cartridge",
        "Projectile",
        "Suppressor",
    }
