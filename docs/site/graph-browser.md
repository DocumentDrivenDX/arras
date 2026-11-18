<!-- helix:publish audience=user page=graph-browser kind=tutorial voice=onboarding budget=250 reviewed=2026-11-18/arras_reader_review/- -->
<!-- helix:source examples/catalog/README.md sha256:600a75a39fd42705 -->
<!-- helix:source examples/catalog/catalog.graph.json sha256:4a79c8b07b22f79c -->
<!-- helix:source ui/e2e-static/browse.spec.ts sha256:7d4dbcbb4c2546b7 -->
<!-- helix:source docs/helix/02-design/contracts/CONTRACT-012-static-read-only-profile.md sha256:43aa98bb5817b3df -->

# Explore a graph

Use the fictional software catalog to find a solution and see the use case it addresses.

1. [Open the Graph Browser demo](demo/index.html). The home page is called **Product catalog**.
2. Search for **runbook** and select **Solutions** under **Narrow by type**.
3. Open **Alert triage against runbook**. The detail page shows fields such as the delivery mode and summary.
4. Under **Addresses**, open **Triage incoming alerts at volume**. The use case shows links back to solutions under **Addressed by**. You can also follow those links from its neighbourhood diagram.

[Open the solution directly](demo/index.html#/explore/catalog/Solution/alert-triage-playbook)

## What the demo loads

The demo uses the [catalog UMF module and graph snapshot](https://github.com/DocumentDrivenDX/arras/tree/main/examples/catalog). The snapshot contains fictional products, use cases, solutions, and evaluation records. The static Graph Browser reads those files on the same origin and provides record browsing and search. The demo is read-only.

[Run the development host locally](quickstart.md) to try the operator console with sample data. See the [static read-only contract](https://github.com/DocumentDrivenDX/arras/blob/main/docs/helix/02-design/contracts/CONTRACT-012-static-read-only-profile.md) for how the two profiles differ.
