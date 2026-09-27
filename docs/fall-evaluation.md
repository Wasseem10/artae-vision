# Browser fall detector evaluation

Artae includes a local, repeatable benchmark at `/evaluation/fall`. It runs the
same self-hosted MediaPipe Pose Landmarker Lite worker and `BrowserPoseRule` used
by `/live`. The benchmark does not call Amazon Bedrock or any other paid service.

## Run it

```powershell
pnpm --dir apps/web dev
```

Open `http://localhost:3000/evaluation/fall` and select **Run evaluation**. The
page analyzes all five clips at 0.1-second intervals. It shows aggregate metrics
and enables JSON export only after every clip finishes. A stopped or failed run
keeps completed clip rows for diagnosis, but has no aggregate score or export.

The export records `scoringUnit: "clip"`, the detector rule identifier, pinned
MediaPipe runtime and Pose Landmarker Lite model version and SHA-256, and the
sampling interval. `provenance.codeRevision` is `null` unless a known Git commit
is supplied as `NEXT_PUBLIC_GIT_COMMIT_SHA` when starting or building the web
app. Supply that public value only for a clean committed build; a commit SHA
does not describe uncommitted changes.

## Initial baseline — September 21, 2026

| Clip | Ground truth | Detected events | First event | Pose coverage | Inference p95 | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Staged lateral fall | Fall | 1 | 6.8 s | 71% | 43.5 ms | Pass |
| Staged forward fall | Fall | 1 | 8.2 s | 53% | 31.3 ms | Pass |
| Staged backward fall | Fall | 1 | 8.7 s | 100% | 32.6 ms | Pass |
| Sitting down and standing up | No fall | 0 | — | 100% | 35.0 ms | Pass |
| Bending down and standing up | No fall | 0 | — | 91% | 36.0 ms | Pass |

For this five-clip baseline, **clip-level** fall recall was 3/3 and clip-level
precision was 3/3. A positive clip counts as detected when it produces at least
one alert; a negative clip counts as a false positive when it produces any alert.
The benchmark does not match individual alerts to labeled event windows, so it
does not measure event-level precision or recall. Mean first-candidate latency
from the approximate labeled fall onset was 2.23 seconds. Both negative controls
produced zero alerts.

These values are a regression baseline, not an accuracy claim. All five excerpts
come from one staged source collection, contain the same subject and environment,
and cover only two negative activities. The onset labels are approximate. The
`falseAlertsPerHour` export field describes only those two short negative clips;
it is not a field false-alarm rate. This run does not measure occlusion, multiple
people, camera movement, poor lighting,
unusual mobility, assistive devices, or real accidental falls.

## Promotion gate for a field pilot

Before the feature is described as reliable outside a controlled demonstration,
Artae should be evaluated on a separately held-out set with multiple people,
rooms, camera angles, lighting conditions, falls, and ordinary activities. A
provisional engineering gate is:

- at least 100 independently sourced positive fall clips and 300 hours of
  representative negative footage, with exposure reported in analyzed and
  scheduled camera-hours;
- event-level recall of at least 90% on the held-out set, measured with labeled
  event windows and one-to-one alert matching;
- no more than 0.1 false alerts per monitored hour;
- p95 local candidate latency below five seconds; and
- every failure retained with its footage, model version, configuration, and
  human label so the result is reproducible.

Meeting these engineering gates would still not make Artae a medical device or
an emergency response service. It would establish a credible computer-vision
baseline for a limited field pilot.
The installed-camera YOLO path must be measured separately from this browser
MediaPipe path; see [native candidate replay](native-fall-evaluation.md) and the
[supervised pilot plan](fall-pilot-plan.md).
