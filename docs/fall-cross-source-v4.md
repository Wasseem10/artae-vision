# Cross-source fall failure audit and next detector gate

September 29, 2026. This is a development audit of sources already inspected in
earlier experiments. It does **not** provide a new independent accuracy estimate.
Run `python scripts/analyze-fall-generalization.py --output
docs/benchmarks/fall-generalization-v1.json` after preparing the local ignored
browser reports. The checked-in JSON pins each report SHA-256 and contains
aggregate results and per-case diagnostic signals, without images or pose traces.

| Source | Fall clips flagged by live temporal rule | Fall clips flagged by pose-window v1 | Daily-activity clips flagged by temporal / window rule | Daily-activity hours |
| --- | ---: | ---: | ---: | ---: |
| UR Fall | 8/30 | Not scored in this report | 1/40 / not scored | 0.080 |
| GMDCSA-24, all subjects | 52/79 | 24/38 on subjects 3–4 only | 3/81 / 2/42 on subjects 3–4 only | 0.210 |
| CAUCAFall | 17/50 | 4/50 | 0/50 / 0/50 | 0.140 |
| IMU & Video Fall/ADL | 1/35 | 27/35 | 0/60 / 0/60 | 0.063 |
| RealBiomFall | 5/100 | 11/100 | No negative clips | 0 |

These clip counts are not interchangeable with event recall. UR and GMDCSA
reports include annotated onset; CAUCAFall has event ranges. IMU-video and
RealBiomFall have only clip-level labels in this replay. RealBiomFall's 100
clips derive from six videos, so treating them as 100 independent falls would
overstate the evidence. Across all four sources with negatives, only about
0.49 hours of daily activity was analyzed—far too little to estimate normal
caregiver alert workload.

The audit records simple pose signals for each temporal miss. For example, 17
of 33 CAUCAFall misses and 18 of 34 IMU-video misses still had pose estimates
on at least 70% of sampled frames. Eleven CAUCAFall misses and 24 IMU-video
misses contained upright, descent, and horizontal signals somewhere in the
clip. These are descriptive signals, **not** proof that all three formed one
valid fall sequence. They show that increasing pose coverage alone will not
solve every miss. On RealBiomFall, 28 of 95 misses had at least 70% pose
coverage; its low-resolution source and lack of negatives remain separate
limitations.

## Multi-source development experiment

`scripts/explore-fall-multisource-logistic.py` fits the existing 11-feature
causal pose-window logistic model using annotated UR, GMDCSA-24, and CAUCAFall
traces. It balances training contribution by source and clip, and holds out
each entire source in turn. These sources and the feature family were already
examined, so this is a stress test, not a clean validation.

| Entire source held out | At threshold 0.98: fall clips flagged | Activity clips flagged | Current temporal rule on same source |
| --- | ---: | ---: | --- |
| UR Fall | 19/30 | 1/40 | 8/30 falls, 1/40 activities |
| GMDCSA-24 | 58/79 | 3/81 | 52/79 falls, 3/81 activities |
| CAUCAFall | 3/50 | 0/50 | 17/50 falls, 0/50 activities |

At threshold 0.90, the CAUCAFall fold matched 17/50 falls but flagged 2/50
activities; the UR and GMDCSA folds flagged 17/40 and 21/81 activities.
Other thresholds in the script show the same cross-source tradeoff. The
multi-source fit **fails promotion**. It is not exported to the browser or
used for caregiver alerts.

## Next gate

1. Obtain an independent, permitted video source with longer continuous
   daily-activity exposure and person/scene separation. The [Ursul dataset](https://figshare.com/articles/dataset/Sensor-Based_Fall_Detection_Dataset_with_2017_Activities_from_29_Subjects/28596332)
   is a candidate: its publisher reports 999 staged falls and 1,017 daily
   activities under CC BY 4.0. It has not been downloaded or scored here. A
   full archive is about 2.36 GB; access on this host was too slow for this
   iteration. Inspect its actual metadata and source grouping before fixing
   a holdout protocol. The newer [SAFER-Activities](https://safer-activities.github.io/)
   offers long untrimmed annotated videos, but its Hugging Face files require
   dataset terms and account access; no files were accessed.
2. Try a detector with a longer temporal sequence and explicit hard negatives
   for sitting, lying down, exercising, and bed transitions. Keep training,
   threshold selection, and the new test source separate. Record failure
   slices and negative exposure hours, not just overall clip accuracy.
3. Promote a new automatic alert rule only after a frozen browser replay on
   the untouched source improves event matches without increasing the
   predeclared false-alert workload. Until then, the live temporal alert and
   device-only review suggestion retain their current roles.

The [pilot protocol](fall-pilot-plan.md) remains the gate for any continuous
monitoring claim. These research videos are staged and cannot measure recall
on real accidental falls.
