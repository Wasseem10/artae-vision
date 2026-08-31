# Visual skills and scene memory

Phase 20 introduces a stable contract for adding visual capabilities without turning
the rule engine into a collection of model-specific branches.

## Smallest-capability routing

The registry describes PPE, text/screens, license plates, barcodes/labels,
pose/actions, open-vocabulary grounding, segmentation, and change/anomaly skills.
The prompt router selects only skills whose visible evidence is required. For example:

- “person without a hard hat” selects PPE compliance;
- “treadmill screen shuts off” selects text/screen reading, grounding, and change
  detection; and
- “person performs a backflip” selects pose/action analysis.

Today all eight skills are explicitly `fallback_only` and use the already bounded
temporal-VLM execution path. They are selectable, but they are not mislabeled as
specialized model support. Each manifest defines its input contract, output contract,
supported temporal modes, preferred specialized executor, and mandatory
scenario-specific replay policy. Registering a model is not proof that it is accurate
for a customer's angle, lighting, distance, or event definition.

A skill can become `specialized_ready` only when an executor returns the typed evidence
contract and passes representative replay promotion gates. The planner can then select
that executor without changing the camera-job contract or incident pipeline.

## Observable boundaries

The planner assigns every request one of four support levels: deterministic local,
general semantic fallback, requires outside context, or not visually verifiable.
Access authorization and package routing require business records. Intent, thoughts,
identity, and sensitive personal attributes are not treated as camera capabilities.
Both categories remain visible in a saved plan, but unsupported capabilities block
deployment instead of being silently ignored.

## Automatic scene observations

Vision decisions may return stable `scene_observations` alongside the event decision.
Each observation has a stable key, label, kind, normalized bounding box, state,
confidence, attributes, and relationships. The API upserts that state into
`SceneMemoryItem` and appends `SceneChange` only when the state changes.

Items begin as `proposed`. Operators may confirm, correct, or reject them, but the
default workflow does not require anyone to draw all regions manually. Rejected items
are hidden from ordinary lists while their audit history remains stored.

The dashboard's **Preview discovery** button is a provider-free demonstration of the
contract. It creates clearly marked simulated proposals and does not claim that a
model analyzed the live camera. Real observations arrive from authenticated edge
workers or from semantic-event metadata.

## Accuracy boundary

Skill routing and schema tests prove orchestration, validation, and persistence—not
visual accuracy. Before deployment, the exact skill/model/camera configuration must
pass a labeled replay suite with the rule's accuracy, false-alarm, latency, and cost
gates. The generic VLM fallback remains available when no specialized executor has
earned promotion.
