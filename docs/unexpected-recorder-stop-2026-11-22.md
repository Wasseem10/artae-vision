# Keep an unexpected recorder stop visible

November 23 follow-up: [review without footage](review-without-footage-2026-11-23.md)
replaces the disabled incident action with a review path that explicitly
discloses missing video. Recording interruption behavior below is unchanged.

November 22, 2026. An unsolicited `MediaRecorder` stop now ends recording with
the existing failure message, keeps any usable final segment, and requires a
fresh session to record again. Pose inference continues independently.

## Failure and change

Previously, `onstop` rotated to a new recorder unless the controller had already
been stopped or failed. A native stop without a controller request could silently
create another recorder on the same stream. A segment shorter than 200 ms was
discarded without reporting a problem, so even short interruptions could retry.

The controller already records an end time when it requests a ten-second
rotation, a user stop or error cleanup. A stop event without that end time now
marks recording as failed. Final nonempty bytes of at least 200 ms are retained
before reporting failure. Duplicate stop events remain ignored, capture tracks
are released once, and no replacement recorder starts automatically.

Normal ten-second rotation and explicit stop retain their existing behavior,
including clean sessions shorter than 200 ms. This does not stop detection,
change alert rules or alter the landing page or `/live` layout.

## Verification

- Two new unit cases reproduce the old restart at 100 ms and 1.5 seconds. They
  fail on the previous implementation and pass after the change, checking one
  failure, one recorder, one track release, no outstanding timers and retention
  of the longer segment. Existing rotation, short-stop, timeout and late-byte
  cases also pass.
- All **107 web unit tests**, TypeScript, ESLint and the production build pass.
- `scripts/check-unexpected-recorder-stop.cjs` runs real local inference and a
  native recorder. It deliberately calls the recorder's `stop()` outside the
  controller after about 1.5 seconds. The page reports recording failure while
  detection continues, and the retained segment decodes successfully.
- A later staged-sample incident remains detectable but its unavailable footage
  is disclosed and Review footage stays disabled. No automatic recorder restart
  occurs; capture tracks end. An explicit new session records again and produces
  reviewable incident footage. Zero browser page errors.
- Desktop and 390 px mobile screenshots of the failure message and retained
  playback were inspected. No horizontal page overflow. Screenshots and JSON
  results are written to `artifacts/unexpected-recorder-stop/`.

The browser check runs in Web quality CI, with diagnostics retained on failure.
To repeat it against a local production build:

```powershell
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3342/live'
node scripts/check-unexpected-recorder-stop.cjs
```

## Limits and next priority

The browser check injects a controlled native stop; it does not reproduce a
particular device, operating-system or encoder failure. Retained bytes are not
guaranteed decodable for every real interruption. Clips shorter than 200 ms
remain discarded. Detection can continue without new recorded evidence, and
the UI explicitly discloses that limitation.

No new fall-accuracy result or production reliability claim is made. Independent
person/duplicate annotations, untouched multi-person footage and longer hard
negatives remain the detector's next gate. No deployment or cloud changes.
