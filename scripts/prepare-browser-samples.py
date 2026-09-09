"""Encode already-downloaded licensed benchmarks into browser-playable H.264.

No generated detections: the browser must analyze these frames on every run.
Sources and licenses are in docs/calibration-sources.json.
"""
from pathlib import Path
import subprocess
import imageio_ffmpeg

root = Path(__file__).resolve().parents[1]
destination = root / "apps/web/public/vision/samples"
destination.mkdir(parents=True, exist_ok=True)
sources = {
    "person.mp4": "artifacts/calibration/public/pexels/4435565-person-entry.mp4",
    "fall-lateral.mp4": "artifacts/calibration/derived/person-fall/umafall-lateral-13-25.mp4",
    "fall-forward.mp4": "artifacts/calibration/derived/person-fall/umafall-forward-13-25.mp4",
    "fall-backwards.mp4": "artifacts/calibration/derived/person-fall/umafall-backwards-8-20.mp4",
    "sitting.mp4": "artifacts/calibration/derived/person-fall/umafall-adl-sitting-8-20.mp4",
    "bending.mp4": "artifacts/calibration/derived/person-fall/umafall-adl-bending-8-20.mp4",
}
for name, source in sources.items():
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
                    "-i", str(root / source), "-t", "15", "-an", "-vf", "scale=-2:480",
                    "-c:v", "libx264", "-crf", "25", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(destination / name)], check=True)
    print(name)
