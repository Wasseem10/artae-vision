# Artae upstream assessment

## Source inspected

- Repository: `https://github.com/Sammy-Dabbas/Artae.git`
- Local remote name: `artae`
- Branch inspected: `artae/master`
- Commit inspected: `12849c7e6eabab3d592386b6f16c2f63822a90d8`
- Commit date: 2026-08-17

The remote is fetched into this repository, so its files and history can be inspected
without copying or merging them into the current working tree.

## Access-boundary clarification

The checked-in public route `POST /api/v1/labs/live/sessions` returns HTTP 501.
That response must not be interpreted as proof that the internal Artae Labs service
or its video intelligence pipeline is absent. The repository owner clarified that
Labs is currently internal-only. Reuse permission has since been confirmed; an
internal API credential and gateway address are still required to call that
surface. The indexing pipeline is implemented through the index,
library, Celery, and Intel service paths described below.

## Why Artae Labs is relevant

Artae Labs already demonstrates several platform capabilities planned for the video
intelligence product:

- FastAPI routers organized by resource
- PostgreSQL and SQLAlchemy models for indexes, videos, shots, and stream sources
- asynchronous video ingestion and analysis jobs
- Redis-backed API rate limiting
- scoped API-key authentication
- usage records and request identifiers
- signed webhook delivery with retry state
- object-storage upload and download flows
- natural-language multimodal search over timestamped video moments
- Python and TypeScript SDK boundaries
- a Next.js application and product documentation

The Labs ingestion, embedding, and retrieval core is a genuine starting point for
the future API and historical-video intelligence plane. It should sit alongside a
low-latency camera inference path rather than inside the per-frame YOLO loop.

## Video ingestion path

The inspected branch implements two ingestion entrances:

1. `POST /labs/indexes/{index_id}/index-url` creates an `IntelVideo` with
   `status="pending"` for a remote source URL.
2. `upload-init` returns a presigned S3 PUT URL. After the client uploads directly
   to object storage, `upload-complete` creates the corresponding `IntelVideo`.

Both entrances enqueue `intel_index_video_task` in Celery. The task uses late
acknowledgement and worker-loss rejection, opens its own synchronous SQLAlchemy
session, and invokes `index_video_sync`. The default repository configuration uses
the established indexing path; `UNIFIED_ANALYZER=true` switches to a consolidated
analyzer path at deployment time.

The default indexing stages are:

```text
URL or S3 object
  -> download/fetch and ffprobe
  -> transcript with timestamped words
  -> cut-aligned visual segments
  -> Gemini visual source-memory analysis
  -> audio, beat, onset, and semantic-event analysis
  -> per-shot multimodal embeddings
  -> PostgreSQL/pgvector + S3 shot assets
  -> status rollup + signed webhooks
```

The visual index detects shot boundaries, samples one to three 640-pixel frames per
segment, and sends batches of up to three segments to
`gemini-2.5-flash-lite`. It receives structured JSON containing literal visual
inventory, subjects and normalized boxes, readable text, motion, producer context,
timing anchors, segmentation targets, and search tags.

The feature-flagged unified analyzer performs equivalent work through a reusable
`AnalysisBundle`, fans independent analysis stages out concurrently, and isolates
individual primitive failures. It is cleaner for future extraction, but the code's
default is `UNIFIED_ANALYZER=false`; the deployed internal environment may override
that value and should be checked before deciding which implementation is canonical.

## Gemini Embedding 2 service

Artae uses `gemini-embedding-2-preview` and truncates its Matryoshka output to 768
dimensions. For each eligible shot it can produce five separate pgvector lanes:

| Vector | Input |
|---|---|
| `text_embedding` | Composite summary, visual memory, tags, transcript, OCR, audio description, and semantic events |
| `video_embedding` | A re-encoded video chunk, capped at 120 seconds |
| `audio_embedding` | A mono 16 kHz MP3 chunk |
| `transcript_embedding` | Only the spoken words within the shot |
| `ocr_embedding` | Only visible on-screen text |

Gemini 2.5 Flash separately creates a dense audio description that is included in
the composite text representation. Shot audio/video chunks can be stored in S3 for
playback and query-time reranking. Calls are wrapped in a Gemini cost/usage logger.

The analyzer limits parallel shot embedding work to four concurrent jobs. In the
default path, `reference_edit` videos always use full embeddings. Ordinary source
videos use full embeddings only up to the configured duration and segment caps
(defaults: one hour and 300 segments). In the inspected code, the resulting `lean`
mode skips all shot vector generation, while the search query requires a non-null
`text_embedding`; long-video behavior therefore needs verification against the
deployed configuration or any production backfill jobs.

There is also an embeddings-as-a-service API for text, image, audio, and video, plus
a separate dense sampled-frame pipeline. Dense frames are embedded as images,
timestamped, persisted in `video_frame_embeddings`, and indexed with HNSW. This is
particularly relevant for finding short visual moments that fall inside a broad
shot-level segment.

## Queryability

The implemented Labs search path embeds a natural-language query with the same
Gemini Embedding 2 model, then performs pgvector cosine search within an owned index.
It returns the matching video and shot IDs, start/end timestamps, similarity,
summary, transcript, audio description, visual analysis, semantic events, playback
URL, and thumbnail URL.

It supports routing to visual, audio, transcription, OCR, or all vector lanes.
The `all` mode currently ranks each shot by the greatest similarity among the
selected lanes. Image search embeds an uploaded image and searches the shot video
embedding lane. The implemented hybrid endpoint combines semantic search with
video, tag, duration, and creation-date filters. Optional deep-listen reranking
sends top candidate audio back through the richer query-aware audio evaluator.

PostgreSQL HNSW indexes exist for text, video, audio, transcript, and OCR cosine
search. Search is therefore timestamp-level and suitable for questions such as
"show me moments where a person approaches a loading door" across previously
indexed footage.

The checked-in documentation, SDK, and route are not completely aligned:

- Documentation describes reciprocal-rank fusion; the route uses `GREATEST` across
  modality scores.
- Documentation describes text-plus-image hybrid search; the route's hybrid request
  is text plus metadata filters.
- The route accepts `group_by` but does not currently apply grouping.
- The Python SDK models a `data/total/start/end/score` response while the route
  returns `results/count/time_start/time_end/similarity`.
- The route requires `text_embedding IS NOT NULL` even for non-text modality search.

The deployed internal gateway may adapt some of these contracts, but the branch
itself needs an integration contract test before its SDK or public documentation is
treated as authoritative.

## Relationship to real-time camera intelligence

Artae Labs can provide semantic understanding and queryability over rolling camera
segments, historical clips, or event evidence. It does not remove the need for the
low-latency deterministic path:

That is different from this product's hot path:

```text
camera frame -> YOLO detection -> persistent track -> zone membership
             -> temporal state -> rule evaluation -> event/alert
```

For a rule such as "a person remains in the loading zone for more than 30 seconds,"
YOLO, persistent tracking, zone geometry, and a temporal state machine should decide
the live alert. Labs can enrich the event, index its evidence clip, answer later
natural-language searches, and support semantic conditions that are difficult to
express with object classes alone.

## Recommended reuse map

| Artae concept | Destination here | How to use it |
|---|---|---|
| Labs API resource routers | `services/api` | Reuse the resource-oriented FastAPI organization, not the creator-specific routes |
| API keys and scopes | `services/api` | Adapt when machine/API access is introduced after user authentication |
| Index/video/shot records | PostgreSQL domain models | Use as inspiration for camera, stream-session, detection, track, zone, rule, and event records |
| Labs video ingestion | background workers | Use for rolling segments, event evidence, historical indexing, and reprocessing |
| Redis rate limits | API infrastructure | Add when an externally consumed API exists |
| Signed webhooks | alert delivery worker | Adapt exact-byte HMAC signing, durable delivery records, and retry scheduling |
| Object-storage flows | event clip storage | Adapt presigned upload/download patterns for recorded evidence clips |
| Timestamped multimodal search | historical event/clip search | Reuse for indexed footage and semantic rule enrichment |
| Dense sampled-frame embeddings | historical visual search | Use selectively when shot-level windows are too coarse |
| Next.js Labs surfaces | `apps/web` | Reuse interaction patterns selectively; do not import the whole creator/editor UI |
| Python/TypeScript SDKs | future `packages` or `sdks` | Add only after the public API contract stabilizes |

## Patterns to improve rather than copy verbatim

- The public live route is access-gated in the inspected checkout. Integrate through
  the authorized internal contract rather than inferring capability from HTTP 501.
- Verify whether the deployed service uses the legacy or unified analyzer before
  porting code; the repository default is the legacy path.
- Add contract tests across the search route and both SDKs before depending on the
  documented request/response shape.
- Resolve long-source `lean` embedding behavior so searchable metadata rows are not
  excluded by the route's `text_embedding IS NOT NULL` condition.
- The rate limiter fails open when Redis is unavailable. That may be acceptable for
  availability in some products but should be an explicit policy decision.
- Usage metering records an optimistic HTTP 200 before the final response status is
  known. Production billing or quotas should meter the actual outcome.
- Some request helpers create synchronous database engines and make synchronous
  HTTP calls. Workers should own slow webhook delivery and retries.
- Several Labs modules rely on direct SQL and runtime table-creation helpers. This
  project should use reviewed migrations as the source of truth.
- The upstream repository includes generated `node_modules` files in an SDK. Those
  should not be brought into this monorepo.

## Integration recommendation

Keep the current low-latency inference milestone, but treat the Artae Labs
ingestion/embedding/search subsystem as the leading base for the asynchronous video
intelligence plane rather than merely a superficial reference. The intended split is:

```text
real-time plane: camera -> YOLO -> tracking -> zones -> temporal rules -> alert
intelligence plane: rolling/event clip -> Artae Labs -> Gemini vectors -> search/enrichment
```

Selectively extract the Labs core with its tests and provenance instead of merging
the entire Artae product, which also contains creator marketplace, editing,
campaign, mobile, marketing, and social-stream functionality unrelated to camera
event detection.

Reuse permission was confirmed by the user through the repository owner. Preserve
the upstream commit and file provenance when code is extracted. A clear root
license would still make that permission durable and unambiguous for future
contributors.
