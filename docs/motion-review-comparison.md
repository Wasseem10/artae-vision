# Compare person annotations before adjudication

November 5, 2026. The offline comparator turns two reviews of the frozen motion
packet into a list of count, person/non-person, duplicate and identity-continuity
disagreements. It supports the independent review step before another tracking
candidate is evaluated. It does not create labels or choose a winning reviewer.

## Workflow

1. Each reviewer opens a blank [review packet](motion-association-review.md) and
   exports a separate JSON file. Inspect independently before reading the AI
   draft or the other review. Use the [fresh skeleton context](motion-pose-context.md)
   where needed, remembering that it comes from a separate inference capture.
2. Run the comparator from the repository root with the committed packet manifest
   and the two exported reviews. Create the output directory first and use a new
   filename. Existing files are never overwritten.

   ```powershell
   node scripts/experiments/compare-motion-reviews.cjs docs/benchmarks/motion-review-packet-v1.json artifacts/reviewer-a.json artifacts/reviewer-b.json artifacts/review-comparison.json
   ```

3. Inspect each clip's unresolved fields and disagreements. Each item names its
   frame and observation slot; identity conflicts include both observation
   references and each review's same-person/different-people relationship. Return
   to the local frames, notes and skeleton context for adjudication.
4. Keep both original reviews and the comparison as provenance. Record any
   adjudicated labels separately with the reviewer and rationale. An agreement
   report, a reviewer name or a `single-review` export does not establish
   independent ground truth.

## What is compared

| Output | Meaning |
| --- | --- |
| `unreviewedCounts` | At least one review has no visible-person count. Null never becomes zero. |
| `countDisagreements` | Both counts are present and differ. |
| `unresolvedObservations` | At least one assignment is `uncertain` or `unreviewed`, even if both use the same label. |
| `categoryDisagreements` | One reviewed assignment is a person and the other is non-person. |
| `identityConflicts` | Both reviews assign people to two observations, but disagree about whether those observations belong to the same person. |

Person numbers are arbitrary names within a clip. Consistently renaming
`person-1` to `person-7` creates no disagreement. A swap between actors in later
frames does create conflicts, even when both reviews have identical person
counts. Pairs within one frame help identify duplicate-assignment disagreements;
pairs across frames help identify continuity disagreements. Person IDs in
different clips are never compared.

`identityComparisons` counts correlated observation pairs, not independent
people, frames or clips. Large pair counts must not be presented as a large
validation set. The tool deliberately exports no accuracy, agreement percentage,
promotion decision or automatic adjudication.

## Provenance, checks and limits

The comparator verifies the packet-content digest, unique frame/slot identities,
and both reviews' packet, frame order and observation coverage. The output stores
hashes of the parsed review JSON, declared reviewer/status metadata, and a hash of
the comparator source. Parsed-JSON hashes ignore file whitespace; they are not
raw-file digests. Human-adjudication metadata is preserved as a declaration, not
accepted as proof. Original review files are not edited.

Eight targeted tests cover renumbering, separate clip namespaces, cross-frame
identity swaps, within-frame duplicates, uncertainty, missing counts, person vs
non-person assignments, malformed inputs and overwrite prevention. A structural
self-comparison of the existing AI draft covers all 21 frames and 52 observations
and keeps its four uncertain assignments unresolved. That test is not a second
review or evidence that any assignment is correct.

```powershell
node --test tests/benchmarks/motion-review-comparison.test.cjs
```

No independent human review was produced in this run. The existing draft remains
provisional, and the tracking candidate remains rejected. The next accuracy gate
is independent adjudication followed by a frozen candidate evaluated on retained
regressions and untouched multi-person footage with longer hard negatives.
