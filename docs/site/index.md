# Arras @VERSION@

Arras is an open-source interface to an ontology. Types and actions are defined in UMF; every read states
its freshness; a backend contract lets one module span a record store and its replicas. It is a Python
library that a host application embeds, and it ships a React operator console and Graph Browser.

- **UMF types and actions.** A module is a UMF document: entity types, relationships and the actions that
  change them.
- **Reads that state their freshness.** Every answer names the backend that served it and its position.
- **A backend contract.** Arras ships a Truss adapter (PostgreSQL) and an in-memory adapter; the Ashlar
  adapter is experimental and not CI-tested.
- **Access is the backends' own.** Every call runs as the person who made it.

Status: beta (`0.x`). Release @VERSION@. [Try the static Graph Browser demo](demo/index.html) over the
bundled catalog example, or follow the [quickstart](quickstart.md).

Source and issues: [github.com/DocumentDrivenDX/arras](https://github.com/DocumentDrivenDX/arras).
