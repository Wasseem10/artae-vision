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
same permission. External messaging remains a separate opt-in connector decision.

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
