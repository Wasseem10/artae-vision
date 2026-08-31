# Simple operator experience audit

## Scope

The Automations screen, live-feed control, and the transition into Advanced Tools at the local operator console.

## User goal

Start or stop the computer camera, create a plain-language automation, review its action, and reach one maintenance tool without crossing a long technical dashboard.

## Steps

1. **Before — blocked by technical diagnostics:** The camera-commissioning panel rendered above the operator workspace and repeated down the page. The first useful action was not visible. General health: failing.
2. **Automations — focused live workflow:** The diagnostic stack is removed. Start/Stop live feed is available in the sticky header and the camera card. Rule, upload, activity, delivery, and incident creation remain visible. General health: good.
3. **Advanced Tools — one tool at a time:** The long all-panels dashboard is replaced by a compact tool picker. Rules show the active automation first and fold seven paused/older rules behind one control. General health: good.

## Highest-impact fixes

- Removed the duplicated camera commissioning content from the operator experience.
- Added explicit **Start live feed** and **Stop live feed** controls.
- Replaced the endless Advanced Tools page with a focused tool switcher.
- Kept common tools visible and moved technical maintenance into a separate System home.
- Collapsed inactive rule history without deleting it.

## Accessibility notes

- Start/stop state is communicated by text as well as color.
- The advanced-tool selector and older-rules disclosure have programmatic labels/state.
- Keyboard focus and screen-reader announcements still require a dedicated assistive-technology pass; screenshots alone cannot establish WCAG conformance.

## Evidence

- `01-before.png`
- `02-simplified-automations.png`
- `03-focused-advanced-tools.png`
