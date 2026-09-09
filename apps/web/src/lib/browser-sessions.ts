import { API_URL, request as apiRequest } from "./api";
import type { BrowserJob } from "./browser-pose";
export type MonitoringJob = BrowserJob | "custom";
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
  summary?: string;
  review?: IncidentReview;
  actions?: string[];
  evidence?: { status: string; recording_ids: string[]; start_seconds: number; end_seconds: number };
  notification?: { channel: string; status: string; message: string; priority: string };
};
export type ReviewOutcome = "acknowledged" | "resolved" | "false_alarm";
export type IncidentReview = {
  status: "open" | "acknowledged" | "resolved";
  outcome: ReviewOutcome | null;
  reviewed_at?: string;
};
export type CloudEventResult = {
  details: {
    strands_agent?: { status: string; summary: string; tools_invoked?: string[] };
    review?: IncidentReview;
    evidence?: BrowserEvent["evidence"];
    notification?: BrowserEvent["notification"];
  };
};
export function cloudEventFields(result: CloudEventResult) {
  return {
    saved: true,
    coordinator: result.details.strands_agent?.status,
    summary: result.details.strands_agent?.summary,
    review: result.details.review,
    actions: result.details.strands_agent?.tools_invoked,
    evidence: result.details.evidence,
    notification: result.details.notification,
  };
}
export async function reviewCloudEvent(s: BrowserSession, event: BrowserEvent, outcome: ReviewOutcome) {
  return request<CloudEventResult>(`/browser-sessions/${s.id}/events/${event.id}/review`, {
    method: "PATCH", body: JSON.stringify({ outcome }),
  });
}
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
  job: MonitoringJob;
  prompt?: string;
  createdAt: string;
  events: BrowserEvent[];
  clips: BrowserClip[];
  cloud?: boolean;
  agentId?: string;
};
export const sessionMetadata = (s: BrowserSession): BrowserSession => ({
  ...s, clips: s.clips.map((clip) => ({ ...clip, blob: undefined })),
});
export type SavedBrowserJob = { id: string; name: string; job: MonitoringJob; prompt?: string };
export const listSavedBrowserJobs = () => request<SavedBrowserJob[]>("/browser-sessions/jobs");
export const saveBrowserJob = (job: SavedBrowserJob) => request<SavedBrowserJob>("/browser-sessions/jobs", {
  method: "POST", body: JSON.stringify(job),
});
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
    const open = indexedDB.open("artae-browser-sessions", 2);
    open.onupgradeneeded = () => {
      const db = open.result;
      const sessions = db.objectStoreNames.contains("sessions")
        ? open.transaction!.objectStore("sessions")
        : db.createObjectStore("sessions", { keyPath: "key" });
      if (!sessions.indexNames.contains("scope")) sessions.createIndex("scope", "scope");
      if (!db.objectStoreNames.contains("clips")) db.createObjectStore("clips", { keyPath: "key" });
    };
    open.onblocked = () => reject(new Error("Close older Artae tabs to upgrade recording storage, then reload."));
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      open.result.onversionchange = () => open.result.close();
      resolve(open.result);
    };
  });
}
export async function saveLocal(value: BrowserSession) {
  const db = await database();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(["sessions", "clips"], "readwrite");
    tx.objectStore("sessions").put({
      ...sessionMetadata(value),
      key: `${value.scope}/${value.id}`,
    });
    // Metadata changes must not clone/rewrite an hour of video every ten seconds.
    // The v1 inline blobs migrate lazily during a run's next successful save.
    const clips = tx.objectStore("clips");
    for (const clip of value.clips) {
      if (!clip.blob) continue;
      const key = `${value.scope}/${value.id}/${clip.id}`;
      const existing = clips.getKey(key);
      existing.onsuccess = () => { if (existing.result === undefined) clips.put({ key, blob: clip.blob }); };
    }
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  }).finally(() => db.close());
}
export async function readLocal(scope: string): Promise<BrowserSession[]> {
  const db = await database();
  return new Promise<BrowserSession[]>((resolve, reject) => {
    const read = db.transaction("sessions").objectStore("sessions").index("scope").getAll(scope);
    read.onsuccess = () =>
      resolve(
        (read.result as BrowserSession[])
          .filter((s) => s.scope === scope)
          .map(sessionMetadata)
          .sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
      );
    read.onerror = () => reject(read.error);
  }).finally(() => db.close());
}
export async function loadLocalSession(s: BrowserSession): Promise<BrowserSession> {
  const db = await database();
  try {
    const value = await new Promise<BrowserSession | undefined>((resolve, reject) => {
      const get = db.transaction("sessions").objectStore("sessions").get(`${s.scope}/${s.id}`);
      get.onsuccess = () => resolve(get.result);
      get.onerror = () => reject(get.error);
    });
    if (!value) return s;
    const tx = db.transaction("clips");
    const clips = await Promise.all(value.clips.map((clip) => new Promise<BrowserClip>((resolve, reject) => {
      const get = tx.objectStore("clips").get(`${s.scope}/${s.id}/${clip.id}`);
      get.onsuccess = () => resolve({ ...clip, blob: get.result?.blob ?? clip.blob });
      get.onerror = () => reject(get.error);
    })));
    return { ...value, clips };
  } finally { db.close(); }
}
export async function createCloudSession(s: BrowserSession) {
  await request("/browser-sessions", {
    method: "POST",
    body: JSON.stringify({
      id: s.id,
      name: s.name.slice(0, 80),
      job: s.job,
      started_at: s.createdAt,
      agent_id: s.agentId,
      prompt: s.prompt ?? "",
    }),
  });
}
export async function saveCloudEvent(
  session: BrowserSession,
  event: BrowserEvent,
) {
  return request<CloudEventResult>(`/browser-sessions/${session.id}/events`, {
    method: "POST",
    body: JSON.stringify({
      id: event.id,
      at_seconds: event.at,
      landmark_visibility: event.visibility,
    }),
  });
}
export type VisualCheckResult = {
  status: "match" | "no_match" | "uncertain" | "unsupported";
  summary: string;
  frames_analyzed: number;
  cooldown: boolean;
  event: (CloudEventResult & { source_event_id: string; occurred_at_seconds: number }) | null;
};
export function analyzeCloudFrames(s: BrowserSession, frames: { at_seconds: number; jpeg: string }[]) {
  return apiRequest<VisualCheckResult>(`/browser-sessions/${s.id}/analyze`, {
    method: "POST", body: JSON.stringify({ id: crypto.randomUUID(), frames }),
    signal: AbortSignal.timeout(70000),
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
      { id: string; name: string; job: MonitoringJob; created_at: string; agent_id?: string; prompt?: string }[]
    >("/browser-sessions");
  return rows.map((r) => ({
    id: r.id,
    name: r.name,
    job: r.job,
    createdAt: r.created_at,
    scope,
    cloud: true,
    agentId: r.agent_id,
    prompt: r.prompt,
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
        details: CloudEventResult["details"];
      }[]
    >(`/browser-sessions/${s.id}/events`),
    request<
      {
        id: string;
        started_at: string;
        duration_seconds: number;
        content_url?: string;
        width: number;
        height: number;
      }[]
    >(`/cameras/${s.id}/recordings?limit=500`),
  ]);
  return {
    ...s,
    events: events.map((e) => ({
      id: e.source_event_id,
      at: e.occurred_at_seconds,
      visibility: e.confidence,
      title:
        e.event_type === "visual_match" ? "Visual condition matched" : e.event_type === "person_fall"
          ? "Possible fall — please review"
          : "Person detected",
      ...cloudEventFields(e),
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
