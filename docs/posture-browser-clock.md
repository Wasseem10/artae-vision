# Browser clock and source-aware startup

October 20, 2026. This checks a prerequisite for the new source's browser
evaluation. **No detector inference, fall-accuracy result, or model change is
included.** The landing page and `/live` are unchanged. The source-aware plan
is tested in an offline harness; it is not integrated into the evaluation UI.

## Measured result

The harness uses the exact seven hash-verified videos from the
[full decode report](benchmarks/posture-media-v1.json), and the unchanged
`seekPresentedFrame` helper from PR #20 at
`f670e4bf1a0202514ab6ad3a5d5d07fbb136806b`. It loads that committed TypeScript
directly from Git, fingerprints it, and transpiles it for the local browser.
It never imports pose models or runs a fall rule.

On Chrome **155.0.8059.85** on this Windows host:

- All **14 first/last frame observations** matched the raw decoded PTS clock,
  within a predeclared two-microsecond tolerance. The largest observed absolute
  difference was about **0.333 microseconds**. Subtracting the first video PTS
  did not match those browser observations.
- All seven direct startup requests at time **0** were rejected by the
  unchanged strict helper. Their first video frames are 13.1–59.4 ms later;
  the helper allows only 2 ms of frame lead.
- Requesting each file's **verified first PTS** with the same helper succeeded
  on **7/7 files**, presenting the first frame in a fresh player each time.
  These are startup-compatibility outcomes, **not fall detection rates**.

| Video | Scheduled tick | Source-aware request (s) | Request at zero | Verified-start request |
| --- | ---: | ---: | --- | --- |
| `fall_detection_4` | 0 | 0.0278 | Rejected | Accepted |
| `fall_detection_5` | 0 | 0.0131 | Rejected | Accepted |
| `fall_detection_6` | 0 | 0.0361 | Rejected | Accepted |
| `fall_detection_7` | 0 | 0.0210 | Rejected | Accepted |
| `fall_detection_8` | 0 | 0.0594 | Rejected | Accepted |
| `fall_detection_9` | 0 | 0.0557 | Rejected | Accepted |
| `fall_detection_10` | 0 | 0.0568 | Rejected | Accepted |

This agrees with the API's presentation-timestamp semantics in the
[WICG `requestVideoFrameCallback` draft](https://wicg.github.io/video-rvfc/#dom-videoframecallbackmetadata-mediatime).
The local evidence establishes correspondence at the sampled endpoints only;
it does not prove pixel identity, every interior frame, other browsers, or
how the dataset author timed the annotations.

## What changed

`scripts/posture-clock.cjs` adds a caller-side plan that preserves
`scheduledSeconds`, `requestedSeconds`, and `verifiedFirstPTS` separately.
It requests the first available verified video timestamp for a tick before
that timestamp; later ticks stay on the original media timeline. It rejects
invalid or out-of-source bounds. It does not infer an offset from an arbitrary
callback or widen the helper's stale/future-frame limits.

`scripts/check-posture-video-clock.cjs` serves only the seven pinned media
files over a temporary loopback server, with full/HEAD/range/suffix handling.
It verifies media hashes before and after the run and requires clean unchanged
code. Page requests outside that local origin cause the experiment to fail.
The server and private test browser close when the run finishes or fails.

The probe records the first frame, a completed near-end seek, and a fresh
source-planned startup. An intermediate run was rejected for an endpoint
mismatch and published no aggregate report. Tail capture was strengthened to
require a completed seek and a presented near-end frame, retaining all callback
observations rather than classifying a queued initial observation as the tail.
The clock hypotheses are compared afterwards, not used to select callbacks.

## Evidence and verification

- The [checked-in report](benchmarks/posture-browser-clock-v1.json) pins the
  source-lock/media-report hashes, both new script hashes, sampler revision and
  hash, Node, TypeScript, Playwright, Chrome, and compositor launch arguments.
- It was captured from clean commit
  `481c999b901959b4f8e237f89caf0aa140ed4bc7`. Two final runs produced identical
  report bytes: SHA-256
  `f2b255f4f151547f16b4270f144ace9f4ba1877eec75283d242b489925f0cb97`.
- **11 Node tests** pass for clock hypotheses, unmatched/ambiguous observations,
  source-aware planning, byte ranges, and the complete recorded source roster.
  The existing **34 Python tests** also pass, including the real decoder test.
- There were no browser/server errors or nonlocal page requests in the final
  runs. A default Chrome launch closed before connection; the recorded software
  compositor configuration succeeded. No existing user browser was controlled.

Reproduce after acquiring the videos with the [media tool](posture-media-preflight.md).
Install the web project's development dependencies (Playwright and TypeScript),
or set `ARTAE_PLAYWRIGHT_ROOT` to a directory containing those installed packages.
Use a clean committed checkout and a fresh output filename:

```powershell
git fetch origin codex/evaluation-presented-frames
node scripts/check-posture-video-clock.cjs --sampler-ref f670e4bf1a0202514ab6ad3a5d5d07fbb136806b --output artifacts/posture-clock-new.json
node --test tests/benchmarks/posture-clock.test.cjs tests/benchmarks/posture-clock-evidence.test.cjs
```

The [full media report](posture-media-preflight.md) documents the separate Python
verification command and optional decoder dependency.

## Remaining accuracy gate

The browser endpoints support using the raw media timeline in this runtime.
**The annotator's clock and actual event boundaries remain unverified.** The
earlier first-frame-zero convention was diagnostic; it must not silently become
the scoring clock. Review timed falls, recovery, deliberate lying/sitting,
unassigned intervals and the disputed CSV rows against a player with a known
clock. Preserve the raw labels and put reviewed corrections in a sidecar.

Only after that review should the source-aware start plan enter the full
continuous evaluator, with both scheduled and actually presented timestamps
retained in its export, before the frozen detector comparison. This one-person
dataset still cannot validate multi-person tracking or field reliability.
