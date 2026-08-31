# Model routing

Artae Vision compiles each natural-language camera job into two related documents:

1. a versioned camera-job specification describing **what** constitutes an event;
2. an execution plan describing **how** the current platform will evaluate it.

The operator reviews both documents before activation. Every plan also carries a support
assessment so routing breadth is not confused with proven accuracy. The inference worker then
validates the execution strategy instead of independently guessing which models to run.

## Support levels

| Level | Meaning | Deployment behavior |
|---|---|---|
| `deterministic` | Known detector class plus geometry/time state machine | Allowed only after representative replay validation |
| `semantic_fallback` | Visibly observable open-ended condition evaluated with chronological VLM windows | Allowed only after the exact camera/scenario passes replay gates |
| `requires_context` | Pixels must be correlated with access-control, inventory, order, payment, or another business record | Blocked until the required connector is configured and tested |
| `not_visually_verifiable` | The request asks for intent, thoughts, identity, sensitive traits, or another fact pixels cannot establish | Blocked; the operator must rewrite it as an observable condition |

This classification happens before model capability checks. For example, “unauthorized person
enters” is not reduced to ordinary person entry, because doing so would silently discard the word
*unauthorized*.

## Current strategies

| Strategy | Use it for | Runtime | Vision-provider requests |
|---|---|---|---|
| `deterministic_tracking` | Known object classes, counts, zones, dwell, entry/exit, and line crossing | YOLO → ByteTrack → spatial/temporal state machine → evidence | No |
| `semantic_window` | Attributes, equipment state, unusual actions, and relationships requiring scene context | Overlapping frame sheets → VLM → confidence/confirmation gate → evidence | Yes, with hard ceilings |

A semantic-only camera does not load YOLO. A mixed camera shares one YOLO/tracking pass among all
deterministic jobs while semantic jobs observe their own bounded frame windows.

## Routing examples

- “A person remains in the loading zone for 30 seconds” → deterministic tracking.
- “At least three people enter the lobby” → deterministic tracking.
- “A masked person enters the store” → semantic windows because *masked* is an attribute.
- “Someone tailgates through the gate” → semantic windows because the relationship unfolds over
  time and cannot be inferred from one person box.
- “A treadmill screen shuts off” → semantic windows because screen state is scene-specific.
- “The humanoid robot falls” → semantic windows because posture and scene context are required.
- “A person performs a triple backflip” → semantic windows because it is an unusual action.
- “A worker removes a hard hat” → semantic windows in transition mode; the runtime must observe a
  negative baseline before accepting the change and rearms after an event.
- “An unauthorized person enters” → access-control context required; camera-only deployment is
  blocked.
- “A package is sent to the wrong destination” → business-system context required.
- “A person intends to steal” → not visually verifiable and blocked.

## Temporal modes

Semantic jobs declare `state`, `transition`, or `sequence`. State jobs confirm that a visible
condition persists across the configured number of windows. Transition jobs additionally require
one or more non-triggering baseline windows before a positive change can produce an event; after an
event the baseline is cleared so a continuing state cannot be reported as repeated changes.
Sequence jobs retain ordered chronological sheets and are evaluated as an ordered action. The
runtime records the selected temporal mode in event evidence.

## Safety boundary

Routing correctness does not prove visual accuracy. The checked-in language evaluations prove that
prompts select the intended supported strategy. Real accuracy must be measured using labeled video
for each deployment scenario, camera angle, lighting condition, and alert threshold. Until that
benchmark exists, the dashboard describes these jobs as VLM-observed rather than deterministic.

Pose, OCR, segmentation, grounding, PPE, plate, barcode, and change skills currently declare
`fallback_only`. A specialized executor may move to `specialized_ready` only after it satisfies the
skill input/output contract and a scenario replay benchmark shows that it improves accuracy,
latency, or cost.

## Relevant files

- `services/api/src/video_intelligence_api/execution_plans.py` is the control-plane planner.
- `services/api/src/video_intelligence_api/rule_compiler.py` recognizes when open-ended visual
  reasoning is required.
- `services/inference/src/video_intelligence_inference/routing.py` validates and groups deployed
  plans at runtime.
- `tests/evals/rule_compiler_cases.json` contains industry-neutral language-routing cases.
- `tests/inference/test_routing.py` protects the runtime routing boundary.
