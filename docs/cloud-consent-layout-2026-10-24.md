# Readable webcam and upload consent

October 24, 2026. Scoped follow-up to the layout defect observed during the
[source-interruption checks](video-source-reliability-2026-10-23.md).
Latest main remains `174346215`; PRs #16–21 remain open. PR #17's previous
source-interruption change passed its hosted web and preview checks. This
change continues that clean worktree without touching the original checkout.

## Defect and correction

The optional AWS review checkbox inherited the application's generic input
width and height. At a 1440 px viewport, the checkbox consumed the entire
305 px label width, pushing 9 px consent text beyond the sidebar. The page
itself had no horizontal scrollbar, so a page-overflow check alone missed it.

The control now has explicit 18 × 18 px dimensions and a flexible text span.
Its explanation uses 13 px normal-weight text, wraps inside the label, and
inherits the panel's text color. A visible focus outline supports keyboard use.
The whole label remains clickable. No consent wording, default, event handler,
cloud-upload decision, or disabled-state logic changed.

| Desktop measurement | Before | After |
| --- | ---: | ---: |
| Checkbox width | 305 px | 18 px |
| Consent font size | 9 px | 13 px |
| Rendered text width, approximately | 39 px | 274 px |
| Text extends beyond label boundary | Yes | No |

## Verification

- Optimized production build (including TypeScript), changed-component ESLint,
  and diff checks pass.
- Browser checks on Chrome 155.0.8059.85 cover webcam and uploaded-video source
  selections at **1440, 390, and 320 px**: six combinations. Each verifies
  checkbox dimensions, text bounds, no horizontal page overflow, and zero
  uncaught browser errors.
- Each combination starts unchecked, toggles with keyboard Space in both
  directions, and enables via clicking its explanation. Switching to sample
  video still shows the existing sample disclosure instead of this control.
- Before/after screenshots were captured; desktop and narrow mobile layouts
  were visually inspected. Local QA script, measurements, and screenshots are
  retained under ignored `artifacts/check-cloud-consent-layout.cjs` and
  `artifacts/cloud-consent-layout/`.
- No camera was started, no user footage was loaded, and external/API requests
  were blocked. This checks presentation and interaction, not AWS delivery.

The landing page and single `/live` workflow are preserved. This is a UI fix,
not an accuracy improvement. The detector's unresolved person/duplicate labels
and independent multi-person validation remain tracked in
[PR #19](https://github.com/Wasseem10/artae-vision/pull/19). Those gates remain the
next accuracy priority; a fresh hosted demo check is still needed before sharing
the final recruiter link.
