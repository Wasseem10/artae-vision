# Replay evaluation laboratory

The replay lab turns visual-agent quality into stored measurements rather than a
demo impression. A baseline contains:

- a video path or URI and its duration;
- the exact natural-language job;
- the production compiler output and reviewed execution route;
- human-labeled expected event intervals; and
- detected intervals plus model usage from a run.

## Temporal scoring

Expected and detected intervals use seconds from the beginning of the video. The
scorer builds valid same-label pairs, ranks them by temporal intersection-over-union,
and matches each expected and detected interval at most once. By default a pair is
valid at 0.1 IoU; a one-second boundary tolerance also supports brief events.

The report records true positives, false positives, false negatives, precision,
recall, F1, mean detection latency, unmatched interval indices, provider requests,
tokens, and estimated cost. A clip with no expected and no detected events is a valid
negative test with perfect precision and recall. A no-event clip with a detection is
a false alarm.

## Automatic execution

Choosing **Run replay automatically** queues the baseline for an idle edge worker.
The worker never creates real incidents from replay data:

- deterministic routes reuse the production YOLO tracker and temporal rule engine;
- semantic routes reuse the production overlapping sampler, provider, confirmation,
  cooldown, and a worker-wide replay request budget; and
- the resulting temporal intervals and provider token usage return only to the replay
  scorer.

The dashboard accepts MP4, MOV, MKV, WEBM, and AVI uploads up to the configured size
limit (512 MiB by default). Each upload is stored under the authenticated organization
with a generated server-side filename; browser filenames cannot choose a storage path.
Advanced operators can still provide a finite file path or URI reachable by the worker.

During execution the worker reports processed video time at bounded intervals. Every
heartbeat renews the database lease, while the dashboard polls the evaluation and shows
its percentage and processed seconds. This prevents long clips from being reassigned
merely because they run longer than the initial lease.

Provider prices are configuration rather than hard-coded constants because pricing
changes by model and region. When a paid run reports requests but the worker's input
and output prices are both zero, the dashboard says **Configure pricing** instead of
presenting a misleading zero-dollar estimate.

Keeping execution separate from scoring is intentional: metrics stay deterministic,
re-runnable, and comparable even when a model provider or replay worker is unavailable.
Finite semantic replays flush their final partial contact sheet so events near the end
of a short clip are not silently ignored. If the shared replay request ceiling is
exhausted, the evaluation fails explicitly instead of scoring unobserved windows as
negative evidence.

## Regression suites and promotion gates

A regression suite groups one or more stored replay baselines. Starting a suite queues
every baseline through its saved production route and creates a separate historical
suite run. Re-running a suite never overwrites an earlier batch decision.

The gate is deterministic application code. A model does not decide whether it passed.
Each run stores the threshold snapshot and evaluates:

- every worker replay completed successfully;
- macro F1 meets the configured minimum;
- macro recall meets the configured minimum;
- total false alarms stay below the configured maximum;
- total estimated provider cost stays below the configured maximum; and
- paid-provider pricing is configured when the suite requires it.

All checks must pass before the run is marked `passed`; otherwise it is marked `failed`.
The dashboard shows the aggregate decision, every gate calculation, per-video results,
capability-by-capability metrics, and recent history. An active suite also records
completed-video progress. The result is
the release evidence for a configuration; connecting it to a future versioned plan
promotion workflow belongs to Phase 17.

## Cross-industry camera calibration

The calibration pack is the evidence checklist for the general visual-intelligence
layer. It currently covers person presence, entry, PPE removal, a staged safe fall,
equipment stopping, a spill appearing, a package falling, and serial-number reading.
The scenarios intentionally span deterministic detection, tracking, transitions,
pose/action understanding, change detection, segmentation, grounding, and OCR.

Each replay can be classified as:

- `synthetic`, which proves only that the software pipeline runs;
- `public_benchmark`, which is traceable licensed real footage used for general testing;
- `controlled`, recorded deliberately on a real target camera; or
- `field`, captured during representative real operation.

Synthetic clips never count toward readiness. Licensed public benchmarks can establish
general benchmark readiness, but only controlled/field footage can support a
site-specific claim. An automatically scored scenario becomes ready only after at
least two credible positive clips, two credible negative clips, one difficult-condition
clip, F1 and recall of at least 0.80 on every positive clip, and zero false alarms on
every negative clip. Low light, distance, partial occlusion, and camera motion are
recognized difficult conditions. The overall claim remains blocked until every
automatically scored core scenario is ready.

Source pages, creators, licenses, hashes, rejected candidates, and derived-excerpt
instructions are recorded in `docs/calibration-sources.json` and
`docs/calibration-datasets.md`.

Serial-number OCR is deliberately marked `manual_only`: event timing cannot establish
whether the characters were read correctly. It requires exact ground-truth strings and
value-level scoring before that capability can be claimed.

Use the recording protocol shown in the dashboard for every scenario. Label intervals
from the moment the visible condition becomes true until it ends. Negative clips must
have no expected interval. Do not lower confidence thresholds merely to make one clip
pass; inspect misses and camera placement first, then preserve representative clips in
a regression suite before changing execution settings.
