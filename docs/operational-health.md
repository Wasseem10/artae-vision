# Automated operational health incidents

Phase 25 turns existing camera and edge telemetry into an always-on reliability
workflow. The system now detects evidence gaps while they are happening instead of
waiting for an operator to discover that a camera or recorder was unavailable.

## What the watchdog monitors

The existing operations worker evaluates health every ten seconds. The control plane
applies deterministic, deployment-configurable thresholds and opens incidents for:

- a requested camera job that never receives its first worker heartbeat;
- a camera worker whose heartbeat becomes stale;
- a live worker whose video frames stop arriving;
- an explicit camera runtime error;
- a continuous-recording error; and
- an attached edge station that never connects or stops checking in.

Intentionally stopped cameras are excluded. An enrolled edge station is monitored only
after a camera is attached or assigned to it, which avoids false alarms for spare or
not-yet-installed devices.

## Incident lifecycle

Each resource/category has at most one active incident. Repeated watchdog observations
update its latest-detection time, diagnostics, and occurrence count instead of creating
duplicates. An operator can acknowledge the incident, but cannot manually claim that
the underlying failure is fixed. The watchdog resolves it automatically after healthy
telemetry returns and retains the full history.

The dashboard displays active and recently recovered incidents. If the operator has
already enabled browser notifications, newly opened reliability incidents use that
same permission.

## Watchdog liveness

Each successful evaluation writes a single last-success timestamp in the same database
transaction as the incident changes, even when there are no cameras or incidents. The
authenticated dashboard reads `GET /api/v1/operational-health/watchdog` and shows
`never_run`, `fresh`, or `stale` using API server time. A missing record is never run;
the default stale limit is 60 seconds. Set
`VIDEO_INTEL_API_OPERATIONAL_HEALTH_WATCHDOG_STALE_SECONDS` above the operations
worker's `VIDEO_INTEL_ALERT_HEALTH_EVALUATION_SECONDS` plus expected scheduling and
network delay. A recent timestamp proves only that an evaluation call completed; it does not
prove that any camera is covering a room or that someone is responding.

For an independent uptime service, configure a separate
`VIDEO_INTEL_API_OPERATIONAL_HEALTH_MONITOR_KEY` (at least 16 random characters) in
the API secret manager. The service can call `GET /api/v1/health/watchdog` over HTTPS
with `X-Health-Monitor-Key`. The endpoint returns only `200 {"status":"ok"}` for a
recent successful evaluation or `503` for never run/stale; missing or invalid monitor
credentials return `401`. It does not expose camera or tenant details. The monitor
credential must be distinct from the agent and dashboard keys. Place the checker on
infrastructure independent of the camera site and configure it to alert a human on
`503`, `401`, a timeout, or any other non-200 response. This repository does not
configure or operate that external monitor.

## Opt-in prolonged camera outage notifications

An administrator may attach an existing, tenant-owned signed alert webhook channel to
one camera through `POST /api/v1/cameras/{camera_id}/health-alert-routes` with
`channel_id` and `outage_after_seconds` (60–3600, default 120). GET on that path lists
the routes and DELETE on `/{route_id}` removes one. No external outage route exists by
default. The camera and channel must belong to the same organization. Test the
destination and confirm its intended recipient before enabling the route.

The watchdog queues one durable delivery per incident and channel only after a
critical camera-runtime incident remains active beyond the route threshold. Heartbeat
loss, stalled video, a runtime error, and a camera job that never starts share one
runtime incident, so changing symptoms do not create a stream of messages. An
intentionally stopped camera and a brief outage do not send externally. A recovered or
acknowledged incident, or route removal, suppresses outstanding delivery. A webhook
already being sent cannot be retracted: the incident marks it suppressed with an
unknown outcome, and the recipient may still receive that one in-flight message. A
new outage after recovery gets a new incident and may notify again.

The operations worker claims each delivery with a lease, signs the canonical JSON
body with the channel secret, uses `video.monitoring.unavailable` as the event type,
and retries transient failures with the existing bounded backoff. When ordinary fall
alerts and outages are both queued, the worker alternates claim priority so neither
queue can starve the other. The incident API
shows queued, retrying, delivered, failed, or suppressed delivery status. A 2xx
response means the webhook endpoint accepted the request; it does not prove a person
saw the message. A responder acknowledges the incident separately through their
authenticated account; `acknowledged_at` and `acknowledged_by` record that action.
Use named OIDC accounts in a real pilot, because the development dashboard key gives
all users the same `local-dashboard-operator` identity.

This route covers camera-monitoring loss while the control plane and operations worker
are running. It cannot report an outage of that whole stack or a home-wide power or
network failure if the stack runs on the same machine. A supervised pilot needs an
independent uptime check for those failures and must retain its normal human check-in
process.

## Safety and scale boundaries

The watchdog does not open cameras, start analysis, start recording, or call a visual
model. It reads control-plane telemetry only. Its active-key uniqueness constraint
prevents duplicate active incidents even if evaluators overlap, while row locks protect
updates to existing incidents. Prometheus exports the active incident count for hosted
monitoring.

Production deployments should tune grace and stale thresholds for their network and
camera restart behavior, then alert on the watchdog worker itself. Hardware redundancy,
RAID/power monitoring, and remote appliance diagnostics require signals from the
selected physical edge platform and remain deployment work.
