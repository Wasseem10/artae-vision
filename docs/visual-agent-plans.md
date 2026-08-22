# Versioned visual-agent plans

Phase 17 turns an accepted natural-language camera rule into a stored contract that an
operator can understand before deployment. It is deliberately separate from the raw
model prompt. The prompt proposes intent; the typed plan controls what the platform is
allowed to execute.

## Plan graph

Every plan is an ordered graph of five explicit node types:

- `observe` reads camera frames and runs deterministic or semantic perception;
- `query` requests authorized context from a connector, when a future plan needs it;
- `decide` applies the compiled spatial, temporal, confidence, and cooldown logic;
- `verify` preserves and checks the evidence window; and
- `act` creates an incident or invokes a separately authorized connector.

The current runtime supports camera capture, YOLO detection, ByteTrack identities,
semantic frame windows, spatial/temporal decisions, evidence verification, and local
alert creation. A prompt that asks for access-control data or a physical/business-system
action produces the relevant nodes, but the plan stays blocked until those Phase-18/19
connectors exist. The compiler never silently pretends a connector is available.

## Safe lifecycle

1. The operator describes the camera job and reviews the compiled interpretation.
2. Accepting it creates a draft rule and a versioned visual-agent plan.
3. Safe simulation walks every node and records a trace. All side effects are blocked.
4. Deployment requires a passed replay regression-suite run from the same organization.
5. Approval activates the plan's rule and supersedes the previous approved camera plan.
6. A previously approved version can be restored with rollback and its original passed
   gate remains attached for auditability.

The mutation API is covered by the existing authenticated audit middleware. Tenant
queries always filter by organization, and a regression run from another organization
cannot approve a plan.

## API surface

- `POST /api/v1/agent-plans` creates the next camera-scoped revision from a rule.
- `GET /api/v1/agent-plans` lists visible plans and can filter by `camera_id`.
- `GET /api/v1/agent-plans/{id}` returns one plan.
- `POST /api/v1/agent-plans/{id}/simulate` stores a no-side-effect trace.
- `POST /api/v1/agent-plans/{id}/approve` requires a passed regression run.
- `POST /api/v1/agent-plans/{id}/rollback` restores a superseded approved version.

Database migration `0013_visual_agent_plans` creates the durable plan and simulation
tables. The guided dashboard presents the same lifecycle as: describe, review, simulate,
test, deploy, then start analysis.
