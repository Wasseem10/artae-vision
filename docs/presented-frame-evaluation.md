# Presented-frame verification for browser evaluations

October 12, 2026. `/evaluation/fall` now waits for a presented video frame
before making its inference bitmap. `/live`, the landing page, model files,
fall thresholds, and person tracking rules are unchanged.

## Contract

`seeked` and `currentTime` alone describe a logical seek, not proof of the
frame actually supplied to inference. The evaluation-only helper uses
`requestVideoFrameCallback` to record decoded `mediaTime` and `presentedFrames`.
It seeks one millisecond past a frame boundary, then checks the actual decoded
timestamp before making a bitmap.

- Allow at most 50 ms of decoded-frame lag and 2 ms of lead relative to the
  requested sample. These are explicit quantization bounds, **not exact-frame
  identity proof**. Lower-FPS or unusual sources may need another declared
  sampling protocol rather than silently enlarging these bounds.
- Reject unsupported browsers, invalid timestamps, stale/future frames outside
  the bounds, decode errors, cancellation, and a 15-second presentation timeout.
- Retain `presentedFrameTrace` for every analyzed sample. Completion and export
  require the full inclusive 0.1-second sampling schedule, increasing presented
  frame counters, and nondecreasing decoded times. A malformed clip fails the
  run; completed rows remain available without an aggregate score or export.
- Feed the rule the original requested timeline, preserving its temporal
  contract. Store the decoded timeline separately so quantization is auditable.

This verifies sampled input timing. It does not analyze every source video frame
or establish whether every visible person was detected.

## Full MPFDD development comparison

Two clean, committed replays ran on the same local host in overlapping sessions.
The old seek-only path used `bda5679` (the observation diagnostic branch); the
presented-frame path used `80182da`. Five detector/model source hashes and all
seven served worker/runtime/model asset hashes matched. The source manifest and
all 28 video hashes were identical. The before branch adds observation logging
but uses the same production rule and worker.

| Sampling method | Fall clips alerted | Activity clips alerted | Sampled frames |
| --- | ---: | ---: | ---: |
| Seek-only baseline | 2/22 | 0/6 | 2,761 |
| Presented-frame verification | 2/22 | 0/6 | 2,761 |

All per-clip alert times and counts of frames with at least one fused pose were
identical in this pair. The new trace passed verification for all **2,761**
samples. Maximum decoded lag was **49 ms**; 14 samples differed from their
requested time by more than 1 ms, demonstrating why decoded times must be
retained rather than assumed equal. There was no decoded lead in this run.

The [per-clip comparison](benchmarks/mpfdd-presented-frames-v1.json) records
exact report hashes, source/runtime hashes, revisions, alert times, pose-frame
counts, and per-clip lag/lead bounds. Full exports and videos stay local and
ignored. Initial exploratory replays had a dirty flag because Next dev rewrote
the generated `next-env.d.ts` route import. Those exports were retained locally
and excluded from this comparison; both runs were repeated with clean sources.

These clips were already examined. The six negative clips total **63.071666
seconds**, far too little for a field false-alert rate. There are no timed fall
windows or person identities, so these are clip alerts, not event/person recall.
The older runner did not export its browser version, and overlapping sessions
are not a latency/performance experiment. This result improves measurement
integrity; it does not demonstrate an accuracy improvement or justify promotion.

## Export compatibility and reproduction

The new exports use **schema 5** for the original path and **schema 6** for the
fused path. Provenance includes `frameSampling.method: "presented-frame-v1"`
and its timing bounds. Strict older scorers expect schema 3/4 and must be
deliberately migrated to validate this trace before consuming a new report.
Changing just their expected version would discard the new timing contract.

The CLI writes `evaluation-presented-v1.json` or
`evaluation-multiperson-presented-v1.json` under the dataset's artifact folder;
it does not overwrite the archived seek-only filenames. The runner now checks
clean sources at start and finish, unchanged revision, and records browser
version for future exports.

Prepare the pinned local media, commit the implementation, and start the local
app. If Next dev regenerates `next-env.d.ts`, inspect the diff and restore only
that generated route-import change after startup; preserve any unrelated work.
Then run:

```powershell
$env:ARTAE_BENCHMARK_URL = 'http://127.0.0.1:3000'
node scripts/run-mpfdd-benchmark.cjs
```

Verification: 16 focused unit tests passed; TypeScript and targeted ESLint
passed; both full 28-clip browser replays completed. Functional checks exercised
the evaluation page's run, completion, and JSON download. The screen layout is
unchanged; no web UI visual comparison was needed for this data-path change.

Next: migrate the strict scoring tools to the new sampling contract, then use
adjacent-frame person labels to evaluate primary-slot identity changes and
duplicate observations. A new held-out source and longer negative exposure
remain necessary before any detector promotion.
