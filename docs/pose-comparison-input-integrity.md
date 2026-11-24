# Validate and explain pose-model comparisons

November 24 follow-up: output schema 2 now includes paired per-clip results and
activity exposure for **both** reports. It replaces the misleading
`candidateDailyActivityAlertsPerAnalyzedHour` field with
`dailyActivityExposure.candidate.alertsPerReportedVideoHour`. The denominator
is the sum of reported activity-video durations, not independently verified
analyzed exposure. Existing callers must migrate to that path; no repository
application consumes the old field. Historical verification files are retained
unchanged with their original schema.

Each side now reports activity-clip count, clips alerted, total alert count,
reported video seconds and the normalized rate. Multiple alerts in one clip
count separately in the rate but only once in `clipsAlerted`. Both sides carry
`analyzedExposureVerified: false`. This remains false even when a report declares
itself complete. Total-duration overflow is rejected before producing a rate.

`perClip` follows manifest order and pairs baseline/candidate alert timestamps,
reported duration and `matchedFall`. Activity clips use `matchedFall: null`;
they are not missed falls. All alert timestamps remain visible, including those
outside a fall's matching interval. The existing interval plus two-second
allowance is unchanged and stated in the output's limitations. This does not
verify which person an alert concerned.

The schema-2 compatibility run reprocessed five previously examined reports,
each containing the same 100 clips. Existing scores and gain/loss/alert lists
are unchanged; the renamed candidate rate has the same numeric value. Every
paired timestamp list and duration matches its input row. Each report has
50 activity clips with **514.05 reported video seconds**. This is repeated
evaluation of the same footage, not five independent test sets or five times
the negative exposure. The [new verification record](benchmarks/paired-comparison-2026-11-24.json)
pins inputs, output hashes, comparator source and paired totals. Full generated
reports remain local under `artifacts/paired-comparison-2026-11-24/` and can be
regenerated using the CLI below. No inference was rerun and no model promoted.

All **11 regression tests** pass locally, including new checks for symmetric
denominators, per-clip reconciliation, activity/null semantics, detached output
snapshots and overflow. CI runs the same test module. There is no UI change.

November 18, 2026. The CAUCAFall comparison script now rejects duplicate clip
rows, mismatched labels and invalid numeric observations before calculating a
score. This is benchmark tooling, not a detector or accuracy improvement.

## Reproduced failure

The prior script converted result rows into a dictionary before checking clip
coverage. Appending a duplicate to a complete 100-clip report still passed,
because the dictionary silently discarded one row. It also checked each video
hash and event interval but trusted the result's `category` without comparing it
to the manifest. Changing a fall row to `daily_activity` therefore changed the
comparison's negative exposure and classifications despite unchanged provenance.

Both failures were reproduced using modified, temporary copies of archived
CAUCAFall reports. Original reports were not edited. Neither reproduction is
evidence that the archived reports were corrupt.

## Change

- Validate exactly 100 rows and unique, nonempty IDs before dictionary creation,
  in the manifest and both reports. Reject omitted or unexpected clips.
- Require each report's category, video hash and event intervals to match the
  supplied manifest. Validate manifest categories and interval structure.
- Reject nonfinite, negative, boolean or otherwise invalid numeric values;
  require positive duration and analyzed frames, integer pose counts bounded by
  analyzed frames, and alert times within the clip. Require activity footage
  before computing the negative-exposure denominator.
- Keep comparison calculations and event matching unchanged. A new optional
  `--manifest` argument supports explicit local archive checks without copying
  dataset media into a new checkout. Its default remains the prepared dataset.
- Run eight standard-library regression tests in a small GitHub Actions job.
  No media downloads, model inference or project dependency installation is
  required for those tests.

## Archived compatibility check

On November 18, the old and updated scripts compared the original baseline against each of five
existing 100-clip reports. **All output fields matched exactly**, including
gained/lost clip lists, false-alert lists, exposure, coverage and timing.

| Existing report | Matched fall clips / 50 | Activity clips alerted / 50 | Before vs after |
| --- | ---: | ---: | --- |
| `evaluation.json` | 17 | 0 | Identical |
| `evaluation-full.json` | 19 | 1 | Identical |
| `evaluation-heavy.json` | 22 | 0 | Identical |
| `evaluation-multiperson-unfused.json` | 8 | 0 | Identical |
| `evaluation-multiperson.json` | 20 | 1 | Identical |

These are rescored **previously examined development reports**, not five new
evaluations or a new independent test set. No model is selected or promoted by
this check. Input hashes and per-comparison outputs are retained in the
[verification record](benchmarks/comparison-input-integrity-2026-11-18.json).
The duplicate-row and category-mutated copies are both rejected after the fix.

## Reproduce

```powershell
python -m unittest discover -s tests/benchmarks -p 'test_pose_comparison.py' -v
python scripts/compare-pose-models.py <baseline.json> <candidate.json> --manifest <manifest.json>
```

Tests cover valid scoring and boundary timestamps, both forms of duplicate
rows, label/media/interval mismatches, malformed metrics, invalid alert times,
incomplete or wrong datasets, invalid manifest labels and CLI failure without
score output. Local testing used Python 3.12; CI uses Python 3.11 on Linux.
There is no UI change requiring a visual check.

## Limits and next priority

This validates consistency with a **supplied** manifest; it does not authenticate
that manifest, read/hash video bytes, establish annotation correctness, prove a
complete inference replay or establish train/test independence. A syntactically
valid but false duration or count can still pass. Reviewed labels, verified
capture provenance and independent evaluation remain separate requirements.

The live detector, landing page and `/live` workflow are unchanged. The accuracy
priority remains independent person/duplicate annotation, followed by a frozen
candidate on retained regressions and untouched multi-person footage with
longer hard-negative exposure. No production or cloud changes were made.
