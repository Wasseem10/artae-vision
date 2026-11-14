# Preserve reported fall provenance across devices

November 13, 2026. Newly saved browser fall events can now retain their reported
detection source in account history. Reopening the account copy can restore
temporal-rule/pose-window agreement without requiring the original device's
local record.

## Contract and behavior

The browser sends its stored `detectionSource` as optional `detection_source` in
the existing observation request. The API accepts `temporal_rule` and
`temporal_and_pose_window` only for fall sessions. It stores the supplied value
in event details together with `detection_source_origin: client_reported` and
keeps `independently_verified: false`. This is recorded client metadata, not a
second inference run, identity proof or server verification.

Presence sessions cannot claim fall provenance. Unknown labels and the
device-only `pose_window_v1` source are rejected before an event is created.
Existing request payloads without the optional field remain accepted. No
database migration is needed because event details already hold JSON metadata.

Save, review and account-history responses share the same source mapping in the
web client. Older API responses that omit the field do not erase the source on
an existing device event. The earlier same-device history merge remains useful
for old records. An idempotent retry returns the original event and never
rewrites its provenance or creates a second alert.

## Verification

- **19 browser-session API tests pass**, including seven new parameterized cases
  for both accepted sources, a legacy request, three rejected labels and a
  presence-session mismatch. Accepted metadata survives create, review and
  history responses. Retrying with a different source retains the original
  metadata and one alert. Tests use an isolated SQLite database and test client.
- **104 web unit tests pass**. New cases check the outgoing payload, account-only
  history-to-report mapping, explicit source replacement and compatibility with
  older API responses. Existing same-device fallback tests still pass.
- TypeScript, ESLint, Ruff for the changed API/test files, and the production
  build pass. The API test process explicitly imports this worktree's API source
  via `PYTHONPATH`, rather than the older editable checkout in the shared venv.
- Report rendering assertions cover the recorded agreement and review outcome.
  No UI markup, styling or layout changed; existing visual checks remain
  applicable. Hosted web verification is linked in PR #17.

## Limits and rollout

This change is committed for review, not deployed to production. Both API and
web updates are needed for newly saved events to retain this field across
devices. Previously saved events are not backfilled; a retry does not amend
them. The browser has no new evidence to recover provenance that was never
stored. These tests do not verify production account delivery or improve fall
accuracy. Independent person labels and untouched multi-person validation
remain the next detector gate.
