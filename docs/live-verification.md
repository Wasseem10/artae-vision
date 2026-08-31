# Live semantic verification

Broad visual instructions are useful because they let an operator describe a job in
plain language. They are also probabilistic. Artae Vision therefore treats the first
semantic model result as a **proposal**, not as permission to alert or act.

## Decision path

1. The proposer evaluates overlapping chronological frame windows. Existing confidence,
   baseline, confirmation-window, and cooldown rules remove obvious noise at the edge.
2. Only a candidate that clears those checks is sent to a second model. The configured
   verifier must have a different model identifier from the proposer.
3. The control plane independently enforces model separation and the rule's minimum
   confidence. It does not trust an edge-supplied `confirmed` label by itself.
4. A high-confidence confirmation releases the event to scene memory, correlation,
   incidents, outbound deliveries, and guarded actions. A rejection is retained for
   audit but releases nothing.
5. Missing, failed, same-model, low-confidence, or contradictory verification becomes
   `pending` or `uncertain`. An operator must inspect the clip and record a reason before
   confirming or rejecting it.

Deterministic tracking jobs such as line crossing, counts, entry/exit, and dwell keep
their existing direct event path. They are not mislabeled as independently verified.

## Operator workspace

The Visual verification inbox separates three things:

- case/report-card selection with camera, job, time, and status;
- the uploaded evidence clip, visual window, and proposer/verifier confidence;
- the durable decision record and explicit operator Confirm or Reject controls.

Unverified semantic events are omitted from the normal event feed and never broadcast
as `event.created`. Evidence can still upload while a case is quarantined so the operator
has something real to inspect.

## Provider configuration

Automatic two-model verification is enabled only for Gemini in the current edge runtime:

```text
VIDEO_INTEL_OBSERVER_PROVIDER=gemini
VIDEO_INTEL_GEMINI_MODEL=gemini-3.5-flash-lite
VIDEO_INTEL_GEMINI_VERIFIER_MODEL=gemini-3.7-flash
```

Both calls consume provider quota. Dry-run and Qwen proposer jobs deliberately fall back
to operator review until a genuinely separate verifier is configured and benchmarked.
Provider failure never silently promotes a proposal.

## Accuracy boundary

Two-model agreement reduces unsupported alerts; it does not establish customer-scene
accuracy. Every job still needs representative positive and negative field clips through
the replay promotion gate. The verification inbox supplies a useful correction trail,
but this phase does not yet train a model from operator decisions.
