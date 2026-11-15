# Keep the latest session selection visible

November 8, 2026.

## Reproduced failure

Opening saved sessions performs asynchronous device and optional account reads.
Previously, every completed read could replace the current session, incident
feed, replay and status. Selecting A, then B, could end on A if A's read finished
last. A delayed history read could also replace a newly started monitoring view.

The new browser regression fails against the preceding production build at
`89173469de515a65b2539989d534c5dad1196c0a`. It holds A's native IndexedDB read,
opens B, then releases A. A's incident incorrectly reappears in the current feed.
The two saved incident records are synthetic fixtures, not detector outputs.

## Change

Each history selection receives a request number. Before applying a result or
error, the monitor checks that the request is still the latest, the component
is mounted, the session belongs to the current account scope and live monitoring
is inactive. Starting a new monitoring session invalidates pending selections.

Load warnings stay local to their request until it is allowed to update the
view. A superseded failure cannot replace the newer session's status. A current
failure still displays its warning and retains the existing metadata fallback.
The guard also avoids starting a cloud read when its local-read result has
already been superseded. Already-started reads are allowed to finish normally.

## Verification

`scripts/check-history-load-order.cjs` runs against a local production build. It
uses native IndexedDB and delays one selected read's success callback. API and
external requests are blocked. The live-start case temporarily holds the local
model download, releases the old history read during startup, then lets the
actual model load and stops the session explicitly.

Four cases pass in Chromium `153.0.8010.12`:

- A slow older selection cannot replace the newer selection's incident feed.
- An older read failure cannot replace the newer selection or its status.
- A pending history result cannot replace a new live session's loading view;
  the session subsequently reaches the analyzing state.
- A current read failure still displays the storage warning and metadata.

All cases produce zero page errors and pass a 390 px horizontal-overflow check.
The mobile history screenshot was visually inspected. Screenshots and the
machine-readable results remain in ignored `artifacts/history-load-order/`.
The regression is included in Web quality CI with path triggers and retained
failure screenshots.

TypeScript, ESLint, all 96 existing web unit tests, the production build, harness
syntax and diff checks pass locally. No detector score is inferred from the
synthetic history records or the model-startup check.

## Limits and next priority

The browser checks cover guest device history. Authenticated account transitions,
remote history latency and cross-tab writes require separate verification. The
request guard ignores stale results; it does not cancel database operations or
change evidence retention.

Independent person/duplicate labels, untouched multi-person footage and longer
hard negatives remain prerequisites for the next detector promotion decision.
