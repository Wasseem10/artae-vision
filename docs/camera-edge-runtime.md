# Production camera and edge runtime

The managed camera runtime now treats video capture, lease ownership, recording, and
health as separate responsibilities so a blocked stream cannot silently create two
workers for one camera.

## Live-source recovery

RTSP sources use OpenCV FFmpeg open/read timeouts when the installed build supports
constructor parameters. A failed live read closes the capture and performs bounded
exponential reconnect attempts. File sources still end normally and are never looped
or reconnected. Credentials are redacted from every error and log message.

The control plane applies its own exponential restart backoff after a camera exhausts
the in-process reconnect budget. This prevents a permanently invalid URL or offline
camera from creating a tight claim/crash/reclaim loop. A manual stop/start clears the
failure counter and permits an immediate operator-directed retry.

## Lease and health behavior

Each camera has a frame-independent heartbeat. A temporarily blocked capture therefore
continues renewing its exclusive database lease. The API reports healthy, recovering,
stale, offline, or error health along with last heartbeat, last frame, frames processed,
reconnects, failure count, and next retry time. Running/error/stopped telemetry also
updates the camera's top-level online/error/offline state.

## Continuous edge recording

Continuous recording is deliberately opt-in. When enabled, a bounded background queue
writes rotating MP4 segments without blocking inference. Completed files are renamed
atomically from `.partial.mp4`, paired with JSON manifests, and pruned by both age and
total bytes. Queue pressure is visible as a dropped-frame counter; recording failures
do not terminate safety inference.

Completed segments can optionally enter a restart-recoverable upload spool. The control
plane creates a tenant-scoped catalog record before accepting content, stores the
archive under an organization/camera boundary, calculates its digest, and returns a
short-lived signed playback URL. Administrators can place or release legal holds and
run explicit retention deletion. The storage boundary supports local development disk
or a private S3-compatible bucket; production still requires a selected provider,
approved lifecycle policy, capacity alarms, and tested recovery.

## Camera discovery

Operators request a scan against a specific enrolled edge station. That station—not
the cloud API—sends a bounded ONVIF WS-Discovery multicast probe on the camera LAN.
Results are deduplicated and capped before the worker reports service addresses and
scopes through its leased device identity. Discovery does not guess credentials or
silently activate a camera. An administrator can start a separate credentialed job;
the same edge station resolves ONVIF media profiles, selects a compatible RTSP stream,
and creates the camera only after a real preview frame succeeds. Credentials are
encrypted at rest, omitted from API reads and logs, and released only in the pinned
edge assignment.

## Camera commissioning

After connection, an administrator can request a short model-free health check from
the camera's pinned edge station. The worker samples the real stream without starting
the inference agent and reports delivery, resolution, frame rate, exposure, contrast,
sharpness, frozen-frame, and black-frame measurements. The control plane computes one
consistent readiness score and operator guidance. See
[`camera-commissioning.md`](camera-commissioning.md) for thresholds and the accuracy
boundary: a passing stream still requires scenario-specific replay calibration.

## Production checks

- Use an OpenCV build with FFmpeg and confirm no timeout-compatibility warning appears.
- Set heartbeat below the API lease duration.
- Alert on stale leases, camera errors, restart backoff, reconnect growth, recording
  errors, recording drops, and disk availability.
- Validate reconnect behavior with the actual camera model, network, codec, and
  credentials before claiming site readiness.
- Run commissioning after installation or camera/network changes, then complete the
  scenario replay gate before claiming detection accuracy.
- Enable continuous recording only after retention, privacy, access, and deletion
  requirements are approved.
