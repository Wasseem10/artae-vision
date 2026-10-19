# Candidate video acquisition and full decode

October 19, 2026. This continues the [annotation preflight](posture-source-preflight.md)
with actual local video verification. **No detector inference, threshold change,
accuracy measurement, or model promotion occurred.** The landing page and `/live`
are unchanged.

## What is now verified

All seven candidate validation recordings in the
[pinned source lock](benchmarks/posture-source-v1.lock.json) were downloaded and
verified against their exact byte sizes and SHA-256 hashes: **1,981,798,589 bytes**
total. The three upstream training videos were excluded, preserving the fixed
roster. Videos and context thumbnails remain under ignored local `artifacts/`;
the PR contains only tools, tests and derived metadata.

The [full decode report](benchmarks/posture-media-v1.json) records **51,363 decoded
frames**, all at 1280×720, totaling **1,712.136789 seconds** of video-frame span
(about 28.5 minutes). That total is source footage, **not verified negative
exposure**. The exact sum of the per-video rational spans is `154092311/90000`.

| Video | Decoded / declared frames | Video-frame span (seconds, rounded) | First raw PTS (ms) | Final inclusive label bin exceeds span? |
| --- | ---: | ---: | ---: | --- |
| `fall_detection_4` | 11,619 / 11,619 | 387.260622 | 27.8 | Yes, row 66 |
| `fall_detection_5` | 7,105 / 7,105 | 236.791789 | 13.1 | Yes, row 84 |
| `fall_detection_6` | 4,290 / 4,290 | 143.000000 | 36.1 | No |
| `fall_detection_7` | 4,453 / 4,453 | 148.414644 | 21.0 | Yes, row 49 |
| `fall_detection_8` | 13,050 / 13,050 | 435.166567 | 59.4 | No |
| `fall_detection_9` | 3,821 / 3,821 | 127.366667 | 55.7 | Yes, row 35 |
| `fall_detection_10` | 7,025 / 7,025 | 234.136500 | 56.8 | Yes, row 69 |

Every frame was decoded sequentially, including decoder flush, with a present
and strictly increasing presentation timestamp. The decoded counts matched
declared video-stream frame counts. No corrupt frame flags, missing frame
durations, interval gaps, or interval overlaps were detected. Every first PTS
matched its declared stream start, and each decoded span matched stream duration.
These checks establish successful decoding in the recorded local runtime;
they do not establish browser playback or live monitoring reliability.

## Clock and label findings

The tool uses rational `PTS × time_base` and explicit decoded frame durations;
it does not derive time from frame count or nominal FPS. Both raw video-stream
and container timing metadata are retained. See the primary PyAV documentation
for [frame presentation timestamps and durations](https://pyav.basswood.io/docs/stable/api/frame.html)
and [container decoding](https://pyav.basswood.io/docs/stable/api/container.html).

All videos have nonzero first video PTS, ranging from 13.1 to 59.4 milliseconds.
Technical consistency between decoded frames and stream metadata **does not
confirm the annotation/player clock**. The report therefore records
`decoded_timeline_consistent` separately from `label_clock_verified: false`.
For bounds diagnostics only, it assumes label zero is the first decoded video
frame. That assumption must be checked against the labeling/player convention
before reporting event latency or exposure.

Under the earlier diagnostic convention of inclusive integer-second bins, five
final bins extend beyond the measured video-frame spans. This does not mean
their entire final CSV rows are invalid: **no row starts or ends at/after the
video end** under the declared clock assumption. It means rounding the last
label bin up to a complete second would count unavailable video. No labels
were silently clipped, rewritten, or converted to exposure. The four duplicate
groups, six conflicting bins, two gaps and unassigned activity from the October
18 audit still require review against footage.

A local visual spot check inspected 21 approximate context thumbnails across
all seven videos: before/after the first positive label and an example labeled
lying non-fall (or a fixed early context frame). The scenes include beds,
sofas/chairs, poor visibility and partial occlusion. This was an AI context
inspection, not independent human event adjudication. OpenCV seek thumbnails
were not used as frame-accurate timestamps or to change ground truth.

## Tooling and reproduction

`scripts/acquire-posture-media.py` requires Python 3.11+. Download/hash-only mode
uses the standard library. Full decoding additionally uses the pinned optional
`av==19.0.1` dependency; it is not added to the application. On PowerShell:

```powershell
python -m pip install --target artifacts/media-audit-deps --only-binary=:all: --no-deps -r scripts/requirements-posture-media.txt
$env:PYTHONPATH = (Resolve-Path artifacts/media-audit-deps).Path
python scripts/acquire-posture-media.py --fetch --download-only --output artifacts/posture-download-new.json
python scripts/acquire-posture-media.py --output artifacts/posture-decode-new.json
python -m unittest discover -s tests/benchmarks -p 'test_posture*.py' -v
```

Full decode requires a clean committed checkout; the report pins code revision,
both audit scripts' hashes, source lock hash, Python/platform, PyAV and FFmpeg
library versions. Existing media are rehashed, including immediately before
and after decoding. Source/provenance drift during decoding prevents report
publication. Partial downloads are cleaned up; only fully verified files are
published into the cache. A corrupt cache is rejected without overwriting it.
Downloads are bounded to two concurrent files. Output paths must be fresh;
existing reports are never overwritten, and an incomplete run publishes no
aggregate report.

## Verification and evidence limits

- Thirty-four focused tests pass with the optional decoder installed. These
  include interrupted, short, oversized and wrong-hash downloads, preserved
  corrupt caches, invalid/missing PTS, variable frame durations, decode count
  mismatch, changing dimensions, timestamp gaps/overlaps, partial final bins,
  unverified label clocks, and a real eight-frame generated MP4 decode.
- Two complete decodes produced identical per-video frame counts and
  presentation-trace SHA-256 digests for all seven videos. The second report
  adds explicit container timing and the label-clock caveat; the report files
  themselves are not byte-identical across those tool revisions.
- The published report was captured from clean revision
  `50fa243da6213f4a0633499de9c324822185a9a6`. The report's exact revision is
  authoritative if reproducing it; model inference was never invoked.
- The media were not distributed, deployed, or uploaded to cloud resources.
  No application visual check is needed for this offline-only change. The
  source video context inspection described above is not a UI test.

Attribution and permitted use remain as recorded in the [source preflight](posture-source-preflight.md).

## Next priority

Create a separately reviewed event sidecar with the confirmed player/label
clock, actual fall onset/end and recovery windows, and intentional sitting or
lying hard negatives. Preserve unknown intervals and retain difficult scenes.
Then freeze continuous replay, one-to-one alert matching, repeated-alert
accounting and negative exposure **before** comparing detectors. The existing
automatic rule remains unchanged. This one-person source cannot replace
independently adjudicated multi-person identity and fall-event labels.
