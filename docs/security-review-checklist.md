# Security review checklist

Record an owner, evidence link, and approval date for every item before hosted launch.

- [ ] OIDC issuer, audience, asymmetric algorithms, membership provisioning, logout,
      session expiry, and administrator recovery were tested.
- [ ] Tenant isolation tests cover every new table, search path, clip, WebSocket, map,
      edge device, connector, and background-worker endpoint.
- [ ] Development dashboard and shared edge keys are disabled.
- [ ] Database, alert, media, device, provider, webhook, and signing secrets are unique,
      centrally stored, rotated, scoped, and absent from logs/browser bundles.
- [ ] Evidence URLs expire and remain tenant-bound; object storage is private.
- [ ] Connectors use allowlisted actions, minimum scopes, rate limits, idempotency,
      approvals for consequential actions, retries, and dead-letter review.
- [ ] Internet egress and inbound ports are allowlisted; internal metrics are private.
- [ ] Dependency, container, license, secret, and static-analysis scans pass.
- [ ] Signed edge configuration and update artifacts are verified on the station;
      rollback and compromised-station revocation were exercised.
- [ ] Backups are encrypted and a full restore drill passed.
- [ ] Retention, deletion, export, legal hold, camera notice, employee monitoring,
      biometric/re-identification, and data residency policies were approved.
- [ ] Replay accuracy, false-alert rate, cost ceilings, provider outages, load limits,
      and fail-safe behavior meet the documented launch criteria.
- [ ] Incident response owners and customer notification procedures are on call.
