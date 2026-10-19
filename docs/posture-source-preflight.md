# A new video source: annotation preflight

October 18, 2026. **No detector was changed or evaluated in this work.** This
adds a reproducible annotation audit for a candidate source of continuous
activity/fall footage. It does not establish improved accuracy, usable negative
exposure, independent-person generalization, or multi-person performance.

October 19 update: [all seven candidate videos are now hash-verified and fully
decoded](posture-media-preflight.md), with 51,363 frames and explicit PTS/label-clock
diagnostics. The October 18 snapshot below predates that acquisition. Event
adjudication and the scoring protocol remain unfinished; no accuracy is claimed.

## Source and fixed inventory

[Patrick O. Ogbuitepu's Fall Detection and Posture Classification Dataset,
version 1.0.1](https://doi.org/10.5281/zenodo.21360087) contains self-recorded
footage of one consenting adult. The publisher releases it under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The
[Hugging Face mirror](https://huggingface.co/datasets/pat2echo/fall-detection-posture-classification/tree/5c075333e557e43cbcb42306fc4475201a625982)
provides individual files, avoiding an all-or-nothing archive download.

The [source lock](benchmarks/posture-source-v1.lock.json) pins that exact mirror
revision, byte sizes and SHA-256 digests for all ten videos. It also pins Git
blob SHA-1 and SHA-256 for fourteen downloaded metadata/annotation files.
Unmodified upstream labels, card, schema, citation and license are retained
under `tests/fixtures/posture-source-v1/`; `.gitattributes` preserves their
original bytes on Windows. Attribution: Ogbuitepu, Patrick O. (2026), University
of Essex. No endorsement is implied. Source-card performance statements refer
to the publisher's system, not Artae, and are not adopted here.

The seven `valid/fall_detection_4.mp4` through `fall_detection_10.mp4` recordings
are the **candidate evaluation roster**, fixed before any Artae inference on
this source. All three upstream `train/` videos are excluded from that roster;
their annotations are included only to preserve and audit the source split.
The candidate video files total 1,981,798,589 bytes. **None was downloaded,
decoded, visually adjudicated, or scored in the original October 18 preflight.**
Its video hashes were publisher metadata, not verified local media hashes.
The separate October 19 report records subsequent verified acquisition.

This source is new to the project's recorded benchmarks, but its seven videos
are not seven independent people: they all feature the same adult. It can
eventually add continuous single-person activity checks. It cannot replace
person-identity adjudication on MPFDD or the multi-person promotion gate.

## What the audit actually found

The upstream schema uses integer start/end timestamps but does not specify
endpoint semantics. The audit examines **integer bins `start..end` inclusive**
as a declared diagnostic convention. This preserves single-timestamp rows and
exposes shared boundaries; it does not establish frame-accurate labels. A
half-open interpretation would discard 233 single-timestamp rows in the seven
candidate files, including some fall transitions.

| Candidate file | Rows | Duplicate row groups | Conflicting bins | Gap bins | Unassigned bins | Single-timestamp rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `fall_detection_4` | 65 | 1 | 0 | 0 | 72 | 27 |
| `fall_detection_5` | 83 | 1 | 1 | 0 | 54 | 42 |
| `fall_detection_6` | 56 | 1 | 2 | 1 | 25 | 27 |
| `fall_detection_7` | 48 | 0 | 1 | 0 | 48 | 18 |
| `fall_detection_8` | 134 | 0 | 1 | 0 | 121 | 65 |
| `fall_detection_9` | 34 | 0 | 1 | 0 | 16 | 14 |
| `fall_detection_10` | 68 | 1 | 0 | 1 | 13 | 40 |
| **Total** | **488** | **4** | **6** | **2** | **349** | **233** |

Examples (CSV row numbers include the header):

- `fall_detection_4.csv` rows 15 and 16 repeat `116,116,Sit-Lie,False`.
- `fall_detection_5.csv` rows 5 and 6 assign both `Sit` and `Sit-Stand` to bin 10.
- `fall_detection_6.csv` has shared boundaries at 34 and 115, and no label for
  bin 98. `fall_detection_10.csv` has no label for bin 128.
- `None` and blank activity values mean unassigned activity. A `False` flag
  on such a row does **not** make it verified negative footage.

The checked-in [machine-readable audit](benchmarks/posture-source-v1.audit.json)
retains each conflict's source row numbers, duplicate groups, gaps, unassigned
bins, fall rows, and contiguous positive-label runs. Duplicate rows do not
double-count bins; conflicts are excluded from both positive and negative
counts. Adjacent `Stand-Lie,True` and `Lie,True` rows are not automatically two
falls. Neither a raw row nor a contiguous positive-label run is an adjudicated
fall event.

There are 1,267 unambiguous non-fall **label bins** under this convention.
These are **not** 1,267 measured seconds of usable negative exposure. Video
duration, actual transitions, unassigned scenes, and post-fall recovery still
need reconciliation. No false-alerts-per-hour denominator is exported.

## Reproduce without running the app

Python 3.11+ and the standard library are sufficient. From the repository root:

```powershell
python scripts/audit-posture-source.py --output artifacts/posture-source-audit.json
python -m unittest discover -s tests/benchmarks -p test_posture_source_audit.py -v
```

To independently re-fetch the fourteen pinned small files into a new cache:

```powershell
python scripts/audit-posture-source.py --source-dir artifacts/posture-source-cache --fetch-missing --output artifacts/posture-source-fresh.json
```

Existing files are verified too; a corrupt existing file is rejected rather
than silently replaced. A download with an incorrect size or hash is never
written. These commands do not download videos or run pose inference. They do
not require accounts, API keys, or paid services.

Optional `--media-root <directory>` verifies any available original video bytes
against the lock, using upstream `train/` and `valid/` paths. Missing media stay
`not-verified`; a mismatch fails the audit. A matching hash is explicitly
`hash-verified-not-decoded`, never proof of valid duration or annotations.
The report always stays ineligible for benchmark promotion: this tool audits
source material and deliberately cannot issue a detector score.

## Verification completed

- Sixteen focused tests pass: interval parsing, single-timestamp labels,
  overlapping classes/actions, duplicate coverage, unknown intervals, source
  identity/split drift, exact byte integrity, safe cache paths, corrupt
  downloads, and both media-size and media-checksum failures.
- Two full audit runs produce identical results. A separate fresh network
  retrieval of all fourteen pinned files produces the same report bytes as
  the checked-in-source run.
- The generated report is compared to the checked-in report in the regression
  suite. JSON reports use explicit LF newlines across platforms, while raw
  upstream file bytes are preserved. No application, detector, landing-page,
  or `/live` changes were made;
  browser visual checks are not applicable to this offline-only change.

## Accuracy work identified on October 18

The [October 19 follow-up](posture-media-preflight.md) completes acquisition and
decoding, and documents remaining clock and event-label blockers. The original
sequence below explains the wider evaluation gate.

1. Retrieve and hash the seven candidate videos, decode them, measure actual
   durations, and reconcile their labels against the footage. Store corrections
   in a separate, reviewed sidecar; do not rewrite the upstream CSVs. Resolve
   all six shared boundaries, two gaps, and four duplicate groups, and retain
   genuinely unknown intervals as unknown.
2. Adjudicate onset/end and recovery boundaries for each fall, deliberate lying
   down, sitting, occlusion, and empty-room intervals. Confirm endpoint
   semantics before deriving exposure. Preserve difficult non-falls; do not
   remove them because a detector alerts on them.
3. Before inference, freeze exact baseline/candidate revisions and all model,
   rule, runtime and media hashes, sampling method, event-matching tolerance,
   repeated-alert accounting, and the negative-exposure protocol. Use verified
   presented video frames and continuous state across the recording; do not
   reset the detector at annotation boundaries. Require per-video matched and
   missed events, unmatched alerts, unknown-interval alerts and measured
   negative exposure, with one-to-one event matching and retained failures.
4. Treat this as an additional staged single-person check. Independently
   adjudicated multi-person footage, longer representative negatives, and
   person/scene separation remain required. Once its outputs guide tuning,
   this source becomes development evidence; reserve another untouched source
   for promotion.

The current `origin/main` inspected for this work is
`17434621568012e8d05a72d23c0d98953de45b37`. Its published MPFDD result remains
**2/22 fall clips and 0/6 activity clips alerted**, with only about 63 seconds
of activity footage. This preflight provides no new accuracy result and
promotes no model. The [product plan](fall-product-plan.md) and
[cross-source gate](fall-cross-source-v4.md) still apply.
