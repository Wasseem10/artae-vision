# Product completion roadmap

Revised August 23, 2026 after completing automated operational-health incidents.

## North-star product loop

The target is not merely a camera that detects objects. It is a visual operations
agent that can complete the same loop as a human operator:

```text
natural-language job
        |
reviewable agent plan
        |
camera perception + business-system context
        |
temporal decision + optional verification
        |
guarded action in another system
        |
incident, evidence, audit trail, and search
```

Examples from the transcript make every part of this loop necessary:

- Tailgating requires seeing two people, querying access-control swipes, correlating
  both streams in time, and then locking a door, filing a ticket, or calling someone.
- Misrouted cargo requires recognizing and tracking an item, understanding its
  expected destination, locating it on a site map, and notifying an operator quickly.
- Car-wash automation requires license-plate recognition, loyalty/POS lookup, and a
  guarded command to the gate or tunnel controller.

The platform will support three operating modes. Camera-only mode evaluates visual
conditions and sends alerts without access to client systems. Connected mode enriches
camera observations with authorized business-system data and may take approved
actions. Edge/offline mode runs the required perception and rules on a local station,
queues integrations while disconnected, and synchronizes when connectivity returns.

## Current position: guarded visual-agent automation and camera commissioning complete

The repository already has the foundation needed for all three modes:

- webcam, MP4, and RTSP ingestion;
- YOLO detection, tracking, geometry, and deterministic temporal rules;
- overlapping VLM windows for open-ended visual conditions;
- a natural-language compiler with human review and typed execution plans;
- FastAPI control plane, Next.js operator dashboard, events, evidence clips,
  WebSockets, incidents, audit records, roles, and organization isolation;
- durable webhooks and optional Artae/local evidence search; and
- host workers, edge enrollment, Docker infrastructure, and safe local start/stop.

This is a substantial foundation, but it is not yet the complete OpenVector-style
product. In particular, a successfully routed prompt is not proof that the visual
decision is accurate, and the current webhook path is not yet a general tool-using
integration engine.

## Remaining phases

### Phase 16 — Replay evaluation and cost laboratory (next)

Build a repeatable way to run the exact production rule pipeline over labeled MP4
clips without a live camera. Record true positives, false positives, false negatives,
decision latency, provider requests, tokens, and estimated cost. Start with a small,
diverse suite covering dwell, line crossing, missing PPE, masked entry, tailgating,
screen-off, fall, and unusual-motion prompts.

Exit criteria:

- an operator can upload/select a replay clip and a natural-language job;
- expected event intervals can be labeled and stored;
- deterministic and semantic routes use the same code as live processing;
- a report compares accuracy, latency, and cost by rule/model/settings; and
- no model or routing change is promoted without a recorded regression result.

Status: complete. Durable baselines, production compilation/routing snapshots,
interval scoring, provider-cost fields, authenticated browser upload, automatic leased
video execution, progress heartbeats, batch regression suites, immutable run history,
deterministic promotion gates, APIs, and the dashboard workspace are built.

### Phase 17 — Versioned visual-agent plan

Extend the current execution plan into an inspectable agent contract with typed
nodes for perception, temporal correlation, external queries, decisions, verification,
and actions. The compiler may propose the plan, but schema validation, capability
checks, risk classification, and human activation remain deterministic boundaries.

Example:

```text
observe: count people crossing entrance
query: access-control swipes within the matching time window
decide: people > successful swipes
verify: replay the incident window before a high-consequence action
act: create ticket and call supervisor
```

Exit criteria include plan versioning, plan preview, unsupported-capability errors,
dry-run simulation, and reproducible execution from the stored plan.

Status: complete. Accepted camera jobs now compile into durable typed
observe/query/decide/verify/act graphs. Plans have camera-scoped revisions, explicit
capability requirements, unsupported-connector blockers, side-effect-free simulations,
mandatory passed replay gates, human approval, automatic rule activation, supersession,
and rollback. The dashboard now makes this the default guided workflow instead of
showing infrastructure controls first.

### Phase 18 — Guarded action and integration runtime

Generalize the existing durable webhook delivery into a connector/action framework.
Actions need encrypted credentials, scoped permissions, idempotency keys, retries,
timeouts, rate limits, audit logs, and dead-letter handling. Each action is classified:

- low risk: notify or create a draft record automatically;
- medium risk: create a ticket or update a workflow with configurable approval; or
- high risk: control a door, gate, machine, or payment-related system only through an
  explicit allowlist, verification policy, and customer authorization.

Build a mock connector and generic webhook first, followed by one messaging adapter
and one ticketing adapter. Do not write a custom integration for every vendor inside
the rule engine.

Status: complete. The platform now has encrypted organization-owned connectors,
scoped rule bindings, low/medium/high risk classifications, manual approvals,
idempotent leased executions, per-binding rate limits, retries, dead letters, operator
retry/deny controls, and mock, generic-webhook, messaging-webhook, and ticket-webhook
adapters. Physical-system actions are deliberately unavailable. The guided dashboard
shows connector setup and action history without exposing credentials, and both the
native and Docker launch paths run the durable action worker.

### Phase 19 — External context and temporal correlation

Add read/query connectors for systems such as access control, POS, CRM, loyalty,
inventory, and equipment controllers. Normalize their records into time-stamped
observations and join them with camera events through configurable windows and entity
keys. Tailgating becomes materially stronger when a swipe feed is available, while a
camera-only approximation must be labeled as such.

The first reference scenario should combine a simulated access-control feed with a
two-person entrance event and produce a safe ticket/notification rather than control
a real lock.

Status: complete for the reference architecture. The platform now stores tenant-owned
context sources and idempotent vendor-neutral observations, attaches deterministic
time-window correlation policies to camera rules, defers incident creation until the
window closes, and records matched/clear evaluations with an explanation. The first
workflow compares camera person count to granted-access observations; two people and
one swipe creates the normal guarded incident/action, while equal counts produce no
alert. A simulator and guided dashboard exercise the entire path without a real badge
reader or door control. Vendor-specific access-control/POS/CRM adapters remain future
adapter work behind this normalized contract.

### Phase 20 — Visual skill packs and scene memory

Add benchmarked capabilities only when a scenario requires them: OCR, license-plate
recognition, barcode/label reading, PPE attributes, pose/action analysis, open-vocabulary
grounding, segmentation, and anomaly/change detection. The router selects the smallest
capability set that satisfies the stored plan, with VLM windows as the broad fallback.

Persist useful scene state: stable equipment/regions, tracked entities, relationships,
and changes over time. Automatic scene discovery is the default; operators may review
or correct it, but successful basic operation must not require manually drawing every
box or polygon.

Status: complete for the extensible foundation. Eight versioned skill manifests cover
PPE, OCR/screens, license plates, barcodes/labels, pose/actions, open-vocabulary
grounding, segmentation, and change/anomaly analysis. Prompt routing stores only the
skills a plan requires and uses bounded temporal VLM windows as the honest fallback;
a specialized executor cannot replace that fallback until its scenario replay gate
passes. Structured VLM decisions can now emit normalized stable scene observations.
The control plane persists proposed regions, equipment, displays, tracked entities,
attributes, relationships, and state changes, with operator confirm/reject correction
and a safe discovery preview that requires no drawn geometry. Model-specific accuracy
still must be established per customer scene through Phase-16 replay suites.

### Phase 21 — Multi-camera operations, site maps, and investigation

Correlate an entity or incident across cameras, represent camera placement and relevant
site areas, and display events on an interactive operational map. Harden natural-language
historical search over clips, crops, OCR, entities, and event metadata. This enables
the misplaced-cargo pattern: what the item is, where it was last seen, where it should
be, and the evidence explaining the alert.

Status: complete for the product foundation. Tenant-owned sites, normalized areas,
camera placements, anonymous entity sightings, and ordered cross-camera journeys are
durable and authenticated. Tracked scene entities automatically become idempotent
sightings, while a protected edge endpoint supports explicit observations. One
investigation API searches event metadata, scene descriptions/OCR-like attributes,
and entity sightings as a single chronological timeline. The guided dashboard renders
a simple operational map, includes a provider-free one-click setup, and exposes the
unified search without requiring manual geometry. Production-scale vector/full-text
indexing, specialized re-identification accuracy, and customer site imports remain
deployment-specific work and must pass representative replay evaluation.

### Phase 22 — Offline edge station and fleet management

Package the worker, local inference, storage buffer, and selected connectors for a
supported edge appliance. Add hardware capability discovery, GPU/CPU profiles, signed
configuration, health monitoring, remote updates with rollback, offline event queues,
and reconnect synchronization. Cloud control must not be required for rules explicitly
configured to run offline.

Status: complete for the software foundation, not physical-appliance certification.
Control-plane event delivery now uses a durable SQLite edge outbox and automatically
replays idempotent events after reconnect or restart. Enrolled devices report hardware,
software, storage, queue depth, and sync health; the dashboard exposes that fleet state.
Immutable per-device configuration revisions have canonical SHA-256 fingerprints and
server signatures. Audited software update records enforce download/apply/success,
failure, and rollback transitions without executing untrusted remote binaries. Building
and supporting an actual station image, distributing verification keys, signing update
artifacts, validating specific GPU drivers, and operating a remote update channel remain
deployment work that requires hardware and security/business decisions.

### Phase 23 — Hosted product and production hardening

Finish customer onboarding, real login/session UX, camera discovery and validation,
organization administration, secrets management, object storage, Redis-backed fan-out,
cross-instance worker coordination, quotas/billing protection, observability, backups,
retention/privacy controls, security review, load tests, and operational runbooks.

The hosted dashboard should make the main workflow obvious without developer help:
connect a camera, describe a job, review the generated agent, test it on replay, choose
actions, deploy, monitor health/cost, and investigate incidents.

Status: repository-side hardening complete; hosted deployment is intentionally blocked
on real provider and policy decisions. Production settings already fail closed unless
OIDC, per-device edge authentication, signed media access, and encrypted alert secrets
are configured. An administrator-only readiness report now makes every remaining
launch prerequisite visible in the dashboard. The API exposes authenticated internal
Prometheus metrics, and the repository includes bounded load-smoke tooling, explicit
backup tooling, an operations runbook, and a security/privacy review checklist. Replay
gates, provider request budgets, connector rate limits, tenant audit logs, retry/dead
letter handling, and signed evidence access provide the current billing and safety
foundation.

Completing a real hosted launch now requires choices that code must not invent: the
OIDC provider and callback domain, PostgreSQL/Redis/object-storage vendors and regions,
secret manager, public hostname/TLS and WebRTC networking, backup destination, pricing
and customer quotas, and approved video/identity retention policy. Their credentials
must then be configured and the deployment load/security/restore drills executed.

### Phase 24 — Automated camera commissioning

Status: complete in the product and edge software. An administrator can now request a
bounded health check for any camera from its enrolled edge station. The check opens the
real private source without starting inference or a paid model, samples delivery and
image quality, retains a representative preview through the existing bounded store,
and reports a centrally calculated readiness score with specific remediation for
resolution, frame rate, exposure, contrast, focus, frozen video, black frames, and
read failures. Work is tenant-scoped, device-authenticated, leased, restart-reclaimable,
and limited to one active run per camera. The dashboard exposes the complete workflow.

Commissioning proves stream usability, not scenario accuracy. Every real deployment
still needs the Phase-16 replay gate using representative field video for the exact
camera, model, visual job, and operating conditions.

### Phase 25 — Always-on camera and edge reliability

Status: complete in the software product. The existing operations worker now runs a
bounded watchdog over camera heartbeats, live-frame arrival, recording state, and
attached edge-station check-ins. Failures create durable, tenant-owned incidents with
diagnostics, severity, acknowledgement, deduplication, occurrence history, browser
notification support, and Prometheus visibility. Incidents resolve automatically only
when healthy telemetry returns. Intentionally stopped cameras and unattached spare edge
devices are excluded to prevent planned downtime from becoming alert noise.

This closes the repository-side camera-health workflow expected from a serious video
operations product. Appliance RAID, redundant power, temperature, disk-health, and
remote hardware support still depend on the physical edge platform selected for a
deployment.

### Phase 26 — Live proposer-verifier accuracy gate

Status: complete in the software product. Semantic visual windows now produce durable
verification cases instead of immediately becoming incidents. Candidate detections are
sent to a second configured Gemini model only after the proposer clears temporal and
confidence gates. The control plane independently requires a distinct model identifier
and sufficient confidence. Confirmed cases enter the normal event/correlation/alert/action
pipeline; rejected, failed, same-model, low-confidence, and inconclusive cases release
nothing.

The dashboard now includes a Spot AI-inspired but product-native review workspace with
case report cards, signed evidence playback, a compact time window, proposer/verifier
confidence and reasoning, and explicit operator confirmation or rejection. Missing
verifiers fall back safely to manual review. Deterministic tracking rules retain their
direct path and are not falsely described as two-model semantic verification.

This reduces hallucinated semantic alerts but does not replace per-camera field accuracy
testing. Learning from corrections, verifier calibration by scenario, and reviewer
queues/SLAs across large organizations remain later hardening work.

### Phase 27 — Closed-loop field accuracy and drift control

Status: complete in the software product. Every operator verification decision now
creates a durable, human-grounded live outcome for that exact camera and semantic job.
Automatically decided cases remain auditable, and operators can record a visible missed
event instead of letting the product calculate a misleading recall score from generated
alerts alone. Labels distinguish true alerts, false alerts, missed events, and correct
suppressions, with operating-condition tags for low light, occlusion, distance, and
camera motion.

The control plane stores an immutable rolling accuracy snapshot after every label. Each
job has configurable positive, negative, challenging-condition, precision, recall, and
window-size requirements plus a permanent manual-only control. Gate states are
collecting, ready, failing, and drifting. A distinct verifier can release automatically
only while the field gate is ready; insufficient evidence or new drift immediately
returns the job to operator review.

The dashboard exposes per-job precision, recall, F1, confusion counts, evidence progress,
unlabeled audit workload, corrective recommendations, missed-event capture, and the
manual-only safety control. This provides a defensible operating loop but still requires
representative customer-camera evidence. It does not silently fine-tune a provider model
from its own predictions.

### Phase 28 — Fleet-scale active evidence learning

Status: complete in the software product. The existing operations worker now samples
semantic proposals and ordinary archived footage into one tenant-owned review queue.
Uncertain and challenging cases receive the highest priority. Per-job policies bound
normal-footage frequency, daily volume, reviewer SLA, retention, and whether sampling
is enabled. Verification-case uniqueness plus per-job temporal fingerprints prevent
repeated and overlapping clips from flooding the queue.

Reviewers can self-assign work, see deadlines and overdue counts, route release-sensitive
proposals through the verification inbox, and label ordinary footage as correct
suppressions or missed events. Labels feed the Phase-27 accuracy and drift gate. The
dashboard exposes queue balance, assignments, review controls, and dataset operations.

Labeled samples can be selected into outcome-balanced, versioned datasets. A version is
mutable only while draft; freezing records a deterministic manifest SHA-256, and export
re-verifies integrity before returning JSONL tied to the exact camera, job, model, and
configuration context. Exports use durable evidence IDs rather than expiring URLs and
can feed replay evaluation. No provider is silently fine-tuned or deployed.

### Phase 29 — Replay promotion and reviewer quality

Status: complete in the software product. Per-job evidence policies can now require two
independent reviewers. Agreement creates the final field label; disagreement creates a
durable dispute that only a third, non-voting reviewer can adjudicate. Duplicate votes
and self-adjudication are rejected, while every judgment and reason remains auditable.

Any frozen Phase-28 dataset can be materialized idempotently into real replay evaluations
and a regression suite without recompiling prompts or starting cameras. Positive and
negative label snapshots become replay expectations, retained recording/evidence media
becomes the source, and unavailable media is explicitly reported instead of counted as
a pass.

Candidate and baseline runs must use the same frozen evidence suite. Comparisons record
accuracy and false-alarm deltas plus candidate/baseline plan fingerprints. A regression
blocks promotion even if someone attempts approval. Administrator approval deploys via
the existing agent-plan gate and records the decision and known-good rollback target;
rejection and rollback are also durable. First deployments roll back to a paused rule.

## Immediate build order

For private development, the next phase is Phase 30: shadow and canary deployment. Run a
candidate beside the approved plan without releasing its alerts, measure live disagreement,
latency, cost, and drift, canary it to selected cameras, and automatically return to the
known-good plan when operational limits fail. Add a model/config registry before connecting
any approved provider-specific training adapter. A real-camera pilot can already use
Phases 27–29 to measure accuracy, grow evidence, compare changes fairly, and roll back.

A hosted launch remains a planning decision rather than another speculative subsystem.
Choose identity, database, Redis, object storage, secret manager, deployment region,
domain, pricing limits, and retention policy. Then configure those choices, clear the
dashboard readiness report, run the replay/load/security/restore gates, and begin a
small monitored pilot. Phases 18–29 provide the implementation contracts without
hard-coding a vendor or silently choosing legal policy; Phases 26–29 add the live
semantic release gate, evidence review, measured field accuracy, drift lock, automatic
sampling, integrity-checked dataset versions, consensus review, and controlled promotion.

For a short demonstration, the existing platform can already show a live camera,
compile a visual prompt, display its execution route, run bounded analysis, and create
an incident with evidence. That is an honest visual-alert beta, not yet the finished
cross-system autonomous-operator product.
