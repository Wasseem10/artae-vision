# ADR 0001: Use Artae Labs as the asynchronous intelligence plane

- Status: accepted
- Date: 2026-08-17
- Upstream inspected: `artae/master` at
  `12849c7e6eabab3d592386b6f16c2f63822a90d8`

## Context

This product needs two different kinds of video processing. Live alerts require
low, predictable latency: capture a frame, detect an object, track it, test zone
membership, and advance a timer. Historical natural-language search requires much
heavier clip analysis, Gemini multimodal embeddings, storage, and asynchronous
jobs. Artae Labs already implements the second category.

The repository owner has approved reuse. The checked-in Artae application is much
broader than this product and includes creator, editing, marketplace, campaign,
mobile, and social features that are unrelated to camera event detection.

## Decision

Keep the real-time inference service independent. Integrate Artae Labs through the
narrow `packages/artae-labs-client` adapter for recorded clips, event evidence,
semantic enrichment, and timestamped search.

```text
real-time plane: camera -> YOLO -> future tracker/zones/timers -> alert
                             |
                             `-> short clip -> Artae Labs -> Gemini search
```

Do not call Labs from the per-frame detector loop, and do not merge the complete
Artae repository into this monorepo. When a specific upstream module is later
needed, extract it deliberately with its tests and retain its source provenance.

## Consequences

- Live detection can continue when Labs is slow or unavailable.
- The Labs request/response contract is isolated and mock-testable.
- Presigned object-storage uploads never receive the Labs API key.
- A future background worker can own uploads and polling without changing camera
  capture or YOLO inference.
- The internal API key and gateway URL remain deployment configuration, never
  committed source code.
