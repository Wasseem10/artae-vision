# Separate pose counts from person coverage

November 17, 2026. `summarize-person-coverage.cjs` converts a packet-matched
review into per-frame diagnostics for the primary stream, raw multi-pose stream,
and their combined observations. This makes missing-person and repeated-person
assignments inspectable without treating raw pose count as person coverage.

**The existing labels are provisional AI hypotheses, not independent ground
truth.** This analysis changes no detector, runs no inference, and supplies no
recall, accuracy, identity score or promotion decision. The tracking candidate
remains rejected. Human review and untouched multi-person footage are still
required before another candidate can pass the accuracy gate.

## Reproduce

From the repository root, create `artifacts` if needed and choose a new output
filename. The CLI refuses to overwrite an existing report or input file.

```powershell
node scripts/experiments/summarize-person-coverage.cjs docs/benchmarks/motion-review-packet-v1.json docs/benchmarks/motion-review-ai-draft-v1.json artifacts/person-coverage-2026-11-17.json
node --test tests/benchmarks/*.test.cjs
```

The packet digest, unique frame/slot identities, review coverage and count/actor
consistency are validated before analysis. Unknown stream names are rejected.
Output preserves the review's parsed-JSON digest and declared provenance, plus
raw-file hashes of the summarizer and both validation dependencies. Declarations
such as `humanAdjudicated: true` never turn the output into verified evidence.
Original review files and the pinned packet/reviewer sources are unchanged.

## Reading the output

Each frame retains its key, clip ID and visible-person count. For each stream:

- `assignedPeople` counts distinct `person-N` labels in that frame only.
- `extraAssignmentsToSamePerson` counts person-labeled observations beyond the
  first assignment to each actor. Primary and multi observations can overlap
  by design. The combined count is not a count of duplicate fused tracks.
- `unresolvedObservations` keeps both `uncertain` and `unreviewed`; neither
  becomes a person or a non-person observation automatically.
- `unrepresentedPeople` gives a conditional minimum and maximum. With visible
  count V, distinct assigned people A and unresolved observations U, these are
  `max(0, V - A - U)` and `V - A`. The minimum allows each unknown observation
  to represent a different, otherwise unassigned person. The maximum allows
  all unknown observations to be duplicates or non-person. These are logical
  bounds given the annotations, not statistical confidence intervals.
- A missing visible count produces `null` bounds, never a zero-person frame.
  No aggregate unique-person count is computed across frames or clips.

## Result on the existing draft

The command processed **21 selected frames, 52 observations and five clips**.
All four uncertain assignments remain unresolved. The table describes the
existing draft's implications; no label was independently verified in this run.

| Clip / selected seconds | Visible-person hypothesis | Primary unrepresented | Raw multi unrepresented | Combined unrepresented |
| --- | --- | --- | --- | --- |
| MPFDD rooftop, 4.9 / 5.0 / 5.1 | 2 | 1 | 1 | 1 |
| MPFDD classroom, 3.3 / 3.4 / 3.5 / 3.8 | 4 | 3 | 2 | 2 |
| MPFDD classroom, 3.9 | 4 | 3 | 3 | 2 |
| MPFDD classroom, 4.0 | 4 | 3 | 2–3 | 1–2 |
| MPFDD classroom, 4.5 / 4.6 / 4.7 | 4 | 3–4 | 3 | 2–3 |
| Lateral, forward and backward demos, three selected frames each | 1 | 0 | 0 | 0 |

At classroom 3.3 and 3.4 seconds, the four combined observations have only two
distinct actor assignments. Within the raw multi stream, three observations
have two actor assignments. At 3.9 seconds, the primary and multi streams each
cover a different actor according to the draft; combining them adds coverage
but still leaves two of four people unrepresented. At 4.0 seconds, the unknown
multi assignment widens the combined range to 1–2 rather than silently becoming
a confirmed missing person or a confirmed detection.

The demo frames illustrate why combined repetition alone is not a failure:
the primary and multi streams both represent the same single person. Inspect
within-stream repeats and unrepresented people separately before proposing
deduplication. Torso-center assignments still cannot prove duplicate skeletons
or furniture false positives. These selected, correlated development frames
cannot establish population performance.

## Verification and next step

Seven new regressions exercise repeated-person assignments, stream separation,
uncertainty bounds, null and zero counts, empty observations, complementary
streams, invalid inputs, provisional provenance and CLI overwrite protection.
All **57 JavaScript benchmark tests and seven Python audit tests** pass locally.
The existing comparator tests also pass after sharing its packet validator.
This is an offline JSON/report change; no website or visual layout changed.

Next, use the [independent review workflow](motion-review-comparison.md) to
resolve the person/duplicate hypotheses, then rerun this diagnostic on the
separately retained review. Evaluate any detector change against retained
regressions, untouched multi-person footage and longer hard negatives. The
current MPFDD result remains 2/22 fall clips and 0/6 activity clips, with only
about 63 seconds of negative footage; this report does not improve that result.
