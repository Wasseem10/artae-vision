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
  cooldown, and request budgets; and
- the resulting temporal intervals and provider token usage return only to the replay
  scorer.

The dashboard accepts MP4, MOV, MKV, WEBM, and AVI uploads up to the configured size
limit (512 MiB by default). Each upload is stored under the authenticated organization
with a generated server-side filename; browser filenames cannot choose a storage path.
Advanced operators can still provide a finite file path or URI reachable by the worker.

During execution the worker reports processed video time at bounded intervals. Every
heartbeat renews the database lease, while the dashboard polls the evaluation and shows
its percentage and processed seconds. This prevents long clips from being reassigned
merely because they run longer than the initial lease. Object-storage distribution,
batch suite comparison, and promotion gates remain Phase-16 work.

Provider prices are configuration rather than hard-coded constants because pricing
changes by model and region. When a paid run reports requests but the worker's input
and output prices are both zero, the dashboard says **Configure pricing** instead of
presenting a misleading zero-dollar estimate.

Keeping execution separate from scoring is intentional: metrics stay deterministic,
re-runnable, and comparable even when a model provider or replay worker is unavailable.

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
and recent history. An active suite also records completed-video progress. The result is
the release evidence for a configuration; connecting it to a future versioned plan
promotion workflow belongs to Phase 17.
