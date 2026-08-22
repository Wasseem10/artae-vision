# Multi-camera operations and investigation

Phase 21 adds the first site-wide operating view. It does not claim biometric
identity. An `entity_key` is an anonymous correlation handle produced by a tracker
or approved re-identification component; customers must decide what identification
technology and retention policy are lawful for their deployment.

## Stored objects

- A **site** belongs to one organization.
- A **site area** is a normalized rectangle used by the simple dashboard map.
- A **camera placement** puts one camera at an `(x, y)` position and may assign it
  to an area.
- An **entity sighting** records an anonymous key, label, normalized box,
  confidence, attributes, camera, area, event, and time.

Tracked-entity observations emitted through scene memory automatically create
idempotent sightings. Edge workers may also send sightings directly through the
authenticated `/agent/entity-sightings` API. Repeated camera/entity/timestamp
observations do not create duplicate journey points.

## Investigation search

`POST /api/v1/investigations/search` returns one chronological result contract for:

- deterministic and semantic events, including event details and clip references;
- learned scene state, descriptions, OCR-like attributes, and relationships; and
- entity sightings, attributes, camera names, and area names.

The current implementation performs a bounded tenant-filtered candidate scan and
case-insensitive token matching. This is useful and deterministic for the local
product, but production scale should move indexing to PostgreSQL full-text search
and a dedicated vector/clip index while preserving the API contract.

## Dashboard workflow

The guided dashboard includes **Map the site and investigate**. A safe one-click
preview creates a local three-area layout and places the selected camera on it.
This is intentionally reversible and makes no external request. Real deployments
can create several sites, areas, and camera placements through the same APIs.

## Important boundaries

- Camera-only tracking cannot guarantee a person's real-world identity across
  severe occlusion, clothing changes, or disconnected views.
- Site areas are operational layout regions, not precise survey geometry.
- Historical search quality depends on the observations and evidence that were
  actually stored.
- Biometric face recognition is neither implemented nor implied.
- Cross-camera accuracy must be measured on representative replay data before a
  safety or enforcement workflow is deployed.

## Verification

`tests/api/test_multicamera_operations.py` proves tenant-owned site maps,
camera placements, idempotent sightings, ordered two-camera journeys, safe demo
setup, and unified event/scene/entity investigation results.
