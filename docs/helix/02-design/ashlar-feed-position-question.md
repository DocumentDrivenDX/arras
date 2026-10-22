---
ddx:
  id: ashlar-feed-position-question
  type: design-note
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-10
  authoring:
    home: repo
  links:
    - id: ADR-013
      kind: informed_by
    - id: ADR-014
      kind: informed_by
    - id: CONTRACT-004
      kind: informed_by
---

# Question to Ashlar: answering "has this receipt reached the replica?"

Written to be handed to the Ashlar project as-is. It describes a generic need of a Python host that reads Ashlar's gold tables on Unity Catalog as the person, and names no host-specific concept. Source: Ashlar's PRD, FEAT-004, CONTRACT-001 and CONTRACT-002, and Truss's receipt-position proposal, read on 2026-10-10. Nothing was run.

## The need

The host writes through Truss and reads through Ashlar. After a write it holds an opaque receipt token. A later read must be able to say "include this write" (`at_least=token`), and the host must answer one question per token and backend: **is the write named by this token included in what this backend serves?**

The answer has four outcomes, and the host will not merge them:

| Outcome | Meaning |
|---------|---------|
| included | The write is in the published state this read sees. |
| not yet | The write was issued and is not yet published. The host may wait or read from Truss. |
| invalid | The token is malformed or was never issued. |
| not determinable | Ashlar cannot tell (unknown feed or epoch, no evidence, access denied). |

## What Ashlar already specifies

- Every publication exposes a progress vector of `{feed, epoch, position}` entries and the time it was recorded (CONTRACT-001, PUB-06). Positions from independent feeds stay distinct (PUB-07).
- A read takes `minimumProgress` and `waitMs` (at most 30,000). Behind the requested position it returns `not_ready/PROGRESS_BEHIND`; an unknown feed or a mismatched epoch returns `recovery_required/PROGRESS_INCOMPARABLE`; authorization precedes progress disclosure; there is no fallback to a service principal (CONTRACT-002).
- Unavailable freshness measurements stay unknown (PUB-09).

These map onto the four outcomes: `ok` for included, `PROGRESS_BEHIND` for not yet, `PROGRESS_INCOMPARABLE` for not determinable. The questions below are about the gaps between this and a Truss receipt.

## Questions

1. **What does a Truss receipt token resolve to in Ashlar's vocabulary?** Truss's token is opaque and commits to the source installation, source epoch and the complete committed transaction; it deliberately carries no numeric position that can be compared by hand, and an equal transaction number from another epoch is incomparable. Ashlar's progress is `{feed, epoch, position}` with an integer position. Someone must map one to the other. Which of these does Ashlar intend?
   - (a) Truss supplies an operation that turns a token into the feed progress it requires, and the host passes that as `minimumProgress`.
   - (b) Ashlar's published progress carries enough (complete-transaction coverage, source epoch) that Ashlar can answer for a token itself.
   - (c) Something else.
   Truss's proposal says a replica compares against its durably applied state in the same read snapshot, and that a delivered, assembled, claimed or acknowledged feed batch alone does not certify visibility.

2. **Is Ashlar's `position` a complete-transaction frontier?** A Truss group can span several feed members, and a group with no changes (all no-ops) has a receipt but no feed member. For "included" to be true, every member of the transaction must be published, and a no-op transaction's inclusion must follow from coverage. Does a published position mean every transaction up to it is complete, and does it cover no-op transactions?

3. **How is the epoch lineage handled across a restore or fork of the source?** Truss treats a restore or fork as a new epoch, and a token from the old epoch is incomparable with it unless an explicit lineage or seed proof exists. Ashlar returns `PROGRESS_INCOMPARABLE` for a mismatched epoch. Is there a defined route for the seed or lineage proof, or is the outcome always "not determinable"?

4. **Can the progress be read as the person, and without disclosure to those who may not read?** CONTRACT-002 says authorization precedes progress disclosure. The host needs the answer for the person whose receipt it is. Is the progress readable through the person's own Unity Catalog grants on the gold tables (one query as that person), or only through Ashlar's read operation? If a person may read a module's rows but not another feed's progress, what is the outcome?

5. **Can the host ask once and get a bound, without a polling loop in Ashlar?** `waitMs` allows waiting up to 30 s inside a read. The host would rather decide its own wait: ask whether the position is reached, get `not yet` at once, and retry. Is a zero-wait progress check allowed and cheap, and what does it cost on a SQL warehouse (the latency class matters, since the host classes Ashlar reads as batch and this would be called per `at_least` read)?

6. **What does a token that Ashlar's feed has never seen look like?** After Truss issues a token and before the feed has delivered anything for it, is "not yet" always correct, or can Ashlar know a token is invalid? The host maps "never issued" to invalid only when the backend proves it, so the safe default is "not determinable" rather than "not yet" when Ashlar cannot tell. Please say which Ashlar will give.

## What the host assumes meanwhile

The host's Ashlar adapter implements `reached` as above, with `PROGRESS_BEHIND` as "not yet" and `PROGRESS_INCOMPARABLE` or any missing evidence as "not determinable". It does not infer "included" from the publication time or from a position it computes itself. It treats the freshness it reports as the progress and the recorded time Ashlar publishes, and nothing else.

## Not asked here

Ashlar's query latency budgets (PRD: not set), its feed transport, and the Truss side of the mapping (see the Truss requirements note, R7) are separate.
