# Reliability checks — September 9, 2026

## Completed checks

- Real browser MediaPipe and MediaRecorder ran for two wall-clock minutes using
  a prerecorded UMAFall sitting clip through Chrome's isolated fake-camera input.
  No personal webcam or production credentials were used in this local test.
- 800 frames analyzed; no fall alert; 12 real video segments; 119.796 seconds of
  recording; 6,186,476 stored bytes. The camera stream was released at automatic
  stop, and replay remained available after reload.
- At a 390-pixel viewport, the workspace had no horizontal overflow. This is
  responsive desktop Chrome testing, not a test on an actual phone.
- Denied camera permission produced an actionable error and restored Start.
- The updated build repeated the two-minute test successfully (119.744 seconds
  recorded). With IndexedDB deliberately blocked, real person detection still
  ran and the UI warned that local history could not be saved.
- Unit regressions verify account jobs/history load even when IndexedDB fails,
  and that a failed history request does not hide separately loaded saved jobs.

## Fixes

Device history, cloud history, and saved-job loading are now independent. Local
storage failure no longer prevents loading account footage. Retrying history
also retries saved jobs. A successful account review is not treated as failed
merely because its optional device copy cannot be written. Switching accounts
clears the previous session, preview pixels, playback source, and metrics before
the new account loads.

## Still awaiting user input / not verified

- Fresh account creation and separate-device sign-in require an email controlled
  by the user and completion of any email verification. No account credentials
  are copied from one browser profile to another.
- Physical-phone recording/playback remains untested.
- The production 60-minute run has **not started**. A 3,610-second test file was
  prepared locally by looping the licensed sitting clip, but the Chrome extension
  rejected file attachment because file-URL access is disabled. The user can
  enable that extension permission or manually select the prepared file.
- No one-hour endurance or AWS-usage result is claimed from the two-minute test.

Harness: `scripts/check-browser-lifecycle.cjs`. Set `NODE_PATH` to the installed
Playwright dependency directory and `ARTAE_TEST_URL` to the local app. Prepare
`.runtime/qa-webcam.y4m` from the licensed sitting sample with FFmpeg. The harness
rejects non-local URLs and creates disposable isolated browser contexts.
