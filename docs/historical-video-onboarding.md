# Historical video and camera onboarding

## Distributed recording flow

1. The camera worker finalizes an MP4 segment and JSON manifest atomically.
2. When archive upload is enabled, the recorder hard-links or copies the segment into
   a spool before local retention can remove it.
3. A single background uploader reports immutable metadata under the camera's tenant
   and then uploads the video with its enrolled device credential.
4. Failed transfers leave both spool files in place. Worker restart scans the spool and
   safely retries; segment IDs and source keys make reporting idempotent.
5. The API stores size and SHA-256, marks the segment ready, and exposes only a
   short-lived tenant-bound signed playback URL. Local development uses a protected
   filesystem root; hosted deployments can use a private S3-compatible bucket.

Archive upload is opt-in because central copies change bandwidth, storage cost,
privacy, and retention obligations. Edge-only segments remain visible as catalog
metadata without pretending their bytes are centrally available.

## Retention and legal hold

Each new catalog record receives an expiration time from the server policy. Retention
is an explicit administrator operation and deletes at most 500 eligible objects per
request. It never deletes a segment under legal hold and refuses local paths or S3
object URIs outside the configured storage boundary. The catalog retains an expired
tombstone after content deletion for auditability.

## ONVIF discovery flow

An administrator selects an active edge station and requests a short scan. The job is
leased only to that exact enrolled device. The device broadcasts a standards-based
`NetworkVideoTransmitter` probe, collects responses for at most 15 seconds, filters
service addresses to HTTP(S), caps results, and reports them to the tenant history.

## Credentialed ONVIF onboarding

Each discovered endpoint has an explicit administrator action. The browser submits a
camera name and credentials once; the API encrypts them immediately and never returns
them in operator responses. Only the exact enrolled edge station that performed the
scan can lease the onboarding job.

The edge station uses ONVIF `GetCapabilities`, `GetProfiles`, and `GetStreamUri` with
HTTP Digest and WS-Security UsernameToken authentication. It prefers the largest H.264
profile, falls back to other returned video profiles, strips user information from all
reported URIs, and opens the selected RTSP stream. A camera is created only after a
real frame is read and encoded as a bounded JPEG preview. The clean RTSP URI and
encrypted credentials are stored separately, and the camera remains pinned to the
edge station that can reach its LAN.

For HTTPS ONVIF endpoints, certificate verification defaults on. Disabling it is an
explicit per-camera onboarding choice for devices with private self-signed certificates.

## S3-compatible recording storage

Set `VIDEO_INTEL_API_RECORDING_STORAGE_BACKEND=s3` and configure a private bucket.
The endpoint is optional for AWS S3 and used by providers such as MinIO or R2 that
expose a custom S3 endpoint. Static access/secret keys are optional when the API receives
an IAM workload role. Playback first validates the tenant-bound API signature and then
redirects to a short-lived S3 presigned GET URL. Legal holds remain database-enforced;
retention deletes the exact bucket key before expiring the catalog record.
