# Operator web application

This Next.js application is the milestone-13 control surface for the video
intelligence platform. It manages cameras, draws normalized polygon zones, creates
reviewable dwell rules, changes rule status, and receives committed events over a
WebSocket. It also starts/stops the selected managed vision agent, shows worker
health, and renders transient detection boxes received over that same connection.
It loads MediaMTX's version-matched reader script, attaches the returned
WebRTC track to a direct video element, and draws zones above it. The browser never
receives an RTSP camera's private source URI and does not run YOLO inference.

Milestone 7 adds a searchable-evidence workspace. It discloses whether matches came
from Artae Labs or deterministic local metadata, polls asynchronous provider jobs,
and seeks the native video player to each returned time range. The event timeline
also shows whether a clip is finishing, playable, indexing, or search-ready.

Owners and administrators can enroll capacity-limited edge hosts, rotate or revoke
their one-time credentials, and inspect tenant-scoped operator audit history. The
browser never receives a stored device secret; a new token is returned only by an
explicit enrollment or rotation response.

Copy `.env.local.example` to `.env.local`, start the FastAPI service on port 8000,
then run `pnpm dev`. The full setup and file-by-file explanation live in the root
`README.md` and `docs/file-guide.md`.
