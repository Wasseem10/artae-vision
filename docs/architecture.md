# Architecture direction

## Milestone 1: local inference loop

```text
Webcam -> camera module -> YOLO detector -> renderer -> desktop window
                       configuration + logging
```

A bounded recorder can send a completed MP4 through a separate asynchronous path:

```text
Webcam -> finite recorder -> MP4 -> Artae Labs -> Gemini embeddings -> search results
```

The Labs client is not called inside the per-frame YOLO loop. This keeps local
detection independent from network latency, indexing time, and service outages.

## Milestone 2: first camera-to-action agent

```text
webcam / MP4 / RTSP
        |
   OpenCV source
        |
YOLO + ByteTrack IDs
        |
normalized polygon zone
        |
person dwell state machine
        |
        +----> JSONL event
        +----> pre/post evidence MP4
        `----> background webhook
```

This milestone intentionally supports one compiled rule shape: an object class
remaining inside one zone for a duration. The temporal decision is deterministic;
an LLM is not consulted for each frame. A future natural-language compiler will
produce validated configuration for this engine and other explicit rule types.

Video-file timestamps come from the media timeline, while live source timestamps
use a monotonic clock. This lets the same state machine process prerecorded tests
quickly without changing dwell semantics. Brief missing detections are tolerated by
a configurable grace period, but an observed move outside the zone resets the visit
immediately.

Evidence buffering stores pre-event frames as JPEG rather than raw 720p arrays to
bound memory use. Post-event frames stream directly into a per-event MP4. Webhooks
run on a separate worker thread so a slow integration does not block frame capture
or inference.

The application entry point coordinates four small responsibilities:

1. `config.py` validates values from the environment.
2. `camera.py` owns webcam lifecycle and frame capture.
3. `detector.py` owns model loading and prediction result conversion.
4. `visualization.py` draws detections without knowing where frames came from.

This separation gives later code stable seams for tests and replacements. For
example, an RTSP camera can implement the capture responsibility without changing
YOLO inference, and a worker can consume detections without using a desktop window.

## Milestone 3: durable control plane

```text
                         PostgreSQL
                             ^
                             |
operator / Next.js UI -> FastAPI control plane -> WebSocket event subscribers
                             ^     |
             agent config   |     | authenticated, idempotent event
                             |     v
                    host inference agent
                  camera -> YOLO/track -> rule -> clip
```

FastAPI now owns camera, normalized-zone, rule, and event records. New rules are
always drafts and must be explicitly activated. Camera source credentials are
redacted from normal camera responses; only the agent-key-protected configuration
endpoint returns the original source URI.

The host inference agent can fetch one active `object_dwell` rule from the control
plane. It then uses the API camera ID and rule ID when posting events. Ingestion is
idempotent on the agent-generated event UUID, so a retry does not duplicate an
event. After the database commit, the API broadcasts `event.created` to connected
WebSocket clients.

The WebSocket manager is deliberately process-local in this milestone. A later
multi-instance deployment will use Redis pub/sub or a durable broker for fan-out.
Evidence paths currently point to the agent's local disk; object storage is the
next durable media boundary. The static development keys must be replaced by user
authentication, agent identities, secret management, and short-lived WebSocket
credentials before public deployment.

## Milestone 4: operator console

The Next.js application is a browser control surface over the milestone-3 API. It
loads cameras, zones, rules, and recent events in parallel, then updates its event
timeline from the existing WebSocket after the initial read.

The zone editor converts browser pointer positions into normalized coordinates and
sends only plain polygon points to the API. Milestone 4 intentionally used a static
preview placeholder; milestone 5 replaced that surface without changing the zone
representation.

The rule builder preserves the user's natural-language description but only emits
the supported, inspectable `object_dwell` fields. New rules remain drafts until the
operator activates them. This follows the review-before-action product pattern
without claiming that a general language compiler exists today.

The browser uses a configured API origin allowlist. Its WebSocket key is visible in
client code and is therefore only a development gate; real user sessions and
tenant authorization remain mandatory before deployment.

## Milestone 5: live stream gateway

```text
RTSP camera ---------------------> MediaMTX path
local MP4 -> FFmpeg publisher ---> MediaMTX path
                                      |      ^
                                      |      | private path provisioning/status
                                      v      |
                              WebRTC / WHEP  FastAPI
                                      |
                                      v
                          direct browser video element
                                      + normalized SVG polygon overlay
```

FastAPI derives a stable `camera-{uuid}` path. RTSP cameras are configured as
on-demand proxy sources; webcam/file records are configured as publisher paths.
The browser receives playback URLs and readiness only. Embedded RTSP usernames,
passwords, and the MediaMTX Control API remain server-side.

The web player loads the JavaScript reader served by the same MediaMTX instance,
then owns the peer-connection lifecycle through React. A direct video element is
used instead of an iframe so the polygon surface and displayed pixels share one
coordinate system. The current player stretches unusual aspect ratios to preserve
normalized-coordinate fidelity; preserving aspect ratio later must compensate for
letterbox offsets explicitly.

The MP4 publisher is a development adapter, not an inference worker. It proves the
complete RTSP-to-WebRTC path without camera hardware. The inference agent still
opens its configured source independently; consolidating decode and fan-out is a
later multi-camera worker concern.

The checked-in MediaMTX authentication and ICE settings are only for a private
local stack. Production requires tenant/user authorization, publisher credentials,
TLS, network policy, and a tested STUN/TURN/public-host strategy.

## Milestone 6: managed vision-agent lifecycle

```text
dashboard Start/Stop -> FastAPI desired state -> PostgreSQL camera_agents
                              |                         ^
                              v                         | lease + health
                     host worker claims camera --------+
                              |
                    stable MediaMTX RTSP path
                              |
                  YOLO + ByteTrack + dwell rule
                       |                  |
                durable events     latest-frame telemetry
                       |                  |
                  PostgreSQL        WebSocket broadcast
                                          |
                                boxes over browser video
```

FastAPI stores what the operator wants separately from what a worker currently
observes. This desired/observed split makes crashes visible instead of pretending a
start button means inference is running. A worker owns an assignment only while it
renews a short database lease; an expired running request can be reclaimed after a
process or host failure.

Workers read the same stable MediaMTX path used by the live-video system, so source
routing is controlled in one place. FastAPI never starts a desktop process and
does not decode frames. Durable agent rows contain only status, worker identity,
heartbeat, FPS, latency, dimensions, and errors. Detection boxes are transient
WebSocket telemetry and are deliberately not stored per frame in PostgreSQL.

The milestone-6 managed worker runs one camera at a time. Multiple worker processes can
claim different cameras, while concurrent slots, Redis-backed scheduling, and
cross-API-instance WebSocket fan-out remain future scaling work.

## Milestone 7: durable and searchable evidence

```text
dwell event ---------------------------> PostgreSQL event metadata
     |
post-event recorder finishes
     |
background H.264 conversion + upload --> API evidence directory
                                             |
                                      SHA-256 + queued state
                                             |
                              optional evidence worker lease
                                             |
                            Artae upload -> Gemini indexing
                                             |
natural-language query -> durable search job -> timecoded provider hits
          |                                  |
          +---- local metadata fallback -----+
                                             |
                                      browser clip player
```

An event is committed before its clip finishes. This is an intentional two-phase
contract: alerts remain fast, while the completed MP4 is uploaded separately and
idempotently. Conversion to fast-start H.264 runs in the inference process's
background upload thread, not the frame loop. FastAPI enforces a size limit,
computes a SHA-256 digest while streaming, atomically replaces partial files, and
stores only the resulting path and metadata in PostgreSQL.

The optional evidence worker is the only component that requires an Artae Labs
key. It leases queued index and search jobs from FastAPI, downloads clips through
the API boundary, and reports provider IDs or timecoded results. A 501 is recorded
as provider unavailability rather than breaking event capture or playback. When no
Artae clip is ready, the API performs clearly labeled deterministic token matching
over camera, object, zone, and event metadata.

The filesystem evidence store is a development implementation of a storage
boundary, not the final cloud design. Its API-owned paths can later be replaced by
S3-compatible object storage and signed URLs without changing event, worker, or
dashboard contracts. Likewise, database leases are sufficient for this worker
volume; Redis or a durable queue can replace their scheduling role when needed.

## Milestone 8: review-first natural-language rules

```text
operator prompt + saved camera zones
                |
       provider candidate
      /                  \
deterministic          optional OpenAI
      \                  /
       strict Pydantic validation
                |
       exact saved-zone resolution
                |
     immutable compilation revision
        |                 |
 clarification      human acceptance
                          |
                    draft rule (IR v1)
                          |
                 separate activation click
```

Providers return a candidate, never an executable database object. The control
plane owns the versioned intermediate representation, validates numeric limits,
and maps a provider's zone name to exactly one zone belonging to the selected
camera. Missing or ambiguous object, zone, and duration fields produce a question
instead of a guess.

Initial requests and clarification answers create linked immutable revisions.
Accepting a ready revision writes a normal draft rule through the existing runtime
contract; it does not activate the rule. This keeps the current deterministic
inference engine independent from whichever language provider produced the
reviewed configuration.

The local compiler handles the supported object-dwell pattern without a network
or API key. In `auto` mode, OpenAI structured output is used only when configured,
and provider failure falls back with a visible warning. The checked-in eval cases
are the starting quality gate for adding new phrasing or future rule types.

## Milestone 9: multiple jobs per camera

```text
one camera stream
       |
  decode frame once
       |
 YOLO + ByteTrack once
       |
 shared tracked detections
    /        |        \
 job A     job B     job C
 zone/time zone/time zone/time
    \        |        /
 independent events and evidence clips
```

FastAPI now assigns a non-empty list of active jobs instead of one rule. The edge
worker builds one temporal engine per job but shares capture, decoding, detection,
and persistent tracking. This prevents compute cost from growing linearly with the
number of simple automations on a camera.

Each job retains independent track timers, confidence filtering, zone membership,
and one-event-per-visit behavior. Multiple jobs may fire on the same frame and each
receives its own durable event ID and evidence recording. At milestone 9 the worker
still claims one camera at a time; running several cameras requires several workers until
concurrent camera slots are introduced.

Assignments are deployment snapshots rather than an eventually inconsistent live
list. FastAPI rejects activation or pause changes while a camera's desired state is
running. Stopping, changing jobs, and restarting produces a new atomic snapshot;
hot configuration reload can replace this boundary in a later milestone.

## Milestone 10: universal event engine

```text
one decoded frame -> YOLO detections -> ByteTrack identities
                                      |
                     +----------------+----------------+
                     |                |                |
               polygon jobs      count jobs      crossing-line jobs
             presence / dwell    threshold +      finite segment +
               entry / exit      confirmation        direction
                     +----------------+----------------+
                                      |
                         generic event + evidence clip
```

New jobs are stored as strict `camera-job/2` JSON documents. The discriminated
`rule_type` selects one validated shape instead of adding nullable database columns
for every future rule. Existing version-1 `object_dwell` documents are translated
at the control-plane boundary, so deployed data does not need an unsafe flag-day
rewrite.

Scene geometry now has an explicit type. Polygon zones require at least three
normalized points; crossing lines require exactly two. A line event is emitted only
when the tracked object's motion segment intersects the saved finite line segment,
not merely when it crosses an infinite extension. Count jobs use unique track IDs,
temporal confirmation, and re-arm only after the threshold condition clears.

The capability registry separates core event logic from detector vocabulary. The
API publishes the configured model, detectable object classes, and enabled event
types. Compilation can disclose a capability mismatch and activation rejects it.
That makes specialized PPE, OCR, pose, traffic, or retail models optional capability
packs rather than warehouse assumptions embedded in the event engine.

## Milestone 11: durable alert response

```text
committed event + configured routes
              |
      one database transaction
              |
        alert incident
              +---- operator acknowledge / resolve
              |
       delivery records ---- cooldown / delay
              |
       leased alert worker
              |
 canonical JSON + HMAC-SHA256 ----> customer webhook
              |
       success / bounded retry / permanent failure
```

Every event creates exactly one incident, even when no outbound route exists. This
keeps the operator workflow independent from integrations. Enabled routes create
delivery records in the same transaction, so an API crash cannot commit an event
while silently losing its alert. Event UUID idempotency also prevents duplicate
incidents and deliveries when an inference agent retries ingestion.

Webhook I/O never runs in the API request or camera frame loop. A worker claims one
due delivery with a short lease, receives only that destination's decrypted secret,
and sends a canonical signed body with an idempotency key. The API owns retry state
and exponential-backoff timing. This makes worker crashes reclaimable and response
classification testable without Redis at the current scale.

Cooldowns are per job and destination, not global. Delayed routes model escalation:
acknowledging or resolving an incident before the due time suppresses the pending
delivery. Signing secrets use Fernet encryption at rest and are never returned in
operator schemas. Production still requires a managed secret/KMS strategy, key
rotation, user/tenant authorization, and SSRF/network egress controls before users
can supply arbitrary webhook URLs on an internet-exposed deployment.

## Milestone 12: identity and organization isolation

```text
OIDC access token -> issuer/audience/JWKS validation
                              |
                  organization + membership role
                              |
             +----------------+----------------+
             |                |                |
         cameras/jobs      events/clips      alerts/searches
             |                |                |
             +-------- tenant-scoped queries -+
                              |
                 organization-only WebSocket fan-out
```

FastAPI is a resource server rather than a password database or authorization
server. Production settings require OIDC, asymmetric token verification, an exact
issuer/audience, and provisioned database membership. Local key authentication is
an explicit development mode and cannot be selected in a production environment.

Direct ownership is stored on cameras, alert channels, and durable searches. Other
records inherit ownership through foreign keys and are scoped with joins at every
operator read or mutation. Foreign identifiers return 404 so ownership is not
leaked. Worker endpoints remain on a separate internal credential boundary and
derive organization routing from the camera they already own.

WebSocket connections are keyed by organization, closing the previous process-wide
fan-out leak. Browser video elements cannot attach bearer headers, so evidence uses
short-lived HMAC URLs bound to both asset and organization. The original agent-key
path remains available only for the internal evidence worker.

## Milestone 13: managed multi-camera edge fleet

```text
organization administrator -> enroll/rotate/revoke edge device
                                  |
                           one-time device token
                                  |
camera requests -> database lease allocator -> bounded host supervisor
                                                 |       |       |
                                              camera A camera B camera C
                                                 |       |       |
                                              independent capture/model/state
```

An edge credential belongs to exactly one organization and is stored only as a
hash. The allocator locks the device row, counts its active leases, and returns only
cameras owned by that organization. Rotation or revocation releases its leases so
another healthy device can reclaim still-requested cameras after the normal poll.

The host supervisor fills a configurable number of slots with independent camera
loops. Each slot retains the existing one-decode, one-detection-pass, many-job
optimization for its camera. The host and control plane both impose capacity; this
prevents a local configuration mistake from silently exceeding an administrator's
limit. Database leases remain sufficient for safe PostgreSQL-backed reassignment.

Authenticated operator mutations are recorded after routing with actor, role,
request ID, resource, response status, and timestamp. Bodies are never retained,
so camera credentials, access tokens, webhook secrets, and natural-language prompts
do not enter the audit table.

## Milestone 14: continuous semantic observer foundation

The universal path begins with overlapping sampled windows rather than attempting
to hand-code deterministic logic for every natural-language behavior:

```text
shared camera frame
      |-- YOLO -> local preview
      `-- timed sampler -> numbered 10-frame sheet
                              |
                       bounded background queue
                              |
                       provider boundary -> validated decision
                          |               |
                       dry-run       Gemini Flash-Lite
                              |
                         preview status / future event
```

`observer.py` owns time-based sampling, overlap, sheet composition, provider I/O,
response validation, hard minute/day request budgets, local artifacts, and a
bounded worker queue. Provider latency never blocks the capture loop. If inference
falls behind, the oldest queued sheet is dropped so the observer stays close to
live time instead of accumulating unbounded delay. A predictable dry-run provider
exercises the complete local path without credentials; configuration validation
requires a private key when a cloud provider is selected.

This semantic observer is the broad fallback for visually observable rules. YOLO,
tracking, crops, motion gates, and deterministic rules remain useful optimizations
after representative clips prove that they preserve accuracy and reduce cost.

## Milestone 15: managed natural-language semantic alerts

`camera-job/3` adds `semantic_vision` without creating a parallel event system. If
an operator request does not map safely to a deterministic zone, count, or crossing
primitive, the compiler preserves the exact instruction and grounds it to an
automatic full-frame polygon. The operator still reviews and activates the draft.

The managed camera worker fans each completed overlapping sheet to assigned
semantic jobs on bounded background queues. Each job can require consecutive
positive windows and has a cooldown before another event can be emitted. Positive,
validated VLM decisions become ordinary events with the explanation, first
matching frame, and window timing in `details`; existing clip recording, FastAPI
ingestion, incidents, WebSockets, and durable alert delivery remain shared.

## Intended growth path

Future milestones can add components around these loops rather than rewrite them:

```text
natural-language job -> reviewed visual-agent plan
                              |
Next.js web app -> FastAPI control plane ---- PostgreSQL / Redis
                              |
camera registry -> edge workers -> perception and temporal state
                              |                    |
                  external context queries -------+
                              |
                    decision and verification
                              |
                    guarded action runtime -> authorized legacy systems
                              |
                 events, evidence, audit, maps, and search
```

- The API manages cameras, zones, rules, events, users, organization membership,
  role authorization, edge enrollment, audit records, and tenant-scoped WebSocket
  clients. Hosted provider login UX remains future work.
- Inference supervisors now run bounded concurrent cameras while sharing detection
  and tracking only among the jobs attached to each individual stream.
- PostgreSQL will store durable configuration and event metadata.
- Redis can coordinate short-lived jobs, state, and fan-out where justified.
- API-owned storage now holds clips outside PostgreSQL; external object storage is
  future deployment work. Signed alert delivery is durable today.
- Natural-language jobs can run through the managed `camera-job/3` semantic observer
  first. Proven high-volume behaviors may compile into deterministic `camera-job/2`
  primitives as a cost and latency optimization; no provider call blocks the
  per-frame loop.
- A future versioned visual-agent plan will add external queries, temporal correlation,
  verification, and guarded actions without embedding vendor-specific integrations in
  the perception loop.

See `openvector-competitive-research.md` for the public product evidence and
open-source adoption decisions behind this direction. See `product-roadmap.md` for
the revised completion phases derived from the closed-loop product target.
