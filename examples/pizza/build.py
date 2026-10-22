# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build the Pizza example (the Protégé tutorial ontology) as a UMF module.

    uv run python examples/pizza/build.py          # write pizza.umf.json and seed.json
    uv run python examples/pizza/build.py --check  # fail if they have drifted from this

The pizza ontology is the standard OWL teaching example: named pizzas, their toppings and bases, and
a country of origin. It is here for what the catalog does not exercise: a many-to-many link
(`hasTopping`) that an Add action does not take, a title and summary whose properties appear in no
section (`name`, `description`: the case the header edit covers).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from ontology import main  # noqa: E402

S, N, D, B = "string", "integer", "decimal", "boolean"

SPEC = {
    "id": "pizza-example",
    "module": "pizza",
    "view": {
        "title": "Pizza",
        "description": "Named pizzas, their toppings and bases, and where they come from",
    },
    "types": {
        "Pizza": [
            ("code", S, True),
            ("name", S, True),
            ("description", S, False),
            ("price", D, False),
            ("vegetarian", B, False),
        ],
        "Topping": [
            ("code", S, True),
            ("name", S, True),
            ("category", S, False),
            ("spiciness", S, False),
        ],
        "PizzaBase": [("code", S, True), ("name", S, True)],
        "Country": [("code", S, True), ("name", S, True)],
    },
    "relationships": [
        ("hasTopping", "Pizza", "Topping", "toppingOf", False),
        ("hasBase", "Pizza", "PizzaBase", "baseOf", True),
        ("countryOfOrigin", "Pizza", "Country", "originOf", False),
    ],
    "mutable": ["hasTopping", "countryOfOrigin"],
    "retire": ["Pizza"],
    "records": {
        "Pizza": {
            "label": "Pizza",
            "icon": "star",
            "tone": "rose",
            "title": "{name}",
            "summary": "{description}",
            "sections": [{"label": "Menu", "properties": ["price", "vegetarian"]}],
            "search": ["name", "description"],
        },
        "Topping": {
            "label": "Topping",
            "icon": "circle",
            "tone": "green",
            "title": "{name}",
            "sections": [{"label": "Kind", "properties": ["category", "spiciness"]}],
            "search": ["name", "category"],
        },
        "PizzaBase": {
            "label": "Base",
            "icon": "circle",
            "tone": "amber",
            "title": "{name}",
            "sections": [],
            "search": ["name"],
        },
        "Country": {
            "label": "Country",
            "icon": "globe",
            "tone": "slate",
            "title": "{name}",
            "sections": [],
            "search": ["name"],
        },
    },
    "fields": {
        "Pizza.price": {"format": "number"},
        "Pizza.vegetarian": {"format": "boolean"},
        "Topping.spiciness": {"format": "badge", "tones": {"hot": "rose", "mild": "green"}},
    },
    "relationshipViews": {
        "hasTopping": {"label": "Toppings", "inverseLabel": "On pizzas", "order": 10},
        "hasBase": {"label": "Base", "inverseLabel": "Bases for", "order": 20},
        "countryOfOrigin": {
            "label": "Country of origin",
            "inverseLabel": "Pizzas from here",
            "order": 30,
        },
    },
    "seed": [
        ("AddCountry", {"code": "italy", "name": "Italy"}),
        ("AddPizzaBase", {"code": "thin", "name": "Thin and crispy"}),
        ("AddPizzaBase", {"code": "deep", "name": "Deep pan"}),
        (
            "AddTopping",
            {"code": "mozzarella", "name": "Mozzarella", "category": "cheese", "spiciness": "mild"},
        ),
        (
            "AddTopping",
            {"code": "tomato", "name": "Tomato", "category": "vegetable", "spiciness": "mild"},
        ),
        (
            "AddTopping",
            {"code": "jalapeno", "name": "Jalapeño", "category": "vegetable", "spiciness": "hot"},
        ),
        (
            "AddTopping",
            {"code": "pepperoni", "name": "Pepperoni", "category": "meat", "spiciness": "hot"},
        ),
        (
            "AddPizza",
            {
                "code": "margherita",
                "name": "Margherita",
                "description": "Tomato and mozzarella",
                "price": 9,
                "vegetarian": True,
                "hasBase": "thin",
            },
        ),
        (
            "AddPizza",
            {
                "code": "american-hot",
                "name": "American Hot",
                "description": "Pepperoni, jalapeño and mozzarella",
                "price": 10,
                "vegetarian": False,
                "hasBase": "deep",
            },
        ),
        ("LinkPizzaHasTopping", {"pizza": "margherita", "hasTopping": "mozzarella"}),
        ("LinkPizzaHasTopping", {"pizza": "margherita", "hasTopping": "tomato"}),
        ("LinkPizzaHasTopping", {"pizza": "american-hot", "hasTopping": "pepperoni"}),
        ("LinkPizzaHasTopping", {"pizza": "american-hot", "hasTopping": "jalapeno"}),
        ("LinkPizzaHasTopping", {"pizza": "american-hot", "hasTopping": "mozzarella"}),
        ("LinkPizzaCountryOfOrigin", {"pizza": "margherita", "countryOfOrigin": "italy"}),
    ],
}

if __name__ == "__main__":
    sys.exit(main(SPEC, Path(__file__).parent, sys.argv[1:]))
