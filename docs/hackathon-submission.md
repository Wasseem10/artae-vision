# Agents for Humans submission plan

## AWS setup status — September 9, 2026

- Submitted the Nova 2 Lite cross-region token quota request in `us-east-1`.
- Quota `L-C6F5908D`: applied 8,000,000 tokens/minute, verified in a freshly
  loaded AWS console page (the older open tab was stale).
- Request ID: `0baa1cd9ad5e4b90841a7b6fece6f019ujkqBOCH`; **Case Closed**.
- Actual Nova 2 Lite US-profile playground invocation succeeded with synthetic
  incident text: 151 input tokens, 332 output tokens, 3,634 ms reported latency.
  This proves account model access, not website integration or vision accuracy.
- With owner approval, created a production-project-only Vercel OIDC role with
  Nova 2 Lite inference permissions. No plan upgrade or persistent key was created.
- Production run September 9 at 13:05:39: real browser person detection, completed
  Strands/Nova coordination, saved in-app alert, and uploaded recording segments.
  Evidence requests now link actual account recording IDs as uploads complete.
- Strands is required by the [official rules](https://agentsforhumans.devpost.com/rules).
  Bedrock is our selected provider; AgentCore deployment is optional.
- See [AWS's quota request process](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-runtime.html).

The no-install `/demo` already performs browser MediaPipe inference and saves
account alerts/recordings. Account-connected Strands is now verified separately
from guest inference. Use licensed recorded fall samples, not a person falling live.

## Submission identity

- **Track:** Professional Agents
- **Working title:** Artae — the safety agent for every camera
- **Audience:** Small safety and operations teams that cannot continuously watch
  every camera feed.
- **Problem:** Important incidents are buried in hours of ordinary footage, and
  a person usually notices too late.
- **Promise demonstrated:** Connect a camera, select fall detection, run the
  agent on a licensed recorded fall sample, and receive a persistent alert with evidence.

## One-sentence pitch

Artae gives an existing camera one job, detects a safety incident locally, and
uses a Strands agent to preserve the evidence and notify the person who can help.

## What makes the agent real

The model does not merely chat about an incident. After browser pose inference reports an observation,
the Strands Incident Coordinator receives grounded event data and invokes Artae
tools:

1. `preserve_evidence` selects the useful before/after window.
2. `notify_responder` prepares a factual, prioritized notification.
3. `request_human_review` routes genuine ambiguity to a person.

The browser database, recording, in-app alert, and human-review paths execute
and surface those decisions. Phone/SMS/WhatsApp are not enabled. Each event records the framework, Bedrock model,
tool calls, token counts, completion state, and safe fallback state.

## Eligibility record

- Hackathon submission period began August 10, 2026.
- The `Wasseem10/artae-vision` repository and its root commit were created August
  22, 2026.
- Standard open-source frameworks, models, and libraries are listed in the
  repository. Any code reused from outside this project must be disclosed before
  final submission.

## Requirement checklist

- [x] Project created during the submission period
- [x] Strands Agents SDK dependency and tool-using agent
- [x] Text description and focused audience
- [x] README
- [x] GitHub-rendered architecture diagram
- [x] MIT license
- [x] Enable Amazon Bedrock credentials and run the live Strands path
- [ ] Capture a repeatable end-to-end fall-detection demonstration
- [x] Add a no-login judging path (`/demo`; AWS requires an account)
- [ ] Make the submission repository public
- [ ] Put the MIT license in the GitHub About panel
- [ ] Record and publish a maximum five-minute YouTube or Vimeo video
- [ ] Create AWS Builder ID and complete the Devpost entry
- [ ] Optional: deploy the coordinator to Amazon Bedrock AgentCore Runtime
- [ ] Optional: publish an Agents for Humans build article on builder.aws.com

## Five-minute demo script

**0:00–0:30 — The problem.** A caregiver, shop owner, or safety lead cannot watch
every feed. Artae turns passive video into one autonomous camera job.

**0:30–1:10 — Create the job.** Sign in, choose the camera, select the prebuilt
Fall Detection agent, choose in-app alert, and start it.

**1:10–2:10 — Prove the vision loop.** Show the live feed, MediaPipe pose overlay,
processed-frame counter, and a controlled staged fall. Never perform an unsafe
fall for the recording.

**2:10–3:10 — Prove agentic action.** Open the event and show the Strands badge,
model name, evidence and notification tool calls, severity, and alert status.

**3:10–4:00 — Prove persistence.** Stop the camera. Show that the event, short
clip, and alert remain. Refresh or sign in on another device and show the same
account-owned history.

**4:00–4:40 — Explain architecture.** Show the architecture diagram and explain
why on-device pose handles fast sensing while Strands handles incident coordination.

**4:40–5:00 — Impact.** Existing cameras become quiet safety assistants that ask
for attention only when something meaningful happens.

## Judging strategy

- **Technical implementation:** Show real Strands tool metrics and the full
  camera-to-action path. AgentCore is the stretch goal.
- **Design:** Remove dead controls from the demo path and make every state clear:
  connecting, loading, watching, detected, coordinated, delivered, stopped.
- **Impact:** Focus on one small operations team and one incident workflow.
- **Originality:** Combine continuous edge vision with an auditable agentic action
  layer rather than sending every video frame to an LLM.
- **Presentation:** Use one uninterrupted successful run and disclose the exact
  boundary between the working fall detector and future visual skills.

## Six-day finish plan

### September 8 — agent foundation

- Integrate Strands with grounded event input and real operational tool outcomes.
- Add the license, architecture diagram, disclosure, and compliance checklist.
- Keep the existing YOLO and alert pipeline working when Strands is disabled or
  Bedrock is unavailable.

### September 9 — prove AWS

- Configure an AWS development identity and invoke the Bedrock model once.
- Capture the first real Strands trace and verify evidence plus alert persistence.
- If credentials permit, scaffold AgentCore Runtime; do not delay the core demo
  for this optional bonus.

### September 10 — make the demo repeatable

- Record a short, safe staged-fall clip owned by the team.
- Add it as a clearly labeled demo fixture and make the Fall Detection starter
  agent the shortest path through the product.
- Run the same fixture three times and fix every intermittent failure.

### September 11 — make the work visible

- Show the Strands model, tool calls, severity, evidence status, and alert status
  inside the event detail view.
- Add a no-login judging route or documented judge account with no private data.
- Remove or label controls that are outside the submission's proven path.

### September 12 — record the story

- Record one uninterrupted demo using the script above and keep it under five
  minutes.
- Publish the video as unlisted YouTube or public Vimeo and draft the Devpost page.
- Use the architecture diagram once; spend most of the video on the working agent.

### September 13 — compliance freeze

- Make the repository public only after a final secret and asset-license scan.
- Put the MIT license in the GitHub About panel and verify every setup command on
  a clean checkout.
- Complete the submission fields and ask one unfamiliar tester to follow them.

### September 14 — submission buffer

- Fix only blocking issues, submit before 5:00 PM PDT, and save the confirmation.
- Avoid redesigns or new visual capabilities on the final day.
