import { API_URL, request as apiRequest } from "./api";
import type { BrowserJob } from "./browser-pose";
function request<T>(path: string, init?: RequestInit): Promise<T> {
  return apiRequest<T>(path, { ...init, signal: AbortSignal.timeout(45000) });
}
export type BrowserEvent = {
  id: string;
  at: number;
  title: string;
  visibility: number;
  saved?: boolean;
  coordinator?: string;
};
export type BrowserClip = {
  id: string;
  start: number;
  duration: number;
  width: number;
  height: number;
  blob?: Blob;
  url?: string;
  saved?: boolean;
};
export type BrowserSession = {
  id: string;
  scope: string;
  name: string;
  job: BrowserJob;
  createdAt: string;
  events: BrowserEvent[];
  clips: BrowserClip[];
  cloud?: boolean;
};
export function mergeSession(
  local: BrowserSession,
  cloud: BrowserSession,
): BrowserSession {
  if (local.id !== cloud.id || local.scope !== cloud.scope) return cloud;
  return {
    ...cloud,
    createdAt: local.createdAt,
    events: [
      ...local.events.filter((e) => !cloud.events.some((c) => c.id === e.id)),
      ...cloud.events,
    ].sort((a, b) => a.at - b.at),
    clips: [
      ...local.clips.filter((c) => !cloud.clips.some((r) => r.id === c.id)),
      ...cloud.clips.map((c) => ({
        ...c,
        ...local.clips.find((l) => l.id === c.id),
        url: c.url,
        saved: true,
      })),
    ].sort((a, b) => a.start - b.start),
  };
}
export const formatTime = (t: number) =>
  `${Math.floor(t / 60)}:${Math.floor(t % 60)
    .toString()
    .padStart(2, "0")}`;
function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open("artae-browser-sessions", 1);
    open.onupgradeneeded = () =>
      open.result.createObjectStore("sessions", { keyPath: "key" });
    open.onerror = () => reject(open.error);
    open.onsuccess = () => resolve(open.result);
  });
}
export async function saveLocal(value: BrowserSession) {
  const db = await database();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("sessions", "readwrite");
    tx.objectStore("sessions").put({
      ...value,
      key: `${value.scope}/${value.id}`,
    });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  }).finally(() => db.close());
}
export async function readLocal(scope: string): Promise<BrowserSession[]> {
  const db = await database();
  return new Promise<BrowserSession[]>((resolve, reject) => {
    const read = db.transaction("sessions").objectStore("sessions").getAll();
    read.onsuccess = () =>
      resolve(
        (read.result as BrowserSession[])
          .filter((s) => s.scope === scope)
          .sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
      );
    read.onerror = () => reject(read.error);
  }).finally(() => db.close());
}
export async function createCloudSession(s: BrowserSession) {
  await request("/browser-sessions", {
    method: "POST",
    body: JSON.stringify({
      id: s.id,
      name: s.name.slice(0, 80),
      job: s.job,
      started_at: s.createdAt,
    }),
  });
}
export async function saveCloudEvent(
  session: BrowserSession,
  event: BrowserEvent,
) {
  return request<{
    details: { strands_agent?: { status: string; summary: string } };
  }>(`/browser-sessions/${session.id}/events`, {
    method: "POST",
    body: JSON.stringify({
      id: event.id,
      at_seconds: event.at,
      landmark_visibility: event.visibility,
    }),
  });
}
export async function saveCloudClip(s: BrowserSession, clip: BrowserClip) {
  if (!clip.blob) return;
  const start = new Date(new Date(s.createdAt).getTime() + clip.start * 1000);
  await request(`/browser-sessions/${s.id}/recordings`, {
    method: "POST",
    body: JSON.stringify({
      segment_id: clip.id,
      source_key: clip.id,
      source_filename: `${clip.id}.${clip.blob.type.includes("mp4") ? "mp4" : "webm"}`,
      started_at: start.toISOString(),
      ended_at: new Date(start.getTime() + clip.duration * 1000).toISOString(),
      duration_seconds: clip.duration,
      frame_count: Math.max(1, Math.round(clip.duration * 20)),
      fps: 20,
      width: clip.width,
      height: clip.height,
    }),
  });
  const result = await request<{ content_url?: string }>(
    `/browser-sessions/${s.id}/recordings/${clip.id}/content`,
    {
      method: "PUT",
      headers: { "Content-Type": clip.blob.type || "video/webm" },
      body: clip.blob,
    },
  );
  clip.saved = true;
  if (result.content_url) clip.url = new URL(result.content_url, API_URL).href;
}
export async function listCloudSessions(
  scope: string,
): Promise<BrowserSession[]> {
  const rows =
    await request<
      { id: string; name: string; job: BrowserJob; created_at: string }[]
    >("/browser-sessions");
  return rows.map((r) => ({
    id: r.id,
    name: r.name,
    job: r.job,
    createdAt: r.created_at,
    scope,
    cloud: true,
    events: [],
    clips: [],
  }));
}
export async function loadCloudSession(
  s: BrowserSession,
): Promise<BrowserSession> {
  const [events, clips] = await Promise.all([
    request<
      {
        source_event_id: string;
        occurred_at_seconds: number;
        confidence: number;
        event_type: string;
        details: { strands_agent?: { status: string } };
      }[]
    >(`/events?camera_id=${s.id}`),
    request<
      {
        id: string;
        started_at: string;
        duration_seconds: number;
        content_url?: string;
        width: number;
        height: number;
      }[]
    >(`/cameras/${s.id}/recordings`),
  ]);
  return {
    ...s,
    events: events.map((e) => ({
      id: e.source_event_id,
      at: e.occurred_at_seconds,
      visibility: e.confidence,
      title:
        e.event_type === "person_fall"
          ? "Possible fall — please review"
          : "Person detected",
      saved: true,
      coordinator: e.details.strands_agent?.status,
    })),
    clips: clips
      .filter((c) => c.content_url)
      .map((c) => ({
        id: c.id,
        start: Math.max(
          0,
          (new Date(c.started_at).getTime() - new Date(s.createdAt).getTime()) /
            1000,
        ),
        duration: c.duration_seconds,
        width: c.width,
        height: c.height,
        url: new URL(c.content_url!, API_URL).href,
        saved: true,
      }))
      .sort((a, b) => a.start - b.start),
  };
}
