# Multi-person fall path: browser regression

September 29, 2026. This is a **development regression check** on the 100
CAUCAFall clips already examined in the [independent browser result](caucafall-independent-result.md).
Each clip shows one staged participant. It cannot measure fall recall, person
association, or false alerts in a real shared room with multiple people.

The new `/live` path runs two MediaPipe pose landmarker instances over each
sampled frame: a one-pose instance retains the established primary-person
temporal rule, and a four-pose instance supplies observations for additional
session-only tracks. Each additional track has its own temporal fall rule.
Ambiguous matches discard motion history to avoid joining two people's
movements into an alert. Track numbers are local display labels, not identities.

| Browser rule on CAUCAFall | Staged falls matched within event window | Daily-activity clips alerted | Unmatched alerts | Median inference per sampled frame |
| --- | ---: | ---: | ---: | ---: |
| Original one-pose rule | 17/50 | 0/50 | 0 | Not recorded in this comparison |
| Unfused four-pose tracker | 8/50 | 0/50 | 0 | 32.2 ms |
| Fused primary plus additional tracks | **20/50** | **1/50** | **1** | 49.12 ms |

The four-pose tracker alone lost nine detections versus the original rule;
we did not ship that path. The fused path found three more staged falls but
introduced an alert on `cauca-s10-adl-walk`. Its matched-event recall is
40%, so it still misses 30 of 50 staged falls. Its median delay among detected
falls was 2.58 seconds, excluding misses. The 50 daily-activity clips contain
only 0.1428 analyzed hours (8.6 minutes); one alert in that interval cannot
be extrapolated to a field false-alert rate.

The [fused per-clip report](benchmarks/caucafall-multiperson-regression-v1.json)
contains source and model hashes, the frozen Git revision, event times, track
numbers, pose coverage, and inference time without publishing video. The
[unfused report](benchmarks/caucafall-unfused-regression-v1.json) records the
failed intermediate result. Both were evaluated against the same manifest and
event window as the original result. The fused implementation was committed
before its score was opened.

A browser smoke test composed two permitted sample videos side by side. It
observed two bodies, produced a possible-fall alert with the fall on either
side, and produced no alert for a sitting-plus-standing composite. These are
synthetic layout checks, not a multi-person benchmark. We still need labeled
multi-person footage with falls and challenging non-falls, person-level event
matching, longer negative exposure, and a new untouched source before claiming
an accuracy improvement. The browser demo remains a human-reviewed workflow
prototype.
