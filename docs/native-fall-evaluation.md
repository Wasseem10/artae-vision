# Native fall candidate baseline

`scripts/evaluate_native_fall.py` runs each finite local video through the inference
service's **YOLO pose model → tracked pose observations → PersonFallRuleEngine** replay
path. It calls `run_replay` with the `specialized_pose` execution strategy, rather
than the browser's MediaPipe rule or a scripted demo detector. No cloud provider is
called. Supply clips you have permission to process; the five included staged
UMAFall excerpts are described in `docs/calibration-sources.json` and built by
`scripts/prepare-browser-samples.py`.

Run from the repository root with Python 3.11 and the
`services/inference/pyproject.toml` dependencies installed. Pass a **local** pose
model file; the script does not download one implicitly. In PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path 'services/inference/src').Path
& '.venv/Scripts/python.exe' scripts/evaluate_native_fall.py `
  --model 'C:/path/to/yolo11n-pose.pt' `
  --clip apps/web/public/vision/samples/fall-lateral.mp4 `
  --clip apps/web/public/vision/samples/fall-forward.mp4 `
  --clip apps/web/public/vision/samples/fall-backwards.mp4 `
  --clip apps/web/public/vision/samples/sitting.mp4 `
  --clip apps/web/public/vision/samples/bending.mp4 `
  --dataset-name UMAFall-staged-samples `
  --device cpu `
  --output artifacts/native-fall-baseline.json
```

Omit `--output` to emit JSON on stdout. Model and clip paths are validated before
loading the inference runtime. The CLI also verifies that the imported inference
modules come from this checkout, so the recorded source hashes describe the code
that ran. Corrupt media, undecodable frames, and incomplete replay fail with an
error and produce no baseline file. If the environment reports
`torchvision::nms` is missing, inspect whether torchvision's native extension can
load. On the development host used for this baseline, PyTorch 2.13.0+cpu and
torchvision 0.28.0 are paired, but Windows Application Control blocks
`torchvision/_C.pyd` with WinError 4551. This is a host policy block. Run the
baseline in an approved inference environment where that extension can load; no
candidate results are available from the failed attempt.

The JSON records each clip's SHA-256, duration, source FPS, frame count, number of
frames processed, candidate timestamps and intervals, plus the model SHA-256,
configuration, and hashes of the relevant native inference source files. The
candidate times are the alert emission times in video seconds. This is **unlabeled
candidate output**: it cannot supply recall, precision, false alerts per monitored
hour, or field reliability. Those measurements require independently labeled,
held-out footage across people, cameras, rooms, lighting, and ordinary activities.

## Score against adjudicated labels

`scripts/score_native_fall.py` needs only the candidate JSON above and a **separate**
ground-truth manifest. Review the entire duration of every clip, including clips
with no falls. Have two independent reviewers mark visible fall onset and end,
resolve disagreements, and lock the labels and matching window before looking at
the detector output. Use the same `dataset_name` and the exact clip SHA-256 and
duration from the candidate report. Do not put names or other personal information
in the manifest or filenames. Keep the clips and labels in access-controlled
storage; only use footage you have permission to evaluate.

```json
{
  "schema_version": 1,
  "kind": "native_fall_ground_truth",
  "dataset_name": "permissioned-held-out-set-v1",
  "dataset_role": "held_out",
  "review_status": "independently_adjudicated",
  "clips": [
    {
      "clip_sha256": "<64 lowercase hex characters from the candidate report>",
      "duration_seconds": 42.0,
      "reviewed_full_duration": true,
      "falls": [{"start_seconds": 12.4, "end_seconds": 15.8}]
    },
    {
      "clip_sha256": "<different clip SHA-256>",
      "duration_seconds": 60.0,
      "reviewed_full_duration": true,
      "falls": []
    }
  ]
}
```

Choose `dataset_role` as `staged_regression`, `held_out`, or `field` based on
how the footage was obtained. This is a declared provenance category, not
independent proof of representativeness. The CLI rejects missing or extra clip
hashes, duplicate clips, partial reviews, mismatched durations, invalid event
times, and incomplete replay. A clip with `falls: []` counts as a reviewed
negative only when `reviewed_full_duration` is true.

Predeclare the acceptable alert delay, optional early tolerance, and sample-size
minima in the pilot protocol. For example, if the chosen gate is 100 labeled
falls and 300 analyzed camera-hours:

```powershell
& '.venv/Scripts/python.exe' scripts/score_native_fall.py `
  --candidates artifacts/native-fall-baseline.json `
  --labels C:/permissioned/locked-fall-labels.json `
  --max-alert-delay-seconds 5 `
  --early-tolerance-seconds 0 `
  --minimum-falls 100 `
  --minimum-analyzed-hours 300 `
  --output artifacts/native-fall-score.json
```

The scorer matches a candidate's **alert emission time** to a visible fall
onset at most once within the declared window, maximizing the number of matched
events. A second candidate for the same fall is a false alert; an alert after
the maximum delay is a false alert and the fall is missed. The JSON includes
per-clip matches, misses and unmatched candidates, event-level recall, false
alerts per **analyzed** hour, median and nearest-rank p95 detection latency,
and analyzed, nonfall, and fully negative clip hours. It hashes both input
JSON files. Recall is `unmeasured` when there are no labeled falls; latency is
`unmeasured` when no fall is matched. A point estimate below a declared
sample-size minimum is marked `insufficient_data`, even if it happens to be
100% recall or zero false alerts. Meeting a count minimum is not a statistical
confidence or product-readiness decision.

The report also includes **two-sided 95% exact count intervals**: a
Clopper–Pearson interval for event recall and an equal-tail Poisson interval for
false alerts per analyzed hour. With no labeled falls, recall and its interval
are `unmeasured`. With zero false alerts over one analyzed hour, the rate point
estimate is zero but the 95% Poisson interval still extends to about **3.69
false alerts/hour**; more exposure narrows that bound. Bounds are rounded
outward to six decimal places. The recall interval assumes the labeled events
are independent and representative; the Poisson rate interval assumes a
constant-rate count process. Falls and false alerts may cluster by person,
room, camera, activity, or time, so these intervals alone do not establish
field performance. Report those strata and review the sampling plan separately.

The score covers completed offline replay only. It has no scheduled-hours
denominator and cannot measure camera outages, lost notifications, evidence
playback, or caregiver response. Those require the supervised pilot log and
end-to-end checks in [the pilot plan](fall-pilot-plan.md). The five staged sample
clips remain a regression check, even if a score file is generated for them.
