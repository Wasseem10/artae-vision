# OpenVector and video-intelligence research

Research date: August 17, 2026. This document distinguishes public facts from our
architectural inferences. We are learning from public product behavior and
open-source projects, not copying proprietary implementations.

## What OpenVector publicly demonstrates

OpenVector's public workflow is: describe a condition in plain English, let the
system build a draft agent, review it, then activate it. The agent connects to an
RTSP stream, applies a confidence threshold, executes one or more integrations,
and makes the completed event searchable. That is a strong product pattern because
the model proposes configuration while the user approves an inspectable workflow.

Its research page describes an attention-steered, foveated sub-sampler that keeps
important regions at high resolution while coarsening the rest. The page reports a
roughly 3% pixel budget and lower bandwidth. This is an interesting optimization,
but public research is not proof of the exact production architecture. We should
benchmark conventional motion gating, object crops, frame sampling, and full-frame
models before attempting a specialized sampler.

The offline station is marketed around NVIDIA edge hardware. Together with the
RTSP workflow, this suggests an edge/data plane near cameras plus a control and
search plane, but that separation is our inference rather than a disclosed system
diagram.

Sources:

- [OpenVector: how it works](https://openvector.com/how-it-works)
- [OpenVector: research](https://openvector.com/research)
- [OpenVector: offline station](https://openvector.com/order)

## What the launch transcript adds to the product target

The launch-video transcript supplied during development describes a larger promise
than visual detection and notification alone. Its examples combine camera perception
with queries and actions in legacy business systems:

- tailgating detection is correlated with access-control swipe records, followed by
  a door, ticket, or phone action;
- cargo observations are connected to routing expectations and an interactive site
  map; and
- license-plate recognition is joined with loyalty, POS, and equipment-controller
  workflows.

This changes the competitive unit from a "natural-language camera alert" to a
closed-loop visual operations agent. The differentiating runtime must combine
perception, temporal state, authorized external context, guarded tool execution, and
searchable evidence. The transcript is product messaging rather than an implementation
disclosure, so it does not establish which models or internal architecture OpenVector
uses.

## Competitor patterns worth learning from

| Product | Publicly described pattern | Lesson for this project |
|---|---|---|
| Spot AI | Composes detection, tracking, attributes, search, temporal context, and a proposer/verifier stage into if-then agents | Keep perception modules composable; add a verification stage before high-consequence actions |
| Ambient.ai | AI-native video management, natural-language investigation, and real-time threat detection across camera estates | Treat live operations and historical investigation as two experiences over shared events and video |
| Verkada | Precomputes object crops and CLIP embeddings, separates indexing from search, partitions ingestion by tenant/camera, and organizes vectors by time | Embed useful crops/clips asynchronously; filter by tenant, camera, and time before vector similarity |
| Rhombus | Natural-language search and alerts inside a cloud-managed camera platform | Make query and alert creation simple, but retain reviewable compiled rules |

Sources:

- [Spot AI: engineering video AI agents](https://www.spot.ai/ailabs/introducing-ai-agents-advanced-video-intelligence-with-real-time-operational-impact)
- [Ambient Foundation](https://www.ambient.ai/products/ambient-foundation)
- [Verkada: scaling natural-language video search](https://www.verkada.com/au/blog/scaling-natural-language-video-search-inside-verkadas-breakthrough/)
- [Rhombus AI analytics](https://www.rhombus.com/ai-analytics/)

## Open-source projects we can reuse responsibly

### Strong candidates

- [MediaMTX](https://github.com/bluenviron/mediamtx) is the leading candidate for a
  later streaming gateway. Its MIT-licensed server routes RTSP, WebRTC, HLS, and
  other protocols and includes recording, playback, authentication, a control API,
  and Prometheus metrics. It can keep browser streaming out of our Python inference
  process.
- [Frigate](https://github.com/blakeblackshear/frigate) is an MIT-licensed local NVR
  with mature patterns for motion-gated detection, multiprocessing, recording
  retention, MQTT integration, restreaming, and zone editing. We should learn from
  those boundaries and consider interoperability; importing the entire NVR would
  also import a much larger product surface than we currently need.
- [go2rtc](https://github.com/AlexxIT/go2rtc) is an MIT-licensed, small camera
  streaming bridge with broad protocol support and low-latency browser output. It
  is a good alternative if MediaMTX proves too heavyweight for edge deployments.
- Artae Labs remains our current asynchronous video-intelligence adapter: evidence
  clips can be uploaded and queried without putting Gemini/network latency in the
  frame loop.

### Evaluate later, not now

- Roboflow Supervision has useful model-agnostic annotation and zone utilities, but
  our current polygon and one-rule engine are small and tested. Adding another
  dependency now would not remove enough code to justify it.
- NVIDIA's Video Search and Summarization Blueprint and Intel's edge-video projects
  are valuable reference deployments for GPU batching and edge orchestration. They
  are full stacks, not dependencies to merge into this milestone.
- A separate vector database is premature while Artae supplies semantic indexing.
  If ownership or scale later requires one, begin with measured workloads and
  PostgreSQL/pgvector or a managed vector service before building custom storage.

## Architecture decision

The platform should use three cooperating planes:

1. **Edge/data plane:** camera ingest, YOLO, tracking, zones, deterministic temporal
   rules, short evidence recording, and health reporting.
2. **Control plane:** users, camera registry, draft/active rules, durable events,
   agent configuration, authorization, and live WebSocket updates.
3. **Intelligence plane:** asynchronous clip/crop indexing, natural-language
   retrieval, enrichment, and later proposer/verifier reasoning.

Milestone 3 introduced the first two-plane boundary. PostgreSQL and FastAPI own
configuration and events; by milestone 9 the Python agent fetches every active job,
processes the camera and tracking once, and reports independent idempotent events.
Artae remains behind an asynchronous package boundary for the third plane.

## Revised completion sequence

The original post-milestone-3 items above have largely become implemented foundations.
The remaining sequence now starts with replay evaluation, then introduces a versioned
agent plan, a guarded action runtime, external-system context/correlation, benchmarked
visual skill packs, multi-camera maps/search, an offline edge station, and hosted-product
hardening. See `product-roadmap.md` for the phases and exit criteria.
