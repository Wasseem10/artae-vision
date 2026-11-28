# Recover from a stalled browser-storage connection

November 27, 2026. A device review could remain on **Saving review…** indefinitely
when its IndexedDB open request delivered neither success nor error. The same
unbounded connection setup was used for history and recording persistence.
An open request rejected as blocked could also later succeed and leave an
unowned database connection open.

## Change

`openSessionDatabase` now gives connection setup a 15-second deadline. Success,
error and blocked responses settle once and clear that timer. If a timed-out or
blocked request later opens a connection, the helper closes it without returning
it to a caller. A deferred schema upgrade after rejection is aborted. IndexedDB
has no API to cancel a pending open request, so late-event cleanup is necessary.

Existing callers retain their failure behavior: review actions become available
for explicit retry, the unsaved draft stays in memory, and no completion outcome
is applied before persistence. History and recording writes use the same bounded
connection helper. The database name, version, stores and indexes are unchanged.

## Verification

- The new browser check on the previous production build (`6013c6f`) reached
  **Saving review…** but failed its 20-second wait for a recoverable error.
- All 112 web unit tests, TypeScript, ESLint and the production build pass.
  Five new unit cases exercise timeout, successful setup before the deadline,
  version-change cleanup, blocked/deferred upgrades, open errors and retry.
- The production-build browser check uses a synthetic stored guest incident and
  holds one native IndexedDB success callback. After the deadline it verifies
  the visible error, retained note, enabled retry, and unchanged review outcome.
  Releasing the late callback closes the abandoned connection; a separate native
  read confirms that it did not persist the failed review. An explicit retry
  saves the outcome and note, both of which survive reload.
- Desktop and 390px mobile dialog screenshots check the error presentation and
  wrapping. The browser script asserts no horizontal dialog overflow or page errors.

Run from the repository root with a local production server:

```powershell
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3344/live'
node scripts/check-storage-open-timeout.cjs
```

The script blocks external and API requests. Results and screenshots are written
to `artifacts/storage-open-timeout/`. Web CI runs this regression before the
existing workflow checks and retains its artifacts on failure. Its browser-step
budget increases from eight to nine minutes to accommodate the real 15-second
deadline; the overall job remains bounded at 15 minutes.

## Limits

This bounds **connection setup**, not transactions that stall after a successful
open. The browser timer can be delayed by a suspended page or OS. The controlled
callback fixture is not proof of recovery from real disk faults, browser crashes
or every multi-tab upgrade scenario; blocked-upgrade branches are unit tested.
Drafts remain in memory until a successful save and can be lost on reload before
retry. No inference, detector, notification policy, account API or deployment
changes are included. Independent person labels and longer hard-negative footage
remain the accuracy priority.
