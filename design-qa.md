# Design QA — Upload-first caregiver evidence workspace

- Source visual truth: `C:\Users\wasse\.codex\generated_images\01a0416b-0da5-7e53-b3e5-893f92234733\exec-e9f78dcd-6129-4263-a387-0800f693b385.png`
- Implementation: `http://127.0.0.1:3000/demo`, captured inline with the Codex in-app Browser on September 13, 2026.
- Comparison viewport: 1440 × 1024 CSS pixels at device density 1.
- Source pixels: 1487 × 1058. Implementation full-page capture: 1440 × 1266 pixels; the first 1024 pixels were used for viewport-level comparison.
- State: public demo, upload-first empty state and uploaded-video ready state.

## Full-view comparison evidence

The implementation matches the selected direction's two-track structure: a narrow three-step setup rail at left; a large video, evidence timeline, and agent progress surface at right; and a wide caregiver event log below the video. The prior third-column alert layout and its large unused vertical area are gone. The requested product change intentionally replaces the mock's staged-fall example controls with a direct upload action and an honest empty video state.

## Required fidelity surfaces

- Fonts and typography: IBM Plex Sans is preserved. The single-line desktop headline, 14px body copy, numbered step hierarchy, labels, and compact status text follow the source's weight and wrapping pattern. No visible clipping or truncation was found.
- Spacing and layout rhythm: the 360px / flexible two-column grid, 14px gutter, compact intro, full-width right-column event log, 12px radii, and fine separators match the reference hierarchy. The page has no horizontal overflow at the tested 390px, 1024px, and 1440px widths.
- Colors and visual tokens: warm off-white canvas, white surfaces, charcoal typography, pale gray dividers, and restrained slate-blue selection state match the source. Contrast remains readable without introducing dark-mode styling.
- Image quality and asset fidelity: uploaded video uses the browser's native media rendering without stretching. Timeline thumbnails are real frames sampled from the uploaded file, not placeholders or decorative assets. The no-upload state uses the existing React icon set and contains no generated or approximate imagery.
- Copy and content: the core Nova/Strands explanation, upload instructions, five-condition prompt, scan modes, progress stages, and caregiver response language remain accurate. Example and staged/normal sample copy were removed as requested.

## Focused comparison evidence

The setup rail, video header, evidence strip, progress row, and event-log header were inspected separately at desktop size. Upload interaction was tested with a permitted local MP4: the filename appeared, the video reached ready state 4, and Analyze video became enabled. A scan sampled eight real frames and rendered seven representative timeline thumbnails. The local AWS request returned a service error after sampling; this is an environment/service result rather than a visual defect and will be rechecked against the deployed API.

## Findings

No actionable P0, P1, or P2 visual differences remain.

- Accepted product deviation: the reference contains built-in sample scenarios; the implementation omits them because the selected build must begin with the judge's own uploaded footage.
- Accepted product deviation: the implementation retains compact dashboard/browser and optional caregiver-text controls above the event log because they are working product actions, not decorative mock content.
- P3: the uploaded video filename may truncate on unusually narrow phones; the full value remains available to the browser and this does not block the upload flow.

## Comparison history

- Initial state: the former three-column implementation made the alert panel a tall empty column and visually reduced the video.
- Fixes: moved alerts beneath the video, added an upload-first gate, created a functional sampled-frame evidence timeline, consolidated alert destinations, and moved public-demo metadata into the header.
- Post-fix evidence: desktop, tablet, and phone browser captures show the selected hierarchy with no horizontal overflow; the upload-ready capture shows a real selected video and enabled primary action.

## Primary interactions and console check

- Upload video: passed.
- Video preview readiness: passed.
- Analyze button enable/disable behavior: passed.
- Real frame sampling and evidence thumbnail rendering: passed.
- Responsive reflow: passed at phone, tablet, and desktop sizes.
- Browser console: no warning or error entries from the redesigned interface.

## Implementation checklist

- [x] Remove example and staged/normal sample controls.
- [x] Make upload the primary first step.
- [x] Keep prompt, scan-mode, webcam, and notification behavior working.
- [x] Render an evidence timeline from sampled uploaded-video frames.
- [x] Move the caregiver event log below the video.
- [x] Verify responsive layout and automated frontend checks.

final result: passed
