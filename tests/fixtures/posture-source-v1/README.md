---
license: cc-by-4.0
pretty_name: Fall Detection and Posture Classification Dataset
task_categories:
- image-classification
- video-classification
language:
- en
tags:
- fall-detection
- pose-estimation
- posture-classification
- elderly-care
- mediapipe
- human-activity-recognition
- computer-vision
size_categories:
- 1K<n<10K
---

# AI-Driven Posture Analysis & Fall Detection Dataset (Elderly Care)

## Overview
This dataset supports the dissertation project **"AI-Driven Posture Analysis Fall Detection System for the Elderly"**, completed by Patrick O. Ogbuitepu for the degree of MSc Artificial Intelligence and its Applications (CE901 MSc Project and Dissertation), School of Computer Science and Electronic Engineering (CSEE), University of Essex (2024). Supervisor: Dr Adrian Clark.

The project uses MediaPipe pose estimation, fuzzy logic, and a finite state machine to classify static postures (standing, sitting, lying, bending, squatting, etc.) and detect transitions — particularly falls — from monocular RGB video, achieving a zero false-alarm rate in testing.

This dataset contains the raw video recordings, static pose images, and frame/time-level annotations used to develop and evaluate that system.

## Dataset subject and consent
- **Sole subject**: All images and videos feature one consenting adult — the researcher, Patrick O. Ogbuitepu — performing self-recorded daily activities and posture/fall scenarios for research purposes. No other individuals appear in the data.
- **Consent**: Covered by a self-consent form on file (`Self-Consent Form for Dataset Usage.docx`), signed 31-Aug-2024, under University of Essex ethical guidelines for use of personal data in research.
- **Public release**: Approved under University of Essex research ethics procedures for the dissertation project (supervisor: Dr Adrian Clark), per the consent form's requirement that public sharing have explicit approval beyond the original research-use consent.

## Contents
| Split | Videos | Description |
|---|---|---|
| `train/` | `hr_fall_detection_1.mp4`–`hr_fall_detection_3.mp4` | Training recordings of daily activity and fall scenarios |
| `valid/` | `fall_detection_4.mp4`–`fall_detection_10.mp4` | Validation recordings of daily activity and fall scenarios |
| `test/` | — | Reserved for held-out test recordings |

Each video has a matching label file under `<split>/labels/`:
- `<video_name>.csv` — columns: `start_time`, `end_time` (seconds from video start), `action` (Stand/Sit/Lie and transitions like Stand-Lie), `is_fall` (boolean)
- `<video_name>_in_minutes.md` — human-readable summary of labelled events with timestamps in minutes:seconds

Static pose images (113 total) are in `train/pose/`, one image per labelled posture (e.g. `stand.jpg`, `sit.jpg`, `lie.jpg`, `bend.jpg`, `squat.jpg`, `fall.jpg`, plus variants capturing angle, occlusion, and edge cases). `train/pose-1st-iteration/` contains an earlier capture/processing pass of the same 113 poses, kept for provenance.

Derived outputs (MediaPipe landmark features and classifier predictions) are included for transparency and reproducibility:
- `train/pose/features_output.csv`, `features_output_predicted.csv` — extracted pose-landmark features and model predictions for the static images
- `train/pose-1st-iteration/results/` — equivalent outputs for the first-iteration pass
- `train/results of static pose classifier on training videos/` — per-frame static-pose classifier output for each training video

## File naming
- `hr_fall_detection_N` — training recordings (N = 1–3)
- `fall_detection_N` — validation recordings (N = 4–10)

## Provenance and collection methodology
All data was self-recorded by the researcher (sole subject) specifically for this dissertation. Timing and location were deliberately varied across recording sessions to avoid bias from prior knowledge of the detection logic being developed:
- **113 static pose images** — captured in a STEM lab and a bedroom, recorded four weeks after the training videos. Poses (standing, sitting, lying, and their variations) were inspired by reference poses from openposes.com, adapted to reflect the more limited range of motion typical of elderly individuals.
- **3 training videos** (~11 min total) — recorded in a CSEE lab; used to validate the static-posture classifier and to develop the fall-detection logic.
- **7 validation videos** (~20 min total, recorded across 3 time-separated batches) — recorded about a month after the static images, in a bedroom, a living room, and an event-centre atrium, to test generalization across distinct, previously unseen settings. (Note: the dissertation reports 6 validation videos across these batches; the published set contains 7 — double-check coverage if citing the dissertation's exact figures.)

Derived files in this dataset were produced by the following processing pipeline, applied after raw capture:
1. **Motion localization** — frame-differencing between consecutive video frames, denoised via contour-area thresholding, with overlapping bounding boxes merged, snapped to a fixed grid, and temporally smoothed over the last 3 frames to produce a stable region of interest.
2. **Pose estimation** — the region of interest is passed to Google's MediaPipe pose model to extract joint landmarks per frame/image (saved as `features_output.csv` / `features_output_predicted.csv`).
3. **Static posture classification** — joint angles and bounding-box aspect ratio are used to rule-classify each frame/image as standing, sitting, or lying.
4. **Activity and fall labelling** — fall and posture-transition events were manually labelled per video (frame index + timestamp), with temporal smoothing applied to stabilize frame-to-frame predictions before fall events were flagged.

No synthetic, scraped, or third-party data is included — every video and image is an original recording of the consenting subject.

## Intended use
Research and development of vision-based human activity recognition and fall-detection systems for elderly care: pose estimation benchmarking, activity classification, fall-event detection, and related computer vision / HCI research.

## License
Released under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). See `LICENSE`.

## Citation
If you use this dataset, please cite:

```
Ogbuitepu, P. O. (2026). AI-Driven Posture Analysis Fall Detection System for the
Elderly: Dataset [Data set]. University of Essex. https://doi.org/10.5281/zenodo.21359208
```

See `CITATION.cff` for machine-readable citation metadata.

## Contact
Patrick O. Ogbuitepu — pat2echo@gmail.com

## Mirrors and related resources

- **Zenodo (citable DOI):** https://doi.org/10.5281/zenodo.21359208
- **Kaggle dataset:** https://www.kaggle.com/datasets/patrickogbuitepu/posture-monitor-and-fall-detection
- **Source code (GitHub):** https://github.com/pat2echo/AI-Posture-Monitor
- **Python package (PyPI):** https://pypi.org/project/ai-posture-monitor/
- **Runnable demo notebook (Kaggle):** https://www.kaggle.com/code/patrickogbuitepu/fall-detection-posture-classification-starter

See `column_descriptions.md` for the schema of every CSV and `file_descriptions.md` for per-file descriptions.
