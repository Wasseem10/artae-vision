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
