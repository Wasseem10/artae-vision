# Camera commissioning and visual readiness

Phase 24 adds an automated, model-free health check between connecting a camera and
deploying visual jobs. It answers a narrow but important question: **is this stream
technically usable for visual analysis?** It does not claim that a hard-hat, fall,
tailgating, or other industry scenario is accurate.

## Operator workflow

1. Connect an ONVIF camera or register another supported source.
2. Select the camera in **Advanced tools** and open **Camera commissioning**.
3. Choose an enrolled edge station if the camera is not already pinned to one.
4. Select **Run camera health check**.
5. The edge station opens the private source for eight seconds, samples at most 120
   frames, and reports measurements plus a representative JPEG preview.
6. Fix any listed camera, network, lighting, or focus problems and rerun the check.

The check does not change the camera agent's desired state, start continuous
recording, run object detection, call a VLM, or create billable provider requests.
It uses the same encrypted-source release and exact device identity as onboarding.

## Measurements and readiness gate

The edge worker measures delivered frames, failed reads, resolution, observed frame
rate, average brightness and contrast, Laplacian sharpness, frozen-frame ratio, and
black-frame ratio. The control plane—not the edge worker—applies the deterministic
score so thresholds remain consistent across stations.

A camera passes at a score of at least 80 with no error-level finding. Current checks
flag too few frames, more than 10% failed reads, resolution below 640x360, frame rate
below 5 FPS, extreme exposure, low contrast, blur, a nearly frozen feed, and excessive
black frames. Every finding includes an operator-facing corrective action.

Queued work is leased. If an edge process disappears, the lease expires and another
worker using that same enrolled device identity can reclaim it. Only one queued or
running check is allowed per camera.

## What a pass means

A pass means the stream was reachable and its basic delivery and image properties
met the current technical floor during a short sample. It is a prerequisite for
accuracy work, not accuracy evidence.

Before enabling a real scenario, run the exact camera angle, lighting, model, prompt,
rule, and thresholds through the replay-calibration workflow. Field clips must cover
true events, normal negatives, difficult lighting, occlusion, distance, motion, and
expected wardrobe/equipment variation. Promotion gates in the replay suite remain the
source of truth for measured precision, recall, false alarms, latency, and cost.

## Privacy and operational boundary

Commissioning is explicitly operator-triggered. It never starts itself when a camera
is discovered or connected. The sample is bounded and only the selected preview is
stored in the existing short-lived latest-frame store. Camera credentials are never
returned to the browser or written to commissioning results.

Production teams should rerun commissioning after moving a camera, changing a stream
profile, modifying lighting, replacing network equipment, or updating camera firmware.
Long-term drift monitoring and scheduled rechecks can build on the same measurement
contract once customers choose their operating and privacy policies.
