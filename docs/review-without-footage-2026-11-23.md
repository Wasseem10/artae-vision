# Review an incident when footage is missing or pending

November 23, 2026. An incident without playable footage now opens the same
review dialog through **Review incident**. Available recordings keep the
**Review footage** action. This removes the dead end where missing video also
prevented acknowledging an alert, saving notes or recording an outcome.

## Behavior

- Opening an incident without matching footage clears the previous player.
  It shows no stale video or evidence-download link, and does not claim that
  playback starts before the event.
- A notice distinguishes unavailable footage from a recording still being
  prepared. It states that saving an outcome does not verify the event or
  establish that footage was reviewed. Notes and outcomes use the existing
  persistence and export path.
- If matching footage arrives while the dialog is open, a status message and
  **Open available footage** action appear. Opening it preserves the draft;
  it never silently replaces the reviewer’s context.
- Exported reports continue to describe the evidence available at export time.
  A missing-recording fixture exports the existing explicit no-matching-metadata
  limitation. The outcome is a reviewer declaration, not video verification.

No detector, cloud/API behavior, landing page or second monitoring workflow was
introduced. The original missing-footage notice remains in the event feed.

## Verification

The browser regression reproduced the old disabled action, then passed against
the updated production build. Using local synthetic session metadata and actual
sample video, it covers containing footage, bounded gaps on either side, and no
matching footage. The missing case checks no player/download link, notes,
acknowledgment, saved outcome, HTML report disclosure, and persistence after a
full page reload. The original three playback/gap checks still pass.

The controlled native-recorder interruption check also passes: inference
continues after recording fails, earlier bytes remain playable, and missing
incident footage stays explicit. In the recovered session, a held native stop
callback keeps evidence pending while a review draft is entered. Releasing it
offers the new footage in the open dialog; decoded playback and the draft are
both verified. The callback hold is test-only and is not a production delay.

All **107 web unit tests**, TypeScript, ESLint and the production build pass
locally. Both browser checks report zero page errors. Missing-footage dialog
screenshots were inspected at 1400 px and 390 px, with no horizontal overflow
and reachable review actions. Existing event-count checks now count both action
labels so missing footage cannot hide an incident from those regressions.

```powershell
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3341/live'
node scripts/check-review-recording-gap.cjs
node scripts/check-unexpected-recorder-stop.cjs
```

The scripts remain in Web quality CI. Screenshots and JSON results are stored
under `artifacts/review-recording-gap/` and `artifacts/unexpected-recorder-stop/`.

## Limits and next priority

This does not recover missing video, confirm a fall or prove that a caregiver
checked the person. Reports describe the export-time snapshot; they do not
record which frames a reviewer watched. Drafts remain in memory until an
outcome is saved. Account delivery and other browser/assistive-technology
combinations require separate verification.

Independent person/duplicate annotations and untouched multi-person footage
with longer hard negatives remain the accuracy gate. No deployment, production
data changes or improved-accuracy claim was made.
