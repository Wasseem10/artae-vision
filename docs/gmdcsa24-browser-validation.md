# Separate-subject browser fall validation

We use [GMDCSA-24 v2.1](https://zenodo.org/records/13354453) as a second
source because it publishes 160 staged fall/daily-activity MP4s from four
subjects in multiple home settings. Its author CSVs include clip classes and
approximate event times. This is still acted footage by healthy volunteers,
not field footage from older adults. The source repository includes an MIT
LICENSE. Video remains in ignored local directories and is not redistributed.

## Split fixed before detector revision

- **Development:** subjects 1 and 2 (41 fall, 39 daily-activity clips). We may
  examine their outputs to design and tune the next rule.
- **Reserved:** subjects 3 and 4 (38 fall, 42 daily-activity clips). Do not run
  or inspect detector outputs on these until the next candidate and thresholds
  are committed. Run them once, record misses and false alerts, and then treat
  the set as development for any later revision.

The subject split is person-separated within GMDCSA-24 and the dataset differs
from UR Fall. It is not site-independent field validation; a few subjects and
settings cannot establish monitoring reliability. One author fall clip lacks
an onset timestamp; it remains in fall recall, but not latency calculations.

## Reproduce

From the repository root, with Node.js, pnpm, Chrome, and the project Python
environment available:

```powershell
& '.venv/Scripts/python.exe' scripts/prepare-gmdcsa24-benchmark.py --subjects 1 2
pnpm --dir apps/web dev
# In another terminal:
node scripts/run-gmdcsa24-benchmark.cjs
& '.venv/Scripts/python.exe' scripts/train-pose-window-fall.py
node scripts/check-pose-window-parity.cjs
```

The preparer downloads files from pinned source revision
`5abac7693229900cf80f722e878fbb119211fc1c`, verifies each size and Git
blob SHA-1, and records SHA-256 values in a local manifest. The runner verifies
those hashes again and exports per-clip pose traces and detector outcomes to
`artifacts/gmdcsa24/evaluation.json`. The benchmark reuses the pose worker and
rules from `/live`; it makes no AWS calls.

## Candidate built on development footage

The original browser rule, on all 80 subject-1/2 clips, detected **35/41 falls**
and alerted on **2/39 daily activities**. The posture-only ablation detected
34/41 falls and alerted on 8/39 daily activities. These are development
numbers, not independent performance.

`PoseWindowLogistic/v1` is an 11-feature causal classifier of recent pose
position, torso angle, bounding-box aspect, changes over 0.3/0.7 seconds, and
pose coverage. It requires motion and two consecutive positive samples and
discards pre-gap history after sustained pose loss. The
training script uses all 70 already examined UR Fall clips and GMDCSA subject
1, then chooses a threshold using subject 2. We expanded the threshold grid
above 0.90 after the initial range failed the preselected limit of two subject-2
daily-activity alerts; this makes subject 2 an exploratory tuning set. After
adding the pose-loss guard, the selected threshold is 0.96. On subject 2's
recorded pose traces, the candidate detected **21/25 falls** and alerted on
**0/23 daily activities**; the live temporal rule detected 21/25 and alerted
on 2/23. Python and the actual
TypeScript rule produced identical candidate events across all 80 recorded
development clips. A second run through the full browser/video pipeline on
subject 2 reproduced **21/25 falls, 0/23 activity alerts** for the candidate;
its mean approximate onset-to-candidate delay was 0.89 seconds versus 1.75
seconds for the live rule's detected falls. The candidate is evaluated alongside
`/live` but is not used to create live incidents. Both subject-2 numbers were
used in development and cannot be treated as independent accuracy.

The model JSON records feature order, coefficients, threshold, training report
hashes, and the full subject-2 threshold sweep. The training source includes
UR Fall's noncommercial academic data, so these weights remain a research
candidate; any commercial release needs an appropriate data/license review.

After freezing the next candidate, regenerate the manifest with subjects
`1 2 3 4`, commit the detector, and run the same command once on all 160 clips.
Publish a compact derived result with code and media hashes but no video or
per-frame poses. Report development and reserved results separately; do not
select a threshold using reserved outputs.

## Decision criteria

Report detected fall clips, alerted daily-activity clips, clip precision and
recall, pose coverage, and approximate onset-to-candidate delay. Count a
candidate before onset as a clip detection but mark it separately in future
event-level evaluation. Report negative exposure with hourly false-alert rate;
do not use a short staged collection as a field false-alert estimate. A rule
with many missed falls cannot be promoted to unattended monitoring even if its
few positive predictions have high precision. A supervised pilot still needs
consented site footage, delivery and evidence checks, and a separate field gate.
