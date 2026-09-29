# Chair confusion and shared-room fall check

September 29, 2026. The automatic fall alert path uses the on-device
MediaPipe Pose Landmarker **Lite** model to estimate body joints. A temporal
TypeScript rule checks a sustained upright pose, descent, and down posture.
The separate pose-window model can suggest footage for local human review,
but cannot issue an automatic caregiver alert on its own. Optional AWS Nova
reviews an already captured possible-fall sequence; it is not needed for the
on-device alert.

## People-free chair scenes

The repeatable `pnpm --dir apps/web test:chair` check replays two CC0 scenes
containing empty chairs: [three empty chairs](https://commons.wikimedia.org/wiki/File:Empty_Chairs.jpg)
and an [empty classroom](https://commons.wikimedia.org/wiki/File:Empty_class_room.jpg).
For each image it feeds 31 static frames and 31 frames with a gentle digital
pan into the same four-pose browser worker used by the live fall monitor.

| Pose model | Scenes and motion variants | Frames with a raw person pose |
| --- | ---: | ---: |
| Lite, live model | 4 | **0/124** |
| Full, comparison model | 4 | **0/124** |

The test fails on even one raw pose, before the stricter shoulder/hip
visibility and fall-motion gates. These frames show no chair/person confusion
in these two scenes. Different chairs, viewing angles, lighting, occlusion,
or actual camera movement still need testing with room-specific footage.

## Larger pose model comparison

We replayed the 28 locally hash-verified MPFDD shared-room clips with the
same fused multi-person fall rule and 100 ms sampled video timestamps. Only
the MediaPipe pose bundle changed. This source was already examined, so the
comparison is development evidence, not independent validation.

| Bundle | Fall clips alerted | Activity clips alerted | Median clip inference time | Frames with any pose |
| --- | ---: | ---: | ---: | ---: |
| Lite, current live | **2/22** | **0/6** | 58.68 ms | 96.63% |
| Full | **2/22** | **0/6** | 74.59 ms | 97.14% |

Full gained one fall clip and lost a different one, with no net improvement.
The Full replay JSON SHA-256 is
`0cb03477d29c4d92eae284d773a95617735ea264bd5bca62f50c2ec7e17c505c`.
The [original MPFDD result](mpfdd-first-look-result.md) has clip-level
details and limitations. **Keep Lite in the live path**: switching to Full
would spend more CPU without improving detection on this shared-room source.

## Person detector followed by cropped pose

We also tested a research-only browser worker that uses Google's
[EfficientDet-Lite0 Object Detector](https://developers.google.com/edge/mediapipe/solutions/vision/object_detector)
to find up to four `person` boxes, then estimates a pose separately in each
crop. It preserves the existing single-person Lite pose path as a baseline.
The same 28 MPFDD clips and fused fall rule were replayed. The experiment
worker is in `scripts/experiments/person-crop-pose-worker.js`; the object
model is downloaded with `node scripts/prepare-person-crop-experiment.cjs`
and stays out of Git. Its SHA-256 is
`2e04c53bfeac0ac2a30c057c7e2a777594ce39baaac35a92f74fb1e8c4fc4e0b`.
Set `ARTAE_BENCHMARK_PERSON_CROPS=1` when running
`node scripts/run-mpfdd-benchmark.cjs` to repeat the comparison locally.

| Observation path | Fall clips alerted | Activity clips alerted | Median clip inference time | Frames with any pose |
| --- | ---: | ---: | ---: | ---: |
| Current full-frame Lite | **2/22** | **0/6** | 58.68 ms | 96.63% |
| Person boxes + cropped Lite | **2/22** | **0/6** | 126.67 ms | 99.13% |

The cropped path saw poses in more frames but found **no additional fall
clip**. Its only two alerts were the same primary-person alerts as the
current worker. Median processing exceeded the 100 ms frame interval used
by this replay. The candidate JSON SHA-256 is
`1fdfa8ef22d05a00daf93d2e1b5d45132031ea57c6e1e955d61b6e9b6691e288`;
the candidate worker SHA-256 is
`e4f4a6435dc10fbde59b3f38c1494bd9d8eab64d1d3f43640ea838ee84019ad7`.
**Do not switch the live monitor to this worker.** The remaining problem is
person continuity and fall classification in crowded footage, not merely
whether some pose exists somewhere in a frame. These clip-level labels also
cannot identify which person's fall was missed.
