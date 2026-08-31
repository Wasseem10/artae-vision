# Calibration datasets

The local calibration pack uses traceable, licensed real video. Downloaded media and
derived excerpts live under the ignored `artifacts/calibration/` directory; source,
license, creator, integrity hash, acceptance status, and limitations are recorded in
`docs/calibration-sources.json`.

## Evidence classes

- `public_benchmark` is licensed real footage used to measure general behavior.
- `controlled` and `field` are recordings from a deployment or target-camera context.
- `synthetic` checks pipeline mechanics but does not count as real-world evidence.

General benchmark readiness and site-specific readiness are deliberately reported
separately. A public benchmark can demonstrate that a scenario works on representative
video, but it cannot prove performance under a future customer's exact camera angle,
lighting, distance, occlusion, or operating process.

## Rebuilding excerpts

After the source files have been downloaded and their SHA-256 hashes verified, run:

```powershell
.\.venv\Scripts\python.exe .\scripts\build-calibration-excerpts.py
```

The script creates bounded, reproducible excerpts for replay evaluation. It does not
alter the downloaded originals.

## Acceptance controls

Every candidate is visually reviewed before it can be labeled. Object-detection scans
are also used for person-presence negatives. A mismatched Pexels download and a warehouse
clip containing possible distant people are retained in the provenance file as rejected
or limited rather than silently counted as passing evidence.
