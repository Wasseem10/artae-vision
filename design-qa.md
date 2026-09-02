# Design QA — Hero evidence ribbon

- Source visual truth: `C:\Users\wasse\.codex\generated_images\01a0416b-0da5-7e53-b3e5-893f92234733\exec-5d18d427-feeb-4a8f-80e0-84ea8bf84ff2.png`
- Implementation screenshot: `C:\Users\wasse\OneDrive\Documents\ChatGPT\Project2\.codex-design-refs\hero-evidence-implementation-final.png`
- Full-view comparison: `C:\Users\wasse\OneDrive\Documents\ChatGPT\Project2\.codex-design-refs\hero-evidence-comparison-final.png`
- Focused comparison: `C:\Users\wasse\OneDrive\Documents\ChatGPT\Project2\.codex-design-refs\hero-evidence-focused-comparison.png`
- Viewport: 1672 × 941 CSS pixels, desktop, device scale factor 1.
- Pixel dimensions: source 1672 × 941; implementation 1672 × 941. No density normalization required.
- State: marketing home page, hero at initial load.

## Full-view comparison evidence

The implementation preserves the existing Artae header, announcement bar, centered headline, copy, calls to action, and three-step strip. The selected option's evidence ribbon appears beneath that strip without introducing a large image or changing the page's established visual language. The slightly more compact title and call-to-action scale is intentional because the user explicitly asked to keep the current style and add to it rather than redesign it.

## Focused comparison evidence

The focused comparison confirms the same four-column hierarchy as the source: event icon, orange outcome indicator, primary label, and supporting status. The source uses illustrative object drawings; the implementation deliberately uses the project's existing outline icon library so the addition matches the current product UI and remains sharp at responsive sizes.

## Required fidelity surfaces

- Fonts and typography: Existing Geist-based page typography, weights, line height, and hierarchy are preserved. Evidence labels remain legible and do not wrap at desktop width.
- Spacing and layout rhythm: Ribbon aligns to the centered hero, uses the selected four-column rhythm, and retains clear separation from the three-step strip. No horizontal overflow at 1672 px or 390 px.
- Colors and visual tokens: Existing cool white/gray surface, black copy, light borders, and orange action accent are reused consistently.
- Image quality and asset fidelity: No raster hero image or placeholder was introduced. Icons come from the installed React Icons library and render cleanly at desktop and mobile sizes.
- Copy and content: Outcomes communicate concrete Artae jobs: PPE verification, dock arrival notification, fall alert, and vehicle action.

## Comparison history

1. Initial pass: the evidence outcomes were too small and arranged like settings rows (P2); status icons overlapped supporting copy (P2).
2. Fixes: changed each outcome to a centered icon-first composition, increased icon and label scale, widened the evidence ribbon, and positioned status icons independently.
3. Post-fix evidence: `hero-evidence-implementation-final.png` and `hero-evidence-focused-comparison.png` show distinct, readable outcomes with no overlap or overflow.

## Interaction and responsive checks

- Primary CTA resolves to `/login`.
- Demo CTA scrolls to `#overview`.
- Mobile check at 390 × 844: two-column evidence layout, 339 px ribbon width, 375 px document width, and no horizontal overflow.
- Browser console errors: none.
- Production build: passed.

## Findings

No actionable P0, P1, or P2 differences remain.

## Follow-up polish

- P3: Custom editorial illustrations could move even closer to the concept image, but they would be a broader asset-direction change than the requested additive update.

final result: passed
