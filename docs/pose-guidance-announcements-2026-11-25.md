# Keep changing pose telemetry out of live announcements

November 25, 2026. The pose-coverage percentage remains visible and available
to screen-reader navigation, but is no longer inside a live status region.
Only the camera-guidance sentence has `role="status"`, so routine percentage
updates do not mutate the announced text. The existing 70% guidance threshold,
detector, alert announcements, landing page and single `/live` workflow are
unchanged.

Previously the whole paragraph was a status region. During a controlled rise
in pose coverage, each percentage change also changed its live text. The new
structure keeps the numeric metric as ordinary text and lets the guidance
change only when its existing condition changes. No telemetry is hidden from
assistive technology, and no throttling is applied to incident alerts.

## Verification

The new `scripts/check-pose-announcements.cjs` reproduces the old structure in
the previous production build, failing because the live text contains the
changing percentage. Against the updated build it passes:

- The first 30 local pose-worker results are deliberately replaced with empty
  poses, followed by real results from the sitting sample. This creates a
  controlled coverage transition without changing production inference code.
- The observer records **32 distinct percentage updates** (3% through 70%),
  while guidance has two observed text states: the original repositioning
  warning and the full-body reminder. There is only one guidance-text change.
- The numeric paragraph has no live-region ancestor. The incident feed retains
  its separate polite live region. Zero browser page errors.
- Desktop and 390 px mobile screenshots were inspected; the visible wording
  and wrapping are retained, with no horizontal page overflow.
- All **107 web unit tests**, TypeScript, ESLint and the production build pass.

```powershell
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3343/live'
node scripts/check-pose-announcements.cjs
```

The check runs in Web quality CI. Its JSON observations and screenshots are
written to `artifacts/pose-announcements/`, retained by CI when a check fails.

## Limits

This checks DOM structure and text mutations in Chromium, not the spoken output
of NVDA, VoiceOver or other assistive technology. Manual screen-reader testing
remains necessary. Repeated crossings of the existing threshold can still
change the guidance repeatedly; this change does not introduce hysteresis.
The deliberately missing poses are a UI test fixture, not measured detector
accuracy or a person-coverage benchmark.

Independent person annotations and fresh multi-person footage with longer hard
negatives remain the accuracy priority. No deployment, cloud changes or safety
claims were made.
