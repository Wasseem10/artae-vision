# Recording failure isolation

October 16, 2026. This follow-up improves the existing `/live` evidence workflow.
It preserves the landing page, monitor layout, model, and fall rules. Current
main and open PRs were checked before work; this update continues PR #17 in its
clean worktree, preserving the original checkout's unrelated edits.

The accuracy gate still needs adjudicated person/timed-event labels, untouched
clips, and longer negative footage. PR #19 records the primary-history failure
analysis. This change addresses a separate concrete demo reliability problem
without promoting a detector or changing accuracy claims.

## Failure found in the existing recorder

The previous MediaRecorder setup lived inside the detector startup's outer
try/catch. A supported MIME type could still fail during canvas capture,
recorder construction, or `start()`, stopping detection along with recording.
Runtime `onerror` displayed a shared save warning, but `onstop` unconditionally
started the next recorder; a broken encoder could repeatedly restart. Review
or save actions could clear that shared warning. Missing-event footage also
continued to say it was recording after the session had stopped.

These are code-path findings, not measured field failure rates.

## Changes

- Extract a [segmented recording controller](../apps/web/src/lib/segment-recorder.ts)
  that owns the canvas capture stream, segment rotation, finalization, and
  cleanup. Detection retains its separate worker and source video stream.
- Catch capture, constructor, and start failures locally. A recorder error
  ends recording and releases its capture tracks while pose detection continues.
  Do not automatically restart a failed recorder.
- Bound finalization to five seconds after a stop request. Mark stalled or
  empty recording output failed instead of leaving indefinite progress text.
  A later finalized nonempty segment can still be retained.
- Preserve previously finalized segments and recover nonempty final bytes.
  Freeze segment end time when requesting stop, before video teardown can
  reset the source clock. Stop is idempotent; duplicate completion and late
  errors from already completed segments cannot restart or fail a later segment.
- Show recording failures beside Recorded footage with `role="alert"`.
  Keep their state separate from review/account-save errors and scope callbacks
  to the owning session. Only active healthy recording or finalization shows
  pending-evidence text. Stopped/failed sessions with missing footage explicitly
  say that no recording is available.
- Retain the existing ten-second rotation interval, MIME preference, bitrate,
  local persistence, and account-save queue. No database or API schema changes.

## Verification

All checks use local code and existing staged sample footage. No deployment,
paid-resource change, production write, or real user camera was involved.

- **84 Vitest tests in 19 files pass**, including ten new recorder lifecycle
  cases: normal rotation/final flush; frozen end time and duplicate stop;
  error recovery with existing footage; late completed-segment error;
  constructor/start/stop rejection; empty output; finalization timeout with
  late data; and a deliberately short stopped session.
- TypeScript, ESLint for changed TypeScript files, Node syntax check for the
  browser harness, optimized Next.js production build, and diff checks pass.
- The new [browser regression](../scripts/check-recording-failure.cjs) passes
  five isolated Chrome scenarios against that production build, using real
  MediaPipe and native MediaRecorder with explicit fault injection. All API
  calls and nonlocal requests receive HTTP 503.

| Browser scenario | Recorder constructions | Result |
| --- | ---: | --- |
| Canvas capture throws | 0 | Detection progresses; missing event evidence is explicit |
| Recorder constructor throws | 1 | Detection progresses; capture tracks released |
| Recorder start throws | 1 | Detection progresses; capture tracks released |
| Runtime error after first complete segment | 2 | Detection progresses; no retry loop; earlier footage plays |
| Healthy recording control | 2 | Normal rotation and stop; footage plays |

All five scenarios have zero uncaught browser errors and release their capture
tracks. Each fault case verifies at least five additional analyzed frames after
the recording warning. Constructor/capture/start cases also wait for a real
staged-fall incident and verify that its unavailable footage does not retain
the recording-progress message.

The runtime-error case deliberately slows the source playback to 0.5x to leave
time for observation after the first segment. Its segment metadata follows
source time; this injected condition is not an evidence-seek accuracy test.
The error event is injected into a functioning native encoder, so this does not
establish recovery from actual hardware/codec corruption.

The existing full live-demo smoke test also passes: normal staged fall with
playable evidence, persisted review details and exported incident report after
reload, sitting negative, uploaded video without cloud-review consent, delayed
mock cloud enrichment preserving review, and public/mobile navigation. This
checks the ordinary playback-rate path with the API unavailable or mocked.

Desktop and mobile screenshots of the failed-recording state were inspected
at 1440×1000 and 390×844. Failure feedback, retained segment controls, and native
playback remain visible; the mobile page has no horizontal overflow. Local
screenshots stay ignored under `artifacts/recording-failure/`. Layout and theme
are unchanged.

## Reproduce

From the repository, install existing web dependencies, build, and start the
local production server on port 3320. In another terminal:

```powershell
pnpm --dir apps/web exec vitest run
node scripts/check-recording-failure.cjs
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3320/live'
node scripts/check-live-fall-demo.cjs
```

The new harness refuses a nonlocal test URL. Its network routes prevent real
API/cloud operations, and its browser contexts do not use the user's session.

## Limits and next priority

The [October 17 playback follow-up](evidence-playback-reliability-2026-10-17.md)
now adds native media error/timeout feedback and manual retry in both evidence
players, with review drafts preserved and keyboard focus returned to playback.

The checks establish these local failure paths and regressions, not unattended
monitoring reliability. Historical recordings keep their existing storage
format; the detailed recorder error is current-page state and is not persisted
across reloads. A nonempty blob from a genuinely damaged encoder may still be
unplayable; the injected runtime-error test does not establish otherwise.
Real account saves, SMS delivery, hardware camera failure, and screen-reader
behavior were not tested here.

The live fall result remains 2/22 MPFDD fall clips and 0/6 activity clips, with
only about 63 seconds of negative footage. Next accuracy work remains evaluating
an observable person-association/reset candidate with adjudicated identities
and frozen before/after video results. Next evidence reliability work is
explicit native-playback error/retry feedback for unavailable or corrupt media.
