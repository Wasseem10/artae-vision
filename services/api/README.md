# Control-plane API

This installable FastAPI service is the durable control plane for cameras, zones,
rules, and events. PostgreSQL is the production database; tests use SQLite through
the same SQLAlchemy 2.x models. Alembic migrations, Docker instructions, endpoint
examples, and the relationship to the inference agent are explained in the root
`README.md` and `docs/file-guide.md`.

The service deliberately does not process video frames. Inference workers run
close to camera streams, claim desired camera assignments with short leases, and
report structured events through authenticated internal endpoints. Durable agent
rows store desired/observed status and low-rate health. Per-frame boxes are only
broadcast to connected dashboards and are not inserted into PostgreSQL.

Milestone 7 also makes event evidence a two-phase durable resource. The agent
commits event metadata first, then streams the completed browser-compatible clip
to an authenticated upload endpoint. The API applies a size limit, computes a
SHA-256 checksum, stores the file outside PostgreSQL, and leases slow indexing and
search work to the optional evidence worker. Evidence routes list status, serve
range requests through tenant-bound signed playback URLs, submit searches, and poll
durable results.

The API is also the security boundary in front of MediaMTX. Stream endpoints
provision or inspect derived camera paths through the private Control API and return
only WebRTC/WHEP or publisher URLs. They never return an RTSP camera's original
credentials to dashboard code.

Milestone 8 adds a review-first natural-language compiler. Compilation and
clarification endpoints store immutable revisions, validate provider output through
a strict Pydantic intermediate representation, resolve saved zones inside the API,
and create only draft rules when an operator accepts a result. `auto` mode uses the
optional OpenAI Responses API when a key exists and otherwise uses the deterministic
object-dwell parser; activation remains a separate existing endpoint.

Milestone 9 changes the managed assignment from one rule to a non-empty rule list.
Starting a camera requires at least one active job; the assignment snapshot contains
every active dwell job so one edge worker can evaluate them from the same tracked
detections. Rule status changes are rejected while the camera is requested to run;
operators stop, change the deployed job set, and restart the agent.

Milestone 10 replaces the new-job contract with versioned `camera-job/2` documents.
The strict discriminated union supports polygon presence/dwell/entry/exit,
aggregate count thresholds, and directed-line crossings. Existing `object_dwell`
records remain readable. `/api/v1/capabilities` publishes the configured detector
classes and event engines, and activation refuses jobs that this deployment cannot
run. Polygon zones and two-point lines share the normalized scene-geometry table.

Milestone 15 adds `camera-job/3` semantic-vision jobs. Open-ended visible
conditions retain the operator's exact instruction, use an automatically created
full-frame region, and flow through the same reviewed draft, activation,
assignment, event, incident, evidence, WebSocket, and alert contracts as
deterministic jobs.

Milestone 11 adds durable incidents and signed webhook delivery. Milestone 12 adds
OIDC bearer verification, organization membership roles, tenant-scoped queries and
WebSockets, and offline provisioning through `video-intelligence-admin`. Local
dashboard-key mode maps to one development organization and is rejected by
production settings.

Milestone 13 enrolls organization-owned edge devices. A token is returned once,
persisted only as a SHA-256 hash, and used through `X-Device-Token` for camera
configuration, assignment, telemetry, event, and clip endpoints. Every device has
a server-side camera capacity and supports credential rotation and revocation.
Operator mutations are written to an append-only tenant audit log without request
bodies, access tokens, camera credentials, or webhook secrets.

Current endpoints are visible in the interactive OpenAPI page at `/docs`. New
rules start as drafts. A production camera agent authenticates with
`X-Device-Token` (the shared `X-Agent-Key` is local-development only), fetches the
unredacted source plus active rules from `/api/v1/agent/config`, and posts events to
`/api/v1/agent/events`. Dashboard WebSocket clients connect to
`/api/v1/ws/events`; local development uses the static token, while OIDC mode uses
the same short-lived access token as the HTTP resource server.

Managed lifecycle endpoints live under `/api/v1/cameras/{camera_id}/agent` for
dashboard control and `/api/v1/agent/assignments/claim` plus
`/api/v1/agent/telemetry` for workers. Starting validates that at least one job is
active and provisions the camera's stable MediaMTX path before all active jobs
become claimable together.
