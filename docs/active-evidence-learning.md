# Active evidence learning

Phase 28 turns the recording archive and semantic verification stream into a bounded,
human-grounded evidence operation. It does not train a model from its own predictions.

## Sampling loop

The operations worker calls the protected reconciliation endpoint every 30 seconds.
The control plane creates review samples from:

- semantic verification cases (`candidate`, `uncertain`, or `challenging`); and
- ordinary archived recording segments (`normal`).

Each job has an enable switch, a normal-footage interval, daily limit, review SLA, and
retention period. Candidate cases are unique by verification-case ID. Ordinary footage
uses a per-job time bucket, so adjacent/overlapping archive fragments cannot flood the
queue. The recording SHA-256 is retained in model context for exact-content provenance.

Samples contain IDs and bounded model/job context—not camera credentials or source
URLs. Their expiry cannot extend the underlying recording expiry. Legal holds remain a
recording-archive concern and are never silently added by the learning loop.

## Review and labels

The queue is ordered by priority: uncertain proposals first, then challenging evidence,
other candidates, and routine footage. Reviewers can self-assign work; assignment sets a
per-job SLA deadline and the summary reports overdue items.

Uncertain proposals are decided in the verification inbox because that decision can
release an alert. Routine footage is labeled directly as a correct suppression or a
missed event. Terminal proposals can be audited against what actually happened. Every
review creates or links a Phase-27 field-accuracy label and refreshes the drift gate.

## Dataset versions and export

A dataset version selects only labeled samples. Selection round-robins across outcome
classes to reduce majority-class domination and stores the achieved balance. Drafts can
be inspected, then frozen. Freezing calculates a deterministic SHA-256 over the ordered
JSONL manifest; later export recomputes and verifies the hash before returning data.

Every row carries the dataset name/version, camera, rule, evidence references, sample
kind, captured model/job configuration, and a label snapshot. Exports intentionally
contain durable evidence IDs rather than expiring signed URLs or copied video. They can
feed replay evaluation immediately. Any future training adapter must require a frozen,
approved manifest and separate authorization.

## Boundaries

- Temporal/content provenance deduplication is implemented; visual-embedding similarity
  is a later optimization for archives with overlapping encodes.
- Sampling does not call a paid vision provider and does not start stopped cameras.
- Dataset creation does not fine-tune or deploy a provider model.
- Reviewer consensus, adjudication, and external annotation-vendor workflows remain a
  later fleet-scale quality phase.
