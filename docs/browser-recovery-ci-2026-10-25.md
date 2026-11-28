# Enforce browser recovery checks in CI

October 25, 2026. The latest main (`174346215`), open PRs #16–21, product plan,
and current tracking evidence were checked. Reviewed person/duplicate labels
and untouched multi-person evaluation still block a detector promotion. This
follow-up closes a demo-reliability verification gap in the clean PR #17 worktree.

## Why this change

The October 24 [web job](https://github.com/Wasseem10/artae-vision/actions/runs/40113869876)
has a cancelled overall conclusion. Its recorded steps nevertheless show
successful type checking, lint, unit tests, build, and every guest-demo check;
the log reaches job cleanup. Those records do not establish a product failure
or explain the final cancellation. This change does not claim to fix its cause.

A separate concrete gap was present: the source-interruption and worker-failure
browser scripts were only exercised locally. Future changes could break those
paths without failing CI. Both scripts also selected installed Chrome directly,
whereas the workflow installs Playwright's bundled Chromium.

## What changes

- Both recovery scripts honor `ARTAE_TEST_BROWSER`, retaining Chrome as the
  local default and using bundled Chromium in CI.
- Web quality runs the existing guest workflow, then the inference-health and
  video-source-health suites. Changes to either script now trigger the workflow.
- Startup checks require a live server process and a successful HTTP response,
  with bounded HTTP attempts. Failure prints the server log before exiting.
- Start Next directly so the cleanup trap owns the server process rather than
  a package-manager wrapper. The browser step has an eight-minute limit within
  the existing fifteen-minute job limit.
- On ordinary failures, retain the server log and available recovery screenshots
  and result files for seven days. Abrupt runner loss/cancellation can still
  prevent artifact upload; artifacts are diagnostics, not proof of passing.

The model, association rules, landing page, `/live` interface, and production
configuration are unchanged. The browser tests use local staged media and a
synthetic camera, block external/API requests in the recovery suites, and do
not open a physical camera or modify production records.

## Verification

Run all three browser scripts against a local production build with:

```powershell
$env:ARTAE_TEST_URL = 'http://127.0.0.1:3333/live'
$env:ARTAE_TEST_BROWSER = 'chromium'
node scripts/check-live-fall-demo.cjs
node scripts/check-inference-health.cjs
node scripts/check-video-source-health.cjs
```

The workflow YAML parses successfully, its extracted shell block passes
`bash -n`, both changed scripts pass Node syntax checks, and diff checks pass.
The full sequence passes locally with bundled Chromium **153.0.8010.12**:
five guest workflow checks, three model recovery/control scenarios, and three
source interruption/control scenarios. The frozen source retains one existing
review entry and playable footage; both source failures recover in a new session.
Hosted Linux CI results are recorded in PR #17. No visual
design changed; recovery scripts retain their desktop/mobile screenshot and
overflow checks.

These checks exercise deterministic workflow/recovery scenarios. They do not
measure real-world uptime, actual camera-unplug reliability, or fall accuracy.
The next detector step remains adjudicated labels and independent footage;
before sharing a recruiter demo, require a successful check on its exact commit.
