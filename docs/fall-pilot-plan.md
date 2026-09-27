# Fall monitoring: supervised pilot plan

This plan is for the first **supervised shadow pilot**, not an unattended safety
service. Artae may flag a *possible fall* for a trained reviewer at a consented
camera. The site's existing observation and response process remains primary;
Artae does not diagnose injury, prevent falls, dispatch help, or promise that
every fall will be detected. No live alert becomes an emergency-response trigger
until field performance, delivery, staffing, and the intended use have been
reviewed together.

## Decisions before selecting a site

Record these in a dated pilot protocol with the site owner:

| Decision | Must be specified before live video |
| --- | --- |
| Setting and participants | Private home, assisted living, nursing home, or another setting; who is in view, including staff, roommates, and visitors. |
| Human responder | Named role, staffed hours, expected acknowledgment time, backup, and the site's existing fall-response procedure. In shadow mode, Artae alerts are reviewed for measurement and cannot replace that procedure. |
| Camera boundary | Exact rooms and fields of view, audio on/off, private areas excluded, installation/lighting plan, and how monitoring is visibly disclosed. |
| Data boundary | Who can see live video, clips, reports, and labels; whether bytes leave the site; vendors/regions; retention and deletion schedule; incident access log. |
| Edge isolation | Use one enrolled organization and credential set per edge host/outbox, with persistent local clip and SQLite paths. Do not share those paths across tenants. |
| Detector license | The installed-camera path uses Ultralytics YOLO code and weights. Decide whether its AGPL-3.0 terms fit the intended release or whether a commercial license or different detector is needed. |
| Product claim | Exact intended-use wording, what counts as a fall, what the system promises, and who may rely on an alert. Review this before marketing or care use. |

## Sequence and gates

1. **Freeze the candidate.** Pick the real camera, host, detector/rule, model
   version, threshold, evidence window, and alert path. `/live` runs a browser
   MediaPipe pose detector and requires an open active tab. The installed-camera
   YOLO/RTSP edge workspace is a different path. Its current infrastructure
   does not inherit the browser fall result: demonstrate and evaluate a
   fall-specific candidate on the chosen edge path before a continuous pilot.
   Start with the [native fall baseline procedure](native-fall-evaluation.md);
   it has no successful result yet on the current development host and does not
   by itself establish event-level accuracy.
2. **Create a held-out replay set.** Obtain permissioned clips from multiple
   people, camera placements, rooms, lighting states, mobility patterns,
   assistive devices, occlusions, and normal activities that resemble falls.
   Keep training/tuning sources separate from the locked test sources; split by
   person and site where possible. Two independent reviewers label fall onset,
   end, visibility, and ambiguous cases; adjudicate disagreements. Do not ask
   vulnerable residents to fall for test data. Preserve model/config, label,
   clip provenance, and all failures. The current five same-source staged clips
   are a regression check, not this held-out set; see
   [browser fall evaluation](fall-evaluation.md).
3. **Pass offline and operational gates.** Replay the frozen candidate with
   one-to-one event matching, negative exposure, outage/restart scenarios, and
   actual alert/evidence delivery. Pre-register thresholds with the intended
   responder's acceptable workload. Verify camera commissioning, time sync,
   access controls, audit log, retention/deletion, backup and restoration, and
   a safe visible state when the camera or analysis stops. The installed-camera
   alert-triggered evidence path now saves pending jobs in a SQLite outbox and
   retries after API outages and process restarts. Its local clip file must
   survive for the retry to work, and a camera agent sharing that outbox must
   be active to run retries. **Promotion gates remain:** run inference on an
   approved host (the current development host blocks the required native
   `torchvision` extension); place the edge outbox
   (`VIDEO_INTEL_EVIDENCE_OUTBOX_PATH`) and clip files **and** the
   API's locally stored evidence on persistent volumes with capacity/retention
   controls and monitor the pending-job backlog; test network loss, API failure,
   and process restart using a real camera and verify remote playback from an
   authorized second device. Fail the gate if any incident loses required
   evidence. Unit recovery tests do not replace
   this deployed end-to-end check.
   Incident clip upload and playback currently use the API host's local
   `evidence_directory`. Select a control-plane host with a persistent,
   backed-up volume for the pilot and verify clip playback after an API restart;
   the Vercel browser-demo API is not that storage plan. Choose durable object
   storage and a retention/deletion design before a hosted multi-site launch.
4. **Run a small, consented shadow pilot.** Start with a few supervised cameras
   and staffed hours. Log every scheduled and actually analyzed minute, every
   candidate, independent fall observation or care record, human label,
   received/acknowledged alert, evidence link, and failure. The responder
   follows the existing process independently; compare
   Artae against it without using Artae as the sole source of action. Review
   daily, then extend across day/night and ordinary activities. Pre-plan
   substantial exposure (for example, at least 300 analyzed camera-hours spread
   across rooms and weeks), not just a handful of negative clips. Report a
   confidence interval and every stratum; the exposure does not by itself prove
   sensitivity to rare real falls.
5. **Decide on a bounded assisted trial.** Only after reviewing misses, false
   alerts, delivery failures, privacy incidents, and human workload should the
   site consider allowing alerts to supplement its existing response workflow.
   Document any additional regulatory, clinical, and contractual review before
   changing how people rely on Artae. Expand one camera group at a time with
   a tested rollback to the prior process.

## Measures to publish for each frozen version

Record the denominators, confidence intervals, and slices by site, camera,
lighting, distance, visibility, person, and time of day. Exclude no failure from
the count merely because the software was unavailable. If there are no
independently observed falls, real-world recall is **unmeasured**, not 100%.

| Measure | Definition and denominator |
| --- | --- |
| Event-level recall | One-to-one matched detected falls / all adjudicated falls in scheduled monitored periods. Predefine onset window and maximum acceptable alert delay. Separately show detector-only recall on analyzed video and end-to-end recall including outages. Clip-level recall is not a substitute. |
| False alerts per monitored hour | Unmatched fall alerts / hours of video actually analyzed; also show unmatched alerts / scheduled camera-hours so downtime cannot improve the apparent rate. Give Poisson confidence bounds and total camera-hours. Duplicate alerts count unless a pre-registered grouping rule merges them. |
| Alert latency | Time from adjudicated fall onset to local candidate, reviewer-visible alert, recipient receipt, and acknowledgment. Report median, p95, and missing/never-delivered counts separately. |
| Uptime and coverage | Seconds with usable frames **and** active analysis / scheduled monitoring seconds. Show camera, edge, network, provider, and notification outages separately, plus longest gap and recovery time. |
| Receipt and acknowledgment | Alerts confirmed delivered / attempted deliveries; alerts acknowledged within the pre-set target / delivered alerts. Report p95 acknowledgment time and unacknowledged count. A local UI event alone is not proof a responder received it. |
| Evidence availability | Alerts with the correct playable pre/post-event clip and metadata / all alerts; measure from a separate reviewer account/device and after restart. Missing clips remain failures. |

## Stop and rollback rules

Pause the pilot immediately for any unconsented capture, unauthorized access,
wrong-recipient alert, or lost primary care coverage. Pause the affected camera
for repeated missed visible falls, false-alert volume beyond the pre-registered
responder capacity, an alert that appears delivered but was not received,
prolonged analysis gaps without a visible fault, or inaccessible evidence needed
for review. Investigate and document cause, scope, affected people, and fix;
rerun the relevant replay and end-to-end checks before resuming. A serious miss
is reviewed even when the aggregate threshold still passes. The shadow pilot
ends without promotion if the target metrics, staffing, or privacy controls
cannot be met.

## Consent, privacy, and claims check

Before any real-person recording, obtain the site's written approval and a
setting-specific consent/privacy review covering residents, representatives,
roommates, staff, visitors, camera placement, audio, access, retention, deletion,
breach handling, and whether clips may be used for training or evaluation. Use
the minimum footage and access needed; set deletion dates and verify deletion.
Do not publish identifiable pilot footage or reports as portfolio material
without separate permission.

Applicability depends on the deployment and claims; this plan does not classify
Artae as a medical device or determine legal compliance:

- [FDA Digital Health Policy Navigator](https://www.fda.gov/medical-devices/digital-health-center-excellence/digital-health-policy-navigator): assess each software function by intended use and patient risk. Its result is not a formal device determination. The [January 2026 general wellness guidance](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/general-wellness-policy-low-risk-devices) is not a blanket exemption for a fall alert used for safety.
- [HHS covered entities and business associates](https://www.hhs.gov/hipaa/for-professionals/covered-entities/index.html) and [business-associate guidance](https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/business-associates/index.html): HIPAA depends on who provides the service and on whose behalf identifiable health information is handled. A covered care-provider deployment may require agreements and HIPAA safeguards for Artae and cloud processors before live patient data.
- [CMS nursing-home recording guidance](https://www.cms.gov/medicare/provider-enrollment-and-certification/surveycertificationgeninfo/downloads/survey-and-cert-letter-16-33.pdf): resident/private-space recording without resident or representative written consent violates the privacy rights CMS describes. Other settings and state recording rules need their own review.
- [FTC health-products claims guidance](https://www.ftc.gov/business-guidance/resources/health-products-compliance-guidance): objective health and safety claims need adequate evidence before use in marketing. Do not describe the five-clip demo or an unvalidated pilot as reliable fall prevention or emergency coverage.
- [Ultralytics licensing](https://www.ultralytics.com/license): its YOLO code and model weights are offered under AGPL-3.0 or Enterprise terms. Review the planned commercial and source-disclosure model before distributing the installed-camera product.
- If the pilot is designed as generalizable human-subjects research or a device clinical investigation, obtain the applicable [institutional determination](https://www.hhs.gov/ohrp/education-and-outreach/online-education/human-research-protection-training/lesson-2-what-is-human-subjects-research/index.html) and [FDA study-risk assessment](https://www.fda.gov/medical-devices/investigational-device-exemption-ide/ide-approval-process) before enrollment.
