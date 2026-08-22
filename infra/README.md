# Local infrastructure

`docker-compose.yml` starts MediaMTX, PostgreSQL, the FastAPI control plane, durable
alert worker, and Next.js operator console for local development. MediaMTX accepts RTSP publishers,
proxies RTSP cameras, and gives browsers a low-latency WebRTC/WHEP view. Every media,
Control API, and metrics port is published only on host loopback.

The stack intentionally does not containerize the webcam/inference process:
desktop camera and display access differs across Windows, macOS, and Linux, so the
worker runs on the host and calls `http://127.0.0.1:8000`. Run
`video-intelligence-worker` once and leave it idle; dashboard Start/Stop requests
are claimed through the API. The bounded supervisor can run several cameras after
you enroll the host and configure both local and server-side capacity. It reads
stable MediaMTX RTSP paths, so both
RTSP cameras and local development publishers follow the same inference route.

The Compose secrets are development defaults only. Set `VIDEO_INTEL_API_AGENT_KEY`
and `VIDEO_INTEL_API_DASHBOARD_KEY` in a private `.env` before using the stack on a
shared network, and replace the local encryption/media-signing defaults. Production
configuration requires OIDC rather than the dashboard key and per-device tokens
rather than the shared edge key. `mediamtx.yml` also permits anonymous local publish/read/API access;
that is a development convenience, not an internet-safe security policy. Redis,
object storage, full monitoring, TLS/TURN, and production orchestration will be
added only when a milestone needs them.

The API now mounts an `evidence-data` volume because clip bytes do not belong in
PostgreSQL. The `evidence-worker` service is under the opt-in `artae` Compose
profile; normal development remains healthy without a Labs key. Start that profile
only after setting `ARTAE_LABS_API_KEY` and `ARTAE_LABS_INDEX_ID`.
