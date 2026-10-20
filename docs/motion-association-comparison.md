# Motion association candidate: rejected for the demo

October 20, 2026. An independently written tracking candidate fixes primary-slot
swaps in constructed association tests, but loses every fall clip that the
baseline detects in this paired video comparison. It is research-only; no
live model, rule, worker, or threshold was changed.

## What was implemented

`scripts/experiments/motion-association.cjs` gives all observed poses a shared
association pool. Primary is an observation source, not a permanent identity.
Each existing track predicts its next center from recent velocity. With at
most four observations, exhaustive assignment finds the lowest total cost,
including an unmatched choice; this avoids greedy nearest-pair conflicts.
Each matched track owns its own existing temporal and window rules.
Ambiguous overlaps discard history. Unobserved tracks are retained briefly
for matching but never returned as fresh pose observations.

This is original project code implementing general association techniques.
No SPECTRA source or assets were copied. It is not a ByteTrack implementation,
does not use appearance embeddings, and cannot infer real identity from
center positions alone.

The initial fusion duplicate gate was intentionally retained to isolate the
association experiment. This is also a limitation: its duplicate pose
observations can confuse the new matching stage.

## Paired results

Both rules consumed the exact same newly computed pose features on every
sample, with a fresh real MediaPipe worker per clip. No actor annotations
were passed to either path.

| Source | Baseline fall clips alerted | Candidate fall clips alerted | Baseline / candidate activity clips alerted |
| --- | --- | --- | --- |
| Previously examined MPFDD, 28 clips | 2/22 | **0/22** | 0/6 / 0/6 |
| Five staged demo controls | 3/3 | **0/3** | 0/2 / 0/2 |

All 33 per-clip outcomes, media hashes, sample counts, and event timestamps
are in [the summary](benchmarks/motion-association-v1.json).
The two MPFDD regressions are `mpfdd-s1-p2-f1-fall-1` and
`mpfdd-s3-p4-f1-fall-4`. All lateral, forward, and backward demo positives
also regress. No newly successful fall clip occurs.

MPFDD contributes 2,751 samples and 63.071666 seconds of activity video.
Demo controls contribute 605 samples and 24.090758 activity seconds.
These are short staged clips, not sufficient negative exposure for a field
false-alert rate. The MPFDD filename labels do not provide event timing or
person identity. The collection has already been examined; its upstream
`holdout` field is not a claim of a fresh held-out test here.

This harness samples integer `i/10` timestamps strictly before video end,
with bitmap width capped at 1280. It is a new paired capture, not a replay
of the earlier 2,761-sample report. That evaluator included a clamped final
sample on exact-grid durations. Neither sample counts nor raw features
should be silently compared as if the captures were byte-identical.

## A concrete failure

In the lateral demo, candidate track 1 reaches `descending` at 5.3 seconds.
At 5.6 seconds the model/fusion path supplies an additional pose track.
At 5.7 seconds ambiguous association discards the armed history; subsequent
tracks start unarmed. The baseline reaches `alerted` at 6.7 seconds, while
the candidate never alerts. The real demo recording also visibly shows a
brief duplicate skeleton on one person. Association cannot simply assume
every pose output is a distinct person.

Nine constructed history cases also remain explicit: the candidate alerts
on all three synthetic fall cases, but also on two of six synthetic non-fall
cases involving a different already-down actor at a nearby image position.
The candidate does not see fixture actor labels. Passing crossings and
primary-slot-swap tests therefore does not solve identity during ambiguous
occlusion or establish real-video accuracy.

## Reproduce and verify

Captured clean revision: `2b61b3022fa91702598c868471a9783cf0d6d3a4`.
Chrome `155.0.8059.85`, Node and TypeScript versions plus all model/runtime/
rule hashes are in the local full report. The committed summary pins its SHA-256:
`5c2e4955c2f996d85b291065f9aa9393d18c35d725344feab686149808ef57ed`.
The report retains full-precision features, both rules' outputs, and presented
video timestamps for every sample. All media and the full pose trace stay local.

The capture uses the strict presented-frame sampler from
`f670e4bf1a0202514ab6ad3a5d5d07fbb136806b`, verifies the pinned manifest and
every video hash, and fails on missing clips, worker/decode failures, unexpected
external requests, dirty source, or a changed checkout. A complete result is
written only after all clips finish. It never overwrites earlier evidence.

From a clean checkout with the locally prepared vision assets and web dependencies:

```powershell
node scripts/experiments/compare-motion-association.cjs `
  <vision-root> <web-dependencies-root> artifacts/new-motion-comparison.json
node scripts/experiments/summarize-motion-association.cjs `
  artifacts/new-motion-comparison.json artifacts/new-motion-summary.json
$env:ARTAE_STRESS_DEPENDENCIES_ROOT = '<web-dependencies-root>'
node --test tests/benchmarks/motion-association.test.cjs `
  tests/benchmarks/motion-association-evidence.test.cjs `
  tests/benchmarks/primary-history-stress.test.cjs
```

17 focused tests pass: nine candidate contracts (including retained synthetic
failures), one archived evidence check, and seven existing history stress tests.
Syntax and diff checks pass. The production UI stays on the baseline; its
separate demo-readiness work is in PR #17.

## Next decision

Do not tune away this regression and call the same clips independent validation.
First establish reviewed person observations and duplicate-pose labels around
the failed windows. Then compare a person detector plus a licensed tracking
baseline with pose-only association, retaining ambiguous/missing observations.
A future candidate needs an untouched multi-person test and longer hard
negatives before promotion. The new single-person posture source does not
replace that gate.
