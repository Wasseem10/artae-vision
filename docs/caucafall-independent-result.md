# Independent CAUCAFall browser result

September 28, 2026. The [protocol and model hashes](caucafall-independent-protocol.md)
were committed as `c70594f74` before any CAUCAFall detector output was opened.
One browser run then processed all 100 CAUCAFall v4 videos with the same
self-hosted MediaPipe pose worker used by `/live`. The run reports local Git
revision `c70594f74` and a clean worktree. [Per-clip results](benchmarks/caucafall-independent-v1.json)
include alert times, fall intervals, and pose coverage, without video frames.

| Frozen method | Fall clips with any alert | Falls matched within event window | Daily-activity clips alerted | Unmatched alerts |
| --- | ---: | ---: | ---: | ---: |
| Current live temporal rule | 17/50 | 17/50 | 0/50 | 0 |
| Static posture ablation | 24/50 | 21/50 | 0/50 | 5 |
| Pose-window v1 | 4/50 | 4/50 | 0/50 | 0 |
| Pose-window v2, expanded training | 3/50 | 3/50 | 0/50 | 0 |

An event match required one alert from annotated fall onset through two
seconds after the annotated fall action ended. The live rule's median delay
among its 17 matched events was 2.67 seconds; p95 was 4.15 seconds. Those
latencies omit the 33 falls it missed. The posture ablation has more clip
hits, but three of its 24 positive clips did not alert in the event window
and it produced five unmatched alerts, all on fall clips.

The 50 daily-activity clips total **0.1428 analyzed hours** (about 8.6
minutes). Zero alerts in that brief staged footage do not establish a
field false-alert rate. All 50 positive clips are staged falls. These
figures are neither clinical sensitivity nor evidence of safe unattended
monitoring.

## Failure slices

| Fall activity | Mean pose coverage | Live rule | Pose v1 | Pose v2 |
| --- | ---: | ---: | ---: | ---: |
| Backwards | 81.8% | 4/10 | 1/10 | 0/10 |
| Forward | 55.0% | 2/10 | 0/10 | 0/10 |
| Left | 69.5% | 3/10 | 1/10 | 1/10 |
| Right | 76.4% | 5/10 | 2/10 | 2/10 |
| From sitting | 84.7% | 3/10 | 0/10 | 0/10 |

Pose loss is one contributor: ten fall clips had pose coverage below 50%,
and forward falls averaged 55% coverage. It is not the whole explanation:
17 of the live rule's 33 missed fall clips and 30 of v2's 47 missed fall
clips had at least 70% pose coverage. These aggregate observations do not
identify the cause of any individual miss; local pose timelines and video
review are needed for that.

## Decision

**Do not promote either pose-window candidate.** Expanded training did not
help on the new source, despite matching v1's subject-4 development count.
The current live rule also missed 33 of 50 staged falls, so the browser demo
remains a workflow prototype that requires a person to review possible
incidents. It must not be presented as reliable fall monitoring.

CAUCAFall is now examined and can be used for development diagnostics. A
future detector should address missed pose and cross-scene motion differences,
then be frozen before evaluation on another untouched source. An always-on
camera pilot additionally needs measured uptime, evidence integrity, actual
caregiver receipt and acknowledgment, privacy controls, and much longer
negative exposure. The [pilot plan](fall-pilot-plan.md) sets those gates.
