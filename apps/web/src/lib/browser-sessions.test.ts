import { afterEach, describe, expect, it, vi } from "vitest";
vi.mock("./api", () => ({API_URL:"https://api.example.test", request:vi.fn()}));
import { request } from "./api";
import { buildIncidentReport, renderIncidentReportHtml } from "./incident-report";
import { analyzePublicDemo, cloudEventFields, createPublicDemo, eventsPendingCloudSave, loadBrowserWorkspace, loadCloudSession, mergeSession, reviewCloudEvent, saveCloudEvent, sessionMetadata, type BrowserSession } from "./browser-sessions";

afterEach(() => { vi.unstubAllGlobals(); vi.mocked(request).mockReset(); });

describe("merging account and local history", () => {
  it("sends stored detection provenance and restores it from an account-only history load", async () => {
    const session: BrowserSession = { id: "session", scope: "account", name: "Hallway", job: "fall",
      createdAt: "2026-11-13T12:00:00Z", clips: [], events: [] };
    const event = { id: "event", at: 3, title: "Possible fall", visibility: .8,
      personTrackId: 2, detectionSource: "temporal_and_pose_window" as const };
    vi.mocked(request).mockResolvedValueOnce({ details: { detection_source: "temporal_and_pose_window" } });
    const saved = cloudEventFields(await saveCloudEvent(session, event));
    expect(JSON.parse(vi.mocked(request).mock.calls[0][1]?.body as string)).toMatchObject({
      id: "event", track_id: 2, detection_source: "temporal_and_pose_window",
    });
    expect(saved.detectionSource).toBe("temporal_and_pose_window");
    vi.mocked(request).mockResolvedValueOnce([{ source_event_id: "event", occurred_at_seconds: 3,
      confidence: .8, event_type: "person_fall", track_id: 2,
      details: { detection_source: "temporal_and_pose_window", review: { status: "resolved", outcome: "false_alarm" } },
    }]).mockResolvedValueOnce([]);
    const remote = await loadCloudSession(session);
    expect(remote.events[0].detectionSource).toBe("temporal_and_pose_window");
    const report = buildIncidentReport(remote, remote.events[0]);
    expect(report.provenance.detection).toContain("PoseWindowLogistic/v1 agreement");
    expect(report.review.outcome).toBe("false_alarm");
  });

  it("does not erase device provenance when an older API omits it in save or review responses", () => {
    const event = { detectionSource: "temporal_and_pose_window", review: undefined };
    const fields = cloudEventFields({ details: { review: { status: "resolved", outcome: "false_alarm" } } });
    expect(fields).not.toHaveProperty("detectionSource");
    Object.assign(event, fields);
    expect(event.detectionSource).toBe("temporal_and_pose_window");
    expect(event.review).toMatchObject({ outcome: "false_alarm" });
    expect(cloudEventFields({ details: { detection_source: "temporal_rule" } }).detectionSource).toBe("temporal_rule");
  });

  it("keeps recorded rule agreement after an account reload without restoring an outdated review", async () => {
    const local: BrowserSession = { id: "session", scope: "account", name: "Hallway", job: "fall",
      createdAt: "2026-11-11T12:00:00Z", clips: [], events: [{ id: "event", at: 3,
        title: "Possible fall", visibility: .8, personTrackId: 2, detectionSource: "temporal_and_pose_window",
        review: { status: "acknowledged", outcome: "acknowledged", reviewer_note: "Old local note" },
        sms: { status: "accepted", provider: "aws" } }] };
    vi.mocked(request).mockResolvedValueOnce([{ source_event_id: "event", occurred_at_seconds: 3,
      confidence: .8, event_type: "person_fall", track_id: 2, details: {
        review: { status: "resolved", outcome: "false_alarm", reviewer_note: "Latest account decision" },
        sms: { status: "failed", provider: "aws" },
      } }]).mockResolvedValueOnce([]);
    const remote = await loadCloudSession(local);
    expect(remote.events[0].detectionSource).toBeUndefined();
    const merged = mergeSession(local, remote);
    expect(merged.events[0]).toMatchObject({ detectionSource: "temporal_and_pose_window", saved: true,
      review: { status: "resolved", outcome: "false_alarm", reviewer_note: "Latest account decision" },
      sms: { status: "failed" } });
    const report = buildIncidentReport(merged, merged.events[0]);
    expect(report.provenance.detection).toContain("PoseWindowLogistic/v1 agreement");
    expect(renderIncidentReportHtml(report)).toContain("Resolved — false alarm");
    expect(local.events[0].review?.status).toBe("acknowledged");
    expect(remote.events[0].detectionSource).toBeUndefined();
  });

  it("uses explicit account provenance and does not transfer provenance across event IDs", () => {
    const local: BrowserSession = { id: "session", scope: "account", name: "Room", job: "fall",
      createdAt: "2026-11-11T12:00:00Z", clips: [], events: [{ id: "event", at: 3,
        title: "Possible fall", visibility: .8, detectionSource: "temporal_and_pose_window" }] };
    const remote: BrowserSession = { ...local, events: [
      { ...local.events[0], detectionSource: "temporal_rule" },
      { ...local.events[0], id: "other-event", detectionSource: undefined },
    ] };
    const merged = mergeSession(local, remote);
    expect(merged.events.find(item => item.id === "event")?.detectionSource).toBe("temporal_rule");
    expect(merged.events.find(item => item.id === "other-event")?.detectionSource).toBeUndefined();
    expect(buildIncidentReport(merged, merged.events[1]).provenance.detection).not.toContain("agreement");
  });

  it("never carries device provenance across accounts or sessions", () => {
    const local: BrowserSession = { id: "session", scope: "account", name: "Room", job: "fall",
      createdAt: "2026-11-11T12:00:00Z", clips: [], events: [{ id: "event", at: 3,
        title: "Possible fall", visibility: .8, detectionSource: "temporal_and_pose_window" }] };
    for (const change of [{ id: "other-session" }, { scope: "other-account" }]) {
      const remote: BrowserSession = { ...local, ...change,
        events: [{ ...local.events[0], detectionSource: undefined }] };
      expect(mergeSession(local, remote)).toBe(remote);
      expect(mergeSession(local, remote).events[0].detectionSource).toBeUndefined();
    }
  });

  it("still loads cloud footage and saved agents when local storage is blocked", async () => {
    vi.stubGlobal("indexedDB", { open: () => { throw new Error("Storage blocked"); } });
    vi.mocked(request).mockResolvedValueOnce([{ id: "saved", name: "Cloud session", job: "presence", created_at: "2026-09-09T12:00:00Z" }])
      .mockResolvedValueOnce([{ id: "agent", name: "Hallway", job: "presence" }]);
    const loaded = await loadBrowserWorkspace("account");
    expect(loaded.history[0]).toMatchObject({ id: "saved", cloud: true, scope: "account" });
    expect(loaded.jobs[0].name).toBe("Hallway");
    expect(loaded.warning).toContain("Device history is unavailable");
  });
  it("reports failed cloud history without hiding independently loaded jobs", async () => {
    vi.stubGlobal("indexedDB", { open: () => { throw new Error("Storage blocked"); } });
    vi.mocked(request).mockRejectedValueOnce(new Error("API offline"))
      .mockResolvedValueOnce([{ id: "agent", name: "Hallway", job: "presence" }]);
    const loaded = await loadBrowserWorkspace("account");
    expect(loaded.history).toEqual([]);
    expect(loaded.jobs).toHaveLength(1);
    expect(loaded.warning).toContain("Account footage history could not load");
  });
  it("loads unverified custom incidents through the session history endpoint", async () => {
    vi.mocked(request).mockResolvedValueOnce([{ source_event_id: "event", occurred_at_seconds: 3,
      confidence: 0, event_type: "visual_match", details: {
        review: { status: "resolved", outcome: "false_alarm", reviewer_note: "Checked footage", response_checklist: "Site steps" },
        review_history: [{ status: "resolved", outcome: "false_alarm", reviewer_note: "Checked footage", change_type: "decision" }],
      } }])
      .mockResolvedValueOnce([]);
    const loaded = await loadCloudSession({ id: "session", scope: "account", name: "Office", job: "custom",
      createdAt: "2026-09-09T12:00:00Z", events: [], clips: [] });
    expect(request).toHaveBeenCalledWith("/browser-sessions/session/events", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(loaded.events).toHaveLength(1);
    expect(loaded.events[0].review?.status).toBe("resolved");
    expect(loaded.events[0].review?.reviewer_note).toBe("Checked footage");
    expect(loaded.events[0].review?.response_checklist).toBe("Site steps");
    expect(loaded.events[0].reviewHistory?.[0].change_type).toBe("decision");
    expect(loaded.events[0].title).toBe("Visual condition matched");
  });
  it("keeps history metadata without retaining video blobs or mutating the recording", () => {
    const blob = new Blob(["video"], { type: "video/webm" });
    const session: BrowserSession = { id: "1", scope: "account", name: "Office", job: "presence",
      createdAt: "2026-09-09T12:00:00Z",
      events: [{ id: "event", at: 2, title: "Possible fall", visibility: .8,
        review: { status: "resolved", outcome: "false_alarm", reviewer_note: "Reviewed", response_checklist: "Site steps" } }],
      clips: [{ id: "clip", start: 0, duration: 10, width: 640, height: 480, blob, saved: true }] };
    const metadata = sessionMetadata(session);
    expect(metadata.clips[0].blob).toBeUndefined();
    expect(metadata.clips[0].saved).toBe(true);
    expect(session.clips[0].blob).toBe(blob);
    expect(metadata.scope).toBe("account");
    expect(metadata.events[0].review?.response_checklist).toBe("Site steps");
    expect(sessionMetadata({ ...session, scope: "guest" }).events[0].review?.reviewer_note).toBe("Reviewed");
  });
  it("never sends a device-only review suggestion through alert retries", () => {
    const session: BrowserSession = { id: "1", scope: "account", name: "Room", job: "fall",
      createdAt: "2026-09-09T12:00:00Z", clips: [], events: [
        { id: "review", at: 2, title: "Unverified motion", visibility: .8, reviewOnly: true },
        { id: "alert", at: 5, title: "Possible fall", visibility: .8 },
        { id: "saved", at: 8, title: "Possible fall", visibility: .8, saved: true },
      ] };
    expect(eventsPendingCloudSave(session).map((event) => event.id)).toEqual(["alert"]);
  });
  it("restores human review and model summaries without claiming independent detection", () => {
    const fields = cloudEventFields({details:{review:{status:"resolved",outcome:"false_alarm"},strands_agent:{status:"fallback",summary:"Model unavailable"}}});
    expect(fields.review?.outcome).toBe("false_alarm");
    expect(fields.coordinator).toBe("fallback");
    expect(fields.summary).toBe("Model unavailable");
    expect(cloudEventFields({details:{}}).review).toBeUndefined();
  });
  it("sends operator details with the review and retains them in the cloud response", async () => {
    const session: BrowserSession = { id: "session", scope: "account", name: "Office", job: "fall",
      createdAt: "2026-09-09T12:00:00Z", events: [], clips: [] };
    const event = { id: "event", at: 2, title: "Possible fall", visibility: .8 };
    vi.mocked(request).mockResolvedValueOnce({ details: { review: {
      status: "resolved", outcome: "false_alarm", reviewer_note: "Reviewed footage",
      response_checklist: "Use approved site process",
    } } });
    const result = await reviewCloudEvent(session, event, "false_alarm", {
      reviewer_note: "Reviewed footage", response_checklist: "Use approved site process",
    });
    expect(request).toHaveBeenCalledWith("/browser-sessions/session/events/event/review", expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify({ outcome: "false_alarm", reviewer_note: "Reviewed footage",
        response_checklist: "Use approved site process" }),
    }));
    expect(cloudEventFields(result).review?.response_checklist).toBe("Use approved site process");
  });
  it("does not discard unsaved clips or events when cloud history arrives", () => {
    const blob = new Blob(["clip"],{type:"video/webm"});
    const local:BrowserSession = { id:"1",scope:"a",name:"session",job:"fall",createdAt:"2026-09-08T12:00:00Z",
      clips:[{id:"clip1",start:0,duration:10,width:640,height:480,blob},{id:"pending",start:10,duration:3,width:640,height:480,blob}],
      events:[{id:"event1",at:3,title:"fall",visibility:.9},{id:"pending-event",at:12,title:"fall",visibility:.9}] };
    const cloud:BrowserSession={...local,cloud:true,clips:[{...local.clips[0],blob:undefined,url:"https://signed.example/clip",saved:true}],events:[{...local.events[0],saved:true}]};
    const merged=mergeSession(local,cloud);
    expect(merged.clips).toHaveLength(2);
    expect(merged.clips[0].blob).toBe(blob);
    expect(merged.clips[0].saved).toBe(true);
    expect(merged.events).toHaveLength(2);
    expect(merged.events[1].saved).toBeUndefined();
  });
  it("opens and analyzes a temporary public AWS demo without account credentials", async () => {
    vi.mocked(request).mockResolvedValueOnce({ id: "guest-run", token: "signed-token", max_checks: 4 })
      .mockResolvedValueOnce({ status: "no_match", summary: "No failure is visible.", frames_analyzed: 2,
        cooldown: false, confirmed: false, match_streak: 0, confirmation_count: 1,
        checks_remaining: 3, event: null });
    const session = await createPublicDemo("Find a failed print");
    const result = await analyzePublicDemo(session, [
      { at_seconds: 1, jpeg: "frame-one" },
      { at_seconds: 9, jpeg: "frame-two" },
    ]);
    expect(request).toHaveBeenNthCalledWith(1, "/browser-sessions/public-demo", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ prompt: "Find a failed print", detailed: false }),
    }));
    expect(request).toHaveBeenNthCalledWith(2, "/browser-sessions/public-demo/analyze", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ token: "signed-token", frames: [
        { at_seconds: 1, jpeg: "frame-one" },
        { at_seconds: 9, jpeg: "frame-two" },
      ], refinement: false }),
    }));
    expect(result.status).toBe("no_match");
    expect(result.checks_remaining).toBe(3);
  });
});
