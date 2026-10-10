# Visible-person frame audit

October 10, 2026. This follows the observation diagnostic in
[PR #16](https://github.com/Wasseem10/artae-vision/pull/16). Nine frames from
three already examined staged MPFDD clips received **provisional AI-assisted
visual counts**. These are not independently adjudicated ground-truth labels.
The [annotations](benchmarks/mpfdd-visible-person-labels-v1.json) record the
counting rule, selection, per-frame notes, media hashes, and exact input hashes.
The [generated comparison](benchmarks/mpfdd-visible-person-audit-v1.json)
compares those counts with the unchanged clean observation replay `4da4ab2`.

## Selection and inspection

Use the three representative clips proposed by the observation diagnostic:
the rooftop activity with a raw-to-track gap, the two-faller office miss,
and a four-person classroom. Inspect fixed 2, 5, and 7 second samples from
each. These times were chosen before assigning visible counts, but the clips
were selected because of known failures: this is purposive development analysis.

Count a distinct visible physical person, including partial occlusion and floor
postures. Exclude someone fully outside the frame, furniture, reflections, and
screen images. Each saved frame was visually inspected at its original 1060×516
resolution. Source video hashes were checked before extraction.

The rooftop and office clips use 30 FPS; the classroom uses **20 FPS**. The
extractor uses each source's FPS and verifies decoded timestamps. Assuming
30 FPS would produce classroom frames at 3, 7.5, and 10.5 seconds instead of
the requested 2, 5, and 7 seconds. Initial exploratory frames using that wrong
assumption were replaced before annotation; no counts from them were retained.

## Observed count gaps

| Clip | Time | Provisional visible people | Raw poses | Fused tracks |
| --- | ---: | ---: | ---: | ---: |
| `mpfdd-s1-p2-f0-adl-1` | 2 s | 1 | 2 | 1 |
| `mpfdd-s1-p2-f0-adl-1` | 5 s | 2 | 2 | 1 |
| `mpfdd-s1-p2-f0-adl-1` | 7 s | 2 | 2 | 1 |
| `mpfdd-s2-p2-f2-fall-4` | 2 s | 2 | 1 | 1 |
| `mpfdd-s2-p2-f2-fall-4` | 5 s | 2 | 0 | 0 |
| `mpfdd-s2-p2-f2-fall-4` | 7 s | 2 | 1 | 1 |
| `mpfdd-s3-p4-f1-fall-2` | 2 s | 4 | 2 | 2 |
| `mpfdd-s3-p4-f1-fall-2` | 5 s | 4 | 2 | 2 |
| `mpfdd-s3-p4-f1-fall-2` | 7 s | 4 | 1 | 1 |

Six frames have fewer raw poses than provisionally visible people; eight have
fewer fused tracks. The rooftop 2-second frame has **one visible person** despite
the filename's scene-level count of two, yet two raw poses. This demonstrates
why filename counts alone are an inadequate frame reference. It does not
prove that a chair was detected as a person: the extra pose could be a duplicate
or another false observation. The export contains no landmark coordinates or
per-pose identity matches to resolve that question.

Equal raw and visible counts at rooftop 5 and 7 seconds also cannot prove both
people were detected: a missed person plus a duplicate could produce the same
count. Reductions after fusion warrant pose-to-person matching; count gaps alone
do not distinguish duplicate suppression, missing observations, or association
errors. No person recall, precision, tracking accuracy, or fall accuracy is
reported from these nine selected frames.

## Reproduce

Scoring requires only Python's standard library. Use the pinned local manifest
and the clean observation export from PR #16; current main's earlier evaluator
does not export `observationTrace`. Run from the repository root:

```powershell
python scripts/audit-mpfdd-visible-people.py `
  --labels docs/benchmarks/mpfdd-visible-person-labels-v1.json `
  --manifest apps/web/public/vision/mpfdd/manifest.json `
  --report artifacts/mpfdd/evaluation-multiperson.json `
  --output artifacts/mpfdd-visible-person-audit.json
```

The supplied labels pin the full report hash; a new replay requires deliberately
reviewing and updating provenance. To extract frames for local review, additionally
pass `--media-root apps/web/public/vision/mpfdd --frames-dir artifacts/visible-person-audit`.
This optional extraction requires OpenCV (the verification environment used
`cv2` 4.14.0). Video and frame paths are local; no frames or source videos are
committed or deployed because the source's redistribution license is unresolved.

Verification: seven stdlib tests passed (`python -m unittest discover -s
tests/benchmarks -v`); all nine media frames were extracted at the exact labeled
timestamps and inspected; stdlib-only scoring reproduced the committed report
byte for byte. The landing page, `/live`, detector, model, and thresholds are
unchanged, so a web UI visual check does not apply.

## Next step and limits

Have a human reviewer adjudicate these provisional counts, then retain raw pose
overlays locally and match each pose to a labeled person across consecutive
frames. That will distinguish duplicates, false observations near furniture,
observation misses, and fusion/association errors. This nine-frame audit does
not cover fall onset/end timing or identity continuity. Any detector candidate
still needs an untouched test source, person-level labels, and substantially
longer varied negative exposure before promotion. The earlier 2/22 fall-clip
result and 63 seconds of negative footage remain the current limitations.
