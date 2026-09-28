# Fall candidate failure audit

September 28, 2026. This is an exploratory analysis of the already examined
GMDCSA-24 subjects 3–4 result. It explains where the frozen candidate failed;
it is **not** a second independent evaluation or a new accuracy claim.

Run `python scripts/analyze-gmdcsa24-failures.py` after preparing the local,
Git-ignored GMDCSA media and benchmark report. The script joins the author's
clip descriptions to the browser's per-clip outcomes and prints the slices.

| Frozen browser result | All fall clips | Description mentions a bed | Other falls |
| --- | ---: | ---: | ---: |
| Clips | 38 | 16 | 22 |
| Live temporal rule detected | 17 | 4 | 13 |
| Pose-window candidate detected | 24 | 6 | 18 |
| Mean pose coverage | 88.1% | 86.6% | 89.2% |

Ten of the candidate's 14 missed fall descriptions mention a bed. Eleven of
those 14 missed clips have pose coverage of at least 70%, so loss of pose alone
does not explain all misses. A likely issue is that rising motion, a move into
bed, and an actual fall can look similar in a short pose window. This is a
hypothesis, not a proven cause; the author descriptions are coarse labels.

The threshold exploration in the script is **diagnostic only**. Exported pose
features are rounded to four decimals, and replay of the frozen threshold
differs from the original browser result on `gmd-s3-fall-18` (23 rather than
24 detected falls). The original browser report is authoritative. Lower
thresholds on these rounded traces recover more bed falls but also alert on
more daily activities; simply lowering the threshold is not a credible fix.

## Next detector experiment

1. Treat all GMDCSA subject-3/4 outcomes as development data now that they
   have been inspected. Study bed-related misses and exercising false alerts
   with event-level pose timelines, including the period before each fall.
2. Train a candidate that models transition sequence and pose confidence,
   then freeze its code, threshold, and decision policy. Keep the current live
   detector in place until a new independent check supports a change.
3. Obtain a separately sourced, person- and scene-separated test set with
   permitted research use. Score fall events against labeled time windows,
   count false alerts over **analyzed hours**, and publish all per-case outcomes.
4. Only consider a limited supervised pilot after evaluating evidence capture,
   reviewer receipt, and missed monitoring time alongside detection quality.

The existing [holdout report](gmdcsa24-browser-validation.md) and
[pilot protocol](fall-pilot-plan.md) define what the current numbers do and
do not establish. A new detector needs a fresh test source: the subject-3/4
clips cannot become its validation set again.
