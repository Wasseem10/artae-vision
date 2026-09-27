import type { BrowserClip, BrowserEvent, BrowserSession, ReviewOutcome } from "./browser-sessions";

export type IncidentReportOptions = {
  reviewerNote?: string;
  checklistText?: string;
  /** Pass the export time explicitly so the report can be reproduced later. */
  generatedAt?: string;
};

export type IncidentReportClip = {
  id: string;
  startSeconds: number;
  endSeconds: number;
  durationSeconds: number;
  startedAt: string | null;
  endedAt: string | null;
  width: number;
  height: number;
  availability: "account" | "browser" | "playback_link" | "metadata_only";
};

export type IncidentReport = {
  title: string;
  session: {
    id: string;
    name: string;
    job: BrowserSession["job"];
    startedAt: string | null;
    storage: "device" | "account_saved" | "account_unconfirmed";
  };
  event: {
    id: string;
    title: string;
    atSeconds: number | null;
    occurredAt: string | null;
    timestampSource: "event" | "session_offset" | "unavailable";
    landmarkVisibility: number | null;
    automatedSummary: string | null;
  };
  review: {
    status: "open" | "acknowledged" | "resolved";
    outcome: ReviewOutcome | null;
    reviewedAt: string | null;
    reviewerNote: string | null;
  };
  provenance: {
    detection: string;
    optionalCloudReviewStatus: string | null;
    recordedActions: string[];
  };
  evidence: {
    status: string | null;
    requestedRecordingIds: string[];
    windowStartSeconds: number | null;
    windowEndSeconds: number | null;
    clips: IncidentReportClip[];
  };
  organizationChecklist: string | null;
  generatedAt: string | null;
  limitations: string[];
};

function validIso(value: string | undefined): string | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? new Date(ms).toISOString() : null;
}

function finiteNonnegative(value: number | undefined): number | null {
  return value !== undefined && Number.isFinite(value) && value >= 0 ? value : null;
}

function offsetIso(startedAt: string | null, offsetSeconds: number | null): string | null {
  if (!startedAt || offsetSeconds === null) return null;
  const ms = Date.parse(startedAt) + offsetSeconds * 1000;
  const date = new Date(ms);
  return Number.isFinite(date.getTime()) ? date.toISOString() : null;
}

function clipAvailability(clip: BrowserClip): IncidentReportClip["availability"] {
  if (clip.saved) return "account";
  if (clip.blob) return "browser";
  if (clip.url) return "playback_link";
  return "metadata_only";
}

/** Builds a snapshot of one event without reading storage, the network, or the clock. */
export function buildIncidentReport(
  session: BrowserSession,
  event: BrowserEvent,
  options: IncidentReportOptions = {},
): IncidentReport {
  const startedAt = validIso(session.createdAt);
  const atSeconds = finiteNonnegative(event.at);
  const recordedOccurredAt = validIso(event.occurredAt);
  const occurredAt = recordedOccurredAt ?? offsetIso(startedAt, atSeconds);
  const timestampSource = recordedOccurredAt ? "event" : occurredAt ? "session_offset" : "unavailable";
  const requestedRecordingIds = [...new Set(event.evidence?.recording_ids ?? [])];
  const recordingIdSet = new Set(requestedRecordingIds);
  const clips = session.clips
    .filter((clip) => {
      const start = finiteNonnegative(clip.start);
      const duration = finiteNonnegative(clip.duration);
      return recordingIdSet.has(clip.id) || (atSeconds !== null && start !== null && duration !== null &&
        start <= atSeconds && atSeconds <= start + duration);
    })
    .map((clip): IncidentReportClip => {
      const startSeconds = finiteNonnegative(clip.start) ?? 0;
      const durationSeconds = finiteNonnegative(clip.duration) ?? 0;
      return {
        id: clip.id,
        startSeconds,
        endSeconds: startSeconds + durationSeconds,
        durationSeconds,
        startedAt: offsetIso(startedAt, startSeconds),
        endedAt: offsetIso(startedAt, startSeconds + durationSeconds),
        width: Number.isFinite(clip.width) ? clip.width : 0,
        height: Number.isFinite(clip.height) ? clip.height : 0,
        availability: clipAvailability(clip),
      };
    })
    .sort((a, b) => a.startSeconds - b.startSeconds);

  const limitations = [
    "This is a prototype incident record. An automated candidate does not establish that a fall or injury occurred.",
    "Video is not embedded in this report. Open the incident in Artae to inspect any available recording.",
    "Reviewer identity and checklist completion are not recorded by this report.",
  ];
  if (!clips.length) limitations.push("No matching recording metadata was available when this report was generated.");
  if (requestedRecordingIds.some((id) => !clips.some((clip) => clip.id === id)))
    limitations.push("At least one requested recording was not found in this session snapshot.");
  if (timestampSource === "unavailable") limitations.push("The event's absolute time could not be verified from stored timestamps.");

  return {
    title: "Incident review report",
    session: {
      id: session.id,
      name: session.name,
      job: session.job,
      startedAt,
      storage: session.scope === "guest" ? "device" : event.saved ? "account_saved" : "account_unconfirmed",
    },
    event: {
      id: event.id,
      title: event.title,
      atSeconds,
      occurredAt,
      timestampSource,
      landmarkVisibility: Number.isFinite(event.visibility) && event.visibility > 0
        ? Math.min(1, Math.max(0, event.visibility)) : null,
      automatedSummary: event.summary?.trim() || null,
    },
    review: {
      status: event.review?.status ?? "open",
      outcome: event.review?.outcome ?? null,
      reviewedAt: validIso(event.review?.reviewed_at),
      reviewerNote: options.reviewerNote?.trim() || null,
    },
    provenance: {
      detection: session.job === "fall"
        ? "Browser fall monitoring candidate"
        : session.job === "custom" ? "Configured visual condition candidate" : "Browser monitoring candidate",
      optionalCloudReviewStatus: event.coordinator || null,
      recordedActions: [...new Set(event.actions ?? [])],
    },
    evidence: {
      status: event.evidence?.status ?? null,
      requestedRecordingIds,
      windowStartSeconds: finiteNonnegative(event.evidence?.start_seconds),
      windowEndSeconds: finiteNonnegative(event.evidence?.end_seconds),
      clips,
    },
    organizationChecklist: options.checklistText?.trim() || null,
    generatedAt: validIso(options.generatedAt),
    limitations,
  };
}

function escapeHtml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function field(label: string, value: string | number | null): string {
  return `<div class="field"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value === null ? "Unavailable" : String(value))}</dd></div>`;
}

function reviewLabel(report: IncidentReport): string {
  if (report.review.outcome === "false_alarm") return "Resolved — false alarm";
  if (report.review.status === "resolved") return "Resolved — reviewed";
  if (report.review.status === "acknowledged") return "Acknowledged — awaiting resolution";
  return "Open — human review required";
}

function availabilityLabel(value: IncidentReportClip["availability"]): string {
  switch (value) {
    case "account": return "Saved to account";
    case "browser": return "Available in this browser";
    case "playback_link": return "Playback link present in app";
    case "metadata_only": return "Metadata only";
  }
}

/** Self-contained print/download page. It never embeds video, external links, or executable script. */
export function renderIncidentReportHtml(report: IncidentReport): string {
  const clipRows = report.evidence.clips.length
    ? report.evidence.clips.map((clip) => `<tr><td>${escapeHtml(clip.id)}</td><td>${escapeHtml(clip.startedAt ?? `${clip.startSeconds}s from start`)}</td><td>${escapeHtml(clip.endedAt ?? `${clip.endSeconds}s from start`)}</td><td>${escapeHtml(`${clip.durationSeconds}s · ${clip.width}×${clip.height}`)}</td><td>${escapeHtml(availabilityLabel(clip.availability))}</td></tr>`).join("")
    : '<tr><td colspan="5">No matching clip metadata available</td></tr>';
  const actions = report.provenance.recordedActions.length
    ? `<ul>${report.provenance.recordedActions.map((action) => `<li>${escapeHtml(action.replaceAll("_", " "))}</li>`).join("")}</ul>`
    : "<p>No automated actions recorded.</p>";
  const checklist = report.organizationChecklist
    ? `<section><h2>Organization supplied checklist</h2><p class="caption">Provided text; completion is not recorded.</p><div class="multiline">${escapeHtml(report.organizationChecklist)}</div></section>`
    : "";
  const note = report.review.reviewerNote
    ? `<div class="multiline">${escapeHtml(report.review.reviewerNote)}</div>`
    : "<p>No reviewer note entered.</p>";
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Incident review report</title>
<style>body{font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;color:#17222b;max-width:850px;margin:36px auto;padding:0 20px}h1{margin:0}h2{font-size:18px;margin:0 0 12px}header p,.caption{color:#526271}section{border-top:1px solid #ccd4d8;padding:20px 0}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.field{min-width:0}dt{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#526271}dd{margin:4px 0 0;overflow-wrap:anywhere}.multiline{white-space:pre-wrap;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #dce2e5;padding:8px;vertical-align:top;overflow-wrap:anywhere}th{font-size:12px;color:#526271}ul{padding-left:22px}@media(max-width:650px){.grid{grid-template-columns:1fr}table{font-size:12px}}@media print{body{margin:0;max-width:none;padding:0}section{break-inside:avoid}}</style></head><body>
<header><h1>${escapeHtml(report.title)}</h1><p>Artae prototype · ${escapeHtml(report.generatedAt ? `Generated ${report.generatedAt}` : "Generation time not recorded")}</p></header>
<section><h2>Incident</h2><div class="grid">${field("Event", report.event.title)}${field("Event ID", report.event.id)}${field("Occurred (UTC)", report.event.occurredAt)}${field("Time source", report.event.timestampSource.replaceAll("_", " "))}${field("Elapsed in session", report.event.atSeconds === null ? null : `${report.event.atSeconds}s`)}${field("Session", report.session.name)}${field("Session ID", report.session.id)}${field("Session started (UTC)", report.session.startedAt)}${field("Monitoring job", report.session.job)}${field("Record storage", report.session.storage.replaceAll("_", " "))}</div></section>
<section><h2>Human review</h2><div class="grid">${field("Review state", reviewLabel(report))}${field("Last review update (UTC)", report.review.reviewedAt)}</div><h3>Reviewer note</h3>${note}</section>
<section><h2>Automated observation and provenance</h2><div class="grid">${field("Candidate source", report.provenance.detection)}${field("Optional cloud review status", report.provenance.optionalCloudReviewStatus)}${field("Landmark visibility", report.event.landmarkVisibility === null ? null : `${Math.round(report.event.landmarkVisibility * 100)}%`)}</div><h3>Automated summary</h3><div class="multiline">${escapeHtml(report.event.automatedSummary ?? "No automated summary available.")}</div><h3>Recorded actions</h3>${actions}</section>
<section><h2>Evidence metadata</h2><div class="grid">${field("Evidence status", report.evidence.status)}${field("Requested recording IDs", report.evidence.requestedRecordingIds.length ? report.evidence.requestedRecordingIds.join(", ") : null)}${field("Window start", report.evidence.windowStartSeconds === null ? null : `${report.evidence.windowStartSeconds}s`)}${field("Window end", report.evidence.windowEndSeconds === null ? null : `${report.evidence.windowEndSeconds}s`)}</div><table><thead><tr><th>Clip ID</th><th>Start (UTC)</th><th>End (UTC)</th><th>Duration · resolution</th><th>Availability</th></tr></thead><tbody>${clipRows}</tbody></table></section>
${checklist}<section><h2>Limitations</h2><ul>${report.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section></body></html>`;
}
