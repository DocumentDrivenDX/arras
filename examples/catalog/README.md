# Catalog example

A small catalog module for trying Arras with a schema of your own, and the data to seed it: the
software tools an engineering organization has, is trialling or is considering, the work they are
for, and what an evaluation found.

```bash
uv run --extra devhost python -m arras.devhost --module examples/catalog/catalog.umf.json --seed examples/catalog/seed.json
```

**The data is invented.** The products, vendors and URLs are fictional. The coverage levels,
lifecycle statuses, caveats and the finding with its score are made up for the demonstration; none
of it is an evaluation result or a statement about how any real product performs.

| Type | What it is |
|------|------------|
| `UseCase` | A kind of work someone in the organization needs done. |
| `Solution` | One way of doing a use case, with how it is delivered (`deliveryMode`: `chat`, `handoff` or `app`) and, for an app or a handoff, where it opens (`launchUrl`). |
| `Product` | A tool the organization has, is trialling or is considering. |
| `CoverageAssertion` | How far a product covers a use case (`level`: `full`, `partial` or `adjacent`). It is a record of its own because a read returns a relationship's keys, not its properties. |
| `ProductVersion` | A version of a product. |
| `Finding` | Something an evaluation observed about a product, and where it is known, on which version. |

A solution `addresses` a use case and may be `providedBy` a product. A coverage assertion points
at its product (`ofProduct`) and its use case (`ofUseCase`). A product version is a `versionOf` its
product. A finding is `about` a product and may be `aboutVersion` one of its versions; it
`appliesTo` a use case it is evidence for, and is `adjacentTo` one it only bears on.

## How it is presented

The document declares an `arras.view` for the module, its six types, a few of their fields and
its relationships (CONTRACT-010): a label, icon and tone for each type; a title such as
`{name}[ ({code})]`; sections that group the properties; the properties a search matches, in rank
order; badges with a tone for `deliveryMode`, `availability` and the coverage `level`; and a label
and order for each relationship. Presentation only: it changes no type, field or action, and a
module with no view is shown with defaults derived from its types. The Graph Browser reads it
from the registered document.

## Changing the schema

`catalog.umf.json` is written by `build.py`, which holds the schema in a short form: a type is a
list of fields, a relationship is four names, and an action is built from the type it acts on.

```bash
uv run python examples/catalog/build.py          # write catalog.umf.json
uv run python examples/catalog/build.py --check  # fail if the file has drifted
```

Edit `build.py`, run it, and load the result: restart the dev host, or import the file in the
console's Schema area (pick a role that holds the schema grant, such as `schema author`, to see a
preview and apply it). A test fails if the file and `build.py` disagree. `seed.json` is data and is
edited directly.

## Iterating on the graph

Until a database holds the graph, git does. `catalog.graph.json` is the catalog's graph as the
interface's **Export graph** writes it: every entity and link, in a stable order, with nothing that
changes between runs, so a diff of the file is a diff of the graph. It is a known-good fixture: the
tests load it and read it like the seed.

```bash
# 1. load the graph
uv run --extra devhost python -m arras.devhost --module examples/catalog/catalog.umf.json \
    --records examples/catalog/catalog.graph.json
# 2. in the interface, as an operator (alice): unlock the pencil, edit properties and links
# 3. on the catalog's page choose Export graph; it saves catalog.graph.json
# 4. replace examples/catalog/catalog.graph.json with it, review the diff and commit
# 5. start the dev host again: the graph is what you committed
```

The dev host keeps its data in memory, so an edit is gone on restart until it has been exported and
committed. `--records` loads after `--seed`; a record that already exists is skipped, so the file
never overwrites. `seed.json` (action steps) is for authoring a graph from scratch; once a graph
file is the record, the file, not the seed, is the truth. The same file is what a database will
load.

## Changing the records

Every write is an action. Besides the actions that add records and link them:

- `Correct…` changes the details of a use case, a solution or a product. A detail that is not
  given is left as it is.
- A required field has an action of its own, because it can only be set from an input that is
  itself required: `Rename…`, `ChangeCoverageLevel`. A type with several required fields has one
  action for them, `UpdateSolution` (name and delivery together), which the Graph Browser offers as
  a popup form started from the current values.
- `UpdateFinding` changes a finding's statement, kind and status together: all three are required
  inputs, so none can change without the others. The Graph Browser offers it as a popup form.
- `CorrectCoverageAssertion` and `CorrectProductVersion` change the optional details of a coverage
  assertion and a version, and `RelabelProductVersion` its required label.
- Links that a record can gain or lose after it exists have an action each: `AddressUseCase` and
  `UnaddressUseCase`, `SetSolutionProvider` and `ClearSolutionProvider`, `SetFindingVersion` and
  `ClearFindingVersion`, `ApplyFindingTo` and `UnapplyFindingTo`, `RelateFindingTo` and
  `UnrelateFindingTo`. The links that make a record what it is (`ofProduct`, `ofUseCase`,
  `versionOf`, `about`) are set when the record is added; to point one elsewhere, retire the record
  and add it again.
- `RetireSolution`, `RetireCoverage` and `RetireFinding` remove a record and its links. There is no
  retire for a use case, a product or a product version, since removing one would leave what points
  at it pointing at nothing.

In the console an action is filled in from a field for each input, with the keys a reference may
name offered as you type.

## Reading it

`read.py` holds the reads a page over the catalog needs, written against the query interface:

- `cards(session, audiences=())`: one card per solution, with how it is delivered, the use case it
  addresses and the product that provides it. A solution with an `audience` is left out unless
  that audience is passed.
- `use_case(session, code)`: one use case with its solutions, the products that cover it, and
  its findings, each with the product and version it is about.
- `products(session)`: every product with its status, its versions, the use cases it covers and
  at what level, and the solutions it provides.

All return plain dictionaries with JSON-friendly keys. They are a worked example for a host to
copy into its own catalog code; Arras itself knows nothing about catalogs.

## What the seed holds

30 use cases in seven areas, 12 products with their vendors, 33 coverage assertions, 9 solutions
(five chat workflows, two handoffs that give the user a ready prompt, one app, and one chat
workflow limited to an audience), 2 product versions and 1 finding linked to two use cases. The
use cases that have a solution also carry a `problem` sentence.
