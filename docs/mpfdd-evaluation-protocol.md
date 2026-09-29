# First-look MPFDD browser evaluation protocol

Frozen before viewing detector output. Source: [MPFDD public repository](https://github.com/Hnnuliulei123456/MPFDD),
Git revision `ec6cbcd81ed27e745ba5f6918192d7ec302d31c2`.

The repository README describes 220 videos of two to five people. At this
revision, its Git tree exposes **28 MP4s** totaling 73,046,860 bytes: 22
filename-labeled fall clips and six daily-activity clips. The videos show
two or four people; the accessible set does not include a five-person scene.
The source has no stated license. Preparation downloads the files only to a
gitignored local directory, verifies each Git blob, and records SHA-256 values
in a local manifest. Neither media nor the manifest is published or deployed.

Run the committed browser evaluator at 0.1-second sampling, once with the
one-pose temporal rule and once with the fused primary plus additional-person
rules. Both must use the same frozen code revision, model, videos, and browser.
The primary metric is **fall clips with at least one alert / 22**. Record
**daily-activity clips with at least one alert / 6**, the number of activity
alerts, and the total analyzed activity duration. Break out fall clip hits by
the nominal number of fallers in the filename. Record pose coverage, observed
track counts, per-clip alert times, and inference time for diagnosis.

The filenames give scene, number of people, nominal number falling, and
fall/ADL class. They do **not** give fall onset/end or the identity of each
faller. Accordingly, this protocol cannot score person-level recall, event
latency, or identity-switch errors. Multiple alerts in a positive clip do not
prove that multiple fallers were detected. Six short ADL clips cannot support
a field false-alert rate. The footage is staged and cannot establish
unattended monitoring reliability. Do not tune on the first-look result and
then call a replay independent validation.

The scorer rejects incomplete runs, changed manifest/media hashes, dirty Git
trees, changed detector rule IDs, and mismatched revisions. It writes a compact
per-clip report without video or pose coordinates.
