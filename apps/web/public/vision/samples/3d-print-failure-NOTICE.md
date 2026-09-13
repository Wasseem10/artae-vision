# 3D-printer failure demo footage

`3d-print-failure.mp4` is a 26-second presentation sequence assembled from the
ten source frames in the `GreenSkullEarly` sequence of the
[Bed-Adhesion Failure-Onset Dataset for FDM 3D Printing](https://github.com/EmptyDeck/3DPrint-Failure-Video-Dataset).
It shows real printer observations in chronological order; it is not an Artae
detection animation. The timing was expanded to make the progression inspectable
in a short interactive demo.

The dataset authors release the source frames and externally hosted videos under
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). This derived demo
is used for the non-commercial Artae hackathon prototype under the same license.
Attribution: EmptyDeck, “Bed-Adhesion Failure-Onset Dataset for FDM 3D Printing,”
`GreenSkullEarly` sequence, accessed September 12, 2026.

Rebuild with:

```powershell
.\.venv\Scripts\python.exe scripts\build-printer-demo.py `
  <dataset>\data\P2\GreenSkullEarly\masks `
  apps\web\public\vision\samples\3d-print-failure.mp4
```
