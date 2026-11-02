# D12 baseline-six diagnostic retention

This D12 run was a baseline-only diagnostic using the public Truss 0.0.50 release and Arras source commit `2d1bc7e34af7499d5f4f582d4ee41e0d772920cc`. Its six cases finished 5 passed, 1 failed, 0 blocked; LB-SETTLEMENT failed with `genuine_transport_interruption_not_observed`. The managed gate was not run, full twelve-case acceptance was not established, and no acceptance is claimed. The run lasted 623.288901375 seconds, from 2026-10-24 19:37:54 to 19:48:17 UTC, with the existing 60-second SQL operation limit and no VM. The canonical Arras wheel SHA-256 was `259e16c7d4c8f6c56d9930ee5f16e74c4ab6b2c8a3ecffdb7d8b306c77b60f18`.

The recorded commit-driver outcome took 51.759458 ms. No `transport_cut` row was recorded, and the projected driver exception field was empty. The worker cause remains unknown. The observer sentinel binding defect means an empty selected event group cannot be treated as proof that raw events were absent. D12 does not infer the cause of D11.

Cleanup, the fresh read-only native/provider audit, process census, and custody handback passed. The audit recorded 33 native roles, 18 memberships, no new roles, 16 ordinary selected closures false, and three provider checks. The full managed campaign was not run in this diagnostic.

This stage contains only closed, hash-bound projections. The two private fault-archive copies were independently checked against their recorded hashes, sizes, and row counts; only their SHA-256 commitments and bounded event summaries are retained here. No raw archives, private paths, process identifiers, target or identity material, credentials, or opaque resource identifiers are included. See `retention.json` for receipt and file hashes.
