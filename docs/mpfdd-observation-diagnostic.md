# MPFDD observation diagnostic

October 8, 2026. This is a development analysis of the same 28 staged MPFDD
clips used in the [first-look result](mpfdd-first-look-result.md), **not a new
independent accuracy test**. The clean browser replay used commit `4da4ab2`,
the pinned media hashes, MediaPipe Pose Landmarker Lite, four full-frame pose
slots, and the unchanged fused fall rule. The compact [per-clip data](benchmarks/mpfdd-observations-v1.json)
includes the exact source hashes and browser-report hash. The full frame trace
and videos stay local and gitignored.

The new evaluator trace records, at each 0.1-second sample, the number of raw
MediaPipe poses, the number with usable fall features, whether the separate
primary pose is present, and the session-local IDs returned by the fused rule.
It records no video frames, landmarks, or person coordinates.

| Observation | Result |
| --- | ---: |
| Sampled frames | 2,761 |
| Frames with at least the filename's nominal people count in raw poses | 724 (26.2%) |
| Frames with at least that many fused tracks | 527 (19.1%) |
| Clips with no frame at nominal raw-pose count | 11/28 |
| New track IDs appearing after the first second, summed across clips | 103 |
| A previously absent track ID reappearing, summed across clips | 45 |
| Fall clips with an alert | 2/22, unchanged from the first look |

The 10 clips labeled with **two fallers** have 254 of 920 frames at nominal
raw-pose count and 208 at nominal fused-track count; none alerted. Of the 12
clips labeled with one faller, six never reached nominal raw-pose count in any
sampled frame. The strongest raw-to-track gap is the activity clip
`mpfdd-s1-p2-f0-adl-1`: raw poses reached two in 100/121 frames, while the
fused rule returned two tracks in 15/121. This warrants frame annotation to
determine whether the extra raw pose represents another person, a duplicate,
or an unusable observation.

These counts do **not** measure visible-person recall or track identity
accuracy. The filename gives a scene-level people count, not who is visible in
each frame. Raw multi-pose output can duplicate a person, and the primary pose
is inferred separately before fusion. New or reappearing IDs can reflect
ordinary entrances, occlusion, duplicate detections, or broken association.
There are no person-level boxes, identities, or timed fall labels in this source.
The six activity clips cover only about 63 seconds, so zero activity alerts
does not establish a false-alert rate.

## Next experiment

Annotate visible people and matching raw poses on sampled frames from three
representative clips: a raw-to-track gap (`mpfdd-s1-p2-f0-adl-1`), a clip with
no nominal raw-pose frame (`mpfdd-s2-p2-f2-fall-4`), and a crowded four-person
clip (`mpfdd-s3-p4-f1-fall-2`). Mark occlusion, partial visibility, and
duplicate poses. Use that frame-level reference to separate pose observation
failures from fusion and track-association failures before changing the
detector. Any candidate change needs a new held-out source and longer varied
non-fall footage before a product accuracy claim.
