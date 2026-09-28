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
```

The preparer downloads files from pinned source revision
`5abac7693229900cf80f722e878fbb119211fc1c`, verifies each size and Git
blob SHA-1, and records SHA-256 values in a local manifest. The runner verifies
those hashes again and exports per-clip pose traces and detector outcomes to
`artifacts/gmdcsa24/evaluation.json`. The benchmark reuses the pose worker and
rules from `/live`; it makes no AWS calls.

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
