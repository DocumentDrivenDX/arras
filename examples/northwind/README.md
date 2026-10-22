# Northwind example

A slice of Northwind, the classic trading-company sample database from Microsoft's sample-database collection, as a second module for testing
Arras against a schema that is not the catalog. It exists to exercise what the catalog does not:

- numeric (`decimal`, `integer`) and boolean fields;
- a title built from two required properties (`{firstName} {lastName}`) that only change together: one `UpdateEmployee` action, so a form, with one header pencil;
- a self-relationship (`Employee reportsTo Employee`);
- an order line that is a record of its own, linked to an order and a product;
- every property but the key has an action that edits it (a test holds all three examples to this).

```bash
uv run --extra devhost python -m arras.devhost --module examples/northwind/northwind.umf.json --seed examples/northwind/seed.json
```

**The data is the sample database's well-known rows, abridged.** Seed decimals are whole numbers
because a seed file carries JSON numbers, which a decimal input does not accept as fractions.

`northwind.umf.json` and `seed.json` are written by `build.py` from the spec at its top
(`examples/ontology.py` is the shared generator); `build.py --check` fails if they have drifted.
To serve all three examples at once, give the others with `--also`:

```bash
uv run --extra devhost python -m arras.devhost --module examples/catalog/catalog.umf.json \
  --seed examples/catalog/seed.json \
  --also examples/northwind/northwind.umf.json:examples/northwind/seed.json \
  --also examples/pizza/pizza.umf.json:examples/pizza/seed.json
```

The interface then opens on a module chooser.
