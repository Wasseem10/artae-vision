# Bound browser setup and retain installation diagnostics

November 12, 2026. Web quality checks now limit browser dependency installation
to three minutes and retain its combined stdout/stderr in the failure artifact.
The application, landing page, monitoring workflow and detector are unchanged.

## Trigger

The [November 11 run on Ubuntu 26.04](https://github.com/Wasseem10/artae-vision/actions/runs/43034957740)
spent the remaining job budget installing browser dependencies and reached the
15-minute job timeout before the browser tests or artifact upload could run.
The [retry on Ubuntu 24.04](https://github.com/Wasseem10/artae-vision/actions/runs/43037698295)
failed with temporary DNS resolution errors for the Ubuntu package mirror.
Unit tests, types, lint and the build passed in both runs; hosted browser checks
did not start. The complete eight-script browser suite passed locally on the
same application code, as recorded in PR #17.

## Change

- Keep the existing dependency-install command, including system dependencies.
- Give installation its own three-minute step deadline, leaving room within
  the unchanged 15-minute job budget for failure diagnostics. Successful setup
  continues to the unchanged eight-minute browser verification step.
- Use explicit Bash with its Actions `-e -o pipefail` behavior. Pipe stdout and
  stderr through `tee` into `/tmp/artae-browser-install.log`; a failed installer
  remains a failed step even when log writing succeeds.
- Include that log in `web-failure-diagnostics`, with the existing seven-day
  retention and `failure()` condition. No tests are skipped or made optional.

## Verification and limits

The workflow parses successfully. A local Git Bash check runs the exact install
pipeline with a stub installer returning 0 and 23. Both exit codes are preserved,
and both stdout and stderr appear in the logs. The local check also confirms
the setup, browser and job deadlines, failure-artifact path, and absence of
`continue-on-error`. Results are in ignored `artifacts/ci-install-check/`;
the helper is `artifacts/check-ci-install.py`.

This checks pipeline behavior, not the hosted three-minute scheduler deadline.
The new hosted run and its outcome are linked in PR #17. No visual checks are
needed for this workflow-only change; existing application checks still run.

The deadline does not repair DNS or guarantee artifact upload if the entire
runner or job is cancelled. A dependency outage still correctly blocks hosted
verification. A legitimate slow installation may require rerunning later;
do not bypass dependencies or count unexecuted browser checks as passing.
No new inference, labels or detector accuracy results are produced.
