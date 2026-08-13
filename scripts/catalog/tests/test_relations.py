from scripts.catalog.relations import content_relations, relation_key


def test_storage_contents_preserve_probability_and_quantity():
    resolved = {
        "components": {
            "StorageFill": {
                "contents": [
                    {"id": "Item", "amount": 2, "maxAmount": 4, "prob": 0.5}
                ]
            }
        }
    }
    assert content_relations("Box", resolved) == [
        {
            "from": "Box",
            "to": "Item",
            "type": "contains",
            "position": 0,
            "quantity": 2,
            "maxQuantity": 4,
            "probability": 0.5,
        }
    ]


def test_relation_key_is_order_independent():
    assert relation_key({"from": "A", "to": "B", "type": "contains"}) == relation_key(
        {"type": "contains", "to": "B", "from": "A"}
    )
