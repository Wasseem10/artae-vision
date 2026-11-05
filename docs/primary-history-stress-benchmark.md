# Can primary pose history combine different people?

October 15, 2026. **Yes, on constructed feature sequences.** The unchanged
`FusedMultiPersonFallRule` can combine person A's upright history with person
B's already-down pose and emit a possible-fall alert. This benchmark makes
that failure reproducible without changing the live detector or suggesting
that it measures video accuracy.

The previous [adjacent-frame audit](mpfdd-primary-continuity-audit.md) showed
provisional evidence of a primary-person change. Today's tooling tests its
state-machine consequence and exports the rule phases already present in
that local capture. The [derived report](benchmarks/primary-history-stress-v1.json)
keeps the synthetic and recorded-window results separate.

## Constructed challenge cases

The [nine fixed cases](../scripts/experiments/primary-history-cases-v1.json)
provide explicit actor labels and normalized pose features at 0.1-second
intervals. They are designed contract cases, **not video clips, held-out data,
or estimates of false-alert frequency**. No MediaPipe inference runs here.

The harness transpiles the actual application `browser-pose.ts`,
`pose-window-fall.ts`, and `multi-person-fall.ts`, loads the existing window
model, and records their hashes. It does not copy the fall algorithm into
the experiment. Raw pose order alternates; the bystander control also
exercises the additional-person path.

Compare the unchanged rule with an **oracle reset control**: restart the
entire fused rule when a fixture's actor label changes, including across
missing observations. Those labels are unavailable to the live application.
This control isolates the role of motion history; it is not an implemented
person-association algorithm or a deployable detector candidate.

| Synthetic case | Fall in constructed sequence? | Current rule: automatic alert | Oracle reset control: automatic alert |
| --- | --- | --- | --- |
| Same person falls | Yes | 1.6 s | 1.6 s |
| Different person already down | No | **1.6 s** | None |
| Short occlusion, different person already down | No | **2.0 s** | None |
| Large horizontal change to another down person | No | None | None |
| Same person sits | No | None | None |
| Already down from the start | No | None | None |
| Same person falls with standing bystander | Yes | 1.6 s | 1.6 s |
| Long occlusion, different person already down | No | None | None |
| New person stands long enough to arm, then falls | Yes | 2.5 s | 2.5 s |

Both paths alert on all three constructed fall cases. The current rule alerts
on two of six constructed non-fall cases; the oracle control alerts on none.
These deliberately chosen cases support a specific failure mechanism, not a
claim that resets solve real-world tracking or preserve real-video recall.
Window-model suggestions are recorded separately from automatic temporal alerts.

In the simplest failing case, A supplies standing observations from 0.0–0.6 s;
B supplies an already-horizontal pose at the same horizontal coordinate from
0.7 s onward. Neither actor has a complete stand-to-fall sequence, but the
primary slot retains A's armed state and interprets B's pose as descent.
The large horizontal jump and long missing-pose controls show that existing
reset guards handle some discontinuities. They do not establish identity when
two people occupy a nearby image location.

## What the recorded classroom window actually did

The script also validates and reads the unchanged October 14 capture and its
provisional labels. Source/model hashes must match those used by the stress
replay; the existing continuity scorer checks capture, selection, per-overlay
hash references, timestamps, and association coverage before joining phases.

| Retained times | Provisional association | Recorded primary phase |
| --- | --- | --- |
| 5.0–6.1 s | Dark-clothed actor | Upright |
| 6.2–6.4 s | Ambiguous overlap | Upright |
| 6.5 s | Ambiguous overlap | Descending |
| 6.6–7.0 s | Blue-clothed actor | Descending |

Across all 21 retained samples there are 15 upright and six descending states,
**zero automatic alert frames and zero window-suggestion frames**. Primary ID
remains 1. The real capture supports retained state across a provisionally
identified actor change; it does not establish a false alert or an exact switch
time. No counterfactual reset was evaluated on this sparse video capture:
replaying selected frames without the missing warmup would change the rule.
These actor associations still need independent human adjudication.

## Reproduction and verification

Clean replay revision: `0a12b58508db23d877bf1375c65aba846ffc2cd8`.
Runtime: Node `v24.21.0`, TypeScript `5.9.3`. The report contains fixture,
application-source, window-model, capture, and annotation hashes. The script
checks revision and cleanliness before/after execution and refuses to overwrite
an earlier result. Outputs must stay in the checkout's ignored `artifacts` folder.

With TypeScript installed in `apps/web`, run from a clean checkout:

```powershell
node scripts/experiments/primary-history-stress.cjs `
  apps/web artifacts/mpfdd-primary-history/new-run.json
```

To include the previously captured local window, append:

```text
artifacts/mpfdd-primary-continuity/capture-FOM0Hx/capture.json docs/benchmarks/mpfdd-primary-continuity-labels-v1.json
```

The full capture and source footage remain local because redistribution rights
are unresolved. The synthetic portion can run without either. To run tests with
dependencies installed elsewhere, set `ARTAE_STRESS_DEPENDENCIES_ROOT` to that
web package directory, then:

```powershell
node --test tests/benchmarks/primary-history-stress.test.cjs tests/benchmarks/primary-continuity.test.cjs
python -m unittest discover -s tests/benchmarks -p test_visible_person_audit.py
```

Seven new stress/observed-state tests, seven continuity tests, and seven Python
count-audit tests pass (**21 total**). Tests include the actual unchanged rule's
two known synthetic failures, positive controls, malformed sequence coverage,
oracle boundary behavior, and rejected phase/source/alert metadata. Node syntax
and diff checks pass. Two clean runs reproduce the report byte for byte, and the
fixture hash matches the committed Git blob. This change uses previously
reviewed scientific overlays; no new UI or visual design changed.

## Limit and next priority

The live detector, model, thresholds, landing page, and `/live` are unchanged;
the previously measured MPFDD result remains 2/22 fall clips. This adds a concrete
regression target for a future association fix. Promotion remains blocked by
the absence of adjudicated person identities/timed fall labels, an untouched
test source, and sufficiently long varied non-fall footage.

Next, evaluate an association/reset candidate using only observations available
at runtime. Run these regression cases and frozen before/after video replays,
checking fall recall as well as false alerts and identity continuity. The
oracle's perfect fixture labels must never substitute for that algorithm or
its evaluation.
