# Fall detection: prototype to supervised pilot

Status: September 29, 2026. The [pilot protocol](fall-pilot-plan.md) has the
operational gates; this page tracks the next engineering decisions and schedule.

## What works today

`/live` runs pose inference in the browser, creates a possible-fall incident on
the staged sample, records playable evidence, and supports local human review.
The fall/sitting smoke test passes with the API unavailable. The current rule
is reproducible on [UR Fall](urfall-browser-benchmark.md) and a second
[subject-labeled source](gmdcsa24-browser-validation.md).

This is a working **workflow prototype**. The UR Fall reserved result was
2/20 fall clips detected with 1/30 daily-activity clips alerted. It is not a
dependable monitoring detector. The browser also needs an open active tab;
the installed-camera path is a separate system that has not inherited these
browser results.

The first person-separated [GMDCSA-24 check](gmdcsa24-browser-validation.md)
is also complete. The frozen pose-window candidate caught 24/38 falls and
alerted on 2/42 activities, versus 17/38 and 1/42 for the current rule. It
missed 14 falls and increased activity alerts, so it was **not promoted**.
The [failure audit](fall-failure-audit.md) breaks out bed-related misses and
records why threshold replay on rounded traces is only exploratory.

A third, independently sourced [CAUCAFall check](caucafall-independent-result.md)
is now complete. The current live rule caught 17/50 staged falls and alerted
on 0/50 daily-activity clips; the expanded-training pose-window candidate
caught only 3/50. Its failure rules out promotion. The activity footage
lasted about 8.6 minutes, far too little to estimate a field false-alert rate.

The subsequent [five-source audit](fall-cross-source-v4.md) confirmed that
misses are not explained by low pose visibility alone. A multi-source pose
classifier still failed on a held-out source, so it was not promoted. The
existing pose-window model supplies only device-local review suggestions;
the conservative temporal rule remains the automatic alert path. The five
source collections total 525 short clips, with about 0.49 hours of negative
video across four collections. Longer negative exposure and a new independent
test source remain necessary.

The [multi-person browser regression](caucafall-multiperson-regression.md)
now preserves the one-pose fall rule for the primary observation while tracking
additional people separately. On the already examined CAUCAFall clips, it
matched 20/50 staged falls versus 17/50 before, but alerted on 1/50 activity
clips versus 0/50 before. Side-by-side video smoke tests exercise both fall
positions and a sitting negative. This is a development result, not a fresh
multi-person validation; the next detector gate needs labeled footage with
more than one person and longer non-fall exposure.

A first-look [real multi-person source check](mpfdd-first-look-result.md) now
shows why that gate matters. On the 28 accessible MPFDD clips, both the
original and fused alert paths detected only 2/22 fall clips and alerted on
0/6 daily-activity clips. The additional tracks did not add a successful
fall clip; the activity footage lasted just 63 seconds. Improve person
observation and track continuity before changing alert thresholds or making
multi-person performance claims.

The follow-up [chair and shared-room accuracy check](chair-and-shared-room-accuracy-check.md)
added repeatable people-free chair regressions (zero poses across 124 static
and panned frames with the live model). On the already examined MPFDD clips,
neither a larger pose model nor a person-detector-plus-cropped-pose experiment
improved the 2/22 fall-clip result. Keep the current live detector while
collecting person-level labels and longer room-specific negative footage.

The [MPFDD scorer validation check](mpfdd-scorer-validation.md) now rejects
partial sampled timelines before counting full clip duration as negative
exposure, along with invalid coverage and inconsistent track alerts. Both
archived 28-clip paths passed; per-clip results and the 2/22 fall result are
unchanged. This improves benchmark integrity, not detector accuracy.

## Delivery sequence

| Gate | Concrete deliverable | Rough time after the prior gate |
| --- | --- | --- |
| 1. Independent detector check | Two earlier candidates received independent checks; the third multi-source experiment was development-only and failed its held-out-source stress test. Use the examined cases for development and find another untouched source with longer negative footage for the next frozen test. | More detector work is required; estimate several engineering days for another candidate, with data acquisition able to extend this. |
| 2. Always-on supervised prototype | Run the selected detector on one approved camera host without a browser tab. Verify startup, shutdown, reconnection, outage/restart recovery, playable evidence, and actual recipient receipt/acknowledgment. | About 1–2 engineering weeks if the host, camera, and notification route are available. |
| 3. Shadow pilot | Obtain written consent, fixed camera placement, named primary/backup reviewers, data and retention decisions, then measure scheduled versus analyzed hours and every candidate while existing care procedures remain primary. | Setup and observation take weeks; timing depends on participant/site access and actual monitored hours. |
| 4. Assisted or unattended use | Require the pilot's predeclared event recall, false-alert workload, delivery, evidence, uptime, and privacy gates. Review all failures and intended-use obligations. | No credible calendar date until field evidence passes those gates. |

These are planning estimates, not performance promises. For example, the pilot
plan's illustrative 300 analyzed camera-hours would take 150 days at one
two-hour session per day before accounting for missed sessions; extending hours
or adding consented cameras changes that schedule. Real accidental falls are
rare, so elapsed time alone does not establish fall sensitivity.

## Portfolio milestone

A resume-ready engineering case study does not require claiming an unattended
product. It should show a working demo, the architecture, a reproducible
cross-source comparison, a failure analysis, and a clear description of what
was and was not validated. Gate 1's result is recorded, so package those
artifacts with a short demo walkthrough and a concise resume bullet now. Do not present a
staged-clip score as field or medical accuracy.

Offline detector work can continue now. Gate 2 will need a chosen always-on
host and camera. Gate 3 will additionally need a consenting pilot site and
named reviewers; those decisions can be made after the independent benchmark.
