# Model routing

Artae Vision compiles each natural-language camera job into two related documents:

1. a versioned camera-job specification describing **what** constitutes an event;
2. an execution plan describing **how** the current platform will evaluate it.

The operator reviews both documents before activation. The inference worker then validates the
execution strategy instead of independently guessing which models to run.

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

## Safety boundary

Routing correctness does not prove visual accuracy. The checked-in language evaluations prove that
prompts select the intended supported strategy. Real accuracy must be measured using labeled video
for each deployment scenario, camera angle, lighting condition, and alert threshold. Until that
benchmark exists, the dashboard describes these jobs as VLM-observed rather than deterministic.

Future pose, OCR, segmentation, motion, or specialized action models should be added as new typed
strategies only after a replay benchmark shows that they improve accuracy, latency, or cost.

## Relevant files

- `services/api/src/video_intelligence_api/execution_plans.py` is the control-plane planner.
- `services/api/src/video_intelligence_api/rule_compiler.py` recognizes when open-ended visual
  reasoning is required.
- `services/inference/src/video_intelligence_inference/routing.py` validates and groups deployed
  plans at runtime.
- `tests/evals/rule_compiler_cases.json` contains industry-neutral language-routing cases.
- `tests/inference/test_routing.py` protects the runtime routing boundary.
