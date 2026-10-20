# Recruiter demo: monitoring, evidence, and review

October 20, 2026. This is a demonstration of the working browser workflow,
with experimental fall detection. It is not an unattended care deployment.
The landing page and single `/live` entry point stay intact.

## Walkthrough

1. Open `/live`. Keep **A possible fall** and select **Staged lateral fall**.
2. Start the agent. Show real pose overlays and the resulting possible-fall event.
3. Open **Review footage** once its recording is available.
4. Replay the evidence, enter a note, and mark the event reviewed.
5. Download the incident report. Refresh and reopen the saved session to
   demonstrate that its review and evidence persist on this device.
6. Run **Sitting · no fall expected** to show a negative control.
7. Expand **Session diagnostics** to explain the model, execution backend,
   measured inference latency, and processing throughput.

Suggested explanation:

> Artae runs a pretrained pose model in a browser worker and applies temporal
> rules to flag possible falls. It preserves video evidence and supports human
> review and report export. The staged demo works locally when the API is
> unavailable. Independent video evaluation exposed substantial accuracy and
> person-tracking limitations, which are documented rather than hidden.

The current MPFDD reference remains 2/22 fall clips alerted and 0/6 daily
activity clips alerted, with only about 63 seconds of negative footage.
Do not present this as reliable multi-person monitoring. Motion association
experiments are in PR #19; their results do not automatically change this demo.

## Reliability changes

- A 15-second wall-clock deadline covers bitmap creation and an outstanding
  inference request. A silent worker cannot leave the monitor claiming it
  is still analyzing indefinitely.
- Results must carry the timestamp of the one outstanding request. A stale
  or mismatched result stops monitoring and preserves previous evidence.
- Stop clears the deadline, terminates the worker, releases video capture,
  and reports that monitoring has stopped. Restart creates a fresh session.
- Session diagnostics show actual CPU/WebAssembly model identity and a bounded
  30-result latency/throughput window. Missing measurements are explicit.
  These are device measurements, not accuracy or person-identity confidence.
- Opening a saved session clears current-run diagnostics rather than showing
  another session's measurements.

The watchdog is a 15-second best-effort browser timer. Suspended tabs and
sleeping devices can delay it; this is not an always-on background service.
Recovery requires an explicit new session. No automatic detector/model
fallback was introduced because another model needs its own accuracy checks.

## Verification

- 88 Vitest tests pass, including four measurement tests.
- TypeScript, changed-file ESLint, and optimized production build pass.
- Three Chrome production-build scenarios pass: stalled inference after
  successful results, wrong result timestamp, and healthy inference.
  Both faults stop visibly and recover on a new session without page reload.
- Existing live-flow browser checks pass: sample fall, playable evidence,
  review persistence and export, sitting negative, upload consent, late
  mocked cloud enrichment, navigation, and mobile entry.
- Desktop 1440×1000 and mobile 390×844 captures were inspected. Expanded
  diagnostics wrap without horizontal overflow.

Tests use real MediaPipe and native recording. Failure cases inject only
the named worker-response faults. External/API requests are blocked in the
new harness. The existing enrichment test explicitly mocks cloud replies.
No real webcam, account delivery, SMS, Safari, or Firefox validation is claimed.

## Reproduce

From `apps/web`, run `pnpm test`, `pnpm typecheck`, and `pnpm build`, then
`pnpm start --hostname 127.0.0.1 --port 3320`. From the repository root:

```powershell
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3320/live'
node scripts/check-inference-health.cjs
node scripts/check-live-fall-demo.cjs
node scripts/record-recruiter-demo.cjs
```

The recording tool creates a fresh ignored `artifacts/recruiter-demo/take-*`
directory with a WebM, screenshots, an incident report, a capture manifest,
and attribution notice. It records actual inference and the automated UI
walkthrough at normal source-video speed, with cloud calls unavailable.
Keep the attribution with any shared recording; no detector output is fabricated.

## This week's acceptance criteria

- One reviewed demo branch and one link, with no competing demo instructions.
- The exact preview revision passes the sample → review → export → reload flow.
- A short recording and explanation of the architecture and measured limits.
- Any tracking candidate is compared on identical observations, with all
  regressions retained. Promote only with appropriate independent evidence.

The local workflow checks above are complete. The updated PR still needs
review and the chosen hosted revision needs a final smoke check before it is
sent to recruiters. This work does not deploy, merge, or change cloud resources.
