# Identity and tenant security boundary

## Authentication modes

`development` mode accepts the configured dashboard key and maps it to one seeded
local organization. The settings validator rejects this mode in production.

`oidc` mode treats FastAPI as a resource server. Tokens must be signed by a key from
the configured JWKS endpoint and must match the exact issuer and audience. The API
requires `exp`, `iat`, and `sub`, allows only configured asymmetric algorithms, and
extracts a provisioned organization UUID. Unknown, disabled, or non-member
organizations receive 403 responses.

The browser sign-in client should use Authorization Code with PKCE or a
backend-for-frontend session. The API deliberately does not implement passwords,
the OAuth implicit grant, or a home-grown authorization server. Current OAuth
security best practice is documented in [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html),
and PKCE is standardized in [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636.html).

## Authorization roles

| Role | Read tenant data | Operate cameras/jobs/alerts | Manage secrets/devices/audit |
|---|---:|---:|---:|
| viewer | yes | no | no |
| operator | yes | yes | no |
| admin | yes | yes | yes |
| owner | yes | yes | yes |

After the first trusted provisioning, database membership is authoritative. A new
token cannot silently promote an existing member by changing its role claim.

## Tenant ownership

Cameras, alert channels, and evidence-search jobs store `organization_id` directly.
Zones, rules, compilations, events, evidence, incidents, and deliveries inherit
ownership through their camera or parent record. Operator queries join through that
chain and return 404 for foreign resources to avoid disclosing their existence.

WebSocket connections are registered under one authenticated organization and
broadcasts carry an explicit organization routing key. Evidence playback uses a
short-lived HMAC URL bound to the evidence ID, organization ID, and expiry; changing
any value invalidates the signature. Internal evidence workers may use the separate
agent credential and never receive a dashboard bearer token.

## Edge-device authentication

Camera workers use an organization-owned device token with the form
`vid1.<device UUID>.<random secret>`. The complete token is shown only at enrollment
or rotation. PostgreSQL stores its SHA-256 digest and a short display fingerprint,
which is appropriate because the generated secret has at least 256 bits of entropy.
Authentication uses a constant-time digest comparison. Revocation immediately
releases that device's camera leases; rotation releases leases and invalidates the
old token. Production settings reject the shared development edge key.

Every claim is restricted to the device organization and serialized through a
device-row lock before its active lease count is checked. Both the host setting and
the server-owned capacity bound concurrent camera execution.

## Operator audit history

Authenticated POST, PUT, PATCH, and DELETE requests create tenant-scoped audit
records with actor, role, action, status, request ID, resource ID, and time. Request
bodies and credential values are intentionally never retained. Audit-log reads
require an owner or administrator role.

## Remaining production work

- Select and configure the hosted OIDC provider and browser login/BFF flow.
- Put signing and encryption keys in a managed secret service and define rotation.
- Move audit records to tamper-evident archival storage with a defined retention policy.
- Add network egress policy and DNS/IP validation for customer webhook URLs.
- Add PostgreSQL row-level security as defense in depth after the application-level
  tenant contract stabilizes.
