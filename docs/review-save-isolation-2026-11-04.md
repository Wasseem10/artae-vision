# Failed reviews stay out of background recording saves

November 4, 2026.

## Reproduced failure

The review handler previously changed the shared incident before awaiting its
device save. Recording finalization independently saves that same session. If
the review's database open was delayed, a background recording save could commit
the proposed outcome first. Failing the review save then restored the in-memory
incident but left the failed outcome in IndexedDB.

The new browser regression fails against the preceding production build at
`d8792be83427b08800e1a961d5ea86215aa2bbea`. The stored outcome was `resolved`
when the expected prior outcome was absent, despite the review error in the UI.

## Change

Guest reviews and device-only suggestions now save a separate session/event
snapshot containing the proposed review. The shared incident receives that
review only after the write completes. Background recording saves can therefore
retain footage without including an outcome whose own save has failed. A failed
attempt leaves the previous review and editable draft available for retry.

The pending state keeps the existing outcome actions disabled and shows the
saving message. A newly resolved incident's report button appears after its
write completes. Account alert reviews continue to use their existing remote
save path.

## Verification

`scripts/check-review-save-isolation.cjs` uses real local MediaPipe inference,
native recording and IndexedDB. It holds one review database-open callback,
allows recording finalization writes to commit, then injects an error into that
specific open. Other database operations remain native. Requests to external
services and the API are blocked.

Two cases pass in Chrome `156.0.8078.80` against the updated production build:

| Prior outcome | Background commits while review waits | Stored clips | Result after failed review |
| --- | ---: | ---: | --- |
| No review | 2 | 2 | No review persisted |
| Acknowledged | 2 | 2 | Acknowledgment retained |

Both cases retain the note draft, expose an enabled retry action, and preserve
the successful retry's outcome and note after reload. There are zero page
errors. The 390 px dialog screenshots were inspected, and both dialog overflow
checks pass. Local evidence is in ignored `artifacts/review-save-isolation/`.

Type checking, ESLint, all 93 unit tests and the production build pass. The
existing playback regression also checks that a pending new review does not
expose a downloadable completed report. The new isolation regression is included
in Web quality CI, including failure-artifact retention and path triggers.

The first hosted run, [41884490486](https://github.com/Wasseem10/artae-vision/actions/runs/41884490486),
passed the existing browser suite and the new open-incident case, then failed
waiting for the injected error in the acknowledged case. The fixture initially
armed the next database open before Playwright dispatched the review click,
allowing an intervening recorder write to consume it. Arming now happens in the
click's capture phase, immediately before the review handler, with an explicit
pending-review assertion. Both cases pass locally in the CI-matching Chromium
`153.0.8010.12` after this correction. The application assertions remain intact.

## Scope and next gate

This is a controlled write-order regression, not a measurement of physical disk
failure or browser crash recovery. The browser checks exercise guest review;
device-only suggestions share the changed branch, while authenticated account
review is outside this run. Draft notes are retained only while the page stays
open. Cross-tab write coordination remains outside this change.

Detector accuracy remains subject to independent person/duplicate adjudication,
untouched multi-person validation and longer hard-negative footage. No detector
weights, thresholds or accuracy results are changed by this persistence fix.
