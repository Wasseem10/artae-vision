# Publish review completion only after the save finishes

November 1, 2026. Main remains `174346215` and PRs #16–21 remain open. PR #17's
[October 29 CI run](https://github.com/Wasseem10/artae-vision/actions/runs/40883704161)
failed at the playback suite's final saved-note assertion after reload. All
preceding guest, inference/source, storage, visibility, and playback recovery
checks passed in that run. This follow-up addresses the premature completion
signal exposed by that assertion.

## Reproduction and change

The local review handler sets the event's review fields before awaiting the
IndexedDB transaction. The existing save label says “Saving review…” during that
await, but the same event already displayed “Closed · reviewed.” The playback
test waited for that closed label and reloaded, which could happen before
storage committed. CI then read an empty reviewer note.

A controlled regression now holds the next IndexedDB-open success callback
before the review can write. On the previous production build (`bc4ae4e`), it
fails because “Closed · reviewed” is visible while the save is held. This
reproduces the premature completion signal without relying on machine speed.

While a review is pending, the event now displays “Review save pending.” The
open review dialog also announces “Saving review…” with `role="status"`.
Completed/acknowledged status is shown after the handler finishes; the existing
failure path restores the previous review if the device save fails. Report
export remains disabled during the save. The test waits for the explicit saved
label before reload, in addition to testing that closure is absent while held.

No storage format, review outcome, model, detector, landing page, or cloud
configuration changes. This is a completion-state fix in the single `/live`
review flow, not a new persistence mechanism.

## Validation

- The delayed-save assertion fails on the previous production build.
- All 93 unit tests, production build/TypeScript, changed-component ESLint,
  harness syntax and diff checks pass.
- The browser harness retains the existing real local inference/recording and
  playback faults. Only the database-open callback is held for this scenario;
  no stored bytes are replaced. The API and external network remain blocked.
- The updated production build passes in Chromium 153.0.8010.12: held saves
  show no closed/saved label, report export is disabled, releasing the save
  enables completion, and the note survives immediate reload. All four existing
  playback fault/recovery scenarios and stale-error checks pass with zero
  uncaught browser errors. The 390 px pending-save dialog was visually checked.

Reproduce after starting the production build locally:

```powershell
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3338/live'
$env:ARTAE_TEST_BROWSER = 'chromium'
node scripts/check-evidence-playback.cjs
```

## Limits and next priority

The controlled callback delay exercises application timing, not physical disk
latency or power-loss durability. Users can still leave before a save completes;
the change makes the pending state clear rather than preventing navigation.
Production account review delivery is not exercised by this guest regression.
Detector accuracy remains unchanged. Independent person/duplicate labels,
untouched multi-person footage and longer hard negatives remain the detector
promotion requirements.
