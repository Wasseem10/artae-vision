# Fresh skeleton context for the tracking failures

November 2, 2026. The original review archive contains torso features, not full
landmarks. This separate capture supplies full skeleton context for its 21
selected frames. **It is fresh inference, not a recovery of the original
skeletons, independent labels, or a new accuracy result.** The rejected tracking
candidate remains offline; the live detector is unchanged.

## Result

Using the pinned videos, worker, model, WASM runtime, feature extractor and
presented-frame sampler, the harness processes each of the five clips from time
zero through its last review frame. A new worker is used per clip, with the same
10 Hz request grid and 1280 px maximum bitmap width as the earlier comparison.

- **306 sequential inference samples**, including the 21 retained review frames.
  The JSON field `warmupSamples` includes those retained frames, not just the
  intervening warmup samples.
- **21 primary poses and 31 raw multi poses**, each containing all 33 returned
  landmarks, including depth and visibility values. These are 52 observations,
  not 52 different people.
- All **21 selected frames** exactly reproduce the archived observation slots
  and five compact feature values (`x`, `y`, verticality, aspect, visibility).
  Presented timestamps also match at recorded precision. This checks only
  selected outputs; it does not establish identity, label accuracy, identical
  full skeletons, or equality of every intermediate sample.
- Capture revision `cb5da4de5da7c745568872066902f62ae0c33c93`, Chrome
  `156.0.8078.74`. The older compact-feature archive used Chrome 155.

The [pixel-free summary](benchmarks/motion-pose-context-v1.json) records per-frame
agreement, source/runtime/harness hashes, image digests and the digest of the
full local capture. Raw frames, skeleton arrays and the local viewer stay in
ignored artifacts because research-media redistribution permission is not
established. No historical labels or evidence files were overwritten.

## Inspect the evidence

The local viewer lets a reviewer select Primary or a raw multi slot for each
frame. Slot numbers are not person identities. Visible joints are drawn when
their visibility is at least 0.6; a missing rendered line does not mean the
model returned no coordinates. Expand the coordinates section to inspect all
returned values, including less-visible joints.

One useful visual example is the classroom frame at 4.0 s: raw multi slot 1
places upper joints in the chair/backrest region while lower joints extend
toward the moving foreground body. This is a **provisional visual observation**,
not a human-adjudicated furniture false positive. At 4.5 s the fresh primary
skeleton supplies more context around the body/stool overlap. Keep the earlier
uncertain labels intact until a reviewer evaluates the full context; matching
torso features cannot prove matching historical skeletons.

This gives the next review a concrete question: whether malformed or duplicate
observations are making association ambiguous, and whether rejecting them would
also discard a valid falling person. Do not choose thresholds or promote a
candidate from these five previously examined failure clips alone.

## Reproduce

Use a clean committed checkout and the existing local research-media/runtime
directory. The capture refuses changed pinned inputs, nonlocal output paths,
and reuse of an existing evidence folder. It serves pinned assets on loopback
and blocks external browser requests. All intermediate samples warm the VIDEO
mode trackers; it does not jump directly between the selected review frames.

```powershell
node scripts/experiments/capture-motion-review-poses.cjs <vision-root> <web-dependencies-root> artifacts/new-pose-context
node scripts/experiments/check-motion-pose-context.cjs artifacts/new-pose-context <web-dependencies-root>
node --test tests/benchmarks/motion-pose-context.test.cjs
```

Open the generated `index.html` locally, keeping its frame PNGs beside it. A
failed capture may leave an incomplete folder; retry with a new directory.
`capture.json` contains the full fresh landmarks; `summary.json` contains the
pixel-free comparison. Publish only the latter after checking it. The viewer
opens without a server, external scripts, or network access.

## Verification and remaining gate

- All **35** focused tracking/history/evidence/review tests pass. New cases
  reject changed packets, missing frames or sources, incomplete warmup counts,
  mismatched timestamps, truncated skeletons, nonfinite values and invalid raw
  slot mappings. Published summary/code hashes are checked.
- Local browser check verifies all 21 frame-image digests, all slot selections
  against the stored landmark arrays, keyboard selection, complete image loading,
  and no horizontal overflow at 390 px. Zero page errors or external requests.
- Desktop/mobile viewer screenshots and selected primary/multi overlays were
  visually inspected. This is a review tool check, not complete person annotation.
- Landing page, `/live`, model weights, alert thresholds and cloud resources
  are unchanged. No fall-rule outputs or fall metrics were produced in this run.

Next: independently adjudicate the person/duplicate assignments with this
additional context, then evaluate a bounded observation/association change on
the retained regressions and untouched multi-person footage with longer hard
negatives. Full skeleton context reduces an evidence gap; it does not satisfy
the independent-review or detector-promotion requirements.
