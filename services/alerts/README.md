# Alert delivery worker

This small process claims durable webhook jobs from the control-plane API. It sends
canonical JSON with an HMAC-SHA256 signature, reports success or failure, and leaves
retry scheduling to the API. It contains no camera, inference, or database code.

Run `video-intelligence-alert-worker` after configuring the `VIDEO_INTEL_ALERT_*`
values documented in the repository root `.env.example`.
