# Replay promotion and review quality

Phase 29 closes the gap between collecting field evidence and changing production
behavior. It adds independent review consensus, deterministic dataset-to-replay builds,
fair baseline/candidate comparisons, explicit approval, and durable rollback metadata.

## Independent review and adjudication

Each semantic job can require one or two independent reviews. When two are required:

1. the first judgment moves the sample to `reviewing`;
2. a different reviewer must submit the second judgment;
3. agreement creates the field-accuracy label automatically; and
4. disagreement moves the sample to `disputed` until a third person adjudicates it.

A reviewer cannot vote twice and cannot adjudicate a dispute they voted on. Every vote,
reason, environment tag, reviewer, and timestamp remains durable. High-risk deployments
should use two reviews with adjudication enabled.

The local development identity represents one operator, so real multi-person consensus
requires production OIDC identities. The single-review default keeps local development
usable without pretending one person is two reviewers.

## Frozen dataset to replay suite

A frozen Phase-28 dataset can be converted once into a replay suite. The build is
idempotent and creates one replay evaluation for every retained, replayable sample.
Positive labels become full-window expected intervals and negative labels expect no
event. Evaluations inherit the exact camera, accepted compilation, job specification,
execution plan, environment tags, and retained media URI.

Missing or expired media is listed explicitly in `skipped_samples`; it is never silently
treated as a passing evaluation. A build fails if no sample remains replayable.

## Candidate comparison and promotion

Candidate and baseline replay runs must use the same frozen dataset suite. The comparison
stores macro F1, macro recall, false alarms, their deltas, and SHA-256 fingerprints of the
candidate and baseline agent plans. The default no-regression gate allows at most a
one-point F1/recall decrease and no increase in false alarms, in addition to the replay
suite's own pass criteria.

Creating a comparison does not deploy anything. An administrator must explicitly approve
it. Approval uses the existing safe agent-plan promotion path and stores who decided,
when, why, the prior plan, prior regression run, camera, and rule. Rejection is equally
durable. Rollback restores the previous approved plan and its passed gate; a first-ever
deployment rolls back to a paused job.

## Safety boundaries

- Building suites does not run them and does not call a paid provider.
- Promotion cannot bypass a failed candidate run or a detected regression.
- Camera desired state is not changed by dataset building or comparison creation.
- Phase 29 promotes configuration/agent plans; provider-specific fine-tuning remains an
  explicit future adapter with its own authorization and model registry.
- Live shadow/canary deployment and automatic operational rollback are Phase 30 work.
