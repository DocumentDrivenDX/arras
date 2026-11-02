# D11 full-managed failed campaign and cleanup evidence

D11 used Arras 0.6.1 source commit `2d1bc7e34af7499d5f4f582d4ee41e0d772920cc` (tree `396f50b8ddc10bc8d3e16a5baf7f81055e17efc4`) with the public Truss 0.0.50 release. The canonical Arras wheel SHA-256 was `259e16c7d4c8f6c56d9930ee5f16e74c4ab6b2c8a3ecffdb7d8b306c77b60f18`. The original run lasted 980.656331541 seconds, from 2026-10-24 18:24:15 to 18:40:36 UTC, with the existing 60-second SQL operation limit and no VM. It finished **10 passed, 2 failed, 0 blocked of 12**. LB-SETTLEMENT and MP-05 failed with `genuine_transport_interruption_not_observed`. The full campaign was not accepted; partial passes do not satisfy the full 12-case gate.

The retained diagnostics report no matching validated fault-event group and no captured pre-fault exception. That does not establish that the raw event stream was empty, and the cause remains unknown. No fault attribution is made here.

Original cleanup passed. A fresh independent read-only audit passed with installed source unchanged: 33 native roles, 18 memberships, no new roles, 16 ordinary selected closures false, and three provider checks. The audited handback returned source and target custody, and the process census found the launched process groups absent. These results establish cleanup and custody only; they do not grant campaign acceptance.

The exact safe inner verifier and diagnostic receipts are retained. Other records are closed summaries bound to their original SHA-256 values; private paths, process identifiers, identities, and opaque resource identifiers are omitted from those summaries. Raw logs, credentials, provider identity details, and native catalogs are not included. The retention manifest records file hashes and the source receipt bindings.
