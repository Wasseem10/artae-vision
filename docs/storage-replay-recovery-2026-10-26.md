# Preserve current footage after a device save failure

October 26, 2026. Latest main remains `174346215` and PRs #16–21 remain open.
PR #17's previous web CI run passed. Detector promotion still needs reviewed
person/duplicate labels and independent multi-person footage; this change
addresses a concrete evidence-recovery defect in the existing `/live` flow.

## Defect and fix

History rows intentionally omit video blobs. After a failed IndexedDB write,
the current in-memory session can be the only copy containing playable footage.
Previously, clicking that session's history row could replace it with metadata
returned by an empty local lookup. The click also cleared the save warning.

Reopening the current session now retains its in-memory object when both the
session ID and scope match, and keeps any existing save warning visible. Other
sessions continue through the normal storage lookup; an explicitly requested
account-only replay continues through its original cloud path. The guest status
now says “this browser only,” and replay says “Session history,” instead of
implying that an in-memory recording is durably saved.

No IndexedDB schema, detector, model, alert threshold, landing page, or external
service configuration changed. The original dirty checkout was preserved.

## Verification

The new [browser regression](../scripts/check-storage-failure-replay.cjs) uses
real local inference and native recording with API/external requests blocked.
One isolated context injects `QuotaExceededError` on device write transactions;
another permits normal writes. These are controlled write failures, not an
exhausted physical disk or a field storage-failure rate.

On the final local production build, bundled Chromium 153.0.8010.12 verified:

- Failed writes: an existing fall review entry survives two history clicks,
  footage remains playable, and a **440,170-byte segment** downloads. The save
  warning stays visible. Reload correctly shows no saved history.
- Normal writes: footage replays and downloads; after running a separate sitting
  session, selecting the earlier fall session still loads the correct events
  and footage. That footage also survives reload.
- Both cases produce zero uncaught browser errors. The 390 px failure view was
  visually checked and has no horizontal page overflow.
- Production build including TypeScript, changed-component ESLint, harness
  syntax, YAML parsing, and diff checks pass.

The regression is included in web CI and its path filters. Available results,
screenshots, sample-derived downloads, and attribution are included with failure
diagnostics; local copies live in ignored `artifacts/storage-failure-replay/`.
The download size describes one test run, not a compression/performance claim.

```powershell
# Start the production build locally first.
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3335/live'
$env:ARTAE_TEST_BROWSER = 'chromium'
node scripts/check-storage-failure-replay.cjs
```

## Limits and next priority

This preserves the current session during same-session replay. It cannot make
a rejected write durable: reload, closing the tab, starting a new run, or
switching away can still discard unsaved in-memory footage. Download it first.
Account persistence and physical storage exhaustion were not exercised by this
guest test. Fall accuracy remains unchanged; reviewed labels and fresh
multi-person/hard-negative footage remain the next detector gate.
