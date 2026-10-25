# Lakebase qualification inputs

These files are inert examples, not an authorization or a runnable target. Replace
them only from the separately approved Truss-owner handoff. Never commit a service
hostname, resource identifier, credential reference, token, password, certificate,
or private target receipt here.

The `target.example.json` and `authorization.example.json` contain deliberate
placeholders and are rejected by the verifier. The fixture below raises a fixed
prerequisite error. It has no provider endpoint and cannot create a connection.
Synthetic tests exercise admission and refusal behavior only; they do not qualify
Lakebase or any managed PostgreSQL service.

The current 0.6.1 candidate names public Truss 0.0.50 in
`target.example.json`. This example remains inert: changing its version pin or
placeholders does not provision a target or qualify the selected wheel.
