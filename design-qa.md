# Design QA — Hero event illustration ribbon

- Source visual truth: `C:\Users\wasse\AppData\Local\Temp\codex-clipboard-b7e8651f-6fe4-411b-9d75-fdf4a82a21f9.png`
- Desktop implementation capture: `C:\Users\wasse\OneDrive\Documents\ChatGPT\Project2\artifacts\hero-event-ribbon-detail.png`
- Mobile implementation capture: `C:\Users\wasse\OneDrive\Documents\ChatGPT\Project2\artifacts\hero-event-ribbon-mobile-detail.png`
- Focused source/implementation comparison: `C:\Users\wasse\OneDrive\Documents\ChatGPT\Project2\artifacts\hero-event-ribbon-comparison.png`
- Desktop viewport: 1340 × 655 CSS pixels.
- Mobile viewport: 390 × 844 CSS pixels; document client and scroll widths both 375 px.
- State: marketing home page, hero evidence ribbon visible.

## Visual comparison

The source ribbon appears in the upper half of the focused comparison and the implementation appears in the lower half. Both use the same four-event sequence, centered four-column rhythm, grayscale technical illustration language, orange scanner corners, circular outcome badges, and faint edge motion lines.

The implementation deliberately increases subject detail and display size slightly because the user explicitly rejected the prior generic outline icons. Each event now reads as a distinct real operational scene: a hard-hat worker, a delivery truck, a person falling, and a rear-view vehicle.

## Required fidelity surfaces

- Typography: Existing Geist page typography and hierarchy remain unchanged; labels are centered and readable.
- Spacing: Four equal desktop columns and a two-by-two mobile grid preserve the existing hero structure.
- Color: Cool white/gray hero surface, charcoal illustrations, and the existing orange action accent match the reference.
- Asset quality: Four purpose-built raster illustrations replace generic React icon glyphs. Images retain detail at their refined 112 px desktop and 100 px mobile display sizes.
- Responsiveness: No horizontal overflow at the checked mobile breakpoint. All four subjects, scanner corners, badges, labels, and supporting text remain visible.
- Accessibility: Each illustration has descriptive alternative text; the surrounding list retains its descriptive ARIA label.

## Findings and fixes

1. P1 — Prior implementation used generic outline icons and did not match the selected visual target. Fixed with four detailed generated illustrations.
2. P2 — Initial generated truck asset contained a baked transparency checkerboard. Rejected and regenerated with a true alpha background.
3. P2 — The first render faded artwork to 42% opacity during its pulse animation, obscuring illustration detail. Raised the minimum opacity to 88% and added restrained contrast.
4. P2 — Mobile layout risked crowding after the larger assets were introduced. Verified at 390 × 844; the two-column grid has no horizontal overflow.
5. User polish — Reduced each illustration by roughly 11% while preserving legibility, badge clarity, and four-column alignment.

## Verification

- TypeScript: passed.
- Web tests: 17 passed.
- Production build: passed.
- ESLint: 0 errors; one pre-existing hook cleanup warning in `browser-webcam-preview.tsx`.

No actionable P0, P1, or P2 visual differences remain for the requested hero illustration update.

final result: passed
