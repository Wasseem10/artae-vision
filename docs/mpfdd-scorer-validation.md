# MPFDD scorer validation check

October 9, 2026. The clip scorer now rejects incomplete sampling before using
full clip duration as negative exposure. Previously, a report marked complete
with a positive `framesAnalyzed` count could pass even if most frames were missing.
The same validation rejects invalid coverage, non-finite durations/timings,
alerts outside the sampled timeline, and duplicated or inconsistent track events.
Simultaneous alerts from two different people remain valid.

## Verification

- Eight standard-library unit tests passed: `python -m unittest discover -s tests/benchmarks -v`.
- Revalidated the archived original and fused MPFDD exports: 28 clips and 2,761
  sampled frames in each. Compared against the scorer on main (`174346215`):
  all per-clip data and aggregate summaries are identical.
- Injected a truncated negative into the archived fused export: reduced its
  frame count and trace to one sample while retaining its full duration. The
  previous scorer accepted it; the updated scorer rejected it with:
  `Incomplete sampling or invalid coverage: mpfdd-s1-p2-f0-adl-1`.
- No detector, website, alert threshold, model, or published benchmark result changed.
  No UI visual check applies to this offline scorer change.

| Archived input | SHA-256 |
| --- | --- |
| Original export | 326eac09497fb00bd5fbaff6021489a9d6c70a3f73bf0cf565a85343e4de3c6d |
| Fused export | cfc94404c93027e1febda385b651b3c6022ebc0f95c5fff11aedca03502283d9 |
| Media manifest | 77b10d1a1eda79892e8915bd8b4d95be647f2e9f6e6afdc545469fde9f42b49d |

## Per-clip comparison

Each row passed the new validation. The original-path and fused-path alert times
below are retained from the archived replay, not a new inference run. Each path's
before/after values are unchanged. Both paths remain at **2/22 fall clips** and
**0/6 activity clips**, with **63 seconds** of negative footage.

| Clip | Samples per path | Original alert seconds | Fused alert seconds | Before/after scorer |
| --- | ---: | --- | --- | --- |
| mpfdd-s1-p2-f0-adl-1 | 121 | [] | [] | unchanged |
| mpfdd-s1-p2-f0-adl-2 | 101 | [] | [] | unchanged |
| mpfdd-s1-p2-f0-adl-3 | 101 | [] | [] | unchanged |
| mpfdd-s1-p2-f1-fall-1 | 101 | [6.3] | [6.3] | unchanged |
| mpfdd-s1-p2-f1-fall-2 | 101 | [] | [] | unchanged |
| mpfdd-s1-p2-f1-fall-3 | 101 | [] | [] | unchanged |
| mpfdd-s1-p2-f2-fall-1 | 101 | [] | [] | unchanged |
| mpfdd-s1-p2-f2-fall-2 | 101 | [] | [] | unchanged |
| mpfdd-s1-p2-f2-fall-3 | 101 | [] | [] | unchanged |
| mpfdd-s2-p2-f0-adl-1 | 101 | [] | [] | unchanged |
| mpfdd-s2-p2-f0-adl-2 | 111 | [] | [] | unchanged |
| mpfdd-s2-p2-f0-adl-3 | 101 | [] | [] | unchanged |
| mpfdd-s2-p2-f1-fall-1 | 81 | [] | [] | unchanged |
| mpfdd-s2-p2-f1-fall-2 | 101 | [] | [] | unchanged |
| mpfdd-s2-p2-f1-fall-3 | 81 | [] | [] | unchanged |
| mpfdd-s2-p2-f1-fall-4 | 91 | [] | [] | unchanged |
| mpfdd-s2-p2-f1-fall-5 | 71 | [] | [] | unchanged |
| mpfdd-s2-p2-f2-fall-1 | 81 | [] | [] | unchanged |
| mpfdd-s2-p2-f2-fall-2 | 101 | [] | [] | unchanged |
| mpfdd-s2-p2-f2-fall-3 | 91 | [] | [] | unchanged |
| mpfdd-s2-p2-f2-fall-4 | 81 | [] | [] | unchanged |
| mpfdd-s2-p2-f2-fall-5 | 111 | [] | [] | unchanged |
| mpfdd-s3-p4-f1-fall-1 | 92 | [] | [] | unchanged |
| mpfdd-s3-p4-f1-fall-2 | 162 | [] | [] | unchanged |
| mpfdd-s3-p4-f1-fall-3 | 132 | [] | [] | unchanged |
| mpfdd-s3-p4-f1-fall-4 | 91 | [5] | [5] | unchanged |
| mpfdd-s4-p4-f2-fall-1 | 71 | [] | [] | unchanged |
| mpfdd-s4-p4-f2-fall-2 | 81 | [] | [] | unchanged |

## Limits and next priority

This validates internal consistency of supplied exports and pinned media hashes.
It does not authenticate a producer, prove that a worker actually processed every
sample, or replace independent ground truth. The trace includes sampled frames,
not all original video frames. Clip durations must still agree across the paired
runs. These are already examined staged clips, so this is a regression check,
not new accuracy evidence or a promotion decision.

Independent validation of a detector improvement still needs visible-person and fall
identity/timing labels and longer, independently sourced negative exposure.
The next useful step is to annotate representative shared-room frames and match
raw poses to visible people, building on the observation diagnostic in PR #16,
before changing observation, association, or fall thresholds.

To reproduce with the original private research inputs, prepare the pinned MPFDD
manifest and place the archived exports at `artifacts/mpfdd/evaluation.json` and
`artifacts/mpfdd/evaluation-multiperson.json`, then run
`python scripts/score-mpfdd-clips.py`. Compare its generated report with the
committed `docs/benchmarks/mpfdd-first-look-v1.json`. Videos and full exports
remain local and gitignored; their redistribution license is unresolved.
