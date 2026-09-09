# Browser demo third-party notices

MediaPipe Tasks Vision 0.10.32 runtime: Google, Apache License 2.0.
https://github.com/google-ai-edge/mediapipe
https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE
The npm runtime files are copied unmodified at build time. The official
Pose Landmarker Lite model is downloaded from the versioned Google-hosted URL
in `apps/web/scripts/prepare-vision.mjs`, which checks its SHA-256 digest.

Fall, sitting and bending samples: **UMAFall: Fall Detection Dataset
(Universidad de Malaga)**, Eduardo Casilari and Jose A. Santoyo-Ramón.
Source: https://figshare.com/articles/dataset/UMA_ADL_FALL_Dataset_zip/4214283
License: Creative Commons Attribution 4.0 International,
https://creativecommons.org/licenses/by/4.0/
Changes: short excerpts, resized to 480 pixels high, re-encoded to H.264, audio
removed. The subjects perform staged activities. No endorsement is implied.
Source IDs/hashes and acquisition details are in `docs/calibration-sources.json`.

Person sample: Pexels contributor, “Man walking office alone”, video 4435565.
Source: https://www.pexels.com/video/man-walking-office-alone-4435565/
License: https://www.pexels.com/license/
Changes: short excerpt, resized and re-encoded, no audio. No endorsement implied.

The derivative sample files can be regenerated from the separately acquired
source clips using `scripts/prepare-browser-samples.py`. They are illustrative
test inputs, not evidence of real-world fall-detection reliability.
