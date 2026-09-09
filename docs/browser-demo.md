# Browser monitoring: tested scope and remaining work

## What runs

`/demo` is real inference, not a timed animation. A Web Worker runs pinned
MediaPipe Pose Landmarker Lite (Tasks Vision 0.10.32). The UI draws the measured
landmarks. A one-person temporal rule produces either a person-in-view event or
a possible-fall event. A fall requires upright posture, downward motion, and a
sustained horizontal posture. The displayed visibility score is **not a fall
probability**. Missing/obscured bodies and camera angles can cause misses.

Start/Stop controls own the worker, video tracks, animation loop, and recorder.
The canvas is recorded in independent approximately 10-second segments, with a
two-minute session cap. Logs and recording blobs are stored in IndexedDB, scoped
to guest or the current account. Stop retains history. Browser storage can be
cleared or evicted; download important clips.

Signed-in users also submit tenant-owned sessions, observations and footage to
`/api/v1/browser-sessions`. These reuse cameras/rules/events/alerts/recordings
tables and the existing archive storage provider. No new migration is required.
The backend treats browser observations as **client-reported, not independently
verified** and creates in-app alerts only. No arbitrary recipients, phone calls,
or physical actions are accepted. Cross-device replay requires successful cloud
uploads; local-only history is explicitly labeled. Account failures retain the
local copy and expose Retry account save. Signed playback URLs expire; reload
account history to refresh them.

## Measured local checks (2026-09-08)

Real model execution in isolated desktop Chrome, with no mocked detections:

| Video | Expected | Observed |
|---|---|---|
| Pexels person sample | Person in view | One event |
| UMAFall lateral fall excerpt | Possible fall | One event |
| UMAFall forward fall excerpt | Possible fall | One event |
| UMAFall backward fall excerpt | Possible fall | One event |
| UMAFall sitting excerpt | No fall | No event |
| UMAFall bending excerpt | No fall | No event |

Stop and page-reload tests retained the events and playable recording segments.
These few clips are development smoke tests, **not an accuracy benchmark or
evidence of medical reliability**. Do not stage a real fall to test the app.

Run `pnpm test`, `pnpm typecheck`, `pnpm lint`, and `pnpm build` in `apps/web`.
Run `pytest tests/api` in the configured Python environment. The browser harness
is `scripts/check-browser-monitor.cjs` and requires Playwright plus installed
Chrome. Set `ARTAE_TEST_FILE`, `ARTAE_TEST_JOB` (`presence`/`fall`), and
`ARTAE_EXPECT_EVENTS` (`yes`/`no`) to select a test. The model is downloaded and
SHA-256 checked by `apps/web/scripts/prepare-vision.mjs` before dev/build.

## Not complete

- Live AWS Strands/Bedrock integration: Nova 2 Lite quota is zero in this AWS
  account. A console request returned `ThrottlingException`. No successful model
  run has been observed; do not claim hackathon AWS compliance yet.
- Phone/SMS/WhatsApp delivery: not enabled in this route (Twilio work remains on hold).
- Continuous unattended monitoring, multi-person tracking, arbitrary prompts,
  validated fall accuracy, production support and emergency response.
- Cross-device recording must be verified against the deployed backend and
  storage before calling it production-ready; local API tests alone do not prove it.

The existing native YOLO/RTSP workspace is separate. Browser MediaPipe is the
no-install path; it is not YOLO and never shows fabricated YOLO boxes.
