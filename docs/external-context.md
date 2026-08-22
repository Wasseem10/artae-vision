# External context and temporal correlation

Phase 19 lets a visual event be evaluated alongside authorized records from another
system. This is how the platform can distinguish “two people entered” from suspected
tailgating: the camera supplies the people count, the access feed supplies granted
swipes, and a deterministic policy compares them inside one time window.

## Normalized contract

A `ContextSource` represents a tenant-owned read/query integration. Each vendor
adapter translates its data into `ContextObservation` records with:

- a source-owned idempotency ID;
- an observation type such as `access_granted`;
- an occurrence timestamp;
- an optional privacy-preserving entity key; and
- bounded vendor-specific attributes.

The rule engine never needs vendor branches. A future badge, POS, CRM, loyalty, or
equipment adapter only has to emit the normalized observation contract.

## Correlation lifecycle

An enabled `RuleCorrelationPolicy` defines the source, observation type, visual-count
field, and before/after window. When that visual rule fires, ordinary alert creation is
deferred and a durable evaluation is queued:

```text
camera event -> wait for window end -> count matching observations
                                      |
                                      +-- camera count > authorized -> incident/action
                                      +-- camera count <= authorized -> clear/no alert
```

Waiting through the after-window matters because an external record can arrive a
moment after the corresponding camera frame. The action worker processes due
evaluations before the incident/action pipeline continues. Every outcome preserves
both counts, timestamps, status, and a plain-language explanation.

## Safe reference workflow

The guided dashboard creates a simulated access-control source and attaches a
count-versus-authorizations policy. “Run 2 people / 1 swipe” writes one synthetic
granted-access observation and one two-person camera event. No real access system is
queried and no door can be controlled. A matched evaluation enters the same guarded
notification/ticket runtime built in Phase 18.

The simulator proves orchestration, tenancy, idempotency, timing, and action gating.
It is not an accuracy benchmark for detecting two people; that remains a replay/model
evaluation concern.
