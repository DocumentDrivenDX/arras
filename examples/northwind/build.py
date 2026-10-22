# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build the Northwind example (the classic trading-company sample database) as a UMF module.

    uv run python examples/northwind/build.py          # write northwind.umf.json and seed.json
    uv run python examples/northwind/build.py --check  # fail if they have drifted from this

A slice of Northwind, chosen for what the catalog example does not exercise: numeric, boolean and
money fields; a title built from two required properties (`{firstName} {lastName}`); a
self-relationship (`reportsTo`); an order line that is a record of its own; a key that appears in
a title. The data is the sample database's well-known rows, abridged.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from ontology import main  # noqa: E402

S, N, D, B = "string", "integer", "decimal", "boolean"

SPEC = {
    "id": "northwind-example",
    "module": "northwind",
    "view": {
        "title": "Northwind",
        "description": "Customers, orders, products and the people who sell them",
    },
    "types": {
        "Category": [("code", S, True), ("name", S, True), ("description", S, False)],
        "Supplier": [("code", S, True), ("companyName", S, True), ("country", S, False)],
        "Product": [
            ("code", S, True),
            ("name", S, True),
            ("quantityPerUnit", S, False),
            ("unitPrice", D, True),
            ("unitsInStock", N, False),
            ("discontinued", B, False),
        ],
        "Customer": [
            ("code", S, True),
            ("companyName", S, True),
            ("contactName", S, False),
            ("city", S, False),
            ("country", S, False),
        ],
        "Employee": [
            ("code", S, True),
            ("firstName", S, True),
            ("lastName", S, True),
            ("jobTitle", S, False),
        ],
        "Order": [
            ("code", S, True),
            ("orderDate", S, False),
            ("shipCountry", S, False),
            ("freight", D, False),
        ],
        "OrderLine": [("code", S, True), ("quantity", N, True), ("discount", D, False)],
    },
    # name, source, target, inverse, whether the source's Add action takes the target
    "relationships": [
        ("inCategory", "Product", "Category", "products", True),
        ("suppliedBy", "Product", "Supplier", "supplies", True),
        ("placedBy", "Order", "Customer", "orders", True),
        ("handledBy", "Order", "Employee", "handles", False),
        ("reportsTo", "Employee", "Employee", "directReports", False),
        ("ofOrder", "OrderLine", "Order", "lines", True),
        ("ofProduct", "OrderLine", "Product", "orderedIn", True),
    ],
    "mutable": ["handledBy", "reportsTo"],
    "retire": ["Order", "OrderLine"],
    "records": {
        "Category": {
            "label": "Category",
            "icon": "folder",
            "tone": "teal",
            "title": "{name}",
            "summary": "{description}",
            "sections": [],
            "search": ["name", "description"],
        },
        "Supplier": {
            "label": "Supplier",
            "icon": "box",
            "tone": "slate",
            "title": "{companyName}",
            "sections": [{"label": "Where", "properties": ["country"]}],
            "search": ["companyName", "country"],
        },
        "Product": {
            "label": "Product",
            "icon": "package",
            "tone": "blue",
            "title": "{name}",
            "summary": "{quantityPerUnit}",
            "sections": [
                {
                    "label": "Stock and price",
                    "properties": ["unitPrice", "unitsInStock", "discontinued"],
                }
            ],
            "search": ["name", "quantityPerUnit"],
        },
        "Customer": {
            "label": "Customer",
            "icon": "building",
            "tone": "violet",
            "title": "{companyName}[ ({code})]",
            "summary": "{contactName}",
            "sections": [{"label": "Where", "properties": ["city", "country"]}],
            "search": ["companyName", "contactName", "city", "country", "code"],
        },
        "Employee": {
            "label": "Employee",
            "icon": "user",
            "tone": "green",
            "title": "{firstName} {lastName}",
            "summary": "{jobTitle}",
            "sections": [],
            "search": ["firstName", "lastName", "jobTitle"],
        },
        "Order": {
            "label": "Order",
            "icon": "file-text",
            "tone": "amber",
            "title": "Order {code}",
            "sections": [
                {"label": "Shipping", "properties": ["orderDate", "shipCountry", "freight"]}
            ],
            "search": ["code", "shipCountry"],
        },
        "OrderLine": {
            "label": "Order line",
            "icon": "tag",
            "tone": "rose",
            "title": "{code}",
            "sections": [{"label": "Line", "properties": ["quantity", "discount"]}],
            "search": ["code"],
        },
    },
    "fields": {
        "Product.unitPrice": {"label": "Unit price", "format": "number"},
        "Product.discontinued": {"format": "boolean"},
        "Order.freight": {"format": "number"},
        "OrderLine.discount": {"format": "number", "hideWhenEmpty": True},
    },
    "relationshipViews": {
        "inCategory": {"label": "Category", "inverseLabel": "Products", "order": 10},
        "suppliedBy": {"label": "Supplier", "inverseLabel": "Supplies", "order": 20},
        "placedBy": {"label": "Customer", "inverseLabel": "Orders", "order": 10},
        "handledBy": {"label": "Handled by", "inverseLabel": "Handles", "order": 20},
        "reportsTo": {"label": "Reports to", "inverseLabel": "Direct reports", "order": 10},
        "ofOrder": {"label": "Order", "inverseLabel": "Lines", "order": 10},
        "ofProduct": {"label": "Product", "inverseLabel": "Ordered in", "order": 20},
    },
    "seed": [
        (
            "AddCategory",
            {
                "code": "beverages",
                "name": "Beverages",
                "description": "Soft drinks, coffees, teas, beers, and ales",
            },
        ),
        (
            "AddCategory",
            {
                "code": "condiments",
                "name": "Condiments",
                "description": "Sweet and savory sauces, relishes, spreads, and seasonings",
            },
        ),
        (
            "AddSupplier",
            {"code": "exotic-liquids", "companyName": "Exotic Liquids", "country": "UK"},
        ),
        (
            "AddSupplier",
            {
                "code": "grandma-kellys",
                "companyName": "Grandma Kelly's Homestead",
                "country": "USA",
            },
        ),
        (
            "AddProduct",
            {
                "code": "chai",
                "name": "Chai",
                "quantityPerUnit": "10 boxes x 20 bags",
                "unitPrice": 18,
                "unitsInStock": 39,
                "discontinued": False,
                "inCategory": "beverages",
                "suppliedBy": "exotic-liquids",
            },
        ),
        (
            "AddProduct",
            {
                "code": "chang",
                "name": "Chang",
                "quantityPerUnit": "24 - 12 oz bottles",
                "unitPrice": 19,
                "unitsInStock": 17,
                "discontinued": False,
                "inCategory": "beverages",
                "suppliedBy": "exotic-liquids",
            },
        ),
        (
            "AddProduct",
            {
                "code": "boysenberry-spread",
                "name": "Grandma's Boysenberry Spread",
                "quantityPerUnit": "12 - 8 oz jars",
                "unitPrice": 25,
                "unitsInStock": 120,
                "discontinued": False,
                "inCategory": "condiments",
                "suppliedBy": "grandma-kellys",
            },
        ),
        (
            "AddCustomer",
            {
                "code": "ALFKI",
                "companyName": "Alfreds Futterkiste",
                "contactName": "Maria Anders",
                "city": "Berlin",
                "country": "Germany",
            },
        ),
        (
            "AddCustomer",
            {
                "code": "ANATR",
                "companyName": "Ana Trujillo Emparedados y helados",
                "contactName": "Ana Trujillo",
                "city": "México D.F.",
                "country": "Mexico",
            },
        ),
        (
            "AddEmployee",
            {
                "code": "davolio",
                "firstName": "Nancy",
                "lastName": "Davolio",
                "jobTitle": "Sales Representative",
            },
        ),
        (
            "AddEmployee",
            {
                "code": "fuller",
                "firstName": "Andrew",
                "lastName": "Fuller",
                "jobTitle": "Vice President, Sales",
            },
        ),
        ("LinkEmployeeReportsTo", {"employee": "davolio", "reportsTo": "fuller"}),
        (
            "AddOrder",
            {
                "code": "10248",
                "orderDate": "1996-07-04",
                "shipCountry": "France",
                "freight": 32,
                "placedBy": "ALFKI",
            },
        ),
        ("LinkOrderHandledBy", {"order": "10248", "handledBy": "davolio"}),
        (
            "AddOrderLine",
            {
                "code": "10248-chai",
                "quantity": 12,
                "discount": 0,
                "ofOrder": "10248",
                "ofProduct": "chai",
            },
        ),
        (
            "AddOrderLine",
            {"code": "10248-chang", "quantity": 10, "ofOrder": "10248", "ofProduct": "chang"},
        ),
    ],
}

if __name__ == "__main__":
    sys.exit(main(SPEC, Path(__file__).parent, sys.argv[1:]))
