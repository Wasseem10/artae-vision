# Browser monitoring: tested scope and remaining work

## What runs

Incident cards support Acknowledge, Mark reviewed, and False alarm. Guest reviews
persist on the device; account reviews update the existing alert and event in
one tenant-scoped transaction, using the authenticated actor. Closed incidents
cannot be silently reopened. A human review does not change the detector's
`independently_verified: false` flag. Model summaries appear only when returned
by the server; fallback status is displayed separately from success.

Bedrock account access and a production Strands incident run were verified on
September 9. The 13:05:39 production person-detection run returned a real AWS
summary and saved the account alert and recording segments. The backend uses
`VIDEO_INTEL_API_STRANDS_ROLE_ARN` and exchanges
the Vercel request's OIDC header through STS for 15-minute credentials. The role
must restrict issuer, audience, production project subject and Nova model
resources. Missing/invalid identity fails closed into the disclosed fallback.
The restricted role is created and Strands is enabled in production. It grants
only Nova 2 Lite US-profile inference to the production API project. No persistent
AWS access key was created. See [Vercel's OIDC setup](https://vercel.com/docs/oidc/aws).

`/app` now opens the browser workspace after login; the installed-camera UI is
preserved separately at `/app/native`. Named jobs and past runs load from the
account automatically. A saved job is reusable configuration, not a running
background process. Each run has independent footage and incident history.

`/demo` is real inference, not a timed animation. A Web Worker runs pinned
MediaPipe Pose Landmarker Lite (Tasks Vision 0.10.32). The UI draws the measured
landmarks. A one-person temporal rule produces either a person-in-view event or
a possible-fall event. A fall requires upright posture, downward motion, and a
sustained horizontal posture. The displayed visibility score is **not a fall
probability**. Missing/obscured bodies and camera angles can cause misses.

Start/Stop controls own the worker, video tracks, sampling timer, and recorder.
The canvas is recorded in independent approximately 10-second segments, with a
two-minute guest cap. Account users can select 2, 15, or 60 minutes; all runs stop
at 20 alerts. The 60-minute option is a configured limit, not a completed endurance
test. Logs and recording blobs are stored in IndexedDB, scoped
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

A normal Chrome session exposed compositor throttling of requestAnimationFrame:
only 14 frames were analyzed in 12 seconds, missing the fall. Frame acquisition
now uses a bounded timer independent of rendering. The same live-browser test
then analyzed 81 frames and reported one possible fall at six seconds. Model
processing time is visible in the UI. Keep the tab visible while monitoring.

API tests now enforce SQLite foreign keys, reproducing and preventing a live
PostgreSQL failure caused by inserting a rule before its camera and zone. Explicit
flush ordering also ensures an observation exists before its alert is inserted.
Replay account copy reads fresh cloud metadata and streams the remote footage,
without relying on or deleting locally recorded blobs.

Production Chrome verification on September 8: the 12-second lateral-fall sample
produced an account alert at six seconds and uploaded two WebM segments (423,013
and 67,522 bytes). Cloud-only replay loaded through a signed API URL with a
9.95-second seekable range and no video error. This confirms remote storage and
replay, not testing on every phone/browser. The private `artae-recordings` bucket
now allows `video/mp4` and `video/webm` and retains its 50 MiB per-file limit.
Uploads stage in the OS temporary directory rather than Vercel's read-only app
bundle. Retries of the same saved content are idempotent; changed content conflicts.

Run `pnpm test`, `pnpm typecheck`, `pnpm lint`, and `pnpm build` in `apps/web`.
Run `pytest tests/api` in the configured Python environment. The browser harness
is `scripts/check-browser-monitor.cjs` and requires Playwright plus installed
Chrome. Set `ARTAE_TEST_FILE`, `ARTAE_TEST_JOB` (`presence`/`fall`), and
`ARTAE_EXPECT_EVENTS` (`yes`/`no`) to select a test. The model is downloaded and
SHA-256 checked by `apps/web/scripts/prepare-vision.mjs` before dev/build.

## Not complete

- Complete hackathon submission assets, public-repository approval, and judging
  account access still need verification independently of the successful AWS run.
- Phone/SMS/WhatsApp delivery: not enabled in this route (Twilio work remains on hold).
- Continuous unattended monitoring, multi-person tracking, unrestricted prompts,
  validated fall accuracy, production support and emergency response.
- Phone/browser compatibility and separate-device sign-in testing remain;
  successful desktop cloud replay alone is not universal-device certification.

The existing native YOLO/RTSP workspace is separate. Browser MediaPipe is the
no-install path; it is not YOLO and never shows fabricated YOLO boxes.
