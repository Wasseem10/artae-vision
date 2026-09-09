import { describe, expect, it, vi } from "vitest";
vi.mock("./api", () => ({API_URL:"https://api.example.test", request:vi.fn()}));
import { mergeSession, type BrowserSession } from "./browser-sessions";

describe("merging account and local history", () => {
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
