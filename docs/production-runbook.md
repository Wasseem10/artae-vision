# Production operations runbook

This runbook separates a working local beta from a hosted production deployment.
The API endpoint `GET /api/v1/production/readiness` is the source of truth for the
remaining launch prerequisites. It reports configuration state but never returns
keys, database credentials, or provider secrets.

## Before launch

1. Select an OIDC identity provider and provision organization memberships.
2. Use PostgreSQL with encryption, point-in-time recovery, and tested restores.
3. Select TLS Redis for cross-instance event fan-out and coordination.
4. Select private S3-compatible storage for recordings/evidence, lifecycle rules, and legal holds.
5. Approve explicit retention periods for raw video, clips, events, scene memory,
   identity attributes, and audit records.
6. Store all keys in the hosting provider's secret manager. Never put them in the
   browser bundle, repository, screenshots, tickets, or chat.
7. Enroll every edge station separately and revoke the shared development key mode.
8. Restrict CORS, database, Redis, object storage, metrics, and media control ports.
9. Run replay regression suites against representative customer footage.
10. Complete the security checklist and record the owner of each launch risk.

## Health, readiness, and metrics

- `/api/v1/health/live` proves the API process can answer.
- `/api/v1/health/ready` proves its database can answer.
- `/api/v1/production/readiness` explains hosted launch blockers to an administrator.
- `/api/v1/agent/metrics` emits internal Prometheus text and requires the agent key.

The metrics endpoint is for a private service network. Alert on API readiness,
offline cameras, unhealthy edge stations, growing offline queues, delivery dead
letters, worker lease churn, and end-to-end incident latency.

Camera runtime metrics include online/error camera counts, stale leases, cameras in
restart backoff, and cumulative RTSP reconnects. A live camera renews its lease on a
dedicated heartbeat even while a frame read is stalled. OpenCV builds used on edge
stations must include FFmpeg support so RTSP open/read timeouts are enforced; the
worker logs an explicit warning when its build lacks constructor-level timeout support.

Continuous recording is disabled by default. Enable it only after choosing a lawful
retention period and checking disk capacity. Each edge camera writes rotating MP4 files
under its own directory, publishes a JSON manifest only after the video is atomically
finalized, deletes expired segments, and enforces a byte ceiling. Alert on recording
errors and dropped-frame totals. These local segments are the edge-storage foundation;
remote retrieval and legal holds use the configured recording-storage backend. Hosted
deployments must select `s3`, a private bucket, and a tested lifecycle policy.

The operations worker also reconciles camera, frame, recording, and attached-edge
signals into durable health incidents. Keep that worker running, monitor
`video_intelligence_operational_health_active`, and verify a staged camera disconnect
both opens and automatically resolves an incident before each production rollout.

When centralized archive upload is enabled, monitor spool growth, archived segment
counts, legal holds, failed discovery runs, storage capacity, and signed-playback error
rates. Schedule retention only after the approved policy is configured and test it on
non-production data first. Legal holds override ordinary expiry. ONVIF discovery must
run from the enrolled station attached to the intended camera VLAN; do not expose
multicast discovery or camera service ports to the public network.

Store `VIDEO_INTEL_API_CAMERA_ENCRYPTION_KEY` separately from signing and database
credentials. For ONVIF HTTPS endpoints, keep certificate verification enabled unless
the camera is on a controlled private network and its self-signed certificate has been
explicitly accepted. Rotate a camera password by re-onboarding it; never place RTSP
userinfo in dashboards, logs, tickets, or environment files.

## Backup and restore drill

Run the backup helper with an explicit destination:

```powershell
.\scripts\backup-control-plane.ps1 `
  -DatabaseUrl $env:VIDEO_INTEL_API_DATABASE_URL `
  -DestinationDirectory C:\secure-backups\artae-vision
```

The helper copies SQLite or creates a custom-format PostgreSQL dump. Production
should additionally use managed point-in-time recovery. Quarterly, restore into an
isolated database, run migrations, compare organization/camera/event counts, play a
sample signed clip, and record recovery time and recovery point.

## Bounded smoke load

The checked-in test makes only read-only readiness requests:

```powershell
python scripts/smoke-load.py --requests 500 --concurrency 20
```

This catches obvious availability regressions; it is not a capacity claim. Before a
customer rollout, test expected camera, event, WebSocket, clip, and search volumes in
an isolated environment with synthetic data and explicit spend limits.

## Incident response

1. Preserve audit logs and relevant event/evidence identifiers.
2. Revoke affected user, webhook, or edge credentials; rotate only the compromised
   secret and keep a record of the change.
3. Stop outbound actions if their scope is uncertain; camera observation can remain
   local when safe.
4. Identify affected organizations and retention/legal obligations.
5. Restore from a verified backup when integrity is uncertain.
6. Write a timeline, root cause, customer impact, and prevention actions.

Do not silently delete evidence during an incident. Legal hold, deletion windows,
notification duties, and biometric/privacy treatment require an approved business
policy and jurisdiction-specific review.
