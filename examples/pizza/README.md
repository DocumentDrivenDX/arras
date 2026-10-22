# Pizza example

The Protégé tutorial ontology (named pizzas, toppings, bases, country of origin) as a third module
for testing. It exercises:

- a many-to-many link an Add action does not take (`Pizza hasTopping Topping`);
- a title and summary whose properties appear in no section (`name`, `description`), the case the
  header's edit pencils cover;
- every property but the key has an action that edits it (a test holds all three examples to this).

```bash
uv run --extra devhost python -m arras.devhost --module examples/pizza/pizza.umf.json --seed examples/pizza/seed.json
```

Files are written by `build.py` (spec at its top, shared generator `examples/ontology.py`);
`build.py --check` fails if they have drifted. The data is invented. See the Northwind README for
serving several examples together with `--also`.
