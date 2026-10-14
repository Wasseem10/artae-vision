# Local raw-pose overlay audit

October 11, 2026. This extends the [provisional visible-person audit](mpfdd-visible-person-audit.md)
with local overlays from the unchanged browser worker, `poseFeatures`, and
`FusedMultiPersonFallRule`. It is a selected-frame development diagnosis on
already examined footage, not a new independent accuracy test or detector change.

## Capture protocol

`scripts/capture-mpfdd-pose-overlays.cjs` serves only pinned research inputs on
an ephemeral `127.0.0.1` port and runs a separate headless Chrome instance.
It does not connect to production, upload media, or change the live application.
It requires a clean committed checkout and checks the manifest, all selected
videos, detector source files, window-model file, worker, and pose-model hashes
against the earlier clean replay. It records runtime asset hashes, browser
version, capture revision, decoded timestamps, and overlay image hashes.

Use a fresh four-pose worker and fused rule per clip. Replay every 0.1-second
sample from zero through seven seconds, retaining raw and primary landmarks
only at the preselected 2, 5, and 7 second frames. Preserve full warmup; running
inference independently on just three stills would change tracking state.
White is the separately inferred primary pose; cyan, magenta, yellow, and green
are raw pose slots 0–3. Labels and skeletons are local scientific annotations,
not a new product interface.

Video responses support byte-range requests. The video is attached to the local
test page; inference waits for `requestVideoFrameCallback` and rejects a decoded
timestamp more than one millisecond from the requested sample. A one-millisecond
seek offset enters the intended frame rather than rounding down at a frame
boundary. An exploratory exact-boundary seek presented 4.066667 seconds when
4.1 seconds was requested; the guard rejected that run. Earlier exploratory
captures without presentation verification showed stale frames and are not
the basis for this diagnosis.

The archived evaluator verified logical seek times but did not record presented
frame timestamps. Therefore a count difference in this capture cannot establish
that the model, fusion, or inference accuracy improved. This harness verifies
presented timestamps for its own capture; it does not retroactively verify the
earlier benchmark's decoded frames or change its published result.

## Selected-frame findings

The clean timestamp-verified capture used `da94afa`, Chrome 155.0.8059.39,
and the pinned Lite model. All nine retained overlays were visually inspected;
their hashes and provisional interpretations are in the
[compact derived report](benchmarks/mpfdd-pose-overlay-audit-v1.json).

- **Rooftop 5 and 7 seconds:** both usable raw torso observations overlap the
  same left person. The second visible person on the right has no raw skeleton.
  The raw-to-fused reduction is therefore not evidence of fusion discarding a
  correctly detected second person. Equal counts hid a duplicated/distorted
  observation plus a missed person. At two seconds, the extra skeleton spans
  the visible person and left chair; calling it a separate chair-person
  detection would be stronger than the overlay supports.
- **Office:** the rear bent person has no raw skeleton at any selected time.
  At seven seconds the multi-pose output is empty, while the separate primary
  model still outlines the foreground person on the floor. This is evidence
  that the primary path provides an observation the multi-pose path lacks.
- **Classroom:** the two foreground people have separate raw skeletons at two
  and five seconds, while the rear people are absent from raw output. At seven
  seconds only the foreground blue-clothed person has a raw skeleton. The
  primary slot outlines the dark-clothed person at five seconds and the
  blue-clothed person at seven, while its fused ID remains 1. The primary-slot
  identifier cannot establish person identity continuity.

Counts match the archived raw/usable/fused triple on **7/9 frames**. Office
five seconds changed from `0/0/0` to `1/1/1`; seven seconds changed from
`1/1/1` to `0/0/1`. Record these differences rather than silently substituting
the new capture into the earlier report. Frame-presentation handling and
runtime/platform differences have not been isolated in a full paired replay;
the differences are not evidence of better fall detection. The earlier 2/22
fall-clip result remains unchanged.

Verification: Node syntax check and the seven existing stdlib audit tests
passed; a clean 213-sample capture produced all nine selected overlays, with
verified presented timestamps. This is a new diagnostic harness only. No
landing page, `/live`, detector, model, or threshold changed. No web UI visual
check applies; visual checks were of the nine local scientific overlays.

## Reproduce locally

Use the research media and the observation export from PR #16. Supply installed
web dependencies containing the project's Playwright and TypeScript, and the
prepared self-hosted vision runtime assets:

```powershell
node scripts/capture-mpfdd-pose-overlays.cjs `
  --media-root apps/web/public/vision/mpfdd `
  --vision-root apps/web/public/vision `
  --dependencies-root apps/web `
  --reference-report artifacts/mpfdd/evaluation-multiperson.json
```

The script now writes `capture.json` and overlays in a unique
`artifacts/mpfdd-pose-overlays/capture-*/` directory for each run. The historical
nine-frame capture remains in the original directory. Optional `--samples`
selects a pinned JSON frame list; `--output-dir` must be inside this checkout's
ignored `artifacts` directory. Empty, duplicate, unknown-case, and off-grid
selections fail before inference. Both capture revision and checkout cleanliness
are checked again before the report is written.
These full landmarks and media remain ignored and local because source video
redistribution rights are unresolved. Review the capture's revision and input
hashes before interpreting it; a failed run must not be mistaken for an earlier
successful capture already in that directory. Only a compact derived report
and provisional interpretation are published.

## Next priority

Human-adjudicate the provisional visible-person labels and pose matches. Add
presented-frame timestamp checks to the full evaluator and compare its complete
per-clip results against archived runs before relying on it for another frozen
candidate. Do not tune alert thresholds based on these selected frames; a new
held-out source and longer negative exposure remain required for promotion.
