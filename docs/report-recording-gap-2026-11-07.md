# Incident reports retain nearby review footage

November 7, 2026.

## Reproduced mismatch

The review player uses `clipForEvent` to select containing footage, or the
nearest playable segment within 250 ms of an event. Small recorder-restart gaps
can therefore remain reviewable. The exported incident report previously used
only containing intervals and explicitly requested recording IDs. A guest event
in one of these gaps could play footage in the dialog while its report said
there was no matching recording metadata.

A synthetic regression at the preceding revision
`035a2d968de3e7670764baa76960d2ffd01686ab` reproduces the mismatch. The event is at
10.00 s, the first segment ends at 9.96 s, and the second starts at 10.03 s.
The player selects the second segment; the prior report returns an empty clip
list. These timestamps are a constructed boundary case, not measured video data.

## Change

The report builder now uses the same playback selector and includes its selected
segment alongside containing and explicitly requested metadata. It records the
selected clip ID, whether its interval contains the event, and the gap in seconds.

When the selected interval is nearby, the HTML export places a clear notice
above the evidence table. In the regression, it names the segment, states the
approximately 30 ms separation, and explains that the interval does not contain
the event timestamp. The report continues to omit video bytes and playback URLs.

Larger gaps still have no fallback. Metadata without a playable blob or URL does
not become playable evidence. Exact containing intervals, including a shared
boundary, take precedence and receive no gap notice.

## Verification

- Three new unit cases cover the small gap, exact containment and boundary,
  larger gaps, and nearby metadata without playback. The first case fails on
  the preceding implementation because its clip list is empty.
- The shared-boundary case uses fractional timestamps so floating-point
  subtraction order cannot label an exactly containing endpoint as a tiny gap.
- All 96 web unit tests pass, including the existing recorder-boundary selector
  tests. TypeScript, ESLint, the production build and diff checks pass locally.
- A synthetic HTML export was rendered in Chromium `153.0.8010.12` at desktop
  and 390 px mobile widths and with print CSS. The selected segment and gap note
  appear, with no horizontal overflow, page errors or network requests. Mobile
  and print-layout screenshots were visually inspected. This checks HTML print
  styling, not printer-specific pagination.
- The generated HTML, metadata and screenshots remain in ignored local
  `artifacts/report-gap/`. The local reproduction helper is
  `artifacts/check-report-gap.cjs`; the committed regression is
  `apps/web/src/lib/incident-report.test.ts`.

## Limits and next priority

Matching recorded intervals does not prove that an event's exact frame was
captured or that a recording is decodable. The report describes the session
snapshot available at export time. The 250 ms fallback is an existing review
behavior, not a new detector tolerance or accuracy result.

Independent person/duplicate annotation and untouched multi-person footage with
longer hard negatives remain the next detector gate. This change improves the
consistency of the review record and supplies no new fall-performance evidence.
