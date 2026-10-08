# Product polish — 2026-10-08

This changes the presentation and evidence workflow on one canonical `/live`
monitor. The landing page keeps its light paper, orange announcement band,
black actions, and typography. The monitor keeps its dark mission-control theme
and configuration/video/event layout.

## Changes

- Removed the simulated PPE/dock/vehicle agents, fake model picker, inert prompt
  chips and email form, mismatched Pricing/Enterprise links, and footer links
  that all returned to the top.
- Replaced those sections with the supported workflow and a recorded staged
  demonstration. Mobile visitors can reach the sample from the first screen.
- Added public engineering and data-handling pages with real source links,
  selected per-source results, storage behavior, and validation limits.
- Opened event footage and human review in one native dialog, with Escape and
  keyboard focus return. Empty recording players are hidden; recording progress
  and evidence availability are described explicitly.
- Kept unsaved review notes while closing and reopening the dialog in the same
  page, with an explicit reminder to save an outcome for durable history.
- Matched playable evidence across recorder timestamp gaps up to 250 ms, while
  refusing unrelated footage or metadata without a playable copy.
- Required explicit guest consent for optional fall-frame analysis from uploads
  and webcams. The staged sample's optional cloud analysis is disclosed.
- Hid the empty guest saved-agent section, kept old demo/app entry points going
  to the same monitor, clarified unavailable SMS, and improved signup semantics.
- Added a web CI gate and updated README evidence screenshots.

## Verification

- TypeScript checking, ESLint, 74 Vitest assertions in 18 files, and optimized
  Next.js build pass locally.
- Browser smoke test: public navigation and mobile first-screen action; legacy
  redirects; real staged fall → playable evidence → review → reload → report;
  Escape/focus return; sitting negative control; guest uploaded staged fall with
  no cloud-analysis request; delayed mocked Nova/Strands context preserves the
  already completed local review. All API calls are blocked or mocked.
- Empty-chair regression: two scenes, each static and digitally panned, 31
  frames per case; no poses on any of the four cases. This is limited regression
  evidence, not a general person-detector accuracy claim.
- Manual browser checks at 1440×900 and 390×844: landing, monitor, evidence dialog,
  mobile navigation, and engineering page. Screenshots use licensed staged media.

## Limits and next work

No model, fall threshold, or tracking algorithm is promoted in this change.
The documented MPFDD result remains 2/22 staged fall clips detected and 0/6
activity clips alerted; the activity footage is only 63 seconds. This remains
an experimental prototype with substantial missed-fall risk.

Account authentication, cross-device production saves, real SMS delivery,
webcam permissions, and screen-reader behavior were not exercised against
production services. Browser tests validate the guest path and mocked cloud
responses. The data page documents that account deletion/retention controls
are not yet exposed.

Next accuracy work: label visible people and event timing in failed shared-frame
clips, separate pose-observation failure from tracking/rule failure, and require
untouched clips plus hard negatives before changing the live detector. The
open observation-diagnostics work is tracked separately in PR #16.
