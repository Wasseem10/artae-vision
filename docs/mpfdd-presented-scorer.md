# MPFDD presented-frame scorer migration

October 13, 2026. The MPFDD clip scorer now supports the schema 5/6 exports
introduced by [PR #20](https://github.com/Wasseem10/artae-vision/pull/20), with
explicit validation of their presented-frame contract. It also continues to
validate the archived schema 3/4 pair. The detector and website are unchanged.

## Validation and output

Select the sampling method explicitly; a schema 3/6 or 5/4 mixed pair is
rejected. Schema 5/6 requires the exact `presented-frame-v1` provenance,
including the 1 ms seek offset, 50 ms maximum lag, and 2 ms maximum lead.
Each clip must retain every expected 0.1-second sample, finite decoded times,
increasing positive integer presentation counters, and nondecreasing media
times. Missing, truncated, reordered, stale, future, or malformed traces fail
before scoring. Changing the declared bounds or relabeling a presented trace
as a seek-only schema also fails.

Both paths must have the same frozen code revision, source hashes, model
fingerprint, worker, and runtime metadata. Media and labels must match the
local manifest hash. A successful parse validates reported consistency; it
does not authenticate the producer or prove the physical identity of a frame.

Track IDs are positive session identifiers, not ordinal indexes bounded by
`trackIdsSeen`. For example, a run with only additional track 2 can report one
unique track. The validator now accepts this gap while rejecting invalid IDs,
duplicate alerts, and more distinct alerted IDs than reported unique tracks.
It does not infer person identity accuracy from those identifiers.

## Run

With the pinned local manifest and both clean exports available:

```powershell
python scripts/score-mpfdd-clips.py --sampling presented
```

This reads `evaluation-presented-v1.json` and
`evaluation-multiperson-presented-v1.json` under `artifacts/mpfdd`, and writes
`artifacts/mpfdd/presented-comparison.json`. That summary records schemas 5/6,
the protocol, validated sample counts, report hashes, and a development-only
scope. It does not overwrite the published first-look report.

`--sampling seeked` retains the original schema 3/4 filenames and summary.
Use `--manifest`, `--legacy-report`, `--multi-report`, and `--output` to work
with archived inputs in another local checkout without copying source media.
Never mix the old and new sampling methods in a detector comparison.

## Verification and limits

- Eighteen stdlib tests passed: `python -m unittest discover -s tests/benchmarks -v`.
  Tests include malformed traces/provenance, mixed methods, source/model
  mismatches, gapped track IDs, and an end-to-end CLI check with explicitly
  synthetic schema 5/6 fixtures. Those fixtures are not inference results.
- Revalidated the actual archived schema 3/4 pair (28 clips and 2,761 samples
  each); the entire generated summary, including all per-clip rows, matched
  the committed first-look JSON exactly.
- Revalidated all 28 clips and 2,761 presentation samples in the actual schema
  6 export from `80182da`. Its SHA-256 is
  `d48ab1ccad2bce1de20a5aea488e2f263ae9643bdfc70bf5df74c45343526ad7`.
  The existing 2/22 fall clips and 0/6 activity clips are unchanged.
- No new inference run or detector tuning was performed. Schema 5 support was
  exercised with protocol fixtures; no actual schema 5 replay was available
  to claim a new original-vs-fused presented pair. No UI visual check applies
  to this offline parser change.

The negative footage still totals about 63 seconds. No person identities or
timed fall windows have been independently labeled, and these clips have
already been examined. This migration improves evaluation integrity, not
detection accuracy or field reliability. Other dataset scorers still need
their own contract migrations before consuming schema 5/6. Next priority:
annotate adjacent-frame pose-to-person continuity to diagnose primary-slot
switches before changing the detector.
