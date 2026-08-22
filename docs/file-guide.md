# File guide

This guide explains the hand-written files through Phase 23. Generated caches,
downloaded weights, virtual-environment files, and runtime artifacts are excluded.

## Repository-level files

- `.gitignore` prevents generated caches, virtual environments, private `.env`
  values, downloaded model weights, and future frontend build output from entering
  version control.
- `.dockerignore` keeps the same private and bulky local files out of Docker build
  contexts, which makes builds faster and prevents accidental secret inclusion.
- `.env.example` documents safe local configuration. It is committed; the copied
  `.env` file is private and ignored.
- `README.md` is the main setup, run, test, configuration, and troubleshooting guide.
- `pytest.ini` tells pytest where the monorepo's tests live.

## Next.js operator console

- `apps/web/README.md` describes the frontend's responsibility and shortest local
  development path.
- `apps/web/package.json` pins the patched Next.js/React toolchain and defines
  development, production build, lint, type-check, and unit-test commands.
- `apps/web/pnpm-lock.yaml` records the complete resolved dependency graph so local,
  CI, and container installs use identical package versions.
- `apps/web/pnpm-workspace.yaml` explicitly permits install scripts only for the
  reviewed native `sharp` and resolver packages instead of allowing all dependency
  scripts.
- `apps/web/tsconfig.json` enables strict TypeScript, browser libraries, Next.js
  integration, and the `@/` source alias.
- `apps/web/next-env.d.ts` loads the framework's generated TypeScript declarations.
- `apps/web/next.config.ts` removes the identifying response header and produces a
  minimal standalone server for the runtime container. It also explicitly permits
  the documented `127.0.0.1` origin for local Next.js development assets.
- `apps/web/eslint.config.mjs` applies Next.js performance, accessibility-adjacent,
  React, and TypeScript lint rules while excluding generated output.
- `apps/web/vitest.config.ts` limits fast unit tests to source-owned test files.
- `apps/web/.env.local.example` documents the public API base URL and milestone-only
  browser WebSocket token without committing a working local configuration.
- `apps/web/Dockerfile` installs with the frozen lockfile, builds the static assets,
  copies only the standalone server output, and runs it as an unprivileged user.
- `apps/web/src/app/layout.tsx` defines global metadata, typography, document
  language, and the root HTML/body shell.
- `apps/web/src/app/page.tsx` keeps the route thin by rendering the dashboard
  composition component.
- `apps/web/src/app/globals.css` owns the responsive visual system, sidebar, cards,
  forms, warehouse preview, polygon overlay, rule states, event timeline, focus
  styles, and mobile layout without a UI-framework dependency.
- `apps/web/src/components/dashboard.tsx` loads the initial API state, selects the
  current camera, coordinates mutations and live telemetry, computes summary
  metrics, and assembles the complete operator workspace.
- `apps/web/src/components/agent-control.tsx` gives an operator explicit Start/Stop
  control and displays desired/observed state, worker identity, FPS, latency, and
  actionable rule-readiness guidance.
- `apps/web/src/components/edge-devices-panel.tsx` enrolls organization-owned edge
  hosts, shows one-time credentials, displays capacity and health, and exposes
  administrator-only rotation and revocation actions.
- `apps/web/src/components/audit-log-panel.tsx` shows administrators the latest
  tenant-scoped operator mutations and response outcomes.
- `apps/web/src/components/camera-panel.tsx` registers webcam/file/RTSP sources and
  lets an operator select the camera whose zones and rules they are editing.
- `apps/web/src/components/zone-editor.tsx` translates pointer positions into
  normalized polygon zones or two-point crossing lines, layers them above live
  video, and supports undo, clear, preview, retry, and save actions. It also renders
  live detection boxes in the same normalized SVG coordinate space.
- `apps/web/src/components/live-stream-player.tsx` loads the reader script served by
  the running MediaMTX version, opens the WHEP stream, attaches its media track to a
  direct video element, and closes the peer connection when the camera changes.
- `apps/web/src/components/rule-panel.tsx` submits natural-language intent, renders
  compiler clarification and strict-IR review states, creates accepted drafts, and
  activates or pauses rules only through a separate operator action.
- `apps/web/src/components/event-feed.tsx` renders recent committed events with
  generic event type, track or aggregate context, count/direction/duration details,
  confidence, evidence state, and live-connection context.
- `apps/web/src/components/evidence-search.tsx` owns the natural-language search
  form, camera scope, asynchronous result polling, provider/fallback disclosure,
  scored result selection, and exact timestamp seeking in the clip player.
- `apps/web/src/components/status-pill.tsx` gives camera and rule statuses one
  accessible textual and visual representation.
- `apps/web/src/components/icon.tsx` contains the small inline SVG icon set, avoiding
  a runtime icon-library dependency.
- `apps/web/src/hooks/use-event-stream.ts` owns WebSocket connection status,
  committed-event, agent-status, and transient-telemetry decoding, cleanup, and
  bounded reconnect behavior.
- `apps/web/src/lib/api.ts` centralizes typed HTTP calls, friendly backend errors,
  base URL handling, and WebSocket URL construction.
- `apps/web/src/lib/types.ts` mirrors the API's camera, zone, rule, event, mutation,
  and status contracts so UI code does not use untyped JSON.
- `apps/web/src/lib/geometry.ts` contains the pure clamping, normalization, and SVG
  conversion functions used by the visual zone editor.
- `apps/web/src/lib/events.ts` prepends live events without duplicating retried IDs
  and bounds the in-memory timeline.
- `apps/web/src/lib/geometry.test.ts` verifies zone coordinate normalization,
  boundary clamping, and SVG conversion.
- `apps/web/src/lib/events.test.ts` verifies live-event ordering and idempotent UI
  insertion.
- `apps/web/src/lib/stream.test.ts` verifies that the reader asset is loaded from
  the same trusted media-gateway origin as the WHEP endpoint.

## Current inference service

- `services/inference/README.md` gives package-building tools local service metadata
  and points developers to the complete root guide.
- `services/inference/pyproject.toml` defines the installable Python package, runtime
  dependencies, development tools, supported Python version, and terminal command.
- `services/inference/src/video_intelligence_inference/__init__.py` identifies the
  directory as the package and exposes its version.
- `services/inference/src/video_intelligence_inference/__main__.py` makes
  `python -m video_intelligence_inference` work.
- `services/inference/src/video_intelligence_inference/config.py` reads and validates
  environment configuration in one place.
- `services/inference/src/video_intelligence_inference/logging_config.py` establishes
  one consistent log format and level for the process.
- `services/inference/src/video_intelligence_inference/camera.py` opens, reads, and
  releases the webcam. Its context-manager design guarantees cleanup on errors.
- `services/inference/src/video_intelligence_inference/detector.py` loads YOLO once,
  runs detection or persistent ByteTrack tracking, and converts library-specific
  results into simple `Detection` values with optional track IDs.
- `services/inference/src/video_intelligence_inference/observer.py` samples frames
  by monotonic time, builds numbered overlapping contact sheets, provides no-key
  and Qwen implementations behind one boundary, validates structured decisions,
  enforces request budgets, persists optional artifacts, and keeps provider work in
  a bounded background queue so a slow service never pauses the camera.
- `services/inference/src/video_intelligence_inference/visualization.py` draws boxes,
  track IDs, confidence scores, normalized zones, directed crossing lines, and the
  latest semantic-observer result on a copy of each frame.
- `services/inference/src/video_intelligence_inference/app.py` is the composition
  root: it wires configuration, camera, detector, rendering, keyboard handling, and
  shutdown together.
- `services/inference/src/video_intelligence_inference/recorder.py` records a
  bounded MP4 from the same camera module. It exists for repeatable clip-ingestion
  tests and keeps recording concerns out of the live detection loop.
- `services/inference/src/video_intelligence_inference/source.py` presents webcams,
  local videos, and RTSP streams through one timestamped-frame interface. It treats
  file end as normal completion and live read loss as an error.
- `services/inference/src/video_intelligence_inference/zones.py` validates
  resolution-independent polygon and line geometry, computes an object's
  bottom-center ground point, and provides polygon-membership and signed-line-side
  operations.
- `services/inference/src/video_intelligence_inference/rules.py` owns deterministic
  dwell/presence, entry/exit, count-threshold, and finite-segment crossing state
  machines. Its heterogeneous rule-set engine evaluates them from one shared
  detection list while each job retains independent temporal state.
- `services/inference/src/video_intelligence_inference/events.py` creates versioned
  event records, appends them to a JSONL development log, compresses a bounded
  pre-event frame buffer, and writes pre/post-event MP4 evidence.
- `services/inference/src/video_intelligence_inference/actions.py` sends optional
  webhook or authenticated control-plane actions from background threads. After a
  clip completes, it also converts the OpenCV file to fast-start H.264 and uploads
  it with bounded retries, keeping network and encoding work out of the video loop.
- `services/inference/src/video_intelligence_inference/control_plane.py` fetches and
  validates a camera's active versioned job specifications, translates legacy dwell
  jobs, resolves polygon/line runtime geometry, and retains an optional single-job
  debugging filter.
- `services/inference/src/video_intelligence_inference/control_credentials.py`
  selects a per-device token for real edge hosts and keeps the shared key as an
  explicit local-development fallback.
- `services/inference/src/video_intelligence_inference/agent.py` is the inference
  composition root. It connects local or control-plane configuration, source,
  ByteTrack inference, zones, the dwell engine, event persistence, evidence,
  network actions, visualization, per-frame callbacks, and clean shutdown.
- `services/inference/src/video_intelligence_inference/telemetry.py` converts pixel
  detection boxes into resolution-independent values shared safely with a browser.
- `services/inference/src/video_intelligence_inference/worker.py` is the persistent
  managed-worker composition root. It fills a bounded set of concurrent camera
  slots, translates every assignment into shared-per-camera inference, reports only
  the newest frame, observes Stop requests, and safely reclaims completed slots.
- `services/inference/src/video_intelligence_inference/publisher.py` resolves a
  file camera's publisher URL through FastAPI and starts FFmpeg with a safe argument
  list to loop an H.264 RTSP development stream without invoking a shell.

## FastAPI control plane

- `services/api/README.md` describes the API boundary and points developers to the
  full setup guide and interactive OpenAPI documentation.
- `services/api/pyproject.toml` makes the API an installable Python package and pins
  compatible FastAPI, SQLAlchemy, PostgreSQL, Alembic, server, and test dependencies.
- `services/api/Dockerfile` builds a small Python image, installs only API runtime
  dependencies, drops privileges to an unprivileged user, runs migrations, and
  starts the API.
- `services/api/alembic.ini` tells Alembic where migrations live and configures its
  logging. Runtime database settings override its harmless local default.
- `services/api/alembic/env.py` connects Alembic to the asynchronous SQLAlchemy
  engine and the application's model metadata.
- `services/api/alembic/script.py.mako` is Alembic's template for future generated
  migration files, keeping their layout consistent.
- `services/api/alembic/versions/0008_edge_devices_and_audit.py` adds hashed device
  credentials, server-owned capacity, camera lease ownership, and append-only audit
  history.
- `services/api/alembic/versions/0001_control_plane.py` is the reproducible initial
  schema migration for cameras, zones, rules, events, constraints, and indexes.
- `services/api/alembic/versions/0002_managed_agents.py` adds the one-to-one durable
  camera-agent row used for desired/observed state, leases, heartbeat, health, and
  last-error reporting.
- `services/api/alembic/versions/0003_searchable_evidence.py` adds evidence assets
  and durable search jobs, including a safe awaiting-upload backfill for events
  created by earlier milestones.
- `services/api/alembic/versions/0004_natural_language_rules.py` adds immutable
  compiler revisions, accepted-rule links, and a version number on runtime rules.
- `services/api/alembic/versions/0005_universal_event_engine.py` adds typed scene
  geometry, versioned JSON job specs, nullable aggregate-event track IDs, and
  structured event details without discarding legacy rows.
- `services/api/alembic/versions/0006_durable_alerts.py` adds encrypted webhook
  destinations, per-job routes, incident state, and leased delivery attempts.
- `services/api/alembic/versions/0007_identity_and_tenancy.py` creates organizations,
  OIDC identities, memberships, roles, tenant ownership columns, and scoped unique
  constraints while assigning legacy rows to the local organization.
- `services/api/src/video_intelligence_api/__init__.py` marks the source directory
  as a package and exposes the service version.
- `services/api/src/video_intelligence_api/__main__.py` supports
  `python -m video_intelligence_api` in addition to the installed command.
- `services/api/src/video_intelligence_api/config.py` validates database, host,
  environment, OIDC/JWKS, signing keys, detector-class, and event-capability settings
  from `VIDEO_INTEL_API_*`; insecure auth configuration fails closed in production.
- `services/api/src/video_intelligence_api/auth.py` verifies local or OIDC identity,
  resolves enabled organization membership, enforces role levels, and authenticates
  organization-bound WebSocket connections.
- `services/api/src/video_intelligence_api/tenancy.py` centralizes foreign-resource
  lookups that join through camera ownership and return no cross-tenant object.
- `services/api/src/video_intelligence_api/admin.py` provides offline organization
  and membership provisioning without exposing a public platform-admin endpoint.
- `services/api/src/video_intelligence_api/media_access.py` signs and verifies
  short-lived evidence URLs bound to one asset and organization.
- `services/api/src/video_intelligence_api/job_specs.py` defines the strict,
  versioned discriminated union for all supported camera-job shapes and the small
  compatibility helpers used to read version-1 dwell jobs.
- `services/api/src/video_intelligence_api/capabilities.py` publishes the configured
  detector vocabulary and validates whether a reviewed job is deployable.
- `services/api/src/video_intelligence_api/database.py` owns the async engine,
  session factory, declarative model base, and clean engine disposal.
- `services/api/src/video_intelligence_api/dependencies.py` gives every HTTP request
  a separate database session through FastAPI dependency injection.
- `services/api/src/video_intelligence_api/models.py` defines durable SQLAlchemy
  camera, zone, rule, event, and camera-agent entities plus statuses, constraints,
  and indexes.
- `services/api/src/video_intelligence_api/schemas.py` defines and validates the
  public request/response contracts separately from database objects.
- `services/api/src/video_intelligence_api/security.py` performs constant-time
  comparison of the separate internal agent credential.
- `services/api/src/video_intelligence_api/source_utils.py` classifies webcam, file,
  and RTSP sources and redacts embedded usernames/passwords from normal responses.
- `services/api/src/video_intelligence_api/media_gateway.py` is the narrow async
  MediaMTX Control API adapter. It adds or patches paths, reads live readiness, and
  translates network failures into one service-level error.
- `services/api/src/video_intelligence_api/rule_compiler.py` defines the strict
  provider candidate, deterministic multi-event parser, optional OpenAI
  structured-output adapter, exact saved-geometry resolver, fallback policy, and
  `camera-job/2` runtime IR.
- `services/api/src/video_intelligence_api/websockets.py` manages this milestone's
  in-process set of event subscribers and removes broken connections.
- `services/api/src/video_intelligence_api/main.py` creates the app, attaches shared
  state, mounts route groups, manages startup/shutdown, and runs Uvicorn.
- `services/api/src/video_intelligence_api/routes/__init__.py` marks the route
  directory as a Python package.
- `services/api/src/video_intelligence_api/routes/health.py` exposes inexpensive
  liveness and database-backed readiness endpoints for operators and containers.
- `services/api/src/video_intelligence_api/routes/cameras.py` creates/lists/reads
  cameras, changes their status, handles conflicts, and returns redacted sources.
- `services/api/src/video_intelligence_api/routes/streams.py` maps cameras to stable
  MediaMTX paths, provisions RTSP proxy or publisher modes, and returns only safe
  playback/publisher URLs plus readiness—not original RTSP credentials.
- `services/api/src/video_intelligence_api/routes/zones.py` creates and lists
  validated normalized polygon zones and two-point lines belonging to a camera.
- `services/api/src/video_intelligence_api/routes/capabilities.py` exposes the
  configured detector and event-engine registry to the dashboard and API clients.
- `services/api/src/video_intelligence_api/routes/rules.py` creates reviewed drafts,
  lists/filter rules, validates camera/zone ownership, and changes rule status.
- `services/api/src/video_intelligence_api/routes/rule_compilations.py` stores
  initial and clarified interpretations, exposes their audit trail, and converts an
  explicitly accepted review into a draft without activating it.
- `services/api/src/video_intelligence_api/routes/events.py` lists events, serves
  authenticated unredacted agent configuration, and ingests idempotent agent events
  before broadcasting committed records.
- `services/api/src/video_intelligence_api/alerting.py` creates one incident and its
  cooldown-aware delivery records inside the event-ingestion transaction.
- `services/api/src/video_intelligence_api/alert_secrets.py` is the single boundary
  for Fernet encryption and decryption of webhook signing secrets.
- `services/api/src/video_intelligence_api/routes/alerts.py` manages destinations
  and per-job routes, exposes incident acknowledgement/resolution, leases due
  deliveries, and owns retry scheduling and terminal delivery state.
- `services/api/src/video_intelligence_api/routes/agents.py` validates dashboard
  Start/Stop requests, provisions source routing, leases requested cameras to
  authenticated workers, stores low-rate health, and broadcasts transient boxes.
- `services/api/src/video_intelligence_api/routes/evidence.py` streams and
  checksums completed clip uploads, serves range-capable playback, leases provider
  jobs, maps timecoded hits back to events, and implements clearly labeled local
  metadata search when Artae is not ready.
- `services/api/src/video_intelligence_api/routes/event_stream.py` authenticates and
  maintains the dashboard event WebSocket connection.
- `services/api/src/video_intelligence_api/routes/identity.py` returns the current
  subject, organization, issuer, and authoritative membership role.
- `services/api/src/video_intelligence_api/device_credentials.py` generates
  high-entropy one-time tokens, hashes them, and parses their versioned device ID.
- `services/api/src/video_intelligence_api/routes/devices.py` lists and enrolls
  tenant devices and owns capacity changes, credential rotation, lease release, and
  revocation.
- `services/api/src/video_intelligence_api/audit.py` records authenticated operator
  mutations without retaining request bodies or secret values.
- `services/api/src/video_intelligence_api/routes/audit_logs.py` exposes recent
  organization audit history only to owners and administrators.

## Artae Labs integration package

- `packages/artae-labs-client/README.md` explains the package boundary and why it
  must remain independent from real-time inference.
- `packages/artae-labs-client/pyproject.toml` defines the installable client,
  HTTP/configuration dependencies, development tools, and smoke-test command.
- `packages/artae-labs-client/src/video_intelligence_artae/__init__.py` identifies
  the Python package and exports its version.
- `packages/artae-labs-client/src/video_intelligence_artae/config.py` validates the
  private Labs API key, base URL, request timeout, polling delay, and total indexing
  timeout from `ARTAE_LABS_*` environment variables.
- `packages/artae-labs-client/src/video_intelligence_artae/models.py` describes the
  small portion of the Artae index, video, upload, and search response contract this
  product consumes. Unknown fields are retained so upstream additions do not break
  the client.
- `packages/artae-labs-client/src/video_intelligence_artae/client.py` creates
  indexes, performs safe presigned uploads, completes ingestion, polls video status,
  and runs timestamped searches. It separates authenticated API requests from
  unauthenticated object-storage uploads to protect the API key.
- `packages/artae-labs-client/src/video_intelligence_artae/cli.py` composes the
  client into one manual end-to-end smoke command: upload, wait, search, and print
  the matching timestamps.

## Evidence intelligence worker

- `services/evidence/README.md` explains why this optional process owns provider
  credentials and why the rest of the platform stays useful without it.
- `services/evidence/pyproject.toml` defines the independently installable service,
  its narrow runtime dependencies, test tools, and terminal command.
- `services/evidence/Dockerfile` installs the local Artae adapter and worker into a
  small image, then drops to an unprivileged user.
- `services/evidence/src/video_intelligence_evidence/__init__.py` marks the package
  and publishes its service version.
- `services/evidence/src/video_intelligence_evidence/config.py` validates the API
  address, shared agent key, worker identity, polling interval, and logging values.
- `services/evidence/src/video_intelligence_evidence/worker.py` claims one index or
  search lease, downloads evidence through FastAPI, invokes Artae off-request,
  reports timecoded results, treats HTTP 501 as unavailable, and cleans temporary
  clip files.

## Alert delivery worker

- `services/alerts/README.md` describes the narrow delivery-process boundary.
- `services/alerts/pyproject.toml` defines its independent dependencies and console
  command; no inference or database package is imported.
- `services/alerts/Dockerfile` builds the worker used by the default Compose stack.
- `services/alerts/src/video_intelligence_alerts/config.py` validates the control
  plane address, internal key, worker name, polling interval, and log level.
- `services/alerts/src/video_intelligence_alerts/worker.py` canonicalizes JSON,
  creates HMAC-SHA256 headers and idempotency keys, classifies HTTP responses, and
  reports outcomes while the API remains the source of retry truth.

## Tests

- `tests/inference/test_config.py` proves environment values are parsed and invalid
  confidence thresholds are rejected.
- `tests/inference/test_observer.py` proves chronological overlap, contact-sheet
  dimensions, provider payload construction, and structured response validation
  without making a real network request.
- `tests/inference/test_camera.py` proves camera lifecycle and failure behavior with
  a fake OpenCV device, so tests never touch real hardware.
- `tests/inference/test_detector.py` proves YOLO results are converted into the
  service's model-independent detection type, including persistent IDs, without
  loading real model weights.
- `tests/inference/test_visualization.py` proves rendering changes the output frame
  while leaving its input untouched.
- `tests/inference/test_recorder.py` uses fake camera and writer objects to prove a
  finite clip writes the expected frame count and releases resources on success or
  codec failure.
- `tests/inference/test_source.py` proves local-file completion, webcam capture
  settings, timestamp production, cleanup, and missing-input errors without opening
  physical hardware.
- `tests/inference/test_zones.py` proves normalized polygon membership, boundary
  handling, bottom-center box anchoring, and coordinate validation.
- `tests/inference/test_rules.py` proves dwell thresholds, one event per continuous
  visit, exit/reset behavior, short versus long tracking gaps, and independent
  multi-job evaluation from one detection stream.
- `tests/inference/test_events.py` proves the JSONL event schema and that evidence
  clips contain the buffered pre-event and streamed post-event frames.
- `tests/inference/test_actions.py` proves event JSON is delivered through the
  background webhook boundary and completed evidence uses authenticated retrying
  upload requests, using in-memory HTTP transports.
- `tests/inference/test_agent_control_plane.py` proves remote configuration carries
  authentication, converts polygons and rule values correctly, returns all active
  jobs, supports an optional filter, and rejects an empty supported job set.
- `tests/inference/test_publisher.py` proves the FFmpeg command loops a spaced file
  path, forces a browser-compatible low-latency H.264 RTSP output, and remains a
  structured argument list rather than a shell command.
- `tests/inference/test_telemetry.py` proves pixel detections become clamped,
  normalized browser overlay values without losing class, track, or confidence.
- `tests/inference/test_worker.py` proves assignment conversion, authenticated claim
  behavior for multiple jobs, two-camera concurrency, latest-only telemetry
  delivery, graceful Stop handling, and failures.
- `tests/api/conftest.py` creates a fresh temporary SQLite database and FastAPI test
  client for each API test without requiring a running PostgreSQL server.
- `tests/api/test_control_plane.py` covers camera/zone/rule lifecycle, source
  redaction, protected agent configuration, authenticated/idempotent event ingest,
  WebSocket fan-out, inactive-rule rejection, stream provisioning, credential-safe
  browser contracts, managed assignment claims, leases, telemetry, Start/Stop,
  evidence upload/checksums/playback, provider job leasing, local and timecoded
  searches, health, and OpenAPI generation.
- `tests/api/test_rule_compiler.py` runs deterministic language evals and proves the
  compile, clarify, review, draft, and separate activation lifecycle through HTTP.
- `tests/api/test_agent_plans.py` proves safe simulation, mandatory replay gates,
  capability blockers, plan versioning, approval, supersession, and rollback.
- `tests/api/test_visual_agent_plan_compiler.py` proves deterministic jobs use local
  detection/tracking while open-ended jobs use semantic visual windows.
- `tests/api/test_alerts.py` proves secret-safe channel APIs, atomic event routing,
  ingest idempotency, cooldown suppression, leased completion, and cancellation of
  delayed escalation after acknowledgement.
- `tests/api/test_tenancy.py` proves cross-organization hiding, same-name isolation,
  signed URL tamper rejection, OIDC signature/claim validation, role denial, and
  production configuration fail-closed behavior.
- `tests/api/test_websocket_tenancy.py` proves an event broadcast reaches only
  connections registered to the matching organization.
- `tests/api/test_admin.py` proves offline organization and membership provisioning.
- `tests/api/test_edge_devices.py` proves one-time hashed credentials, organization
  isolation, capacity enforcement, rotation, revocation, lease ownership, and
  operator audit records.
- `tests/evals/rule_compiler_cases.json` is the first version-controlled language
  quality dataset, covering successful normalization, required clarifications, and
  industry-neutral model-routing scenarios.
- `tests/inference/test_routing.py` proves mixed jobs share the appropriate runtime
  and that semantic-only cameras do not require the object detector.
- `tests/evidence/test_worker.py` proves clip download/provider-ID reporting,
  timecoded search reporting, and explicit HTTP-501 unavailability behavior with
  no external requests.
- `tests/alerts/test_worker.py` verifies the exact canonical signed body,
  idempotency header, and retryable versus permanent HTTP response classes entirely
  with an in-memory HTTP transport. It also proves mock, messaging, and ticket action
  adapters without making external requests.
- `tests/api/test_guarded_actions.py` proves scoped connector creation, automatic and
  manually approved actions, leasing, idempotency, retries, dead letters, rate limits,
  alert-resolution suppression, and the physical-action safety block.
- `tests/evidence/__init__.py` and `tests/inference/__init__.py` give pytest unique
  module namespaces now that both services have a `test_worker.py` file.
- `tests/artae/test_client.py` uses in-memory HTTP transports to verify the checked-
  in Artae Labs ingestion/search contract, polling behavior, errors, and the rule
  that API credentials never reach a presigned storage host.

## Infrastructure and design documentation

- `docs/model-routing.md` explains why a job uses deterministic tracking or temporal
  visual reasoning and makes clear that routing tests are not visual-accuracy tests.
- `services/api/src/video_intelligence_api/execution_plans.py` builds the typed,
  operator-reviewable route returned with compilations, rules, and worker assignments.
- `services/inference/src/video_intelligence_inference/routing.py` enforces that route
  on the edge worker and rejects semantically incompatible strategy changes.

- `infra/docker-compose.yml` runs local MediaMTX, PostgreSQL, the API, and the
  operator console with health checks and persistent database/evidence volumes. An
  opt-in `artae` profile starts the evidence worker only when credentials exist.
- `infra/mediamtx.yml` enables only the protocols needed for local RTSP publishing,
  WebRTC/WHEP playback, path provisioning, and metrics. Its anonymous permissions
  and loopback assumptions are explicitly development-only.
- `infra/README.md` explains why the camera agent remains on the host and warns that
  Compose's fallback keys are only for local development.
- `docs/openvector-competitive-research.md` records dated public evidence about
  OpenVector and competitors, reusable open-source candidates, explicit inferences,
  and the recommended build order.
- `docs/product-roadmap.md` converts the visual-operations-agent target into remaining
  phases with concrete exit criteria, including evaluation, integrations, context
  correlation, scene memory, maps, offline edge operation, and hosted hardening.
- `docs/replay-evaluations.md` explains the Phase-16 labeled-video baseline, temporal
  matching rules, reported accuracy/cost metrics, and the automatic-runner boundary.
- `services/api/src/video_intelligence_api/evaluation_scoring.py` implements reusable,
  deterministic one-to-one temporal interval scoring.
- `services/api/src/video_intelligence_api/routes/evaluations.py` creates tenant-owned
  replay baselines through the production compiler, leases queued runs, and stores
  submitted run scores without creating incidents.
- `services/inference/src/video_intelligence_inference/replay.py` executes finite MP4s
  through the production deterministic or semantic components and emits only labeled
  evaluation intervals and provider usage.
- `apps/web/src/components/replay-evaluation-panel.tsx` provides the dashboard workspace
  for defining labels, inspecting the execution route, launching a leased run, and
  inspecting its live status and score.
- `docs/visual-agent-plans.md` explains the Phase-17 typed plan graph, capability
  boundaries, safe lifecycle, versioning, APIs, and rollback behavior.
- `services/api/src/video_intelligence_api/visual_agent_plans.py` compiles accepted jobs
  into typed observe/query/decide/verify/act nodes and validates deployability.
- `services/api/src/video_intelligence_api/routes/agent_plans.py` persists plan versions,
  runs safe simulations, enforces regression approval, and restores prior versions.
- `apps/web/src/components/guided-agent-workspace.tsx` is the default plain-language
  camera-to-alert workflow, including guarded connector setup, approvals, and action
  history; existing engineering controls remain under Advanced tools.
- `docs/guarded-actions.md` explains the Phase-18 connector registry, risk boundary,
  encrypted credentials, durable action lifecycle, adapters, and local worker.
- `services/api/src/video_intelligence_api/guarded_actions.py` defines the fixed action
  registry, connector scopes, and bounded execution payloads.
- `services/api/src/video_intelligence_api/routes/actions.py` exposes tenant-scoped
  connector, binding, approval, dead-letter retry, worker lease, and result APIs.
- `docs/external-context.md` explains normalized external observations, deferred
  time-window evaluation, and the safe two-people/one-swipe reference workflow.
- `services/api/src/video_intelligence_api/correlations.py` extracts bounded visual
  counts, queues due-window evaluations, and performs deterministic count comparison.
- `services/api/src/video_intelligence_api/routes/context.py` exposes context sources,
  idempotent observations, correlation policies, evaluations, the safe simulator, and
  the protected worker processing boundary.
- `tests/api/test_external_context.py` proves matched and clear tailgating outcomes,
  action gating, explanation counts, and idempotent observation ingest.
- `docs/visual-skills-scene-memory.md` explains minimal skill routing, semantic
  fallback, replay promotion gates, automatic scene observations, and review status.
- `services/api/src/video_intelligence_api/visual_skills.py` defines the versioned
  skill manifests and deterministic prompt-to-capability selection.
- `services/api/src/video_intelligence_api/scene_memory.py` validates normalized
  scene observations, upserts stable state, and records real state transitions.
- `services/api/src/video_intelligence_api/routes/scene_memory.py` exposes the skill
  registry, scene lists/changes, agent ingest, operator review, and provider-free demo.
- `tests/api/test_scene_memory.py` proves registry policy, stable upsert, change
  deduplication, relationships, review provenance, and automatic discovery proposals.
- `docs/multicamera-operations.md` explains sites, areas, camera placement,
  anonymous cross-camera sightings, unified investigation search, and accuracy/privacy
  boundaries.
- `services/api/src/video_intelligence_api/routes/operations.py` exposes tenant-scoped
  maps, placements, journeys, edge sighting ingest, safe local setup, and unified search.
- `tests/api/test_multicamera_operations.py` proves two-camera journeys, idempotency,
  map composition, and event/scene/entity investigation results.
- `docs/offline-edge-fleet.md` explains the durable event outbox, device profiles,
  signed config revisions, update state machine, and appliance boundary.
- `services/inference/src/video_intelligence_inference/outbox.py` is the local SQLite
  store that retains canonical events until the control plane acknowledges them.
- `services/inference/src/video_intelligence_inference/hardware.py` discovers a bounded
  host profile and reports the current offline queue depth.
- `services/api/src/video_intelligence_api/routes/fleet.py` exposes enrolled-station
  profiles, fleet aggregation, signed revisions, and audited update/rollback state.
- `tests/api/test_edge_fleet.py` and `tests/inference/test_hardware.py` cover the fleet
  identity, signature, profile, update, and discovery contracts.
- `services/api/src/video_intelligence_api/routes/production.py` exposes the
  administrator readiness report and private Prometheus metrics without leaking
  configuration secrets.
- `apps/web/src/components/production-readiness-panel.tsx` turns hosted launch gaps
  into a plain checklist instead of a misleading green “ready” indicator.
- `docs/production-runbook.md` and `docs/security-review-checklist.md` define backup,
  restore, load, incident, privacy, and security gates for a real deployment.
- `scripts/backup-control-plane.ps1` and `scripts/smoke-load.py` provide explicit,
  bounded operational checks that can be rerun in deployment environments.
- `docs/security.md` documents authentication modes, role permissions, tenant
  ownership inheritance, signed media access, and remaining production hardening.

## Remaining future-boundary placeholders

- `packages/README.md` states the rule for adding further shared code rather than
  using `packages` as a miscellaneous dumping ground.
- `docs/architecture.md` records today's data flow and the intended growth path.
- `docs/artae-upstream-assessment.md` records which Artae Labs patterns are useful,
  which live-camera capabilities are still missing, and how to integrate safely.
- `docs/adr/0001-use-artae-labs-as-intelligence-plane.md` records the accepted
  decision to keep live YOLO processing separate from asynchronous Gemini-powered
  ingestion and search, including its tradeoffs and upstream provenance.
