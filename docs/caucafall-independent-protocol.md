# Independent CAUCAFall detector check — frozen protocol

Frozen before viewing any CAUCAFall detector outcomes on September 28, 2026.
The purpose is to test cross-source generalization of the current browser
fall rule and two pose-window research candidates. It does not authorize
unattended monitoring or a medical claim.

## Source and separation

- [CAUCAFall v4](https://data.mendeley.com/datasets/7w7fccy7ky/4) supplies
  100 AVI videos from ten participants: five simulated fall activities and five
  daily activities per participant. The dataset is CC BY 4.0.
- [OmniFall v3](https://huggingface.co/datasets/simplexsigil2/omnifall)
  supplies time intervals for the fall action. Its annotation file is pinned
  to revision `83572a37b9e3081df8c06a56874b1d1f2a19386c` and SHA-256
  `a5169d3e95b26080527265516d415d068a83c3dea4cddca8d0828a8d2345fd3a`.
  OmniFall labels are CC BY-NC 4.0.
- All 100 CAUCAFall videos form one **untouched cross-source holdout**. No
  CAUCAFall frames or outcomes enter training, threshold selection, or rule
  edits. Participant videos and detailed local reports remain Git-ignored.
  The hash-verified local manifest SHA-256 is
  `b984a772a641d225479b3416e0c77f75fe649827f8adb0e696fd844524bada54`.

The source video SHA-256, transcoded MP4 SHA-256, subject, activity, and event
interval are recorded per clip in the local manifest. Browser replay checks
each MP4 hash before running. MediaPipe samples every 0.1 seconds, as in the
prior browser benchmarks. Transcoding changes the container and compression
but preserves frame dimensions and timing; the browser decodes the MP4.

## Frozen detectors

| Detector | Frozen implementation |
| --- | --- |
| Live temporal rule | `BrowserPoseRule/fall-v2`, unchanged from `/live` |
| Static posture ablation | `PostureOnlyFallRule`, unchanged |
| Pose-window v1 | `fall-window-model.json` SHA-256 `f87a5c88b6a38954997faea80b1b626fd9ea77f5906730ac79a26eddae030aba`, threshold 0.96 |
| Pose-window v2 | `fall-window-model-v2.json` SHA-256 `1e582441b19cc72b28585ab17935555077d20a384d70bfa6ded6e16edbc45bb0`, threshold 0.98 |

V2 uses the same 11 causal pose features and runtime as v1. It retrains on all
previously examined UR Fall clips and GMDCSA-24 subjects 1–3. The already
examined GMDCSA subject 4 selects a threshold using the existing rule:
at most 10% of its daily-activity clips may alert, then maximize fall clips
detected. Its validation was 9/17 falls and 1/20 activity clips alerted,
equal to v1's original browser count on that subject. Neither pose-window
candidate makes live incidents.

## Predeclared scoring

- **Clip score:** a fall clip is positive if it has any alert; an activity
  clip is a false positive if it has any alert. This repeats the earlier
  benchmark for comparison, even though it ignores alert timing.
- **Event score:** one alert matches one labeled fall if it occurs from the
  annotated start through two seconds after the annotated end, capped at the
  video duration. Every other alert is unmatched. Report matched-event recall,
  unmatched alerts, precision, and median/p95 delay from action start.
- **Activity exposure:** sum all decoded daily-activity clip durations and
  divide alert count by those analyzed hours. Report the numerator and hours;
  this short staged exposure is not an operational false-alert estimate.
- Publish every clip's category, event interval, pose coverage, and each
  detector's alert times. Do not omit hard cases or retune on this result.

If v2 performs better, it remains experimental. A promotion decision would
also need longer negative footage, more camera conditions, and a supervised
shadow pilot. If it performs worse, record the failure and use this source
only for later development; a subsequent candidate needs a different fresh
holdout.

## Reproduce locally

Install an ffmpeg executable and `pyarrow` for Python. Set `ARTAE_FFMPEG` to
the executable if it is not on PATH. Then run:

```powershell
node scripts/prepare-caucafall-videos.cjs
python scripts/build-caucafall-manifest.py
python scripts/train-pose-window-fall-v2.py
node scripts/check-pose-window-parity.cjs
pnpm --dir apps/web dev
# In another terminal:
node scripts/run-caucafall-benchmark.cjs
python scripts/score-caucafall-events.py
```

The preparation script verifies the published source SHA-256 for each AVI and
the pinned OmniFall label file. It downloads only the 100 AVI videos, converts
them to browser-playable MP4, and leaves the original and converted research
media on the local machine.
