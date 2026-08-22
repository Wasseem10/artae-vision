# Inference service

This installable Python service owns camera capture and YOLO inference for the
first milestone. It also provides a finite MP4 recorder and the tracked
person-dwell engine for webcam, file, and RTSP inputs. The milestone 13
`video-intelligence-worker` process polls FastAPI for operator-requested cameras,
holds renewable per-camera leases, and supervises a bounded number of camera loops
concurrently. Each loop reports health plus latest-frame detections without writing
every box to the database. Use the
repository's root
`README.md` for setup, configuration, run commands, and troubleshooting. Keeping
this short README inside the service also lets packaging tools build the service
independently of the monorepo root.

The `video-intelligence-publish-file` command is a separate development adapter.
It loops a local MP4 through FFmpeg into the publisher path returned by FastAPI so
the web dashboard can exercise real RTSP-to-WebRTC delivery without a webcam. It
does not run YOLO and is intentionally independent from the inference frame loop.

For normal managed development, leave `video-intelligence-worker` running and use
the dashboard to start or stop a camera. `video-intelligence-agent` remains useful
for a bounded standalone replay or for debugging local rule configuration.

For a real edge host, enroll the device in the dashboard, save the token shown once,
set `VIDEO_INTEL_CONTROL_PLANE_DEVICE_TOKEN`, and choose a conservative
`VIDEO_INTEL_WORKER_MAX_CAMERAS`. The API also enforces the administrator-configured
device capacity. Start with one camera and increase it only after measuring GPU
memory, decode throughput, and inference latency.

Completed evidence clips follow a second background path. The uploader converts
OpenCV's development MP4 into seekable H.264 using the packaged FFmpeg binary,
then streams it to FastAPI with the source event ID. This encoding and network work
never runs in the frame-processing thread.

Milestone 9 assignments contain every active dwell job for one camera. The service
decodes and tracks each frame once, then fans those detections into independent
per-job state machines. Two jobs can use different objects, zones, confidence
thresholds, and durations without loading YOLO twice.

Milestone 10 fans the same tracked detections into heterogeneous deterministic
engines: zone presence, dwell, entry, exit, count thresholds, and finite-segment
line crossing. Each engine owns only its temporal state. The natural-language
model never runs inside the frame loop, and industry-specific detectors can later
plug in without changing these spatial/temporal primitives.
