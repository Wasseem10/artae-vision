# Pose model accuracy experiment

September 28, 2026. The live fall rule remains `BrowserPoseRule/fall-v2`.
This experiment changes only MediaPipe's pose landmark model. The current
production model is Lite (`59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`).
The Full and Heavy bundles are from Google's version-1 float16 Pose Landmarker
release, with SHA-256 hashes `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`
and `64437af838a65d18e5ba7a0d39b465540069bc8aae8308de3e318aad31fcbc7b`.

## Selection on already examined footage

Replay all 100 CAUCAFall clips at 10 sampled frames per second in the browser,
with the same fall rule and event matching used by the [earlier independent
evaluation](caucafall-independent-result.md). This source has been examined;
these comparisons select a candidate, not an independent validation.

The frozen Lite benchmark matched 17/50 annotated falls and alerted on 0/50
daily-activity clips. A larger pose model qualifies for a fresh-source check
only if it matches more than 17 falls, triggers no daily-activity alerts,
and averages less than 100 ms per pose inference on the benchmark host.
If Full fails, test Heavy using this same rule. Do not tune the temporal rule
using the fresh-source results.

The selection replay is complete. Both candidate reports used CAUCAFall
manifest SHA-256 `b984a772a641d225479b3416e0c77f75fe649827f8adb0e696fd844524bada54`.
The Full report SHA-256 is `174f93dc9f7eec232c8e899fb974f3d854fc59c655c4312e4109abf41792182d`;
the Heavy report SHA-256 is `ec881edb70e5c596b329524388b67b42f0e637ee83b0d74fefb19e3a973656a2`.

| Pose bundle, same temporal rule | Matched falls | ADL clips alerted | Mean pose coverage | Mean inference |
| --- | ---: | ---: | ---: | ---: |
| Lite, current live | 17/50 | 0/50 | 77.2% | 20.5 ms |
| Full | 19/50 | 1/50 | 80.4% | 29.1 ms |
| Heavy | 22/50 | 0/50 | 83.1% | 77.2 ms |

Full fails the false-alert gate. **Heavy is the selected candidate for the
fresh-source check**, with no change to the fall rule. It gained eight and
lost three annotated fall matches relative to Lite, for a net gain of five.
The mean inference cost is close to the 100 ms sample interval, so slower
devices may miss the intended sampling rate. These are development-source
results, not a live accuracy claim.

## Fresh-source check after choosing a candidate

- [RealBiomFall v3](https://zenodo.org/records/11636174) supplies 100 released
  positive clips, with the ZIP checksums pinned in `scripts/prepare-realbiomfall.py`.
  The clips will be scored as clip-level hits because the dataset's temporal
  action IDs have not been mapped to our alert windows. There are no negative
  clips in this set. The 100 clips come from six source videos, so their
  outcomes are correlated and must not be treated as 100 independent falls.
  The source MP4V videos are converted to H.264 for browser replay, with
  source and converted hashes recorded separately.
- [Fall Detection IMU & Video Dataset](https://github.com/adityavvvn/Fall-Detection-IMU-Video-Datase)
  supplies 35 staged fall clips and 60 walk, sit, and disturbance-walk negative
  clips from four actors, pinned to Git
  revision `a895be0ed80a33b55363468c804a9e4d7af95b9c`. They are converted
  to H.264 for browser replay without changing their timing. The source README
  describes academic/research use; media stays local and ignored by Git.
  Fall scoring is clip-level because event intervals are unavailable.

Run Lite and the selected candidate on exactly the same locally hash-verified
clips. Compare positive clips alerted, negative clips alerted, total alerts,
pose coverage, and inference time. A candidate with extra negative alerts
cannot replace the live model. Even with a favorable result, these short
research clips cannot measure real-world fall sensitivity or a field
false-alert rate. Live use remains experimental and requires caregiver review.

Media and raw pose traces remain under ignored local paths. Commit only
aggregate metrics, source digests, and per-clip alert times without frames.
