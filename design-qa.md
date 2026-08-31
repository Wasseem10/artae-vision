# Camera Jobs Section — Design QA

- Source visual truth: `C:\Users\wasse\AppData\Local\Temp\codex-clipboard-7f3ca1b9-7578-4a7c-8c34-ebd06d7f2149.png`
- Desktop implementation: `C:\Users\wasse\OneDrive\Documents\ChatGPT\Project2\artifacts-camera-jobs-desktop.png`
- Mobile implementation: `C:\Users\wasse\OneDrive\Documents\ChatGPT\Project2\artifacts-camera-jobs-mobile.png`
- Combined comparison: `C:\Users\wasse\OneDrive\Documents\ChatGPT\Project2\camera-jobs-design-comparison.png`
- Desktop viewport: 1265 px wide, browser density 1; captured section is 1265 × 1590 px.
- Mobile viewport: 390 × 844 CSS px, browser density 1; captured section content is 375 × 2762 px after page gutters.
- Source pixels: 1896 × 1177 px. The source is a before-state used to preserve the established page language while correcting the repeated-card hierarchy requested by the user.
- State: landing page `#features`, light theme, default interaction state.

## Full-view comparison evidence

The source and desktop implementation were combined into `camera-jobs-design-comparison.png` and reviewed together. The update preserves the light technical grid, square borders, Geist typography, restrained green/yellow states, and numbered-section framing. It replaces six nearly identical abstract capability cards with a three-step product explanation, one detailed factory-flow example, and a readable directory of six operational uses.

## Focused region evidence

The whole section was captured at desktop and mobile sizes, so the important details remain readable without a second crop: product inputs, camera jobs, connected actions, camera overlays, WhatsApp-via-webhook copy, saved evidence, and the six-use-case directory.

## Required fidelity surfaces

- Fonts and typography: Geist and the existing weight hierarchy are preserved. The product statement, featured factory example, and use-case directory create three clear reading levels. No clipping or unintended truncation was observed.
- Spacing and layout rhythm: the desktop section moves from a three-step feature flow to one visual example and then a continuous use-case directory; mobile stacks each part with consistent gutters and readable action rows.
- Colors and visual tokens: existing paper, gray, border, green detection, and yellow warning tokens remain consistent with the rest of the landing page.
- Image quality and asset fidelity: the existing Artae-owned factory camera asset is used at a natural crop. Live-camera labels, the monitored queue, evidence states, and alert output clearly show the product in action.
- Copy and content: the section now explains what footage can be connected, what jobs can be described, what actions Artae can perform, and what teams use it for. WhatsApp is accurately described as a webhook-delivered action rather than a native integration claim.

## Comparison history

### Initial finding

- [P1] Six repeated capability boxes made every feature look identical and did not quickly explain that a camera can be assigned a job.
- [P1] The section did not summarize the platform's core features or explain the breadth of operational use cases.

### Fixes made

- Added a three-step explanation covering live/uploaded video, plain-language jobs, and alerts/actions.
- Made factory bottleneck detection the dominant visual example with a complete watch-and-do workflow.
- Added a six-item use-case directory covering workplace safety, factory flow, process compliance, loading docks, security/vehicle access, and recorded-footage search.
- Preserved responsive behavior without returning to a grid of identical boxes.

### Post-fix evidence

- Desktop and mobile captures show clear hierarchy, readable features, a non-repetitive composition, product-in-action imagery, and a complete use-case summary.
- TypeScript typecheck passed.
- Browser console showed no errors. Two Next.js LCP warnings occurred only because QA opened the deep `#features` anchor, making below-the-fold images temporarily count as above-the-fold; this does not affect normal page entry.
- No actionable P0, P1, or P2 issues remain.

## Primary interactions tested

- Anchor navigation to `#features`.
- Desktop rendering.
- Mobile responsive stacking at 390 × 844 CSS px.
- Browser console error check.

## Follow-up polish

- [P3] A future real factory-line video could replace the current warehouse still when original production footage is available.

final result: passed
