# First-look multi-person video result

September 29, 2026. The [protocol](mpfdd-evaluation-protocol.md) and browser
evaluator were committed as `b669f921` before detector output was opened.
Both paths then replayed all 28 hash-verified videos available at the pinned
[MPFDD repository revision](https://github.com/Hnnuliulei123456/MPFDD/tree/ec6cbcd81ed27e745ba5f6918192d7ec302d31c2).
The [per-clip report](benchmarks/mpfdd-first-look-v1.json) records alert times,
track counts, pose coverage, source hashes, and the clean Git revision without
redistributing video.

| Browser alert path | Fall clips with an alert | Daily-activity clips alerted | Median inference per sampled frame |
| --- | ---: | ---: | ---: |
| Original one-pose temporal rule | **2/22** | **0/6** | 22.04 ms |
| Fused primary plus additional-person rules | **2/22** | **0/6** | 58.68 ms |

Both paths alerted on exactly the same two clips, each labeled with one
faller. Neither alerted on any of the **10 clips labeled with two fallers**.
The other 12 positive clips are labeled with one faller; two alerted. The
six activity clips total only **0.0175 analyzed hours, or 63 seconds**.
Zero alerts over one minute does not establish a field false-alert rate or
justify the observed clip precision as a product claim. The labels contain
no onset/end times or faller identities, so this is clip-level hit rate,
not event or person-level recall. The source footage is staged.

## Failure diagnosis

At least one pose was available on an average 96.8% of sampled frames per
clip, but this is **not coverage of every person**. In 11 of 28 clips, the
largest number of simultaneous tracked observations was below the number of
people in the filename. In 16 of 28 clips, the session produced more track
IDs than the nominal number of people. Those counts suggest missed people,
duplicate observations, or broken track continuity; they cannot distinguish
which without person-level ground truth. Local frame inspection also showed
distance, furniture, and occlusion in the shared-room scenes.

The alert times in the paired report are identical for the two successful
clips, and both fused alerts used the primary path (track 1). The additional
tracks added no detected fall clip in this source. The old posture-only
diagnostic flagged 6/22 falls and 0/6 activities, but those 63 seconds of
negative video are far too little to promote a less constrained rule.

## Decision

Keep the deployed browser rule as a **human-reviewed prototype** and do not
claim multi-person accuracy. This first-look source is now examined; changing
the detector and replaying these clips would be development work, not a new
independent test. The next candidate should improve per-person observation
and association before fall classification. A useful comparison is a person
detector followed by cropped pose inference and explicit track continuity,
benchmarked against the current full-frame MediaPipe path. Before promotion,
obtain footage with person-level fall timing/identity labels, longer varied
non-fall exposure, a documented license, and an untouched test source.

The [source paper](https://doi.org/10.1038/s41598-025-86429-6) describes the
full MPFDD collection, but the public repository currently exposes only 28
of the described 220 videos and states no video license. Local research media
and its manifest remain ignored by Git and are not deployed.
