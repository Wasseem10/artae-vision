"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  BrowserPoseRule,
  POSE_CONNECTIONS,
  poseFeatures,
  type BrowserJob,
  type Landmark,
} from "@/lib/browser-pose";
import {
  createCloudSession,
  formatTime,
  listCloudSessions,
  loadCloudSession,
  mergeSession,
  readLocal,
  saveCloudClip,
  saveCloudEvent,
  saveLocal,
  type BrowserClip,
  type BrowserSession,
} from "@/lib/browser-sessions";
import {
  getSupabaseBrowserClient,
  isSupabaseConfigured,
  syncApiSession,
} from "@/lib/supabase";
import styles from "./instant-demo.module.css";

export function BrowserMonitor() {
  const videoRef = useRef<HTMLVideoElement>(null),
    canvasRef = useRef<HTMLCanvasElement>(null),
    playbackRef = useRef<HTMLVideoElement>(null);
  const current = useRef<BrowserSession | null>(null),
    stopRef = useRef<() => void>(() => {}),
    active = useRef(false),
    mounted = useRef(true);
  const accountScope = useRef("guest"),
    cloudQueue = useRef(Promise.resolve()),
    audio = useRef<AudioContext | null>(null);
  const [scope, setScope] = useState("guest"),
    [source, setSource] = useState<"sample" | "file" | "webcam">("sample"),
    [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<BrowserJob>("presence"),
    [phase, setPhase] = useState("Ready"),
    [running, setRunning] = useState(false);
  const [problem, setProblem] = useState<string | null>(null),
    [saveProblem, setSaveProblem] = useState<string | null>(null);
  const [session, setSession] = useState<BrowserSession | null>(null),
    [history, setHistory] = useState<BrowserSession[]>([]);
  const [replay, setReplay] = useState<{
    url: string;
    owned: boolean;
    seek: number;
  } | null>(null);
  const [metrics, setMetrics] = useState({
    frames: 0,
    people: 0,
    seconds: 0,
    state: "Waiting for video",
  });
  const [saving, setSaving] = useState(0),
    [sound, setSound] = useState(true);
  const [fallSample, setFallSample] = useState("fall-lateral");
  const [authReady, setAuthReady] = useState(!isSupabaseConfigured());
  const [loadedScope, setLoadedScope] = useState<string | null>(null);

  useEffect(() => {
    mounted.current = true;
    let unsubscribe = () => {};
    if (isSupabaseConfigured()) {
      const {
        data: { subscription },
      } = getSupabaseBrowserClient().auth.onAuthStateChange((_event, s) => {
        const next = s?.user.id ?? "guest";
        if (next !== accountScope.current) {
          stopRef.current();
          accountScope.current = next;
          if (mounted.current) setScope(next);
        }
        syncApiSession(s);
        if (mounted.current) setAuthReady(true);
      });
      unsubscribe = () => subscription.unsubscribe();
    }
    return () => {
      mounted.current = false;
      unsubscribe();
      stopRef.current();
      void audio.current?.close();
    };
  }, []);
  useEffect(() => {
    let cancelled = false;
    void readLocal(scope)
      .then((rows) => {
        if (!cancelled) {
          setHistory(rows);
          setSession(null);
          setReplay(null);
          current.current = null;
        }
      })
      .catch(() => {
        if (!cancelled)
          setSaveProblem(
            "Local history storage is blocked. Download recordings before leaving.",
          );
      }).finally(() => { if (!cancelled) setLoadedScope(scope); });
    return () => {
      cancelled = true;
    };
  }, [scope]);
  useEffect(
    () => () => {
      if (replay?.owned) URL.revokeObjectURL(replay.url);
    },
    [replay],
  );
  function persist(s: BrowserSession) {
    if (mounted.current && accountScope.current === s.scope) {
      setSession({ ...s, events: [...s.events], clips: [...s.clips] });
      setHistory((rows) => [s, ...rows.filter((r) => r.id !== s.id)]);
    }
    void saveLocal(s).catch(() => {
      if (mounted.current)
        setSaveProblem(
          "Local history could not be saved. Storage may be full. Download your recording before leaving.",
        );
    });
  }
  function queueCloud(s: BrowserSession, task: () => Promise<void>) {
    if (s.scope === "guest") return;
    setSaving((n) => n + 1);
    cloudQueue.current = cloudQueue.current
      .then(async () => {
        if (accountScope.current !== s.scope)
          throw new Error("Account changed; sign back in to retry this save");
        await task();
      })
      .catch((e) => {
        if (mounted.current)
          setSaveProblem(
            `Account save failed: ${e instanceof Error ? e.message : "check your connection"}. Local copy retained. Use Retry account save.`,
          );
      })
      .finally(() => {
        if (mounted.current) setSaving((n) => Math.max(0, n - 1));
      });
  }
  function beep() {
    if (!sound || !audio.current) return;
    const osc = audio.current.createOscillator(),
      gain = audio.current.createGain();
    osc.connect(gain);
    gain.connect(audio.current.destination);
    osc.frequency.value = 740;
    gain.gain.value = 0.08;
    osc.start();
    osc.stop(audio.current.currentTime + 0.18);
  }
  function playClip(clip: BrowserClip, at = clip.start) {
    if (clip.blob || clip.url)
      setReplay({
        url: clip.blob ? URL.createObjectURL(clip.blob) : clip.url!,
        owned: !!clip.blob,
        seek: Math.max(0, at - clip.start),
      });
  }
  async function start() {
    if (active.current || saving || !authReady || loadedScope !== scope) return;
    const video = videoRef.current,
      canvas = canvasRef.current;
    if (!video || !canvas) return;
    if (source === "file" && !file) {
      setProblem("Choose a video file first.");
      return;
    }
    active.current = true;
    setRunning(true);
    setProblem(null);
    setSaveProblem(null);
    setReplay(null);
    setPhase("Loading pose model…");
    setMetrics({ frames: 0, people: 0, seconds: 0, state: "Loading" });
    const s: BrowserSession = {
      id: crypto.randomUUID(),
      scope,
      name:
        source === "webcam"
          ? "My webcam"
          : source === "file"
            ? file!.name
            : job === "fall"
              ? `Sample: ${fallSample}`
              : "Sample: person in view",
      job,
      createdAt: new Date().toISOString(),
      events: [],
      clips: [],
    };
    current.current = s;
    persist(s);
    let worker: Worker | null = null,
      media: MediaStream | null = null,
      recordingStream: MediaStream | null = null,
      recorder: MediaRecorder | null = null;
    let animation = 0,
      timer: ReturnType<typeof setTimeout> | undefined,
      loadTimer: ReturnType<typeof setTimeout> | undefined;
    let sourceUrl: string | null = null,
      stopped = false,
      bitmapPending = false,
      lastSent = -1,
      lastVideo = -1,
      lastAt = 0,
      frames = 0,
      startTime = 0;
    let cancelLoading: (() => void) | undefined;
    let points: Landmark[] = [];
    const engine = new BrowserPoseRule(job);
    const now = () =>
      source === "webcam"
        ? (performance.now() - startTime) / 1000
        : video.currentTime;
    const stop = () => {
      if (stopped) return;
      stopped = true;
      active.current = false;
      cancelLoading?.();
      cancelAnimationFrame(animation);
      clearTimeout(timer);
      clearTimeout(loadTimer);
      worker?.terminate();
      if (recorder && recorder.state !== "inactive") recorder.stop();
      recordingStream?.getTracks().forEach((t) => t.stop());
      media?.getTracks().forEach((t) => t.stop());
      video.pause();
      video.srcObject = null;
      if (sourceUrl) {
        video.removeAttribute("src");
        video.load();
        URL.revokeObjectURL(sourceUrl);
      }
      if (mounted.current) {
        setRunning(false);
        setPhase("Stopped · history kept");
        persist(s);
      }
    };
    stopRef.current = stop;
    try {
      if (sound) {
        audio.current ??= new AudioContext();
        await audio.current.resume();
      }
      worker = new Worker("/vision/pose-worker.js");
      await new Promise<void>((resolve, reject) => {
        cancelLoading = () => reject(new Error("Start cancelled"));
        loadTimer = setTimeout(
          () =>
            reject(
              new Error(
                "Model loading timed out. Check your connection and try again.",
              ),
            ),
          45000,
        );
        worker!.onerror = (e) => {
          clearTimeout(loadTimer);
          reject(
            new Error(
              `Pose engine could not load: ${e.message || "try current Chrome or Edge"}`,
            ),
          );
        };
        worker!.onmessage = ({ data }) => {
          if (data.type === "ready") {
            clearTimeout(loadTimer);
            resolve();
          } else if (data.type === "error") {
            clearTimeout(loadTimer);
            reject(new Error(data.message));
          }
        };
        worker!.postMessage({ type: "init" });
      });
      cancelLoading = undefined;
      if (stopped) return;
      setPhase(
        source === "webcam"
          ? "Allow camera access in your browser…"
          : "Opening video…",
      );
      if (source === "webcam") {
        media = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 1280 },
            height: { ideal: 720 },
            frameRate: { ideal: 24 },
          },
          audio: false,
        });
        if (stopped) {
          media.getTracks().forEach((t) => t.stop());
          return;
        }
        video.removeAttribute("src");
        video.srcObject = media;
      } else {
        sourceUrl = source === "file" ? URL.createObjectURL(file!) : null;
        video.src =
          sourceUrl ??
          `/vision/samples/${job === "fall" ? fallSample : "person"}.mp4`;
        video.load();
      }
      await new Promise<void>((resolve, reject) => {
        cancelLoading = () => reject(new Error("Start cancelled"));
        loadTimer = setTimeout(
          () =>
            reject(
              new Error(
                "Video did not start. Try a supported MP4 or allow camera access.",
              ),
            ),
          15000,
        );
        void video.play().then(resolve, reject);
      }).finally(() => {
        clearTimeout(loadTimer);
        cancelLoading = undefined;
      });
      if (stopped) return;
      if (!video.videoWidth)
        throw new Error("No decoded frames received. Try another video file.");
      startTime = performance.now();
      s.createdAt = new Date().toISOString();
      queueCloud(s, async () => {
        await createCloudSession(s);
        s.cloud = true;
        persist(s);
      });
      const ratio = Math.min(1, 1280 / video.videoWidth);
      canvas.width = Math.round(video.videoWidth * ratio);
      canvas.height = Math.round(video.videoHeight * ratio);
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Canvas is unavailable");
      const mime = ["video/webm;codecs=vp8", "video/webm", "video/mp4"].find(
        (t) =>
          typeof MediaRecorder !== "undefined" &&
          MediaRecorder.isTypeSupported(t),
      );
      if (mime && canvas.captureStream) {
        recordingStream = canvas.captureStream(20);
        const recordSegment = () => {
          if (stopped) return;
          const startAt = now(),
            chunks: Blob[] = [];
          const segmentRecorder = new MediaRecorder(recordingStream!, {
            mimeType: mime,
            videoBitsPerSecond: 600000,
          });
          recorder = segmentRecorder;
          segmentRecorder.ondataavailable = (e) => {
            if (e.data.size) chunks.push(e.data);
          };
          segmentRecorder.onerror = () => {
            if (mounted.current)
              setSaveProblem(
                "Recording failed. Detection may continue, but footage is not being saved.",
              );
          };
          segmentRecorder.onstop = () => {
            const duration = Math.max(0.01, lastAt - startAt),
              blob = new Blob(chunks, { type: mime });
            if (blob.size && duration >= 0.2) {
              const clip: BrowserClip = {
                id: crypto.randomUUID(),
                start: startAt,
                duration,
                width: canvas.width,
                height: canvas.height,
                blob,
              };
              s.clips.push(clip);
              persist(s);
              queueCloud(s, async () => {
                await createCloudSession(s);
                await saveCloudClip(s, clip);
                s.cloud = true;
                persist(s);
              });
            }
            if (!stopped) recordSegment();
          };
          segmentRecorder.start();
          timer = setTimeout(() => {
            if (segmentRecorder.state !== "inactive") segmentRecorder.stop();
          }, 10000);
        };
        recordSegment();
      } else
        setSaveProblem(
          "Recording is unsupported here. Detection works, but replay will be unavailable. Try current Chrome or Edge.",
        );
      worker.onmessage = ({ data }) => {
        bitmapPending = false;
        if (stopped) return;
        if (data.type === "error") {
          setProblem(`Detection stopped: ${data.message}`);
          stop();
          return;
        }
        if (data.type !== "result") return;
        points = data.landmarks;
        frames++;
        const f = poseFeatures(points, canvas.width, canvas.height);
        if (engine.update(f, lastSent) && s.events.length < 20) {
          const event = {
            id: crypto.randomUUID(),
            at: lastSent,
            title:
              job === "fall"
                ? "Possible fall — please review"
                : "Person detected",
            visibility: f?.visibility ?? 0,
          };
          s.events.push(event);
          persist(s);
          beep();
          queueCloud(s, async () => {
            await createCloudSession(s);
            const result = await saveCloudEvent(s, event);
            Object.assign(event, {
              saved: true,
              coordinator: result.details.strands_agent?.status,
            });
            s.cloud = true;
            persist(s);
          });
        }
        setMetrics({
          frames,
          people: f ? 1 : 0,
          seconds: lastSent,
          state: f
            ? {
                unarmed: "Watching posture",
                upright: "Person tracked",
                descending: "Checking movement",
                alerted: "Event detected",
              }[engine.status]
            : "No clear body pose",
        });
      };
      worker.onerror = () => {
        if (!stopped) {
          setProblem(
            "Pose processing stopped unexpectedly. Your existing results are kept.",
          );
          stop();
        }
      };
      setPhase("Analyzing real video");
      setMetrics({ frames: 0, people: 0, seconds: 0, state: "Looking for a body pose" });
      const draw = () => {
        if (stopped) return;
        lastAt = now();
        if (lastAt >= 120) {
          stop();
          return;
        }
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        ctx.strokeStyle = "#43df86";
        ctx.lineWidth = 3;
        for (const [a, b] of POSE_CONNECTIONS) {
          const p = points[a],
            q = points[b];
          if (
            !p ||
            !q ||
            (p.visibility ?? 0) < 0.6 ||
            (q.visibility ?? 0) < 0.6
          )
            continue;
          ctx.beginPath();
          ctx.moveTo(p.x * canvas.width, p.y * canvas.height);
          ctx.lineTo(q.x * canvas.width, q.y * canvas.height);
          ctx.stroke();
        }
        if (
          !bitmapPending &&
          lastAt - lastSent >= 0.12 &&
          video.currentTime !== lastVideo &&
          video.readyState >= 2
        ) {
          bitmapPending = true;
          lastSent = lastAt;
          lastVideo = video.currentTime;
          void createImageBitmap(video)
            .then((bitmap) => {
              if (stopped) {
                bitmap.close();
                return;
              }
              worker!.postMessage(
                { type: "frame", bitmap, timestamp: performance.now() },
                [bitmap],
              );
            })
            .catch(() => {
              bitmapPending = false;
              if (!stopped) {
                setProblem(
                  "Could not read video frames. Choose a supported video file.",
                );
                stop();
              }
            });
        }
        animation = requestAnimationFrame(draw);
      };
      draw();
    } catch (e) {
      if (!stopped)
        setProblem(
          e instanceof Error && e.name === "NotAllowedError"
            ? "Camera permission denied. Allow it in the address bar, or choose a video file."
            : e instanceof Error
              ? e.message
              : "Could not start detection.",
        );
      stop();
    }
  }
  async function retrySave() {
    const s = current.current;
    if (!s || scope === "guest") return;
    setSaveProblem(null);
    queueCloud(s, async () => {
      await createCloudSession(s);
      s.cloud = true;
      for (const e of s.events)
        if (!e.saved) {
          const result = await saveCloudEvent(s, e);
          e.saved = true;
          e.coordinator = result.details.strands_agent?.status;
        }
      for (const clip of s.clips)
        if (!clip.saved && clip.blob) await saveCloudClip(s, clip);
      persist(s);
    });
  }
  async function accountHistory() {
    try {
      const rows = await listCloudSessions(scope);
      setHistory((local) => [
        ...rows.map((r) => local.find((s) => s.id === r.id) ?? r),
        ...local.filter((s) => !rows.some((r) => r.id === s.id)),
      ]);
    } catch (e) {
      setSaveProblem(
        e instanceof Error ? e.message : "Could not load account history.",
      );
    }
  }
  async function openSession(s: BrowserSession) {
    if (running || saving) return;
    let loaded = s;
    if (s.cloud)
      try {
        loaded = mergeSession(s, await loadCloudSession(s));
      } catch {
        setSaveProblem(
          "Account history is unavailable right now. Showing any recordings saved on this device.",
        );
      }
    current.current = loaded;
    setSession(loaded);
    setReplay(null);
    setPhase("Saved session");
    if (loaded.clips[0]) playClip(loaded.clips[0]);
  }
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/">
          artae.
        </Link>
        <div>
          <Link href="/app">Workspace</Link>
          <Link href="/login?next=demo">
            {scope === "guest" ? "Sign in to save to your account" : "Account"}
          </Link>
        </div>
      </header>
      <section className={styles.intro}>
        <small>REAL DETECTION · NO INSTALLATION</small>
        <h1>
          Give your camera
          <br />
          one clear job.
        </h1>
        <p>
          Choose a job, connect video, and watch real detections appear. Start
          with person detection to check your setup.
        </p>
      </section>
      <section className={styles.workspace}>
        <div className={styles.setup}>
          <label>
            1. What should it watch for?
            <select
              value={job}
              disabled={running || saving > 0}
              onChange={(e) => setJob(e.target.value as BrowserJob)}
            >
              <option value="presence">A person in view</option>
              <option value="fall">A possible fall · experimental</option>
            </select>
          </label>
          <label>
            2. Connect video
            <select
              value={source}
              disabled={running || saving > 0}
              onChange={(e) => setSource(e.target.value as typeof source)}
            >
              <option value="sample">Use a sample video</option>
              <option value="file">Upload my video</option>
              <option value="webcam">Use my webcam</option>
            </select>
          </label>
          <button
            className={styles.start}
            disabled={!running && (saving > 0 || !authReady || loadedScope !== scope)}
            onClick={() => (running ? stopRef.current() : void start())}
          >
            {running ? "Stop agent" : !authReady ? "Checking account…" : "Start agent"}
          </button>
          {source === "file" && (
            <label>
              Choose a video
              <input
                accept="video/*"
                disabled={running}
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
          )}
          {source === "sample" && job === "fall" && (
            <label>
              Sample scenario
              <select
                disabled={running || saving > 0}
                value={fallSample}
                onChange={(e) => setFallSample(e.target.value)}
              >
                <option value="fall-lateral">Staged lateral fall</option>
                <option value="fall-forward">Staged forward fall</option>
                <option value="fall-backwards">Staged backward fall</option>
                <option value="sitting">Sitting · no fall expected</option>
                <option value="bending">Bending · no fall expected</option>
              </select>
            </label>
          )}
        </div>
        <p className={styles.note}>
          {job === "fall"
            ? "Keep one person’s full body visible. A possible fall requires upright posture, descent, then a sustained horizontal posture. Use a recorded clip; do not fall to test this. This is experimental, not an emergency monitoring system."
            : "A visible body pose sustained for one second creates an alert. One person is tracked at a time; small or obscured people may not be detected."}{" "}
          Sessions stop after 2 minutes. No audio is recorded.
        </p>
        <div className={styles.ruleBar}>
          <strong role="status">{phase}</strong>
          <label>
            <input
              type="checkbox"
              checked={sound}
              disabled={running}
              onChange={(e) => setSound(e.target.checked)}
            />{" "}
            Sound on detection
          </label>
        </div>
        <div className={styles.content}>
          <section className={styles.camera}>
            <div className={styles.videoStage}>
              <video
                className={styles.sourceVideo}
                ref={videoRef}
                muted
                playsInline
                onEnded={() => stopRef.current()}
              />
              <canvas
                ref={canvasRef}
                aria-label="Live video with real body-pose overlay"
              />
              {!running && (
                <div className={styles.stageEmpty}>
                  <strong>{session ? "Agent stopped" : "Ready when you are"}</strong>
                  <span>{session ? "Your event log and recorded footage are kept below." : "Choose video above, then Start agent."}</span>
                </div>
              )}
              <span className={styles.cameraLabel}>
                MediaPipe pose · on-device
              </span>
            </div>
            <div className={styles.controls}>
              <span>
                {metrics.frames} frames analyzed · {metrics.people} person ·{" "}
                {formatTime(metrics.seconds)}
              </span>
              <span>{metrics.state}</span>
            </div>
            <div className={styles.replay}>
              <h3>Recorded footage</h3>
              <p>
                Independent segments appear about every 10 seconds. Replay them
                while detection continues.
              </p>
              <video
                aria-label="Recorded footage playback"
                ref={playbackRef}
                controls
                playsInline
                src={replay?.url}
                onLoadedMetadata={(e) => {
                  e.currentTarget.currentTime = replay?.seek ?? 0;
                }}
              />
              <div className={styles.clipList}>
                {session?.clips.map((clip) => (
                  <button key={clip.id} onClick={() => playClip(clip)}>
                    {formatTime(clip.start)}–
                    {formatTime(clip.start + clip.duration)}{" "}
                    {clip.saved ? "☁" : ""}
                  </button>
                ))}
              </div>
              {!session?.clips.length && (
                <p>
                  {running
                    ? "Recording the first segment…"
                    : "No recording yet."}
                </p>
              )}
              {replay && (
                <a href={replay.url} download="artae-recording.webm">
                  Download this segment
                </a>
              )}
            </div>
          </section>
          <aside className={styles.log}>
            <header>
              <div>
                <small>DETECTION LOG</small>
                <strong>Events & alerts</strong>
              </div>
              <span>{session?.events.length ?? 0}</span>
            </header>
            <div aria-live="polite">
              {session?.events.length ? (
                session.events.map((event) => (
                  <article key={event.id}>
                    <i />
                    <div>
                      <strong>{event.title}</strong>
                      <small>
                        {formatTime(event.at)} · Landmark visibility{" "}
                        {Math.round(event.visibility * 100)}%
                      </small>
                      <span>
                        {event.saved
                          ? "Account alert saved"
                          : "On-screen alert · this device"}
                      </span>
                      {event.coordinator && (
                        <small>
                          AWS coordinator:{" "}
                          {event.coordinator === "completed"
                            ? "completed"
                            : "unavailable; local alert kept"}
                        </small>
                      )}
                      <button
                        onClick={() => {
                          const clip = session.clips.find(
                            (c) =>
                              event.at >= c.start &&
                              event.at <= c.start + c.duration,
                          );
                          if (clip) playClip(clip, event.at);
                        }}
                        disabled={
                          !session.clips.some(
                            (c) =>
                              event.at >= c.start &&
                              event.at <= c.start + c.duration,
                          )
                        }
                      >
                        Review footage
                      </button>
                    </div>
                  </article>
                ))
              ) : (
                <div className={styles.empty}>
                  <strong>
                    {running
                      ? "Watching for your selected job"
                      : "No detections yet"}
                  </strong>
                  <p>
                    Events come from analyzed video frames, not a scripted
                    timeline. Stop never clears this list.
                  </p>
                </div>
              )}
            </div>
          </aside>
        </div>
        <div className={styles.storage}>
          <strong>
            {scope === "guest"
              ? "Guest session · saved on this device only"
              : saving
                ? `Saving to account… ${saving} pending`
                : session?.cloud
                  ? `${session.events.filter((e) => e.saved).length} alerts saved to account`
                  : "Signed in · account saving enabled"}
          </strong>
          <span>
            {scope === "guest"
              ? "Sign in before starting for cross-device history. No email, text, or phone call is sent."
              : "In-app alerts only. Cloud footage is available once its upload succeeds."}
          </span>
          {scope !== "guest" && session && (
            <button
              disabled={saving > 0 || running}
              onClick={() => void retrySave()}
            >
              Retry account save
            </button>
          )}
        </div>
        {problem && (
          <p className={styles.problem} role="alert">
            {problem}
          </p>
        )}
        {saveProblem && (
          <p className={styles.problem} role="alert">
            {saveProblem}
          </p>
        )}
      </section>
      <p className={styles.attribution}>
        Sample footage:{" "}
        <a href="https://www.pexels.com/video/man-walking-office-alone-4435565/">
          person video / Pexels
        </a>
        ; staged fall and daily-activity excerpts:{" "}
        <a href="https://figshare.com/articles/dataset/UMA_ADL_FALL_Dataset_zip/4214283">
          UMAFall, Eduardo Casilari and Jose A. Santoyo-Ramón
        </a>
        , <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.
        Excerpts trimmed, resized and re-encoded. No endorsement implied.
      </p>
      <section className={styles.history}>
        <header>
          <h2>Past sessions</h2>
          {scope !== "guest" && (
            <button
              disabled={running || saving > 0}
              onClick={() => void accountHistory()}
            >
              Load account history
            </button>
          )}
        </header>
        <p>
          Your logs remain after stopping. Guest history is private to this
          browser; sign in for account history.
        </p>
        <div>
          {history.map((s) => (
            <button
              disabled={running || saving > 0}
              key={s.id}
              onClick={() => void openSession(s)}
            >
              <strong>{s.name}</strong>
              <span>
                {new Date(s.createdAt).toLocaleString()} ·{" "}
                {s.job === "fall" ? "Possible fall" : "Person detection"} ·{" "}
                {s.cloud ? "Account" : "This device"}
              </span>
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}
