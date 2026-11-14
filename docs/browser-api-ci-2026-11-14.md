# Run browser-session API contracts in hosted CI

November 14, 2026. The new **Browser API quality** workflow runs the existing
browser-session API tests for pull requests that change the API, API tests,
pytest configuration or the workflow. It also runs for matching pushes to main.
This closes a gap where account-provenance behavior had local coverage but
the only hosted check was the web workflow.

## What it verifies

The focused `tests/api/test_browser_sessions.py` suite currently has 19 cases.
They exercise browser session/agent ownership, durable event creation,
recording metadata, review persistence, supported detection provenance,
legacy payloads, rejection of unsupported provenance and idempotent retries.

The job uses Python 3.11 on Ubuntu 24.04 and installs the API's existing `dev`
dependencies into a fresh runner environment. Its fixtures use temporary
SQLite databases, local FastAPI test clients and a mocked media gateway.
No production database, API keys, cloud credentials or deployment permissions
are configured. EC2 metadata lookup is disabled and workflow token permissions
are limited to reading repository contents.

Dependency installation has a five-minute limit, test execution has a
three-minute limit, and the job has a ten-minute limit. A failed install or test
fails the job. The workflow uploads JUnit results and resolved package versions
as `browser-api-test-results`, retained for seven days, on success or failure
when those files were produced and the runner can upload them.

## Verification

- Parsed the workflow and checked API path triggers, read-only permissions
  and the job deadline.
- Created a separate virtual environment under ignored `artifacts/api-ci-venv/`,
  installed `./services/api[dev]`, and confirmed imports resolve to this worktree.
  All **19 cases passed** with newly resolved dependencies on local Python
  3.12.14. The older shared environment was not modified.
- Local JUnit and dependency records are in `artifacts/browser-api-tests.xml`
  and `artifacts/browser-api-packages.json`. The first hosted Python 3.11 run
  and its outcome are linked in PR #17.

This is a CI-only change, so no product visual checks are needed. The existing
web workflow continues to cover browser behavior separately. This focused API
suite does not cover every API endpoint, real Postgres behavior, production
authentication or actual notification delivery. Dependencies still resolve from
the existing version ranges; the package inventory is a diagnostic record,
not a lockfile. No branch-protection requirement is configured by this change.
No detector, data labels, benchmark results or deployment settings change.
