"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { FiBell, FiCamera, FiCheck, FiClock, FiPlay, FiSquare, FiUpload, FiVideo } from "react-icons/fi";

import {
  analyzeCloudFrames,
  cloudEventFields,
  createCloudSession,
  listCloudSessions,
  loadCloudSession,
  type BrowserEvent,
  type BrowserSession,
  type VisualCheckResult,
} from "@/lib/browser-sessions";
import { ApiError } from "@/lib/api";

import styles from "./visual-watch.module.css";

type Source = "sample" | "upload" | "webcam";
type RunState = "idle" | "starting" | "watching" | "checking" | "stopped" | "error";

const PRINTER_PROMPT = "Alert me if this 3D print shows visible stringing, spaghetti-like filament, or has detached from the print bed.";
const SAMPLE_PROMPT = PRINTER_PROMPT;

const PRESETS = [
  { label: "3D print failure", prompt: PRINTER_PROMPT },
  { label: "Person at counter", prompt: "Alert me when a person is waiting at the counter and appears to need service." },
  { label: "Empty work station", prompt: "Alert me when this work station is visibly empty." },
];

function elapsed(startedAt: number) {
  return Math.max(0, (Date.now() - startedAt) / 1000);
}

function clock(value: string | number) {
  const date = typeof value === "string" ? new Date(value) : new Date(value);
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

function captureFrame(video: HTMLVideoElement, canvas: HTMLCanvasElement) {
  if (!video.videoWidth || !video.videoHeight) throw new Error("The video is not ready yet.");
  const scale = Math.min(1, 960 / Math.max(video.videoWidth, video.videoHeight));
  canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
  canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
  const context = canvas.getContext("2d");
  if (!context) throw new Error("This browser cannot capture a video frame.");
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.72);
  return { jpeg: dataUrl.split(",")[1], snapshot: dataUrl };
}

export function VisualWatch() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const runningRef = useRef(false);
  const sessionRef = useRef<BrowserSession | null>(null);
  const startedAtRef = useRef(0);
  const uploadUrlRef = useRef<string | null>(null);

  const [source, setSource] = useState<Source>("sample");
  const [uploadName, setUploadName] = useState("");
  const [prompt, setPrompt] = useState(SAMPLE_PROMPT);
  const [intervalSeconds, setIntervalSeconds] = useState(5);
  const [confirmationCount, setConfirmationCount] = useState(1);
  const [state, setState] = useState<RunState>("idle");
  const [status, setStatus] = useState("Ready to monitor");
  const [lastResult, setLastResult] = useState<VisualCheckResult | null>(null);
  const [events, setEvents] = useState<BrowserEvent[]>([]);
  const [checks, setChecks] = useState(0);
  const [nextCheck, setNextCheck] = useState<number | null>(null);
  const [notificationState, setNotificationState] = useState<NotificationPermission | "unsupported">("default");
  const [authRequired, setAuthRequired] = useState(false);

  const stop = useCallback((message = "Monitoring stopped") => {
    runningRef.current = false;
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    const video = videoRef.current;
    if (video) video.pause();
    setNextCheck(null);
    setState("stopped");
    setStatus(message);
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const sessions = (await listCloudSessions("account")).filter((item) => item.job === "custom").slice(0, 6);
      const loaded = await Promise.all(sessions.map((item) => loadCloudSession(item)));
      setEvents(loaded.flatMap((item) => item.events).sort((a, b) => b.at - a.at).slice(0, 20));
    } catch {
      // A new user may have no history yet; monitoring remains available.
    }
  }, []);

  useEffect(() => {
    const notificationTimer = window.setTimeout(() => {
      if (typeof Notification === "undefined") setNotificationState("unsupported");
      else setNotificationState(Notification.permission);
      void loadHistory();
    }, 0);
    return () => {
      window.clearTimeout(notificationTimer);
      runningRef.current = false;
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (uploadUrlRef.current) URL.revokeObjectURL(uploadUrlRef.current);
    };
  }, [loadHistory]);

  const notify = useCallback((summary: string) => {
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      new Notification("Artae found what you asked for", { body: summary, tag: "artae-visual-match" });
    }
  }, []);

  const schedule = useCallback((delaySeconds: number, callback: () => void) => {
    const due = Date.now() + delaySeconds * 1000;
    setNextCheck(due);
    timerRef.current = window.setTimeout(callback, delaySeconds * 1000);
  }, []);

  async function runCheck() {
    if (!runningRef.current || !sessionRef.current || !videoRef.current || !canvasRef.current) return;
    try {
      setState("checking");
      setStatus("Amazon Nova is checking the latest frame…");
      const captured = captureFrame(videoRef.current, canvasRef.current);
      const result = await analyzeCloudFrames(sessionRef.current, [{
        at_seconds: elapsed(startedAtRef.current),
        jpeg: captured.jpeg,
      }]);
      if (!runningRef.current) return;
      setChecks((value) => value + 1);
      setLastResult(result);
      if (result.status === "unsupported") {
        stop(result.summary);
        return;
      }
      if (result.event) {
        const event: BrowserEvent = {
          id: result.event.source_event_id,
          at: Date.now(),
          occurredAt: new Date().toISOString(),
          title: "Condition detected",
          visibility: 0,
          snapshot: captured.snapshot,
          ...cloudEventFields(result.event),
          summary: result.summary,
        };
        setEvents((current) => [event, ...current.filter((item) => item.id !== event.id)].slice(0, 20));
        notify(result.summary);
        setStatus("Condition detected — alert saved");
      } else if (result.status === "match") {
        setStatus(`Possible match ${result.match_streak} of ${result.confirmation_count}`);
      } else if (result.status === "uncertain") {
        setStatus("Nova could not tell from this frame; it will check again");
      } else {
        setStatus("No match — monitoring continues");
      }
      setState("watching");
      schedule(intervalSeconds, () => void runCheck());
    } catch (error) {
      const message = error instanceof Error ? error.message : "The visual check failed.";
      runningRef.current = false;
      setNextCheck(null);
      setState("error");
      setStatus(message);
    }
  }

  async function prepareVideo() {
    const video = videoRef.current;
    if (!video) throw new Error("The video preview is unavailable.");
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (source === "webcam") {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false,
      });
      streamRef.current = stream;
      video.src = "";
      video.srcObject = stream;
      video.loop = false;
      video.muted = true;
    } else {
      if (!video.src) throw new Error(source === "upload" ? "Choose a video first." : "The example video is unavailable.");
      video.srcObject = null;
      video.loop = true;
      video.muted = true;
    }
    await video.play();
    if (!video.videoWidth) await new Promise<void>((resolve) => video.addEventListener("loadeddata", () => resolve(), { once: true }));
  }

  async function start() {
    if (!prompt.trim()) {
      setState("error");
      setStatus("Describe one visible condition to watch for.");
      return;
    }
    try {
      setState("starting");
      setStatus("Opening the video source…");
      setAuthRequired(false);
      await prepareVideo();
      const session: BrowserSession = {
        id: crypto.randomUUID(),
        scope: "account",
        name: prompt.trim().slice(0, 80),
        job: "custom",
        prompt: prompt.trim(),
        createdAt: new Date().toISOString(),
        events: [],
        clips: [],
        cloud: true,
        checkIntervalSeconds: intervalSeconds,
        confirmationCount,
      };
      setStatus("Starting the cloud monitor…");
      await createCloudSession(session);
      sessionRef.current = session;
      startedAtRef.current = Date.now();
      runningRef.current = true;
      setChecks(0);
      setLastResult(null);
      setState("watching");
      setStatus("Monitoring is live");
      await runCheck();
    } catch (error) {
      runningRef.current = false;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      const message = error instanceof Error ? error.message : "Monitoring could not start.";
      if (error instanceof ApiError && error.status === 401) setAuthRequired(true);
      setState("error");
      setStatus(message);
    }
  }

  function chooseSource(next: Source) {
    if (runningRef.current) return;
    const video = videoRef.current;
    setSource(next);
    setUploadName("");
    if (video) {
      video.pause();
      video.srcObject = null;
      video.src = next === "sample" ? "/vision/samples/3d-print-failure.mp4" : "";
      video.loop = next === "sample";
      if (next === "sample") setPrompt(SAMPLE_PROMPT);
    }
  }

  function chooseUpload(file?: File) {
    if (!file || runningRef.current || !videoRef.current) return;
    if (uploadUrlRef.current) URL.revokeObjectURL(uploadUrlRef.current);
    uploadUrlRef.current = URL.createObjectURL(file);
    videoRef.current.srcObject = null;
    videoRef.current.src = uploadUrlRef.current;
    videoRef.current.loop = true;
    setSource("upload");
    setUploadName(file.name);
  }

  async function enableNotifications() {
    if (typeof Notification === "undefined") return setNotificationState("unsupported");
    setNotificationState(await Notification.requestPermission());
  }

  const running = state === "starting" || state === "watching" || state === "checking";

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/" aria-label="Artae home">artae<span>VISION</span></Link>
        <div className={styles.headerStatus}><i className={running ? styles.liveDot : styles.dot} />{running ? "Monitor live" : "Monitor off"}</div>
      </header>

      <section className={styles.intro}>
        <p className={styles.eyebrow}>VISUAL MONITOR</p>
        <h1>Tell your camera what to watch for.</h1>
        <p>Artae checks the video on your schedule. Amazon Nova judges the visible condition, and Strands saves the alert only when action is needed.</p>
      </section>

      <section className={styles.builder} aria-label="Configure visual monitor">
        <div className={styles.step}>
          <div className={styles.stepTitle}><span>1</span><div><strong>Choose a video</strong><small>Use the example, upload a clip, or connect your camera.</small></div></div>
          <div className={styles.sourceGrid}>
            <button className={source === "sample" ? styles.selected : ""} onClick={() => chooseSource("sample")} disabled={running}><FiPlay />3D printer demo</button>
            <label className={source === "upload" ? styles.selected : ""}><FiUpload />{uploadName || "Upload video"}<input type="file" accept="video/*" onChange={(event) => chooseUpload(event.target.files?.[0])} disabled={running} /></label>
            <button className={source === "webcam" ? styles.selected : ""} onClick={() => chooseSource("webcam")} disabled={running}><FiCamera />Webcam</button>
          </div>
        </div>

        <div className={styles.step}>
          <div className={styles.stepTitle}><span>2</span><div><strong>Describe one visible event</strong><small>Your words go directly to Nova. Artae does not rewrite the request.</small></div></div>
          <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} disabled={running} maxLength={500} rows={3} aria-label="Condition to watch for" />
          <div className={styles.presets}>{PRESETS.map((preset) => <button key={preset.label} onClick={() => setPrompt(preset.prompt)} disabled={running}>{preset.label}</button>)}</div>
        </div>

        <div className={styles.stepRow}>
          <div className={styles.compactStep}>
            <label htmlFor="interval"><FiClock /> Check every</label>
            <select id="interval" value={intervalSeconds} onChange={(event) => setIntervalSeconds(Number(event.target.value))} disabled={running}>
              <option value={5}>5 seconds (demo)</option><option value={15}>15 seconds</option><option value={30}>30 seconds</option><option value={60}>1 minute</option>
            </select>
          </div>
          <div className={styles.compactStep}>
            <label htmlFor="confirmations"><FiCheck /> Confirm after</label>
            <select id="confirmations" value={confirmationCount} onChange={(event) => setConfirmationCount(Number(event.target.value))} disabled={running}>
              <option value={1}>1 matching check</option><option value={2}>2 matching checks</option><option value={3}>3 matching checks</option>
            </select>
          </div>
          {!running ? authRequired ? <Link className={styles.startButton} href="/login"><FiPlay /> Sign in to run monitor</Link> : <button className={styles.startButton} onClick={() => void start()}><FiPlay /> Start monitoring</button> : <button className={styles.stopButton} onClick={() => stop()}><FiSquare /> Stop monitor</button>}
        </div>
      </section>

      <section className={styles.monitorGrid}>
        <article className={styles.previewCard}>
          <div className={styles.cardHeader}><div><FiVideo /><strong>{source === "webcam" ? "Webcam" : source === "upload" ? uploadName || "Uploaded video" : "3D printer demo"}</strong></div><span className={running ? styles.livePill : styles.offPill}>{running ? "LIVE" : "OFF"}</span></div>
          <div className={styles.videoWrap}>
            <video ref={videoRef} src="/vision/samples/3d-print-failure.mp4" muted loop playsInline controls={!running} />
            {running && <div className={styles.videoBadge}>{state === "checking" ? "NOVA CHECKING FRAME" : "MONITORING"}</div>}
          </div>
          <canvas ref={canvasRef} hidden />
          <div className={styles.runStatus} role="status"><i className={state === "error" ? styles.errorDot : running ? styles.liveDot : styles.dot} /><div><strong>{status}</strong><small>{checks ? `${checks} check${checks === 1 ? "" : "s"} completed` : "No checks yet"}{nextCheck ? ` · next at ${clock(nextCheck)}` : ""}</small></div></div>
          {lastResult && <div className={styles.lastDecision}><span>Last decision</span><strong>{lastResult.status.replace("_", " ")}</strong><p>{lastResult.summary}</p></div>}
        </article>

        <aside className={styles.alertCard}>
          <div className={styles.cardHeader}><div><FiBell /><strong>Alerts</strong></div><span className={styles.count}>{events.length}</span></div>
          <div className={styles.notificationRow}>
            <div><strong>Browser notifications</strong><small>{notificationState === "granted" ? "Enabled" : notificationState === "denied" ? "Blocked in browser settings" : notificationState === "unsupported" ? "Not supported here" : "Get notified while this page is open"}</small></div>
            {notificationState === "default" && <button onClick={() => void enableNotifications()}>Enable</button>}
          </div>
          <div className={styles.alertList}>
            {events.length === 0 ? <div className={styles.empty}><FiBell /><strong>No detections yet</strong><p>Confirmed matches will appear here with the model’s explanation and timestamp.</p></div> : events.map((event) => (
              <article className={styles.alertItem} key={event.id}>
                {/* Captured frames are short-lived data URLs and cannot use the image optimizer. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                {event.snapshot && <img src={event.snapshot} alt="Frame captured when the condition matched" />}
                <div><div className={styles.alertMeta}><span>CONDITION DETECTED</span><time>{clock(event.occurredAt || event.at)}</time></div><p>{event.summary || event.title}</p><small>Saved to your account · human review recommended</small></div>
              </article>
            ))}
          </div>
        </aside>
      </section>
    </main>
  );
}
