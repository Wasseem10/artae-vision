# Video source interruption handling

Follow-up: the webcam consent layout issue noted below was
[fixed and checked on October 24](cloud-consent-layout-2026-10-24.md).

October 23, 2026. This bounded change improves the existing `/live` monitor in
PR #17. Current `origin/main` (`174346215`) and open PRs #16–21 were checked;
the clean PR #17 worktree was reused, preserving the original dirty checkout.

## Failure and fix

The model-response watchdog starts only when a frame request is dispatched.
If video playback stops advancing **between** requests, no request is pending:
the UI can continue to say it is analyzing, and a file-based session limit also
stops advancing. This is a code-path finding, not a measured field failure rate.
Previously, an ended camera track had no explicit failure handling either.

The monitor now tracks video-clock progress against `performance.now()` after
startup finishes. Fifteen seconds without increasing media time with decoded
data available stops monitoring and displays a retry instruction. An ended
camera video track stops monitoring at the next sampling tick with a specific
camera-disconnection message. Short pauses can recover before the deadline.
Ordinary video completion keeps the existing final-frame grace period.

Both paths use the established stop/cleanup flow: terminate the worker, stop
the recorder and capture tracks, clear pending work, retain existing history,
and return to Start agent. A new session gets a fresh progress deadline.
The landing page, monitor layout, model, fall thresholds, and person association
rules are unchanged. No production deployment or cloud configuration was changed.

## Verification

- **93 Vitest tests in 21 files pass**, including five new source-liveness
  cases: frozen clock/deadline, brief buffering recovery, clock advances without
  decoded data, invalid/rewound media times, and independent session deadlines.
- TypeScript, ESLint for changed TypeScript files, browser-harness syntax,
  optimized Next.js production build, and diff checks pass.
- The [source browser regression](../scripts/check-video-source-health.cjs)
  uses the production build, actual local MediaPipe, native recording, local
  staged footage, and Chrome 155.0.8059.85's synthetic camera. Cloud/API and
  external requests are blocked. It never opens a physical camera.

| Browser case | Observed result |
| --- | --- |
| Sample paused after its first review entry | Source timeout stops monitoring; one existing review entry remains, earlier footage plays, worker/capture tracks are released, and processed-frame count stays stopped |
| Three-second pause, then resume | Analysis resumes; ordinary end of video does not display a source failure |
| Synthetic camera track stopped | Specific camera-disconnection message, stopped analysis, worker/capture cleanup |

Both fault cases start a fresh sitting session without reloading, analyze frames,
and finish normally. All three cases have zero uncaught browser errors.
The existing inference-health browser suite also passes all three cases: a
silent worker, a mismatched response timestamp, and a healthy control. The
source guard does not mask those model failures or prevent their recovery.
Desktop and 390 px mobile fault screenshots were inspected; the new messages
wrap without horizontal page overflow. Screenshots/results remain in ignored
`artifacts/video-source-health/`. The desktop webcam view also exposes an
existing cramped cloud-consent checkbox/text layout; this is a separate UI
follow-up, not a source-timeout regression or a claim that all layout is polished.

```powershell
# Start the production build locally first.
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3330/live'
node scripts/check-video-source-health.cjs
node scripts/check-inference-health.cjs
```

## Limits and next priority

This observes media-clock progress and track lifecycle, not the visual contents
of each frame. Repeated images with an advancing clock can still appear live.
Browser suspension/throttling can delay the sampling tick and warning; this is
not a hard real-time or always-on guarantee. Synthetic track termination is
not a physical USB-camera unplug test, and all injected failures are local.

Fall accuracy has not improved. The rejected tracking experiment and unfinished
person/duplicate annotations remain in [PR #19](https://github.com/Wasseem10/artae-vision/pull/19).
Independent review, untouched multi-person clips, and longer hard negatives
still block a detector promotion. Continue that validation work before changing
association thresholds; the next small UI fix is the webcam consent layout.
