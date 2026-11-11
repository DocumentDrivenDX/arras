# Architecture

Arras is a Python 3.11 library embedded by a host application. Any number of named backends sit behind it,
each a reader (serves graph reads), a provider (applies actions) or both. The host's placement says, per
module, which backend is the record store, which are replicas and which provider applies each action.

Surfaces: a read-only GraphQL console, an operator surface for validating and invoking declared actions and
reading the audit trail, a schema-administration surface, an MCP stdio server for agents, and a React UI
(operator console and Graph Browser) carried in the wheel and as an npm package.

The design documents live in the repository:

- [PRD](https://github.com/DocumentDrivenDX/arras/blob/main/docs/helix/01-frame/prd.md)
- [Architecture](https://github.com/DocumentDrivenDX/arras/blob/main/docs/helix/02-design/architecture.md)
- [Contracts](https://github.com/DocumentDrivenDX/arras/tree/main/docs/helix/02-design/contracts)
- [Decision records](https://github.com/DocumentDrivenDX/arras/tree/main/docs/helix/02-design/adr)
- [Glossary](https://github.com/DocumentDrivenDX/arras/blob/main/docs/helix/glossary.md)
