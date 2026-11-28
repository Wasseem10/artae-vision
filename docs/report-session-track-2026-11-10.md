# Preserve session tracks in incident exports

November 10, 2026. Incident reports now retain the event's stored
`personTrackId` in their structured snapshot and display it as **Session track**
in the downloaded HTML. This distinguishes events with different track labels
even when they use the same timestamp and evidence segment.

## Before and after

At `a3a5d16`, an event carrying `personTrackId: 4` loses that field in
`buildIncidentReport`; the HTML has no explicit track field. Some event titles
include a number, but titles are not a structured source of tracking metadata.

The report now copies a positive safe-integer track label directly from the
event. Missing, zero, negative, fractional, non-finite and unsafe-integer values
become `null`, rendered as **Unavailable**. It never derives a track from the
title or another event. Device-only suggestions keep their recorded track label
and existing device-only provenance.

The HTML places a limitation beside the track field, and the structured report
includes the same limitation: labels are local to the session, may switch between
people and do not identify a person. Exporting a label does not validate the
upstream association or correct any defaults already recorded in an event.

## Verification

- Three new unit cases cover distinct tracks at the same timestamp with shared
  evidence, missing/invalid labels despite a numbered title, and device-only
  suggestions. All **99 web unit tests**, TypeScript, ESLint and the production
  build pass locally.
- A synthetic export was compared against the baseline report builder: the old
  snapshot omitted track 4; the updated snapshot and HTML preserve it.
- Chromium 153.0.8010.12 rendered the exported HTML at 1100 px and 390 px with
  no horizontal overflow, page errors or network requests. Desktop/mobile
  provenance screenshots were inspected; print-media output was also captured.
  A legacy event rendered **Unavailable**.
- Local fixtures, report JSON/HTML and screenshots are in ignored
  `artifacts/report-track/`; the local visual helper is
  `artifacts/check-report-track.cjs`. The committed unit cases are in
  `apps/web/src/lib/incident-report.test.ts` and run with `pnpm test` from
  `apps/web`.

This change uses synthetic report metadata. It adds no inference run, accuracy
measurement, identity guarantee or production-delivery claim. The detector,
landing page and `/live` workflow are unchanged. Independent person labels and
untouched multi-person footage remain prerequisites for another detector gate.
