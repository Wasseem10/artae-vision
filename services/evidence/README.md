# Evidence intelligence worker

This small host/container worker is the only service that needs Artae Labs
credentials. It claims uploaded clips and queued searches from FastAPI, performs
the slow upload/index/search calls outside the request path, and reports durable
results back using the existing internal agent key.

The worker is optional while Artae Labs is unavailable. Clip recording, playback,
events, and local metadata search continue to work without it. See the root
`README.md` for configuration and run commands.
