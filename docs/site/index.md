---
hide:
  - toc
---

<div class="arras-hero" markdown="block">
<div class="arras-intro" markdown="block">
<p class="arras-kicker">Arras <span>·</span> Open source <span>·</span> @VERSION@</p>

# Explore the relationships in your data.

Arras brings UMF-defined records, relationships, and actions into a Graph Browser and an embeddable Python library.

<div class="arras-actions">
  <a class="md-button md-button--primary" href="demo/index.html">Open Graph Browser</a>
  <a class="md-button" href="quickstart/">Run Arras locally</a>
</div>

</div>

<figure class="arras-example">
  <figcaption>From the fictional software catalog</figcaption>
  <div class="arras-node">
    <span>Solution</span>
    <strong>Alert triage against runbook</strong>
  </div>
  <div class="arras-edge">addresses</div>
  <div class="arras-node">
    <span>Use case</span>
    <strong>Triage incoming alerts at volume</strong>
  </div>
  <a href="demo/index.html#/explore/catalog/Solution/alert-triage-playbook">Open this record in the demo</a>
</figure>

</div>

## See what a record connects to

The public demo opens a read-only software catalog. Filter by type, open a result, and follow a relationship to see how the records fit together. The catalog loads from static files in your browser.

[Follow the Graph Browser walkthrough](graph-browser.md)

<div class="grid cards" markdown>

-   **Describe a domain**

    Define entity types, relationships, and actions in a UMF module. The browser uses the module to label records and group their properties.

    [See the catalog module](https://github.com/DocumentDrivenDX/arras/tree/main/examples/catalog)

-   **Keep read context**

    In an embedded app, reads report which backend served them, its position, and the consistency level. A host can place records and replicas on different backends.

    [Read the architecture](architecture.md)

-   **Embed Arras in your app**

    Run the development host with sample data, then use the Python library and React UI in an application that supplies identity and backend configuration.

    [Start locally](quickstart.md)

</div>

[Release notes](changelog.md) · [Source on GitHub](https://github.com/DocumentDrivenDX/arras) · [Explore Novirhyza](https://documentdrivendx.github.io/novirhyza/)
