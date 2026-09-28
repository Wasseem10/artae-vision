# Fall detection: prototype to supervised pilot

Status: September 28, 2026. The [pilot protocol](fall-pilot-plan.md) has the
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

## Delivery sequence

| Gate | Concrete deliverable | Rough time after the prior gate |
| --- | --- | --- |
| 1. Independent detector check | Freeze the pose-window candidate, test it on GMDCSA-24 subjects 3–4 once, publish all clip outcomes and compare it with the live rule. Promote it only if recall and activity alerts justify that choice. | In progress; days of engineering, longer if the candidate fails. |
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
was and was not validated. Once Gate 1 is recorded, package those artifacts
with a short demo walkthrough and a concise resume bullet. Do not present a
staged-clip score as field or medical accuracy.

Offline detector work can continue now. Gate 2 will need a chosen always-on
host and camera. Gate 3 will additionally need a consenting pilot site and
named reviewers; those decisions can be made after the independent benchmark.
