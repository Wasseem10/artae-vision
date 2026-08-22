# Guarded actions and connectors

Phase 18 closes the safe half of the visual-operations loop: a camera event can now
produce a durable, reviewable action in another system. The rule engine still decides
*what happened*; the action runtime owns *what may happen next*. Keeping those
boundaries separate prevents a model response from directly operating an external
system.

## Safety model

Every action has a fixed registry definition, required connector scope, and risk:

- `send_notification` is low risk and may run automatically.
- `create_ticket` and `invoke_webhook` are medium risk and default to manual approval.
- `control_physical` is high risk and is unavailable. Door, gate, machine, payment,
  and similar control will require a future customer authorization and verification
  design rather than merely adding an endpoint URL.

Credentials are encrypted at rest with the API encryption key. Operator responses
never return the secret. Production connector endpoints require HTTPS. Payloads are
built from bounded stored templates plus trusted event, camera, rule, and alert fields;
arbitrary model-generated requests are not executed.

## Execution lifecycle

An enabled rule action creates one idempotent execution per event and binding:

```text
camera event -> awaiting approval or queued -> leased worker -> succeeded
                                                |               |
                                                +-> retrying ----+
                                                +-> dead letter
```

The worker uses a lease so only one process owns an attempt. Connector requests carry
an idempotency key and, when a credential is configured, a body signature. Transient
failures use bounded exponential retries; permanent or exhausted failures move to the
dead-letter state. Operators can approve, deny, or manually retry through the guided
dashboard. Resolving the source alert suppresses work that has not started.

## Adapters

- `mock` proves the end-to-end path without making a network request.
- `generic_webhook` sends the standard bounded action envelope.
- `messaging_webhook` converts that envelope into a concise message payload.
- `ticket_webhook` converts it into a summary, description, and severity payload.

Vendor-specific OAuth and field mapping should be implemented as new adapters behind
the same contract, not as branches in the vision rule engine.

## Local operation

`Start-Native-Dashboard.cmd` now starts the API, web app, inference worker, and action
worker. `Stop-Native-Dashboard.cmd` stops all four while preserving SQLite data and
evidence. Docker Compose already runs the same action worker as `alert-worker`.
