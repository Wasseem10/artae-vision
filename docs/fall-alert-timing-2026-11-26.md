# Make the fall matching allowance visible

November 26, 2026. The comparison report now exposes **when reported alerts fall
relative to the supplied annotation**. A successful clip-level match can otherwise
hide both reliance on the two-second allowance and additional outside-window alerts.
The previous output preserved raw timestamps, but did not classify or total these
cases. This change adds that analysis without changing the matching rule.

## Output

Schema 2 gains additive `fallAlertTiming` fields. For each fall clip, each side
has three arrays of timestamps (seconds):

- `withinAnnotatedInterval`: start through end, inclusive.
- `withinPostEventAllowance`: after end through end + 2 seconds, inclusive at
  the upper bound and limited by the reported video duration.
- `outsideMatchingWindow`: all remaining reported alerts, including alerts
  before the annotated start. No pre-event allowance is introduced.

Every reported timestamp appears in exactly one group. Input multiplicity is
preserved; repeated timestamps are not silently deduplicated. Activity clips
have `fallAlertTiming: null`, and keep their separate negative-exposure metrics.

Top-level `fallAlertTiming.baseline` and `.candidate` contain alert counts for
each group, total fall clips and alerts, clips with outside-window alerts,
matched clips also containing outside alerts, and clips matched **only** in the
allowance. Group counts are alert counts, not counts of unique falls or people.
The per-clip arrays permit inspection of every reported match and miss.

## Archived evidence

The original baseline was compared with five existing reports of the **same
100 CAUCAFall clips** (50 falls, 50 activities). No inference was rerun.

| Report | Matched falls / 50 | Alerts inside annotation | Alerts only in allowance | Alerts outside full window |
| --- | ---: | ---: | ---: | ---: |
| Original baseline | 17 | 5 | 12 | 0 |
| Full model | 19 | 7 | 12 | 0 |
| Heavy model | 22 | 9 | 13 | 0 |
| Unfused multi-person | 8 | 3 | 5 | 0 |
| Fused multi-person | 20 | 6 | 14 | 0 |

Each archived fall clip has at most one reported alert, so allowance-alert
counts equal clips matched only in the allowance **in these inputs**. The scorer
also handles clips with multiple alerts, covered by synthetic regression tests.
The fused result's 20 matches therefore include only six inside the annotated
interval and 14 in the allowance. This explains the reported score; it neither
revises that score nor establishes a measured end-to-end detection delay.

All pre-existing output fields, including every paired timestamp, match flag,
gain/loss list, activity exposure, pose coverage and inference-time aggregate,
were compared with revision `6500e0e394ee0a7e6ef1b596592f4d1c5aa45064` and
remained exactly equal. The only additions are timing fields and a limitation.
The [verification record](benchmarks/fall-alert-timing-2026-11-26.json) pins
input, comparator and generated-output SHA-256 hashes and both sides' totals.
Full paired reports remain local in `artifacts/alert-timing-2026-11-26/`.

## Verify

```powershell
python -m unittest discover -s tests/benchmarks -p 'test_pose_comparison.py' -v
python scripts/compare-pose-models.py <baseline.json> <candidate.json> --manifest <manifest.json>
```

All 14 tests pass locally, including exact interval/allowance boundaries,
outside alerts accompanying a successful match, repeated alerts, separate
activity semantics, output/input isolation, short-clip handling and per-clip
reconciliation with each side's aggregate. CI runs the same suite. No product
UI changed, so no visual check applies.

## Limits and next priority

Outside-window alerts are **review candidates, not verified false positives**.
An inside-window alert does not establish the correct person's identity or
event causality. Supplied annotations, clocks and full inference coverage still
require independent verification. Zero outside-window alerts on these short,
previously examined fall clips does not establish field reliability, and says
nothing about unexamined negative footage. No model is selected or promoted.

Independent person labels, untouched multi-person footage and substantially
longer hard negatives remain the detector gate. Review annotation boundaries
and alert timing together before describing matches as prompt detection.
