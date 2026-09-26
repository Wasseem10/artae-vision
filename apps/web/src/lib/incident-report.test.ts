import { describe, expect, it } from "vitest";
import type { BrowserEvent, BrowserSession } from "./browser-sessions";
import { buildIncidentReport, renderIncidentReportHtml } from "./incident-report";

const session: BrowserSession = {
  id: "session-1",
  scope: "guest",
  name: "Hallway",
  job: "fall",
  createdAt: "2026-09-26T12:00:00Z",
  events: [],
  clips: [
    { id: "before", start: 0, duration: 5, width: 640, height: 480 },
    { id: "incident-clip", start: 5, duration: 10, width: 1280, height: 720, blob: new Blob(["recording"]) },
    { id: "later", start: 20, duration: 5, width: 640, height: 480, url: "https://example.invalid/private?token=secret" },
  ],
};
const event: BrowserEvent = {
  id: "event-1",
  at: 8,
  title: "Possible fall — please review",
  visibility: 0.8,
  review: { status: "resolved", outcome: "false_alarm", reviewed_at: "2026-09-26T12:04:00Z" },
  coordinator: "completed",
  summary: "A person changed posture.",
  actions: ["preserve_evidence", "request_human_review"],
  evidence: { status: "saved", recording_ids: ["incident-clip", "missing"], start_seconds: 5, end_seconds: 15 },
};

describe("incident report", () => {
  it("uses review data and related clip metadata without embedding unrelated footage", () => {
    const report = buildIncidentReport(session, event, {
      generatedAt: "2026-09-26T13:00:00Z",
      reviewerNote: "Observed normal sitting.",
      checklistText: "1. Contact site lead\n2. Record decision",
    });
    expect(report.event.occurredAt).toBe("2026-09-26T12:00:08.000Z");
    expect(report.event.timestampSource).toBe("session_offset");
    expect(report.review).toMatchObject({ status: "resolved", outcome: "false_alarm", reviewerNote: "Observed normal sitting." });
    expect(report.evidence.clips.map((clip) => clip.id)).toEqual(["incident-clip"]);
    expect(report.evidence.clips[0]).toMatchObject({
      startedAt: "2026-09-26T12:00:05.000Z",
      endedAt: "2026-09-26T12:00:15.000Z",
      availability: "browser",
    });
    expect(report.limitations).toContain("At least one requested recording was not found in this session snapshot.");
    const html = renderIncidentReportHtml(report);
    expect(html).toContain("Resolved — false alarm");
    expect(html).toContain("Organization supplied checklist");
    expect(html).toContain("completion is not recorded");
    expect(html).not.toContain("https://example.invalid");
    expect(html).not.toContain("<video");
    expect(session.clips[1].blob).toBeInstanceOf(Blob);
  });

  it("keeps an unreviewed event open and reports missing time and evidence", () => {
    const report = buildIncidentReport(
      { ...session, createdAt: "invalid", clips: [] },
      { ...event, at: Number.NaN, occurredAt: "invalid", review: undefined, evidence: undefined },
    );
    expect(report.event.occurredAt).toBeNull();
    expect(report.event.timestampSource).toBe("unavailable");
    expect(report.review).toMatchObject({ status: "open", outcome: null, reviewedAt: null });
    expect(report.evidence.clips).toEqual([]);
    expect(renderIncidentReportHtml(report)).toContain("Open — human review required");
    expect(report.limitations).toContain("The event's absolute time could not be verified from stored timestamps.");
  });

  it("escapes reviewer, session, event, checklist, and summary text in printable HTML", () => {
    const payload = '<img src=x onerror="alert(1)"> & \'quoted\'';
    const report = buildIncidentReport(
      { ...session, id: payload, name: payload },
      { ...event, id: payload, title: payload, summary: payload, actions: [payload] },
      { reviewerNote: payload, checklistText: payload, generatedAt: "2026-09-26T13:00:00Z" },
    );
    const html = renderIncidentReportHtml(report);
    expect(html).not.toContain(payload);
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; &#39;quoted&#39;");
    expect(html).not.toContain("<script");
  });

  it("prefers a stored event timestamp over a derived session offset", () => {
    const report = buildIncidentReport(session, { ...event, occurredAt: "2026-09-26T12:01:00Z" });
    expect(report.event.occurredAt).toBe("2026-09-26T12:01:00.000Z");
    expect(report.event.timestampSource).toBe("event");
  });
});
