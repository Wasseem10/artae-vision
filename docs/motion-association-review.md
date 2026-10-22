# Review the interrupted fall histories

October 22, 2026. This is a **local development annotation tool**, not a new
detector, inference run, or accuracy result. It advances the five-window review
task identified by the [history diagnosis](motion-association-comparison.md#october-21-why-histories-disappear).
The current candidate still fails all five clips that the baseline alerts on.

## What was produced

The builder extracts the immediately preceding, current, and following 10 Hz
samples around seven armed-history interruptions: **21 video frames, 52 raw
observations, five clips**. These are selected failures from already examined
development footage, not held-out examples. Zero person labels are completed.

| Clip | History interruption(s), seconds | Review frames | Raw observations |
| --- | --- | --- | --- |
| MPFDD s1-p2-f1-fall-1 | 5.0 | 3 | 6 |
| MPFDD s3-p4-f1-fall-4 | 3.4, 3.9, 4.6 | 9 | 28 |
| Lateral demo | 5.7 | 3 | 6 |
| Forward demo | 7.1 | 3 | 6 |
| Backward demo | 7.2 | 3 | 6 |

Each frame shows archived primary and raw multi-pose torso centers, including
observations the fusion gate suppressed. It does **not** reconstruct skeletons:
the original comparison archive retained compact features, not landmarks.
Centers can guide inspection but cannot establish an actor or duplicate pose
by themselves. Overlaps, occlusions, and unexplained markers should remain
`uncertain` until better evidence or a reviewer resolves them.

The local page supports visible-person counts, actor IDs consistent within a
clip, explicit uncertainty/non-person labels, appearance notes, draft export,
and resume from JSON. Blank counts remain null rather than silently becoming
zero. Single-review export requires a named reviewer, complete observation
coverage, counts, and notes explaining uncertain/non-person assignments.
Neither a reviewer name nor a completed export establishes independent
adjudication. There is no automatic saving; export before closing the page.

## Reproduce locally

Use the pinned full comparison archive, prepared research media, and FFmpeg.
The full archive and MPFDD videos remain local because redistribution permission
has not been established. Existing model dependencies are needed only for the
browser smoke check, not for extracting images or reviewing labels.

```powershell
node scripts/experiments/build-motion-review.cjs `
  artifacts/motion-association-v1.json <vision-root> <ffmpeg-executable> `
  artifacts/new-motion-review
node scripts/experiments/check-motion-review.cjs `
  artifacts/new-motion-review <web-dependencies-root>
node --test tests/benchmarks/motion-review.test.cjs
```

Open `artifacts/new-motion-review/index.html` directly in a browser. The packet
has no external dependencies or requests. Keep its JPEGs with the HTML. Use a
desktop-sized view for detailed inspection. The browser check writes clearly
marked smoke-test drafts; those are not human annotations.

The builder verifies the frozen archive digest, complete capture/event
agreement, media manifest, and all five source-video digests. It decodes from
the start and checks the image presentation timestamp against the archived
decoded time (maximum allowed difference: 2 ms). It refuses to reuse an output
folder. A failed extraction may leave an incomplete folder with no `index.html`;
retry in a new directory. Imports must match the packet ID, frame order, and
every observation slot; malformed counts or actor assignments are rejected.

## Recorded verification

Built from clean commit `2e93db8d3cfd875f66253f13bc8aa66e7eb0dd23` using
FFmpeg 7.1. All 21 extracted timestamps matched the archived decoded timestamps
exactly at recorded precision. The [pixel-free packet manifest](benchmarks/motion-review-packet-v1.json)
pins image/media digests, source capture, diagnostic input, builder, review
template, and validator. Local images and screenshots are not committed.

- 31 focused candidate/history/evidence/review tests pass, including seven
  review tests covering incomplete labels, wrong packets, altered coverage,
  invalid actor/count values, uncertainty, window selection, and packet integrity.
- Browser smoke: all 21 images load, draft export/import restores data,
  unfinished reviews and wrong-packet imports are rejected; no page errors or
  external requests.
- Desktop (1440 px) and mobile (390 px) screenshots inspected. Mobile has no
  horizontal overflow; frame controls remain accessible below the instructions.
- Landing page, `/live`, live rules, model weights, and deployment are unchanged.

## Remaining gate

An independent reviewer must inspect and adjudicate person/duplicate labels;
the short windows and torso centers can leave associations unresolved. If they
do, obtain longer context and raw pose overlays without misrepresenting a fresh
inference run as the original archive. Keep any AI-only interpretation explicitly
provisional. These five windows cannot measure general identity accuracy or
justify changing the detector. The next candidate still needs untouched
multi-person clips and longer hard-negative exposure alongside fall recall.
