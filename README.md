# AI Video Intelligence Platform

> **Current status:** `/demo` keeps the compact upload-and-prompt workflow: choose
> a sample, upload a permitted video, or use a webcam; describe the visible condition;
> then run the AWS-backed analysis. Amazon Nova 2 Lite reviews sampled frames through
> Bedrock, and confirmed matches invoke a Strands agent to prepare evidence, an
> in-app notification, and human review. The separate browser-monitor foundation
> also supports on-device MediaPipe fall candidates and optional AWS caregiver SMS.
> This is a hackathon prototype, not a validated medical, emergency-response, or
> unattended monitoring product. See [tested scope](docs/browser-demo.md).

This monorepo is growing toward an OpenVector-style platform: click a camera, give
it a job in natural language, review the generated rule, deploy it continuously,
combine what it sees with authorized business-system context, take guarded actions,
and search the resulting evidence. The revised completion phases are in
[`docs/product-roadmap.md`](docs/product-roadmap.md).

## No-install demo

Open `/demo` for the compact, rate-limited, no-account AWS-backed workflow. Choose
the included example, upload a permitted browser-playable clip, or use a webcam;
describe one or more visible conditions and start analysis. Recorded clips can be
sampled across the full video, and the result panel shows Nova's decision and the
Strands actions prepared for a confirmed match.

The incident feed is the primary alert channel. A granted browser notification and
audible cue can surface a possible fall while the page is open. Signed-in caregivers
can optionally provide an E.164 phone number for AWS transactional SMS. SMS is sent
only after a fall event is created; an accepted AWS request is not proof of carrier
delivery. New AWS SMS accounts can send only to verified sandbox destinations until
production access and any required origination registration are approved.

Nova reports match, no match, uncertainty, or an unsupported request. With two or
three confirmations selected, the server requires that many consecutive matches
before creating an alert. The right-hand alert list loads recent account incidents
and stays visible after stopping. Browser notifications are optional and work only
while the page is open. `/app/native` preserves the installed-camera engineering UI.

### Recorded video: conditions and timing

- **Quick:** up to 32 sampled moments in four image batches. All conditions are
  checked, even after an early match. This is not frame-by-frame video analysis.
- **Detailed:** choose 0.5, 1, 2, 5, or 10 seconds between samples. Maximum 192
  base samples and 10 minutes of video; incompatible duration/cadence combinations
  are rejected before opening the AWS session, not silently downsampled.
- Each batch overlaps its neighbor by one frame. Nova returns active/inactive/
  uncertain observations for each condition and timestamp. Up to four transition
  windows are resampled with eight images each. The browser computes estimated
  duration ranges from those timestamps, not model-generated time guesses.
- Public detailed sessions allow up to 32 AWS checks and expire after 30 minutes.
  Detailed scans can take several minutes. Boundary-only rechecks do not create
  extra notifications. The run must remain open; this is not an unattended cloud job.
- Review start/end links and individual sampled observations. An event active at
  the clip boundary, an occluded subject, or conflicting judgments leaves the full
  duration unknown. Duration ranges assume one continuous event and the same subject
  between samples; they are not statistically calibrated confidence intervals.
- This browser path does **not** run the legacy YOLO tracker described below.
  Use a fixed camera and one clearly described subject. Crowded scenes, rapid events,
  identity continuity, car-parking accuracy, and fall-recovery accuracy are not validated.
  Standing up is not proof that someone is medically safe.
- Cumulative timing results remain in the page after Stop but are not a saved,
  cross-device timeline report. Account incident records and guest temporary results
  retain their existing behavior.

## Working AWS browser path

The production browser path uses a restricted Vercel OIDC role, not permanent AWS
keys. The following path has been exercised against the deployed services:

1. A webcam, uploaded video, or licensed sample remains in the browser preview.
2. At the selected interval, one compressed frame and the user's unchanged visual
   condition are sent to Nova 2 Lite. Artae does not use a second model to rewrite it.
3. The API enforces paid-call limits, concurrency, optional consecutive-match
   confirmation, and alert cooldowns before creating an incident.
4. A confirmed incident is sent to the **Strands Incident Coordinator**.
5. The coordinator invokes `preserve_evidence` and `notify_responder`, adding
   `request_human_review` when the supplied facts are ambiguous.
6. Artae saves an in-app alert with the model explanation. Alert history persists
   after stopping and across signed-in devices.

Strands is disabled by default so ordinary development never spends AWS credits.
After configuring an AWS credential supported by the AWS SDK, set:

```dotenv
VIDEO_INTEL_API_STRANDS_ENABLED=true
VIDEO_INTEL_API_STRANDS_MODEL_ID=us.amazon.nova-2-lite-v1:0
VIDEO_INTEL_API_STRANDS_REGION=us-east-1
```

Then run the normal API and browser workspace. A coordinator outage does not suppress
a locally detected candidate: the API records its fallback and creates the in-app
review item. A vision-call failure is shown as an error, never a fabricated
detection or an implicit no-match. Caregiver SMS is off by default. To enable it,
grant the restricted runtime role `sns:Publish`, configure a verified destination
in the AWS SMS sandbox (or obtain production access), and set:

```dotenv
VIDEO_INTEL_API_SMS_ENABLED=true
VIDEO_INTEL_API_SMS_REGION=us-east-1
# Optional and region-dependent
VIDEO_INTEL_API_SMS_SENDER_ID=Artae
```

The destination is encrypted in the account rule using the existing alert-secret
key and never returned to the browser in full. Phone calls and WhatsApp are not
implemented.
See the [submission checklist](docs/hackathon-submission.md),
[architecture](docs/hackathon-architecture.md), and
[third-party disclosure](docs/hackathon-disclosures.md).

The repository now contains the industry-neutral visual-alert foundation plus the
Phase-16 through Phase-25 evaluation, visual-agent, guarded-action, context, visual-skill,
multi-camera operations, offline-edge, production-hardening, and commissioning layers:

- webcam, MP4, or RTSP capture on the host;
- YOLO object detection with persistent ByteTrack IDs;
- continuous local person-pose tracking for fall/collapse jobs, with an
  upright-to-descent-to-ground confirmation state machine;
- normalized polygon zones and directed two-point crossing lines;
- reusable dwell, presence, entry, exit, count-threshold, and line-crossing jobs;
- pre/post-event clips, JSONL output, and optional webhooks;
- a FastAPI control plane with camera, zone, rule, and event APIs;
- PostgreSQL models and Alembic migrations;
- authenticated agent configuration and idempotent event ingestion;
- live event updates over WebSockets;
- a responsive Next.js operator console for cameras, zones, rule review, and events;
- a MediaMTX gateway that translates RTSP publishers/cameras into browser WebRTC;
- live video beneath the normalized polygon editor without exposing RTSP credentials;
- a repeatable MP4-to-RTSP publisher for development without a webcam; and
- dashboard Start/Stop controls backed by durable desired/observed agent state;
- a bounded host supervisor that runs several independently leased cameras concurrently;
- RTSP open/read timeouts, bounded exponential reconnects, frame-independent lease
  heartbeats, and server-controlled restart backoff that prevents crash loops;
- live camera health, last-frame time, processed-frame and reconnect counters in the
  operator console and Prometheus metrics;
- optional background continuous MP4 recording with atomic segment completion,
  per-segment manifests, bounded queues, and age/byte retention enforcement;
- durable edge upload spooling, tenant-scoped historical-video catalogs, signed
  browser playback, administrator legal holds, and explicit retention execution;
- edge-executed ONVIF WS-Discovery jobs with bounded multicast collection,
  deduplication, device-token leases, and operator-visible results;
- encrypted ONVIF credentials, authenticated media-profile resolution, automatic
  RTSP selection, edge pinning, and mandatory real-frame preview verification;
- operator-triggered, model-free camera commissioning with delivery, resolution,
  frame-rate, exposure, focus, freeze, and black-frame readiness guidance;
- always-on operational health incidents for stale camera workers, stalled video,
  recording failures, and offline attached edge stations, with automatic recovery;
- live semantic proposer-verifier quarantine with distinct-model enforcement,
  signed evidence review, and explicit operator confirmation or rejection;
- per-camera/job human field labels, rolling precision/recall/F1 gates, missed-event
  capture, configurable thresholds, automatic drift lock, and permanent manual mode;
- pluggable local or private S3-compatible recording storage with API-gated presigned
  playback, exact-key retention deletion, and legal-hold enforcement;
- live worker heartbeat, FPS, inference latency, and detection telemetry;
- live detection boxes and labels aligned over the WebRTC player; and
- completed evidence upload with size limits, SHA-256 checksums, and durable status;
- background H.264 conversion so recorded clips seek and play in modern browsers;
- a separately deployable evidence worker for asynchronous Artae upload/index/search;
- natural-language evidence search with camera filters and timecoded playback;
- automatic local metadata search while Artae Labs is unavailable or returns 501; and
- a versioned natural-language rule compiler with clarification and human review;
- deterministic local compilation plus an optional OpenAI structured-output provider;
- strict camera-zone resolution so a compiler cannot invent runtime identifiers; and
- multiple heterogeneous camera jobs evaluated from one shared decode, YOLO, and tracking pass;
- independent temporal state and evidence events for every deployed job; and
- a versioned `camera-job/2` contract plus a model/event capability registry;
- a `camera-job/3` semantic-vision contract for open-ended visible conditions;
- automatic full-frame grounding when a semantic job needs no manually drawn geometry;
- managed Gemini window evaluation with confidence, confirmation, cooldown, and cost ceilings;
- a Strands Incident Coordinator on Amazon Bedrock that invokes evidence,
  notification, and human-review tools after a visual event is confirmed;
- reviewed execution plans that route jobs between local YOLO/tracking,
  specialized pose analysis, and bounded VLM windows;
- honest per-job support levels that distinguish deterministic execution, general visual-AI
  fallback, required business context, and conditions that pixels cannot verify;
- state, transition, and sequence semantics, including baseline/rearm protection for visual changes;
- semantic decisions entering the same incidents, evidence, WebSockets, and alert pipeline;
- activation-time rejection when the configured model cannot support a job; and
- durable labeled-video replay baselines with authenticated browser uploads, production
  route snapshots, leased execution heartbeats, visible progress, temporal
  precision/recall/F1/latency scoring, and provider-cost accounting;
- durable batch regression suites with immutable run history and deterministic
  accuracy, false-alarm, pricing, worker-success, and cost promotion gates;
- an eight-scenario cross-industry camera calibration pack that separates synthetic,
  controlled, and field evidence, blocks premature accuracy claims, and recommends the
  next missing recording or tuning action per capability;
  and
- durable per-event incidents with acknowledge and resolve workflows;
- encrypted webhook destinations, per-job routing, cooldowns, and delayed escalation;
- HMAC-signed, idempotent webhook delivery with leases and bounded retries; and
- OIDC bearer-token verification against issuer, audience, expiry, and JWKS keys;
- organization membership roles for owner, admin, operator, and viewer access;
- tenant-scoped cameras, geometries, jobs, events, evidence, searches, and alerts;
- organization-isolated WebSocket fan-out and short-lived signed clip URLs; and
- one-time, hashed edge-device credentials with capacity, rotation, and revocation;
- tenant-scoped append-only audit records for authenticated operator mutations; and
- versioned visual-agent plans with safe simulations, replay promotion gates,
  approval, supersession, and rollback;
- encrypted, scoped integration connectors with fixed low/medium/high action risks;
- manual approval, idempotent leases, rate limits, retries, dead letters, and operator
  retry/deny controls for external actions;
- mock, Telegram, generic-webhook, messaging-webhook, and ticket-webhook adapters, while physical
  door, gate, and machine control remains explicitly disabled; and
- normalized external observations and deterministic time-window correlations, with a
  safe two-people/one-swipe tailgating reference workflow; and
- prompt-selected PPE/OCR/plate/barcode/pose/grounding/segmentation/change skill
  manifests plus persistent, reviewable scene memory and state changes; and
- tenant-owned site maps, camera placement, anonymous cross-camera entity journeys,
  and unified event/scene/sighting investigation search; and
- durable offline event buffering, enrolled-station hardware/health reports, signed
  configuration revisions, and audited update/rollback state; and
- Docker Compose for MediaMTX, the web app, API, alert worker, and PostgreSQL.

Artae Labs remains behind a separate asynchronous package and optional worker;
camera inference and clip playback never depend on it being reachable. Hosted database
cutover, Redis cross-instance fan-out, external evidence storage, and specialized model
packs such as PPE/OCR are deliberately future milestones.

## Accounts and saved workspaces

The web app supports Supabase email/password authentication. A first-time verified
identity is automatically assigned an isolated organization in the control-plane
database; cameras, agents, events, evidence, connectors, and alerts are then loaded
from that organization on every login. The native Windows launcher uses hybrid auth:
its private bootstrap calls use the development dashboard key, while browser users
use signed Supabase access tokens. Production must use OIDC-only mode and must not
expose the development dashboard key.

Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` in
`apps/web/.env.local`. Configure the API issuer as
`https://<project-ref>.supabase.co/auth/v1`, the audience as `authenticated`, and the
JWKS URL as `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`. Only a
publishable key belongs in the browser; never put a secret or service-role key in a
`NEXT_PUBLIC_` variable.

## Repository layout

```text
.
|-- apps/web/                    # Next.js operator application
|-- services/api/                # FastAPI/PostgreSQL control plane
|-- services/alerts/             # Durable alert and guarded-action worker
|-- services/evidence/           # Background Artae indexing/search worker
|-- services/inference/          # Host camera, YOLO, tracking, rules, and clips
|-- packages/artae-labs-client/  # Internal Labs ingestion/search adapter
|-- infra/                       # Local Docker Compose infrastructure
|-- docs/                        # Architecture, decisions, research, file guide
`-- tests/                       # API, inference, and Artae tests
```

Applications and services can later scale independently. Shared code moves into
`packages` only after two real consumers need it.

## Prerequisites

- Python 3.11 or 3.12
- Node.js 20.9 or newer and pnpm 11 for host frontend development
- Docker Desktop for the complete local stack
- A webcam, IP camera, or MP4 test file
- FFmpeg only when publishing a local MP4 into the live dashboard

An NVIDIA GPU is optional. CPU inference works with the nano model, at a lower
frame rate. A physical webcam is also optional during development: an MP4 exercises
the same tracking, zone, timing, event, and evidence paths.

## 1. Install the Python workspace

Run these commands from the repository root.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".\services\inference[dev]" -e ".\services\api[dev]" -e ".\services\alerts[dev]" -e ".\packages\artae-labs-client[dev]" -e ".\services\evidence[dev]"
Copy-Item .env.example .env
```

### macOS or Linux

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "./services/inference[dev]" -e "./services/api[dev]" -e "./services/alerts[dev]" -e "./packages/artae-labs-client[dev]" -e "./services/evidence[dev]"
cp .env.example .env
```

Use long random values for the two API keys and generate a Fernet alert-encryption
key in the private `.env`. Keep that encryption key stable across API restarts. The
checked-in template contains placeholders, never working secrets.

## 2. Run the no-Docker camera playground

For the simplest Gemini webcam demo on Windows, double-click:

```text
Start-AI-Camera.cmd
```

The launcher asks for a natural-language alert rule and opens one webcam preview.
Rolling contact sheets are evaluated in the background, so camera capture does not
pause while Gemini responds. The latest AI decision remains visible, a triggered
rule sounds a local alert, and its image sheet plus structured decision JSON are
saved under `artifacts/observer`.

Close the playground with the preview window's X button, `q`, or Escape. This path
does not require Docker, PostgreSQL, Redis, or the web dashboard. Request ceilings
from `.env` still apply to protect against unexpected provider spending.

To run the real dashboard without Docker, double-click:

```text
Start-Native-Dashboard.cmd
```

This starts the Next.js console, FastAPI, the managed inference worker, and a durable
SQLite control-plane database, then opens [http://127.0.0.1:3000](http://127.0.0.1:3000).
Use `Stop-Native-Dashboard.cmd` when finished. Camera registration, natural-language
job review, activation, telemetry, events, alerts, evidence, and audit records work
in native mode. The worker sends a bounded, authenticated JPEG preview to the
dashboard, so the selected local webcam is visible in the browser without Docker.
The complete Docker stack replaces SQLite with PostgreSQL and upgrades live video
transport to the MediaMTX RTSP-to-WebRTC gateway.

The dashboard's **Give this camera a job** launchpad is the fastest MVP workflow:

1. Select the camera.
2. Describe a visible event under **Jobs**, review the compiled interpretation, and
   choose **Accept and activate job**.
3. Choose **Start analysis**. Semantic jobs display each live VLM decision, its
   confidence, and the enforced per-minute and worker-session request ceilings.
4. Choose **Enable browser alerts** once if desktop notifications are wanted.
5. Use **Send safe test alert** to verify the incident interface without calling a
   vision provider, delivering a webhook, or fabricating an evidence clip.
6. Choose **Stop analysis** when the camera should not consume additional inference.

The native Windows start and stop scripts fail closed: they persist every camera's
desired state as stopped. Restarting the local stack therefore cannot resume paid
visual requests; each session must be started explicitly from the dashboard. A
durable organization-wide budget ledger is still required before production use.

Real confirmed incidents enter the alert inbox and event timeline over WebSockets.
When capture generated evidence, the timeline's **Play clip** action opens the
browser-compatible H.264 recording.

The job review also displays the exact model route before deployment. Simple known-object
geometry jobs remain local and use no VLM requests. Attributes, equipment states, relationships,
and unusual actions use chronological VLM windows. See [Model routing](docs/model-routing.md) for
the supported boundary and accuracy caveats.

## 3. Start the complete local platform

On Windows, normal local use is one click after Docker Desktop is installed and
the Python workspace has been installed:

```text
Start-Video-Intelligence.cmd
```

The launcher starts the local services and managed camera worker, waits for the API,
and opens the dashboard. When finished, double-click:

```text
Stop-Video-Intelligence.cmd
```

The stop launcher closes the worker and containers while preserving PostgreSQL data
and saved evidence. The commands below are the manual developer equivalent.

```powershell
docker compose -f infra/docker-compose.yml up --build
```

The API container waits for PostgreSQL, runs the Alembic migration, and listens on
`http://127.0.0.1:8000`. The operator console is available at
[http://127.0.0.1:3000](http://127.0.0.1:3000). Open the interactive API at
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). MediaMTX accepts local
RTSP publishers on port `8554`, serves WebRTC/WHEP on `8889`, and keeps its Control
API bound to host loopback on `9997`.

The Compose defaults are for private local development only. Values from your root
`.env` override the development agent and dashboard keys.

Without Docker, start a PostgreSQL server yourself, set
`VIDEO_INTEL_API_DATABASE_URL`, then run:

```powershell
alembic -c services/api/alembic.ini upgrade head
video-intelligence-api
```

In another terminal, start the web application:

```powershell
Set-Location apps/web
Copy-Item .env.local.example .env.local
pnpm install
pnpm dev
```

## 4. Create the first managed agent

Use the operator console at port 3000:

1. Add a camera with source `webcam:0`, an MP4 path, or an RTSP URL.
2. Click **Give camera a job**. Semantic jobs use an automatic full-camera region;
   deterministic spatial jobs can still use a saved polygon zone or crossing line.
3. Enter “Alert me when a person is not wearing a hard hat” or “Alert me if a
   person remains in the loading zone for more than 30 seconds.”
4. Answer a clarification if a deterministic object, zone, or duration is ambiguous.
5. Review whether the platform selected deterministic tracking or semantic vision.
6. Click **Accept and create draft**, then separately click **Activate**.

Selecting a camera asks FastAPI to provision a stable MediaMTX path. For an RTSP
camera, MediaMTX pulls the private source on demand and the browser receives only a
credential-free WHEP URL. A webcam or file camera gets a publisher path instead.

Normalized coordinates range from 0 to 1, so polygons and lines are
resolution-independent. Zone jobs use the bottom-center of the detection box as
the object's ground point. Line jobs compare consecutive tracked ground points
and require their motion segment to intersect the saved line segment.

## 5. Test live video without a webcam

Register `artifacts/person-smoke.mp4` as a file camera in the dashboard, then find
its generated ID and publish the sample in a second terminal:

```powershell
$camera = Invoke-RestMethod http://127.0.0.1:8000/api/v1/cameras |
  Where-Object name -eq "Your camera name"
video-intelligence-publish-file artifacts/person-smoke.mp4 --camera-id $camera.id
```

The command asks FastAPI for the correct RTSP publisher URL, starts FFmpeg without
a shell, converts the source to browser-compatible H.264, and loops it until you
press `Ctrl+C`. Install FFmpeg and ensure `ffmpeg` is on `PATH`, or pass
`--ffmpeg C:\path\to\ffmpeg.exe`. This provides a repeatable development camera;
you do not need to buy hardware yet.

The live player deliberately fills the polygon canvas. Although unusual aspect
ratios can look stretched, a normalized click remains aligned with the exact source
frame used by inference. A later player can preserve aspect ratio by explicitly
compensating for letterboxing rather than silently shifting zone coordinates.

## 6. Run the managed inference worker

In the dashboard, open **Edge devices**, enroll this host, and save the token that
is displayed once. Put it in `.env` with a conservative local capacity:

```dotenv
VIDEO_INTEL_CONTROL_PLANE_URL=http://127.0.0.1:8000
VIDEO_INTEL_CONTROL_PLANE_DEVICE_TOKEN=vid1.device-uuid.random-secret
VIDEO_INTEL_WORKER_ID=my-development-worker
VIDEO_INTEL_WORKER_MAX_CAMERAS=2
```

Then run:

```powershell
video-intelligence-worker
```

Leave this process running. It stays idle until you select a camera with at least
one active job and click **Start agent** in the dashboard. The worker claims every
active job for that camera, reads the stable MediaMTX RTSP path once, and runs one
YOLO/ByteTrack pass per frame. Each job evaluates the shared tracked detections
with independent temporal state. The dashboard shows status, worker ID, FPS,
inference latency, and boxes over the browser video. Click **Stop agent** for a
graceful stop. If a worker dies, its lease expires and another worker can claim the
still-requested camera.

The active-job list is a safe deployment snapshot. Stop the camera agent before
activating or pausing jobs, then start it again to claim the new set. The API
rejects deployment changes while that camera is requested to run instead of showing
configuration that the worker has not loaded.

The supervisor fills up to `VIDEO_INTEL_WORKER_MAX_CAMERAS` slots. FastAPI also
enforces the administrator-configured device capacity, so changing a local setting
cannot exceed the server-side limit. Each slot owns its own capture, model, tracker,
temporal state, telemetry reporter, and renewable database lease. Start at one and
increase only after measuring GPU memory and latency.

When tracked objects satisfy any deployed job, the agent writes JSONL
plus an independent evidence MP4, then posts the event to the API from a background
thread. Several jobs can fire from the same tracked frame without repeating
inference. The API stores each event once even if its UUID is retried and broadcasts
`event.created` to WebSocket subscribers. Frame telemetry is transient:
only the latest boxes travel over the WebSocket, so PostgreSQL is not flooded with
one row per video frame.

When the evidence recorder finishes its post-event frames, a separate background
uploader converts the OpenCV clip to a fast-start H.264 MP4 and streams it to
FastAPI. The bounded upload is checksummed and stored outside PostgreSQL before it
becomes claimable for indexing. Event timing never waits for upload or Artae.

## 7. Configure durable alerts and guarded actions

Open **Alerting** in the operator console. First add an HTTPS webhook destination
and a signing secret, then connect that destination to any job. A route can apply a
cooldown to suppress repeated notifications and a delay for escalation. A delayed
delivery is automatically suppressed when the incident is acknowledged or resolved
before its due time.

The API creates the incident and its delivery records in the same database
transaction as the event. The separate alert worker sends them:

```powershell
video-intelligence-alert-worker
```

Compose starts this worker automatically. Receivers should persist the
`Idempotency-Key` header and verify `X-Artae-Signature`, which is
`v1=` plus HMAC-SHA256 of `X-Artae-Timestamp + "." + exact_request_body`. Successful
2xx responses complete delivery; timeouts, 408, 425, 429, and 5xx responses retry
with bounded exponential backoff; other 4xx responses fail permanently.

The signing secret is encrypted in PostgreSQL and never returned to the dashboard.
The guided **Choose what happens next** section also supports rule-owned mock,
Telegram, generic-webhook, messaging-webhook, and ticket-webhook connectors. Notifications are
low risk and may run automatically; ticket and generic webhook actions default to
manual approval. Physical-system actions remain unavailable. See
[`docs/guarded-actions.md`](docs/guarded-actions.md) for the execution and safety
boundaries.

Telegram is the simplest phone-alert path. Create a bot with `@BotFather`, message the
bot once, then enter its token and the destination chat ID in **Choose what happens
next**. The bot token is encrypted and is never returned to the browser after setup.
Use **Send Telegram test** to exercise the real outbound queue before starting analysis.

## 8. Search recorded evidence

The **Search recorded evidence** panel accepts descriptions such as “a person
waiting in the loading zone.” Before Artae clips are ready, the API returns useful
local matches across camera, object, zone, and event metadata. These results are
clearly labeled **Local metadata** and are not presented as embedding similarity.

To enable Gemini-powered Artae indexing, add the internal key and an existing Labs
index ID to `.env`:

```dotenv
ARTAE_LABS_API_KEY=your-internal-key
ARTAE_LABS_INDEX_ID=your-index-id
VIDEO_INTEL_EVIDENCE_AGENT_KEY=your-agent-key
```

Then start the optional worker:

```powershell
video-intelligence-evidence-worker
```

With Docker, use:

```powershell
docker compose -f infra/docker-compose.yml --profile artae up --build
```

The profile is deliberately opt-in, so a missing key or the currently expected
HTTP 501 does not put the normal stack into a restart loop. A 501 marks that
provider attempt unavailable; search falls back to local metadata and the operator
can retry indexing later.

For a quick local WebSocket client, use a browser console:

```javascript
const ws = new WebSocket("ws://127.0.0.1:8000/api/v1/ws/events?token=your-dashboard-key");
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

Static API and dashboard keys are a milestone-3 development boundary, not public
authentication. Do not expose this service to the internet yet.

## 9. Configure natural-language rule compilation

The default `auto` mode uses the deterministic compiler when no OpenAI key is
configured. This local path recognizes the current object-dwell pattern, named
camera zones, seconds/minutes/hours, and an optional confidence percentage. It is
repeatable, free, and is covered by a checked-in eval dataset.

To enable the optional LLM provider, set:

```dotenv
VIDEO_INTEL_API_RULE_COMPILER_PROVIDER=auto
VIDEO_INTEL_API_OPENAI_API_KEY=your-private-server-side-key
VIDEO_INTEL_API_OPENAI_RULE_COMPILER_MODEL=gpt-5-mini
```

The key remains inside FastAPI and is never sent to the browser. The provider must
produce a Pydantic-validated candidate; FastAPI then resolves the exact zone ID and
validates the versioned rule IR itself. If OpenAI is unavailable in `auto` mode,
the API records a warning and falls back to the deterministic compiler. Set the
provider to `deterministic` to guarantee no external call, or to `openai` to fail
clearly instead of falling back.

Every initial interpretation and clarification is stored as an immutable revision.
Accepting a reviewed revision creates a draft rule only. This means an LLM response
can never activate camera behavior directly.

## 10. Configure identity and organizations

Local development remains simple: `VIDEO_INTEL_API_DASHBOARD_AUTH_MODE=development`
maps the private dashboard key to the seeded Local Development organization. This
mode is rejected when `VIDEO_INTEL_API_ENVIRONMENT=production`.

For a real deployment, configure the API as an OIDC resource server:

```dotenv
VIDEO_INTEL_API_ENVIRONMENT=production
VIDEO_INTEL_API_DASHBOARD_AUTH_MODE=oidc
VIDEO_INTEL_API_OIDC_ISSUER=https://identity.example.com/
VIDEO_INTEL_API_OIDC_AUDIENCE=video-intelligence-api
VIDEO_INTEL_API_OIDC_JWKS_URL=https://identity.example.com/.well-known/jwks.json
VIDEO_INTEL_API_MEDIA_SIGNING_KEY=a-separate-random-secret-of-at-least-32-characters
```

The API accepts only explicitly configured asymmetric JWT algorithms and verifies
signature, issuer, audience, expiry, issued-at time, subject, organization claim,
enabled organization, and database membership. It returns 404 rather than revealing
whether another organization owns a requested resource. The database membership
role—not a later token claim—controls authorization once a membership exists.

Provision an organization and its first member after applying migrations:

```powershell
video-intelligence-admin create-organization `
  --id 11111111-1111-1111-1111-111111111111 `
  --slug example-company --name "Example Company"

video-intelligence-admin grant-membership `
  --organization-id 11111111-1111-1111-1111-111111111111 `
  --issuer https://identity.example.com/ `
  --subject oidc-provider-user-id `
  --role owner --email owner@example.com
```

Put the same organization UUID in the configured OIDC organization claim. Automatic
membership provisioning is off by default. The web client has a session-token seam,
but the hosted Authorization Code + PKCE or backend-for-frontend login flow still
depends on the identity provider selected for deployment; do not place permanent
access tokens in checked-in frontend environment files. See `docs/security.md`.

## Standalone detector and local-rule modes

The original detection-only window still works:

```powershell
video-intelligence-inference
```

The same window can run the first universal semantic-observer mode without an API
key. Start with the predictable local provider in `.env`:

```dotenv
VIDEO_INTEL_OBSERVER_ENABLED=true
VIDEO_INTEL_OBSERVER_PROVIDER=dry_run
VIDEO_INTEL_OBSERVER_RULE=Alert when a person falls down.
VIDEO_INTEL_OBSERVER_SAMPLE_FPS=1
VIDEO_INTEL_OBSERVER_WINDOW_FRAMES=10
VIDEO_INTEL_OBSERVER_OVERLAP_FRAMES=5
VIDEO_INTEL_OBSERVER_DRY_RUN_TRIGGER_EVERY=3
```

Then run `video-intelligence-inference`. The camera is still decoded only once.
The observer samples ten chronological frames into a numbered contact sheet, keeps
the configured overlap for continuity, and analyzes complete windows on a
background thread. A second window shows exactly what a future cloud model will
receive. The latest observer state appears on the main preview, and simulated
triggered sheets plus decision JSON are written to `artifacts/observer`.

The dry-run provider deliberately does not understand the images; it proves the
camera, sampling, queue, budget, display, and artifact paths without spending
money. For the live prototype, change the provider to `gemini`, add the private
key, and keep the conservative request limits shown below. The default model is
`gemini-3.5-flash-lite`; Qwen remains an optional provider. Keys belong only in
the ignored `.env`, never in source control.

```dotenv
VIDEO_INTEL_OBSERVER_ENABLED=true
VIDEO_INTEL_OBSERVER_PROVIDER=gemini
VIDEO_INTEL_GEMINI_MODEL=gemini-3.5-flash-lite
VIDEO_INTEL_OBSERVER_MAX_REQUESTS_PER_MINUTE=1
VIDEO_INTEL_OBSERVER_MAX_REQUESTS_PER_DAY=20
VIDEO_INTEL_REPLAY_MAX_REQUESTS_PER_MINUTE=20
VIDEO_INTEL_REPLAY_MAX_REQUESTS_PER_DAY=20
```

Each VLM call receives one numbered 10-frame sheet, returns schema-validated JSON,
and runs outside the camera/YOLO loop. The daily setting is an application request
ceiling, not a provider-side dollar cap; configure billing alerts in Google Cloud
as a separate safeguard.

The dwell agent can also run entirely from local `VIDEO_INTEL_*` settings when the
control-plane URL and camera reference are absent:

```powershell
video-intelligence-agent --source "C:\path\camera-sample.mp4"
```

On first use, Ultralytics downloads the configured YOLO weights.

## Artae Labs clip search

Artae is kept out of the frame loop because indexing and Gemini queries are
asynchronous. Record a short finite clip:

```powershell
video-intelligence-record --seconds 15 --output artifacts/webcam-smoke.mp4
```

Put the actual internal key and gateway URL supplied by the Artae owner in `.env`,
then run:

```powershell
video-intelligence-artae-smoke artifacts/webcam-smoke.mp4 --query "a person near a doorway"
```

Without a real key, the command fails locally before making a request. HTTP 501
from the public Labs route is expected while that internal capability is not
enabled on the gateway.

## Important configuration

| Variable | Default | Purpose |
|---|---:|---|
| `VIDEO_INTEL_AGENT_SOURCE` | `webcam:0` | Local webcam, MP4 path, or RTSP source |
| `VIDEO_INTEL_CAMERA_OPEN_TIMEOUT_SECONDS` | `10` | Maximum supported RTSP connection-open wait |
| `VIDEO_INTEL_CAMERA_READ_TIMEOUT_SECONDS` | `10` | Maximum supported RTSP frame-read wait |
| `VIDEO_INTEL_CAMERA_RECONNECT_ATTEMPTS` | `5` | Bounded reconnect attempts before the worker reports failure |
| `VIDEO_INTEL_CAMERA_RECONNECT_BACKOFF_SECONDS` | `0.5` | Initial exponential reconnect delay |
| `VIDEO_INTEL_CONTINUOUS_RECORDING_ENABLED` | `false` | Opt into rotating local edge recordings after approving retention |
| `VIDEO_INTEL_CONTINUOUS_RECORDING_ARCHIVE_ENABLED` | `false` | Spool and upload completed segments for centralized signed playback |
| `VIDEO_INTEL_CONTINUOUS_RECORDING_DIRECTORY` | `artifacts/recordings` | Edge-owned continuous segment root |
| `VIDEO_INTEL_CONTINUOUS_RECORDING_SPOOL_DIRECTORY` | `artifacts/recording-upload-spool` | Restart-recoverable archive upload spool |
| `VIDEO_INTEL_CONTINUOUS_RECORDING_SEGMENT_SECONDS` | `60` | Duration of each atomically finalized MP4 segment |
| `VIDEO_INTEL_CONTINUOUS_RECORDING_RETENTION_HOURS` | `2` | Rolling local history retained per camera |
| `VIDEO_INTEL_CONTINUOUS_RECORDING_MAX_BYTES` | `10737418240` | Per-worker local recording byte ceiling |
| `VIDEO_INTEL_CONTINUOUS_RECORDING_QUEUE_SIZE` | `120` | Bounded recording queue before dropped frames are counted |
| `VIDEO_INTEL_MODEL_NAME` | `yolo26n.pt` | Ultralytics weights or a local model path |
| `VIDEO_INTEL_CONFIDENCE_THRESHOLD` | `0.25` | Local minimum detection confidence |
| `VIDEO_INTEL_OBSERVER_ENABLED` | `false` | Enable overlapping semantic visual-window analysis |
| `VIDEO_INTEL_OBSERVER_PROVIDER` | `dry_run` | No-key simulation or real `qwen` analysis |
| `VIDEO_INTEL_OBSERVER_RULE` | generic description | Natural-language condition evaluated for every completed sheet |
| `VIDEO_INTEL_OBSERVER_SAMPLE_FPS` | `1` | Frames sampled per second for semantic observation |
| `VIDEO_INTEL_OBSERVER_WINDOW_FRAMES` | `10` | Chronological frames included in one sheet |
| `VIDEO_INTEL_OBSERVER_OVERLAP_FRAMES` | `5` | Frames retained between consecutive sheets |
| `VIDEO_INTEL_OBSERVER_MAX_REQUESTS_PER_MINUTE` | `1` | Hard short-term provider-call ceiling |
| `VIDEO_INTEL_OBSERVER_MAX_REQUESTS_PER_DAY` | `20` | Per-observer process daily provider-call ceiling |
| `VIDEO_INTEL_REPLAY_MAX_REQUESTS_PER_MINUTE` | `20` | Shared replay-worker short-term provider-call ceiling |
| `VIDEO_INTEL_REPLAY_MAX_REQUESTS_PER_DAY` | `20` | Shared replay-worker process daily provider-call ceiling |
| `VIDEO_INTEL_OBSERVER_ARTIFACT_MODE` | `triggered` | Persist no sheets, triggered sheets, or all sheets |
| `VIDEO_INTEL_QWEN_MODEL` | `qwen3.7-flash` | Cost-efficient Alibaba vision model used by the observer |
| `VIDEO_INTEL_QWEN_API_KEY` | none | Private key required only for the `qwen` provider |
| `VIDEO_INTEL_ZONE_POINTS` | centered rectangle | Local-rule polygon as `x,y;x,y;...` |
| `VIDEO_INTEL_DWELL_SECONDS` | `10` | Local-rule continuous dwell threshold |
| `VIDEO_INTEL_EVENTS_DIRECTORY` | `artifacts/events` | JSONL and local evidence clips |
| `VIDEO_INTEL_OFFLINE_OUTBOX_PATH` | `artifacts/offline/event-outbox.db` | Durable unsent control-plane event queue |
| `VIDEO_INTEL_CONTROL_PLANE_URL` | none | FastAPI base URL; also enables event delivery |
| `VIDEO_INTEL_CONTROL_PLANE_DEVICE_TOKEN` | none | One-time enrolled credential for a production edge host |
| `VIDEO_INTEL_CONTROL_PLANE_AGENT_KEY` | none | Shared fallback accepted only by edge development mode |
| `VIDEO_INTEL_CONTROL_PLANE_CAMERA_REF` | none | Camera UUID or name whose config should be fetched |
| `VIDEO_INTEL_CONTROL_PLANE_RULE_REF` | none | Optional standalone-debug filter; managed workers run every active job |
| `VIDEO_INTEL_API_DETECTOR_MODEL` | `yolo26n.pt` | Model name published by the capability registry |
| `VIDEO_INTEL_API_OBJECT_CLASSES` | COCO classes | JSON list of classes the configured detector can actually identify |
| `VIDEO_INTEL_API_EVENT_TYPES` | six core engines | JSON list of deployable generic event types |
| `VIDEO_INTEL_WORKER_ID` | generated host/process ID | Stable name shown for a managed worker |
| `VIDEO_INTEL_WORKER_POLL_SECONDS` | `2` | Delay between assignment claims while idle |
| `VIDEO_INTEL_WORKER_TELEMETRY_SECONDS` | `0.5` | Minimum interval between live frame updates |
| `VIDEO_INTEL_WORKER_HEARTBEAT_SECONDS` | `2` | Frame-independent camera lease heartbeat interval |
| `VIDEO_INTEL_WORKER_MAX_CAMERAS` | `1` | Local concurrent camera-process capacity |
| `VIDEO_INTEL_CAMERA_DISCOVERY_MAX_DEVICES` | `100` | Maximum ONVIF devices accepted from one bounded scan |
| `VIDEO_INTEL_API_DATABASE_URL` | local PostgreSQL | Async SQLAlchemy database URL |
| `VIDEO_INTEL_API_AGENT_KEY` | required | Minimum-16-character internal agent secret |
| `VIDEO_INTEL_API_EDGE_AUTH_MODE` | `development` | Shared local key or production per-device authentication |
| `VIDEO_INTEL_API_DASHBOARD_KEY` | required | Minimum-16-character development WebSocket secret |
| `VIDEO_INTEL_API_DASHBOARD_AUTH_MODE` | `development` | Local key mode or production `oidc` bearer validation |
| `VIDEO_INTEL_API_OIDC_ISSUER` | none | Exact trusted token issuer in OIDC mode |
| `VIDEO_INTEL_API_OIDC_AUDIENCE` | none | Required API audience claim |
| `VIDEO_INTEL_API_OIDC_JWKS_URL` | none | Trusted asymmetric signing-key set |
| `VIDEO_INTEL_API_OIDC_ORGANIZATION_CLAIM` | `org_id` | Claim containing the provisioned organization UUID |
| `VIDEO_INTEL_API_OIDC_ROLE_CLAIM` | `role` | Initial membership role claim when auto-provisioning is enabled |
| `VIDEO_INTEL_API_ALERT_ENCRYPTION_KEY` | required for channels | Stable Fernet key used to encrypt webhook secrets at rest |
| `VIDEO_INTEL_API_MEDIA_SIGNING_KEY` | required in production | Separate secret for tenant-bound expiring clip URLs |
| `VIDEO_INTEL_API_MEDIA_URL_TTL_SECONDS` | `300` | Clip URL lifetime in seconds |
| `VIDEO_INTEL_API_REDIS_URL` | none | Hosted TLS Redis URL; a readiness blocker until selected |
| `VIDEO_INTEL_API_OBJECT_STORAGE_ENDPOINT` | none | Private hosted evidence-storage endpoint |
| `VIDEO_INTEL_API_OBJECT_STORAGE_BUCKET` | none | Private evidence bucket name |
| `VIDEO_INTEL_API_BACKUP_TARGET` | none | Approved encrypted control-plane backup destination |
| `VIDEO_INTEL_API_RETENTION_POLICY_CONFIGURED` | `false` | Whether an approved retention policy has been configured |
| `VIDEO_INTEL_API_ALERT_LEASE_SECONDS` | `60` | Exclusive delivery-worker ownership window |
| `VIDEO_INTEL_API_ALERT_RETRY_BASE_SECONDS` | `5` | First webhook retry delay before exponential backoff |
| `VIDEO_INTEL_API_ALERT_RETRY_MAX_SECONDS` | `900` | Maximum delay between webhook attempts |
| `VIDEO_INTEL_API_CORS_ORIGINS` | local web origins | JSON allowlist for trusted browser origins |
| `VIDEO_INTEL_API_MEDIA_GATEWAY_API_URL` | `http://127.0.0.1:9997` | Private MediaMTX Control API used only by FastAPI |
| `VIDEO_INTEL_API_MEDIA_GATEWAY_WEBRTC_URL` | `http://127.0.0.1:8889` | Browser WebRTC/WHEP playback origin |
| `VIDEO_INTEL_API_MEDIA_GATEWAY_RTSP_URL` | `rtsp://127.0.0.1:8554` | Publisher origin returned for webcam/file paths |
| `VIDEO_INTEL_API_AGENT_LEASE_SECONDS` | `10` | Assignment ownership window renewed by worker heartbeats |
| `VIDEO_INTEL_API_AGENT_RESTART_BACKOFF_BASE_SECONDS` | `5` | First retry delay after a failed camera runtime |
| `VIDEO_INTEL_API_AGENT_RESTART_BACKOFF_MAX_SECONDS` | `300` | Maximum camera restart delay after repeated failures |
| `VIDEO_INTEL_API_CAMERA_DISCOVERY_LEASE_SECONDS` | `30` | Exclusive ownership window for one edge discovery scan |
| `VIDEO_INTEL_API_CAMERA_COMMISSIONING_LEASE_SECONDS` | `90` | Reclaimable edge lease for one camera health check |
| `VIDEO_INTEL_API_OPERATIONAL_HEALTH_CAMERA_STALE_SECONDS` | `20` | Camera heartbeat age that opens a reliability incident |
| `VIDEO_INTEL_API_OPERATIONAL_HEALTH_FRAME_STALE_SECONDS` | `15` | Live-frame age that opens a stalled-video incident |
| `VIDEO_INTEL_API_OPERATIONAL_HEALTH_EDGE_STALE_SECONDS` | `30` | Attached edge-station check-in age that opens an incident |
| `VIDEO_INTEL_API_RECORDING_ARCHIVE_DIRECTORY` | `artifacts/recording-archive` | Control-plane historical-video archive root |
| `VIDEO_INTEL_API_RECORDING_UPLOAD_MAX_BYTES` | `1073741824` | Maximum accepted archived segment size |
| `VIDEO_INTEL_API_RECORDING_RETENTION_HOURS` | `2` | Rolling playable cloud history retained per camera |
| `VIDEO_INTEL_API_EVIDENCE_DIRECTORY` | `artifacts/evidence` | API-owned durable clip directory |
| `VIDEO_INTEL_API_EVIDENCE_MAX_BYTES` | `536870912` | Maximum accepted evidence upload size |
| `VIDEO_INTEL_API_EVIDENCE_LEASE_SECONDS` | `1800` | Long lease for provider indexing jobs |
| `VIDEO_INTEL_API_RULE_COMPILER_PROVIDER` | `auto` | `auto`, local `deterministic`, or required `openai` compilation |
| `VIDEO_INTEL_API_OPENAI_API_KEY` | none | Optional server-side key used only by the rule compiler |
| `VIDEO_INTEL_API_OPENAI_RULE_COMPILER_MODEL` | `gpt-5-mini` | Structured-output model used for rule candidates |
| `VIDEO_INTEL_EVIDENCE_CONTROL_PLANE_URL` | local API | Evidence worker's FastAPI address |
| `VIDEO_INTEL_EVIDENCE_AGENT_KEY` | required for worker | Internal key shared with FastAPI |
| `VIDEO_INTEL_ALERT_CONTROL_PLANE_URL` | local API | Alert worker's FastAPI address |
| `VIDEO_INTEL_ALERT_AGENT_KEY` | required for worker | Internal key shared with FastAPI |
| `VIDEO_INTEL_ALERT_HEALTH_EVALUATION_SECONDS` | `10` | Reliability-watchdog evaluation interval |
| `VIDEO_INTEL_ALERT_EVIDENCE_SAMPLING_SECONDS` | `30` | Active-evidence queue reconciliation interval |
| `ARTAE_LABS_INDEX_ID` | none | Existing Labs index used by the evidence worker |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | API address compiled into the web application |
| `NEXT_PUBLIC_DASHBOARD_KEY` | none | Development WebSocket token visible to the browser |

Backend and agent values are documented in `.env.example`; browser build values
are documented in `apps/web/.env.local.example`.

## Tests and verification

Tests mock cameras, YOLO responses, HTTP services, and evidence writers; they do not
require hardware or download weights.

```powershell
python -m pytest -q
ruff check .
ruff format --check .
python -m compileall -q services packages tests
Set-Location apps/web
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

## Troubleshooting

- **No webcam exists:** use an MP4 now; buy a webcam only when you want to test real
  capture, lighting, camera permissions, and continuous operation.
- **Camera cannot open:** close Zoom/Teams, grant camera permission, and try
  `webcam:1` if another device owns index 0.
- **RTSP fails:** verify the URL in VLC, check network reachability, and URL-encode
  special characters in credentials. Regular API responses redact credentials.
- **Live panel says waiting:** for a file/webcam camera, start a publisher; for an
  RTSP camera, check MediaMTX logs and then click **Retry stream**.
- **Agent stays waiting:** start `video-intelligence-worker`, confirm its enrolled
  device token is current, check both device and host capacity, and make sure the
  camera has at least one active job.
- **Clip says finishing:** event metadata arrives before post-event recording ends;
  wait for the background H.264 upload and refresh the evidence state.
- **Search says Local metadata:** no Artae-indexed clip is ready, the optional worker
  is stopped, or Labs is unavailable. Playback and deterministic metadata matching
  still work.
- **Artae returns 501:** this is expected for the internal-only route right now. The
  evidence record preserves the error and can be retried when access is enabled.
- **WebRTC works locally but not remotely:** WebRTC needs reachable ICE candidates;
  production deployments generally require public host configuration and possibly
  STUN/TURN. The checked-in settings are intentionally local-only.
- **Publisher says FFmpeg is missing:** install FFmpeg or provide its executable
  with `--ffmpeg`. The Python package does not silently download system binaries.
- **No active job:** activate at least one reviewed job in the dashboard. Multiple
  all six core job types are supported and share the same inference pass.
- **No event:** verify that the box's bottom-center enters the polygon and that the
  source lasts longer than the dwell threshold.
- **Docker command missing:** install Docker Desktop, or run PostgreSQL and the API
  directly using the commands above.

Read [the architecture](docs/architecture.md), [the competitive/open-source
study](docs/openvector-competitive-research.md), and [the file guide](docs/file-guide.md)
for the rationale and a plain-language explanation of the repository.

## License note

The inference service uses Ultralytics; review its current licensing terms before
commercial distribution. Open-source candidates also require preserving their
licenses and notices. The research document records candidates, not automatic
approval to copy every component into the product.
