# External browser fall benchmark

This evaluates Artae's `/live` MediaPipe pose model and `BrowserPoseRule` on
research footage from the [UR Fall Detection Dataset](https://fenix.ur.edu.pl/~mkepski/ds/uf.html).
The university publishes 30 staged fall sequences and 40 daily activity sequences
with RGB frames from camera 0. The dataset is licensed **CC BY-NC-SA 4.0** for
noncommercial academic use. We download media only into ignored local directories;
the repository contains preparation and evaluation code, not the footage.

## Reproduce

From the repository root, use the project's Python environment with
`imageio-ffmpeg` installed (or `ffmpeg` on PATH), Node.js, pnpm, and Chrome.

```powershell
& '.venv/Scripts/python.exe' -m pip install -r scripts/requirements-benchmark.txt
& '.venv/Scripts/python.exe' scripts/prepare-urfall-benchmark.py --falls 30 --adls 40
pnpm --dir apps/web dev
# In another terminal:
node scripts/run-urfall-benchmark.cjs
& '.venv/Scripts/python.exe' scripts/analyze-urfall-trace.py artifacts/urfall/evaluation.json
```

The preparer downloads the authors' camera-0 RGB ZIPs and depth posture label
CSV, checks every archive and frame number, converts each sequence to an H.264
MP4 at the source's 30 FPS, and writes a local manifest. The manifest stores
the source and derived media hashes, citation, label provenance, and partition.
The benchmark page appears at `/evaluation/fall?dataset=urfall` while the local
manifest exists. The exported JSON records code/model revision, per-clip
detections, pose coverage, model inference time, and a compact pose trace.

The first 10 fall and 10 daily activity sequences are the **development** set.
The remaining 20 falls and 30 daily activity sequences are reserved for one
subsequent check after freezing the rule. The source does not provide subject
IDs for these sequences, so this is not a person-independent split. All results
are from staged activities by healthy volunteers, not accidental falls among
older adults.

## Comparison and scoring

Both rules consume the same MediaPipe pose result at each 0.1-second sample:

- **Temporal rule:** observed upright posture, rapid descent, then sustained
  horizontal or sufficiently large rapid center drop. `/live` uses this rule.
- **Posture baseline:** sustained horizontal posture alone. It is a deliberately
  simple ablation showing the effect of temporal information, not a reproduced
  LSTM or TCN from another repository.

The report counts a fall clip as detected if it has at least one candidate and
a daily activity clip as a false alert if it has any candidate. It reports
clip-level recall and precision, individual candidate counts, false alerts per
hour of negative footage, approximate onset-to-candidate delay, and inference
time. A candidate before labeled fall onset can still make a clip positive, so
these are **not** one-to-one event metrics. The source's depth stream marks the
first transition frame (label `0`); RGB and depth capture are not perfectly
synchronized, so onset delay is approximate. Small exposure makes hourly false
alert rates unstable.

## Development history

The five same-source UMAFall clips initially passed, but the first UR Fall clip
was missed: pose coverage was 42/54 sampled frames, and the horizontal-pose
requirement never confirmed a fall after a sharp descent. On the 20-sequence
development partition, the original rule detected 4/10 fall clips with 0/10
daily activity clips alerted. A broad descent condition raised fall detections
to 7/10 but falsely alerted on someone lying down on a bed. The frozen revision
requires the large center drop within 1.2 seconds of descent and sustained low
pose, resulting in 6/10 fall clips and 0/10 daily activity clips alerted on
that partition. The posture baseline detected 4/10 falls and alerted on 0/10
daily activity clips. These development results informed the rule, so they
must not be presented as independent test performance.

Reserved-sequence results will be recorded below after the one-time run.
