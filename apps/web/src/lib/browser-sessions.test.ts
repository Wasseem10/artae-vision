import { describe, expect, it, vi } from "vitest";
vi.mock("./api", () => ({API_URL:"https://api.example.test", request:vi.fn()}));
import { request } from "./api";
import { cloudEventFields, loadCloudSession, mergeSession, sessionMetadata, type BrowserSession } from "./browser-sessions";

describe("merging account and local history", () => {
  it("loads unverified custom incidents through the session history endpoint", async () => {
    vi.mocked(request).mockResolvedValueOnce([{ source_event_id: "event", occurred_at_seconds: 3,
      confidence: 0, event_type: "visual_match", details: { review: { status: "resolved", outcome: "reviewed" } } }])
      .mockResolvedValueOnce([]);
    const loaded = await loadCloudSession({ id: "session", scope: "account", name: "Office", job: "custom",
      createdAt: "2026-09-09T12:00:00Z", events: [], clips: [] });
    expect(request).toHaveBeenCalledWith("/browser-sessions/session/events");
    expect(loaded.events).toHaveLength(1);
    expect(loaded.events[0].review?.status).toBe("resolved");
    expect(loaded.events[0].title).toBe("Visual condition matched");
  });
  it("keeps history metadata without retaining video blobs or mutating the recording", () => {
    const blob = new Blob(["video"], { type: "video/webm" });
    const session: BrowserSession = { id: "1", scope: "account", name: "Office", job: "presence",
      createdAt: "2026-09-09T12:00:00Z", events: [],
      clips: [{ id: "clip", start: 0, duration: 10, width: 640, height: 480, blob, saved: true }] };
    const metadata = sessionMetadata(session);
    expect(metadata.clips[0].blob).toBeUndefined();
    expect(metadata.clips[0].saved).toBe(true);
    expect(session.clips[0].blob).toBe(blob);
    expect(metadata.scope).toBe("account");
  });
  it("restores human review and model summaries without claiming independent detection", () => {
    const fields = cloudEventFields({details:{review:{status:"resolved",outcome:"false_alarm"},strands_agent:{status:"fallback",summary:"Model unavailable"}}});
    expect(fields.review?.outcome).toBe("false_alarm");
    expect(fields.coordinator).toBe("fallback");
    expect(fields.summary).toBe("Model unavailable");
    expect(cloudEventFields({details:{}}).review).toBeUndefined();
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
});
