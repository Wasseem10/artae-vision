# Keep playback loading until an incident frame is ready

October 29, 2026. Main remains `174346215`; PRs #16–21 are open. Yesterday's
hidden-tab change passed hosted Linux [Web quality](https://github.com/Wasseem10/artae-vision/actions/runs/40760045292)
at `b76671b` in 6m6s. This follow-up fixes an initial evidence playback gap.

## Reproduced defect and fix

The previous player canceled its 15-second deadline on `loadedmetadata`,
applied the incident seek, and immediately dismissed loading. Metadata can
arrive while the requested frame is unavailable or seeking. The stuck player
then lacked timeout/retry feedback unless a native media error also arrived.

The new regression failed on the previous production build: loading had
disappeared while the controlled player reported `readyState: 1` and
`seeking: true`. The fix retains the deadline until the initial seek has been
applied, a frame is available (`readyState >= 2`), seeking has ended, and no
native error exists. Loaded-data, can-play and seek-completion events check
these conditions. Native errors and failed seek setup still provide immediate
feedback. Retry creates a new player for the same recording and offset.

No detector, model, landing page, cloud resource, or workflow changes are
involved. This extends the existing evidence player in `/live`.

## Verification

The [playback regression](../scripts/check-evidence-playback.cjs) exposes a
controlled metadata-only/unfinished-seek state on one player after native
metadata arrives. Native media continues decoding underneath. This tests the
application's readiness gate, not bandwidth, actual decoder starvation, or
field failure frequency.

On the updated local production build in Chromium 153.0.8010.12:

- Loading stays visible during the injected stall; the 15-second deadline
  exposes Retry. Retry restores native playback at the expected incident offset
  (within the harness's 150 ms tolerance) and retains the review draft.
- Existing corrupt-byte, missing-HTTP-recording and held-response cases pass.
  Corrupt bytes remain honestly unplayable after retry; healthy stored footage
  recovers. Late errors from a removed player do not replace the new result.
- Keyboard retry restores player focus. Review save/reload retains the note
  and healthy local footage. Zero uncaught browser errors.
- Desktop and 390 px timeout screenshots inspected; page/dialog have no
  horizontal overflow. Screenshots and results remain in ignored
  `artifacts/evidence-playback/`.
- All 93 unit tests, production build/TypeScript, changed-component ESLint,
  Node syntax, workflow YAML parsing and diff checks pass.

The suite uses real local inference/native recording and isolated IndexedDB.
API and nonlocal requests are blocked. HTTP recovery uses a range-capable
staged MP4 fixture; it tests seek/retry mechanics, not production signed URLs.
The full playback suite now runs in Web quality CI, with path filters, the
existing bounded browser step, and failure artifact collection.

```powershell
# Build and start the app locally first.
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3337/live'
$env:ARTAE_TEST_BROWSER = 'chromium'
node scripts/check-evidence-playback.cjs
```

## Limits and next priority

The deadline covers initial readiness, not later buffering stalls or subsequent
seeks on an already-open player. A late frame may recover the current attempt
before Retry. Retry cannot repair corrupt media, renew expired URLs, or provide
unsupported codecs. Browser suspension can delay timers.

Fall accuracy is unchanged. Independent person/duplicate adjudication and full
pose/context evidence for ambiguous overlaps remain prerequisites for another
tracking change. Untouched multi-person footage and longer hard negatives are
still required for any promotion claim.
