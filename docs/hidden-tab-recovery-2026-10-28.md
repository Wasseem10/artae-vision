# Stop monitoring when the tab is hidden

October 28, 2026. Main remains `174346215`; PRs #16–21 are still open. The
tracking experiment still needs independent person labels and untouched
multi-person footage. This change addresses a browser lifecycle gap in PR #17.

## Behavior

Previously, the page asked users to keep the tab visible but did not end a
session when the document became hidden. Background capture and inference can
be throttled independently, so an active-looking session could conceal a gap.

The monitor now listens for the document's `visibilitychange` event during
startup and monitoring. When its visibility state becomes `hidden`, it uses the
existing stop path: terminate the worker, cancel timers/loading, stop recording
and camera tracks, pause video, and retain available session evidence. The page
explains why it stopped and tells the user to keep the tab visible and start a
new session. Returning to the tab never resumes monitoring automatically.

A start attempted while already hidden is rejected before creating a session.
Stopping removes the listener, so later visibility changes cannot overwrite a
completed session's status. Cancellation checks after asynchronous audio/custom
setup prevent a stopped startup from subsequently creating a worker.

The visible setup instructions explain this behavior. There is no landing-page,
model, threshold, tracking algorithm, storage schema, or cloud-resource change.
The single `/live` flow remains in place.

## Verification

The new [browser regression](../scripts/check-hidden-monitor.cjs) runs against
a local production build using bundled Chromium 153.0.8010.12, real MediaPipe
inference and native recording. API and external requests are blocked. Page
Visibility values/events are deliberately injected; these are controlled app
lifecycle tests, not measurements of actual OS suspension or browser throttling.

| Scenario | Observed result |
| --- | --- |
| Hidden start and interrupted model loading | Hidden start creates no worker initialization. Hiding during a deliberately held initialization terminates the worker, exits loading, and allows an explicit fresh start. |
| Active staged sample | Hiding after the first review suggestion stops inference. The existing entry and playable footage survive; returning to visible does not resume. |
| Synthetic webcam | Hiding stops the worker, fake-camera tracks and recording capture tracks. A new sample session works without reloading. |

All three cases passed with zero uncaught page errors. Every case also checks
explicit restart, a harmless redundant visible event, manual stop, and listener
removal. The sample retained one review suggestion after stopping at 54 analyzed
frames in this run; this is an interruption check, not a fall accuracy result.

- All 93 unit tests pass; production build including TypeScript passes.
- Changed-component ESLint, harness syntax, and diff checks pass.
- All five existing guest workflow checks pass: navigation, staged fall with
  saved replay/review/report, sitting negative, upload privacy, and late mocked
  cloud enrichment that preserves the local review.
- Desktop and 390 px screenshots inspected. The stop explanation wraps without
  horizontal page overflow and the existing footage is playable.
- The harness is included in Web quality CI and its path filters. Failure
  screenshots/results are retained with the existing browser diagnostics.

Reproduce after starting the production build locally:

```powershell
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3336/live'
$env:ARTAE_TEST_BROWSER = 'chromium'
node scripts/check-hidden-monitor.cjs
```

## Limits and next priority

This intentionally ends monitoring when switching tabs or minimizing the
browser. It is not background or always-on monitoring. Abrupt process
termination, OS sleep, and browsers that delay lifecycle events may prevent
cleanup or final recording delivery; the change does not guarantee that footage
survives a crash. Existing storage failures can still leave evidence only in
memory. The test uses a synthetic camera and injected visibility signals, not
a physical camera, mobile app switching, or real Safari/Firefox suspension.

Detector accuracy is unchanged. Independent person/duplicate adjudication and
full pose evidence for the ambiguous overlaps in PR #19 remain the next detector
priority, followed by validation on untouched multi-person footage and longer
hard negatives.
