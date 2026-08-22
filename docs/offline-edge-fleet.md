# Offline edge station and fleet foundation

Phase 22 makes local execution more resilient without claiming that this repository
is already a supported physical appliance.

## Offline event outbox

Camera rules already execute locally. When a managed camera creates an event, the
control-plane dispatcher now writes its canonical JSON to a small SQLite outbox
before attempting HTTP delivery. A successful response removes the record. A network
or server failure increments the attempt count and leaves the event on disk. The next
event or worker restart retries records in creation order. FastAPI's existing
`source_event_id` idempotency prevents a reconnect from duplicating incidents.

The default database is `artifacts/offline/event-outbox.db`; it can be moved with
`VIDEO_INTEL_OFFLINE_OUTBOX_PATH`. Evidence clips remain separate files and follow
their existing authenticated upload lifecycle.

## Hardware and health profiles

An enrolled device-token worker reports hostname, OS, architecture, CPU count,
memory when the host exposes it, available storage, CUDA availability, worker version,
offline queue depth, and last-sync status. The fleet API deliberately rejects the
legacy shared development key for this identity-bearing endpoint.

## Signed configuration revisions

Administrators can create immutable per-device configuration revisions. The API
canonicalizes JSON, stores its SHA-256 digest, and signs the canonical bytes with the
server signing secret. Edge retrieval includes both `ETag` and `X-Config-Signature`.
The contract is ready for a packaged station to pin a verification key; production
key distribution and rotation belong in Phase 23 secrets management.

## Updates and rollback

Update deployment records contain source, target, and rollback versions. The API
enforces the transition sequence from pending through download/apply to success,
failure, or rollback. It records desired state only: this repository does not silently
download or execute remote binaries. A supported appliance must add signed artifacts,
health checks, atomic activation, and a watchdog before real remote updates are enabled.

## Dashboard and verification

Advanced tools show reported fleet health, hardware, worker version, offline queue,
configuration revision, and latest update status. A provider-free preview profile is
available for learning without claiming it describes the actual PC.

- `tests/inference/test_actions.py` proves disconnect persistence and restart sync.
- `tests/inference/test_hardware.py` proves dependency-light profile discovery.
- `tests/api/test_edge_fleet.py` proves device identity, signed revisions, fleet
  aggregation, state transitions, and rollback.
