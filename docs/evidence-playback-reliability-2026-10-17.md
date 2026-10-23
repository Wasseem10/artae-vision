# Evidence playback failures and manual retry

October 17, 2026. This continues PR #17 from its clean worktree after checking
current `origin/main`, open PRs, the product plan, and PR #19's latest tracking
evidence. Detector promotion still lacks adjudicated identities/timed events,
untouched test footage, and longer negatives. This bounded change improves
the existing evidence/review workflow; it changes no model or fall threshold.

## Problem and change

The monitor previously rendered native video controls without application
feedback for missing/corrupt recordings or a media request that never completed.
A caregiver could see a blank or buffering player with no recovery action.

Both Recorded footage and the incident dialog now use a shared
[EvidencePlayback component](../apps/web/src/components/evidence-playback.tsx).
It provides:

- Explicit loading status and a 15-second initial metadata-load deadline.
- Visible `role="alert"` feedback for native media download/decode/source
  errors and initial-load timeout. Error messages expose no raw URL or exception.
- A manual **Retry playback** button that creates a fresh native player for
  the same source and incident offset. There is no automatic retry loop.
- A separate component lifetime per attempt and recording URL, preventing
  late callbacks from a removed player from replacing the new attempt's state.
- Keyboard retry with focus returned to the replacement native player.
- Pause the captured old player on removal, without pausing its replacement.
- Existing download controls, incident state, and review drafts retained
  through failure, retry, closing, and reopening the dialog.

The landing page, monitor layout/theme, recording controller, detection worker,
review decisions, persistence schema, and cloud APIs are unchanged. A playback
failure does not complete or discard a review.

## Local browser verification

The [new browser regression](../scripts/check-evidence-playback.cjs) runs against
an optimized local production build in an isolated Chrome `155.0.8059.80` context.
It uses real MediaPipe, native recording/playback, the existing staged lateral
fall sample, and real local IndexedDB. All API and nonlocal requests receive
HTTP 503; no production account, user camera, paid service, or production deployment is used.

Three new fault/recovery scenarios pass:

| Scenario | Verified behavior |
| --- | --- |
| Invalid recording bytes | Native error becomes visible; retrying the same corrupt blob still fails honestly; selecting healthy stored footage recovers |
| Missing HTTP recording | First response is 404; keyboard retry fetches playable fixture media; focus and incident offset are preserved; draft remains |
| Held HTTP response | Initial load times out at 15 seconds; manual retry succeeds; releasing the old response and dispatching a late old-player error does not replace the new result |

The run also verifies explicit review save and reload after those failures:
the saved note and healthy local recording remain available. There are **zero
uncaught browser exceptions**. Desktop/mobile timeout screenshots were inspected
at 1440×1000 and 390×844; failure text and retry remain readable, and neither
page nor dialog has horizontal overflow. Screenshots stay ignored under
`artifacts/evidence-playback/`.

The HTTP success fixture supports byte-range requests and uses the existing
staged MP4. This verifies retry/seek mechanics, not production signed-URL
renewal, account authorization, or exact incident content in a remote recording.
An initial HTTP fixture without byte-range support remained at time zero and
failed the seek assertion; that fixture was corrected and is excluded from the
passing results. The range-capable run verifies the requested offset within
150 ms. Seeking on arbitrary non-seekable servers is not established here.

Additional verification passes:

- All **84 existing Vitest tests** in 19 files.
- TypeScript, ESLint on changed TypeScript/TSX, Node syntax, diff checks, and
  optimized Next.js production build.
- Existing full live-demo smoke test: staged fall → playable recording → review
  → reload → incident report; sitting negative; uploaded footage without cloud
  consent; delayed mocked enrichment preserving review; public/mobile navigation.

No new fall-accuracy or field-reliability result is claimed. The live MPFDD
result remains 2/22 fall clips and 0/6 activities, with about 63 seconds of
negative footage.

## Reproduce

Build and start the local production app, then run from the repository:

```powershell
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3320/live'
node scripts/check-evidence-playback.cjs
node scripts/check-live-fall-demo.cjs
pnpm --dir apps/web exec vitest run
```

The new script refuses a nonlocal test URL. Its response mocks and injected
object URLs exist only in its disposable browser context; stored recording
bytes are not altered by the corrupt-playback test.

## Limits and next priority

Retry reloads the same source; it cannot repair corrupt bytes, renew an expired
account URL, or make unsupported codecs playable. The deadline covers initial
metadata loading, not every later buffering stall. A late valid metadata event
may recover the existing attempt before a user retries. Detailed playback errors
are page-local and are not added to persisted incident records.

Only local Chrome behavior is verified. Safari/Firefox, real account media,
actual encoder corruption, and screen-reader announcements remain untested.
Next accuracy work remains person-association/reset evaluation with adjudicated
labels and frozen video comparisons. Next media work is source refresh for
expired account links and explicit handling of unsupported seeking/buffering.
