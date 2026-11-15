# Show recording gaps before an incident review decision

November 15, 2026. The incident dialog now discloses when playback uses a nearby
recording whose interval does not contain the event timestamp. Previously the
downloaded report disclosed this, but the review dialog always said playback
started before the event.

## Behavior

The existing selector still prefers containing footage and permits a nearby
segment only within 250 ms. The dialog keeps the start and duration of the
segment actually opened, rather than recomputing a selection as more recordings
arrive. A nearby segment displays **Nearby recording only**, its approximate
gap in milliseconds, and a reminder to inspect surrounding footage before
deciding. Its introductory text describes opening the nearest segment instead
of claiming pre-event playback.

Containing intervals show no gap notice. Missing footage remains unavailable;
the change does not make unrelated recordings reviewable. The report and dialog
share the same interval-distance calculation, including fractional endpoints.
This is a statement about metadata, not proof that a particular video frame was
captured or decoded at the event time.

## Verification

- The new browser check failed against the previous production build because
  the after-event segment opened with no notice.
- All **105 web unit tests**, TypeScript, ESLint and the production build pass.
  The added unit case covers gaps on either side, containment and an exact
  floating-point endpoint without a false gap.
- `node scripts/check-review-recording-gap.cjs` passes four controlled cases:
  a segment 30 ms after an event, one 40 ms before it, containing footage, and
  footage outside the allowed fallback distance.
- The first three cases decode real sample video at the requested seek, complete
  a review on a 390 px viewport, download a report with matching gap disclosure,
  and close using Escape. The missing case keeps review disabled. No page errors
  or dialog horizontal overflow were observed; desktop and mobile screenshots
  were inspected.
- The check runs against a local production server with native IndexedDB and
  synthetic session/interval metadata. Account APIs and external resources are
  blocked. These intervals are fixtures, not measured gaps in the sample video.
- The script is included in hosted Web quality checks and failure artifacts.
  Local screenshots, downloaded reports and results are under ignored
  `artifacts/review-recording-gap/`. Set `ARTAE_TEST_URL` to a local `/live` URL
  when using a port other than the default 3341.

The landing page, detector and single monitoring workflow are unchanged. No new
fall accuracy, identity labels, field reliability or production-delivery results
are claimed. Independent person labels and untouched multi-person footage remain
the next detector gate.
