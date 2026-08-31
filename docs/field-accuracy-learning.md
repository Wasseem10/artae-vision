# Closed-loop field accuracy

Offline replay proves that a job can pass on known clips. Live field accuracy answers a
different question: is this exact camera, visual instruction, proposer/verifier pair,
and operating environment performing well enough today to release alerts automatically?

## Human-grounded outcomes

Every operator decision on a quarantined verification case creates one durable field
label. Terminal automatic decisions remain available for audit. The four outcomes score
the behavior of the final release gate:

- **true positive** — the system released an event and the event was visible;
- **false positive** — the system released an event but the event was not visible;
- **false negative** — the system suppressed or missed an event that was visible;
- **true negative** — the system suppressed a proposal and no event occurred.

A missed event cannot be discovered from alert data alone. The dashboard therefore has
an explicit missed-event record with occurrence time, reason, optional operating-condition
tags, and a recording reference supported by the API. This prevents the product from
claiming recall based only on alerts it happened to generate.

## Rolling accuracy gate

After every new label the control plane stores an immutable snapshot for the camera/job
pair. The default policy uses the most recent 100 labels and requires:

- at least five positive and five negative ground-truth outcomes;
- at least two low-light, occluded, distant, or moving-camera outcomes;
- precision of at least 0.90;
- recall of at least 0.90.

Policies are configurable per semantic job. A safety-sensitive job can demand more data,
higher thresholds, or permanent manual review. A lower-risk job can use a different
evidence threshold without weakening other jobs.

The gate states are `collecting`, `ready`, `failing`, and `drifting`. Only `ready` allows
a distinct verifier's future decision to release automatically. If a previously ready
job falls below policy, a new snapshot becomes `drifting` and automatic release locks
immediately. Deterministic tracking jobs remain outside this semantic field gate.

## Relationship to replay

Replay and field gates are complementary:

1. Replay validates a version against intentionally labeled positive, negative, and
   challenging clips before deployment.
2. Live verification quarantines probabilistic candidates.
3. Field labels measure the deployed outcome and detect changing lighting, placement,
   process, or model behavior.

Neither model agreement nor synthetic clips count as human ground truth. Automatic
verifier decisions do not silently train or promote the same verifier.

## Remaining boundary

This phase records and scores corrections; it does not fine-tune a provider model or
automatically infer every missed event. Fleet-scale active sampling of normal windows,
reviewer assignment/SLAs, balanced dataset export, and approved training adapters are
the next phase. Real accuracy still requires real representative camera evidence.
