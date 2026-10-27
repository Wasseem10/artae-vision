# Provisional review of interrupted fall histories

October 27, 2026. The [AI review draft](benchmarks/motion-review-ai-draft-v1.json)
records visual hypotheses for all **21 frames and 52 archived observations** in
the [frozen review packet](motion-association-review.md). It contains 48 tentative
person assignments and four explicitly uncertain assignments. These counts
describe the annotation file, not detector performance.

**No human adjudication has been completed.** The file remains `status: draft`,
`humanAdjudicated: false`, and `promoted: false`. Do not use it as independent
ground truth, training labels, or a source of identity/fall accuracy metrics.
The candidate remains rejected; this review changes no model or live rule.

## What the frames suggest

All original images were inspected with the archived primary (P) and raw
multi-pose (M0, M1, M2) torso centers. These are observations before fusion;
their slot numbers do not identify people. The capture did not retain full
skeletons. The descriptions below are provisional visual interpretations.

| Clip and sampled times | Visible-person hypothesis | Center associations and gaps |
| --- | --- | --- |
| MPFDD s1-p2-f1-fall-1, 4.9–5.1 s | Two people in each of three frames | P and M0 are near the foreground person's upper body. The rear standing person has no nearby center. Empty chairs do not have nearby centers in these frames. |
| MPFDD s3-p4-f1-fall-4, 3.3–3.5, 3.8–4.0, 4.5–4.7 s | Four people in each of nine frames | Centers cluster on the blue-clothed foreground person and the right seated person. The back-left and back-center people have no nearby centers. At 3.3 and 3.4 s, four observations appear associated with only two visible actors. |
| Lateral demo, 5.6–5.8 s | One person in each of three frames | P and M0 are both near the same visible upper body. |
| Forward demo, 7.0–7.2 s | One person in each of three frames | P and M0 are both near the same visible upper body. |
| Backward demo, 7.1–7.3 s | One person in each of three frames | P and M0 are both near the same visible upper body. |

This separates two problems worth testing: multiple observations of one actor
can inflate raw pose counts, while visible background actors can remain
unrepresented. Center proximity alone cannot confirm that the full skeletons
are duplicates, nor explain whether upstream detection, image scale, occlusion,
or another cause accounts for the missing observations.

Four classroom associations remain `uncertain`: M1 at 4.0 s and P at 4.5, 4.6,
and 4.7 s. The centers overlap a blurred or partly hidden blue body and a stool.
They do **not** establish that the model mistook furniture for a person.
There are no affirmative `non-person` assignments in this draft; that is not
evidence of a zero furniture false-positive rate.

## Inspect or revise the draft

1. Recreate the local packet using the [pinned extraction instructions](motion-association-review.md#reproduce-locally),
   or use the already verified packet with its original JPEGs. Research media
   remains local; only the pixel-free annotations are committed.
2. Open its `index.html` and import
   `docs/benchmarks/motion-review-ai-draft-v1.json` with **Resume a JSON review**.
   The reviewer field identifies the AI provenance, and every frame note repeats
   that the observations are provisional. The top-level actor registry describes
   IDs that are consistent only within a clip, not across different videos.
3. For independent review, inspect a blank packet first, export separately,
   then compare with this draft to reduce anchoring on its guesses. Keep the
   AI file unchanged as provenance; record disagreements and adjudication in
   a separate review. A completed export alone does not establish independence.
4. Where the short windows cannot resolve an association, keep `uncertain`.
   Obtain longer context and full pose overlays. A fresh inference capture must
   be identified separately from this archived observation set.

Structural validation from the repository root:

```powershell
node -e "const p=require('./docs/benchmarks/motion-review-packet-v1.json'); const r=require('./docs/benchmarks/motion-review-ai-draft-v1.json'); require('./scripts/experiments/motion-review-labels.cjs').validateReview(r,p,true); console.log(r.status)"
node --test tests/benchmarks/motion-review.test.cjs
```

The `true` argument checks complete field coverage and uncertainty notes; it
does not change the draft status or validate the visual judgments.

## Verification and next decision

- The local packet exactly matches the committed manifest; all 21 original
  image SHA256 digests were checked before inspection. The draft references
  that packet ID, source-report digest, and capture revision.
- All 31 existing candidate/history/evidence/review tests pass. No detector
  implementation or pinned extraction/reviewer source changed.
- Browser import restored all 21 counts, 52 assignments, notes, and reviewer
  text. Draft export round-tripped the complete JSON exactly, including its
  AI provenance flags. All images loaded; zero page errors or external requests.
- Original-frame overlays and the imported draft were visually inspected.
  No inference was rerun; no new fall detection score was measured.

Next, adjudicate these person associations and capture full pose evidence for
the ambiguous overlaps before choosing a deduplication or association change.
Evaluate any resulting candidate against the retained regressions **and**
untouched multi-person footage with longer hard-negative exposure. These five
selected development failures cannot justify promoting a detector, and the
draft does not remove that blocker.
