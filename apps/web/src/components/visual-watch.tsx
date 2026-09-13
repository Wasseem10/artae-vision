"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { FiBell, FiCamera, FiCheck, FiClock, FiPlay, FiSquare, FiUpload, FiVideo } from "react-icons/fi";

import {
  analyzeCloudFrames,
  analyzePublicDemo,
  cloudEventFields,
  createCloudSession,
  createPublicDemo,
  listCloudSessions,
  loadCloudSession,
  type BrowserEvent,
  type BrowserSession,
  type PublicDemoSession,
  type VisualCheckResult,
} from "@/lib/browser-sessions";
import styles from "./visual-watch.module.css";

type Source = "sample" | "upload" | "webcam";
type RunState = "idle" | "starting" | "sampling" | "checking" | "watching" | "stopped" | "error";
type Stage = "idle" | "video" | "frames" | "nova" | "strands" | "complete";
type CapturedFrame = { at_seconds: number; jpeg: string; snapshot: string };

const PRINTER_PROMPT = "Alert me when this 3D printer is actively extruding green filament onto the print bed.";
const PRESETS = [
  { label: "Printer running", prompt: PRINTER_PROMPT },
  { label: "Print failure", prompt: "Alert me if this 3D print shows visible stringing, loose filament, or has detached from the print bed." },
  { label: "Person waiting", prompt: "Alert me when a person is visibly waiting at the counter." },
  { label: "Empty station", prompt: "Alert me when this work station is visibly empty." },
];

function elapsed(startedAt: number) { return Math.max(0, (Date.now() - startedAt) / 1000); }
function clock(value: string | number) { return new Date(value).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); }

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

function waitForVideo(video: HTMLVideoElement) {
  if (video.readyState >= 2 && video.videoWidth) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error("The video could not be opened.")), 8000);
    video.addEventListener("loadeddata", () => { window.clearTimeout(timeout); resolve(); }, { once: true });
  });
}

function seek(video: HTMLVideoElement, at: number) {
  return new Promise<void>((resolve, reject) => {
    if (Math.abs(video.currentTime - at) < 0.04) return resolve();
    const timeout = window.setTimeout(() => reject(new Error("Could not sample this video.")), 5000);
    video.addEventListener("seeked", () => { window.clearTimeout(timeout); resolve(); }, { once: true });
    video.currentTime = at;
  });
}

async function captureStoryboard(
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
  onProgress: (captured: number, total: number) => void,
) {
  await waitForVideo(video);
  if (!Number.isFinite(video.duration) || video.duration <= 0) throw new Error("This video does not expose a readable duration.");
  if (video.duration > 7200) throw new Error("For this demo, choose a video shorter than two hours.");
  video.pause();
  // Four public AWS checks × eight images gives recorded clips much denser
  // coverage than the original single eight-frame request.
  const count = Math.min(32, Math.max(8, Math.ceil(video.duration / 6)));
  const frames: CapturedFrame[] = [];
  for (let index = 0; index < count; index += 1) {
    const at = Math.min(video.duration - 0.05, ((index + 0.5) / count) * video.duration);
    await seek(video, Math.max(0, at));
    frames.push({ at_seconds: at, ...captureFrame(video, canvas) });
    onProgress(index + 1, count);
  }
  await seek(video, 0);
  return frames;
}

function isStepDone(current: Stage, target: Stage, hasAction: boolean) {
  if (target === "strands") return hasAction;
  const order: Stage[] = ["idle", "video", "frames", "nova", "complete"];
  return order.indexOf(current) >= order.indexOf(target);
}

export function VisualWatch({ mode = "account" }: { mode?: "account" | "public" }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const runningRef = useRef(false);
  const sessionRef = useRef<BrowserSession | null>(null);
  const publicSessionRef = useRef<PublicDemoSession | null>(null);
  const startedAtRef = useRef(0);
  const uploadUrlRef = useRef<string | null>(null);

  const [source, setSource] = useState<Source>("sample");
  const [uploadName, setUploadName] = useState("");
  const [prompt, setPrompt] = useState(PRINTER_PROMPT);
  const [intervalSeconds, setIntervalSeconds] = useState(5);
  const [confirmationCount, setConfirmationCount] = useState(1);
  const [state, setState] = useState<RunState>("idle");
  const [stage, setStage] = useState<Stage>("idle");
  const [status, setStatus] = useState("Ready to analyze");
  const [lastResult, setLastResult] = useState<VisualCheckResult | null>(null);
  const [events, setEvents] = useState<BrowserEvent[]>([]);
  const [checks, setChecks] = useState(0);
  const [nextCheck, setNextCheck] = useState<number | null>(null);
  const [notificationState, setNotificationState] = useState<NotificationPermission | "unsupported">("default");
  const running = state === "starting" || state === "sampling" || state === "checking" || state === "watching";
  const recorded = source !== "webcam";

  const stop = useCallback((message = "Monitor stopped") => {
    runningRef.current = false;
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    videoRef.current?.pause();
    setNextCheck(null);
    setState("stopped");
    setStatus(message);
  }, []);

  const loadHistory = useCallback(async () => {
    if (mode === "public") return;
    try {
      const latest = (await listCloudSessions("account")).filter((item) => item.job === "custom").slice(0, 1);
      const loaded = await Promise.all(latest.map((item) => loadCloudSession(item)));
      setEvents(loaded.flatMap((item) => item.events).sort((a, b) =>
        new Date(b.occurredAt || b.at).getTime() - new Date(a.occurredAt || a.at).getTime()
      ).slice(0, 10));
    } catch { /* Monitoring remains available when history cannot load. */ }
  }, [mode]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setNotificationState(typeof Notification === "undefined" ? "unsupported" : Notification.permission);
      void loadHistory();
    }, 0);
    return () => {
      window.clearTimeout(timer);
      runningRef.current = false;
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (uploadUrlRef.current) URL.revokeObjectURL(uploadUrlRef.current);
    };
  }, [loadHistory]);

  const notify = useCallback((summary: string) => {
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      new Notification("Artae detected your condition", { body: summary, tag: "artae-visual-match" });
    }
  }, []);

  async function openSession() {
    if (mode === "public") {
      publicSessionRef.current = await createPublicDemo(prompt.trim());
      return;
    }
    const session: BrowserSession = {
      id: crypto.randomUUID(), scope: "account", name: prompt.trim().slice(0, 80), job: "custom",
      prompt: prompt.trim(), createdAt: new Date().toISOString(), events: [], clips: [], cloud: true,
      checkIntervalSeconds: intervalSeconds, confirmationCount,
    };
    await createCloudSession(session);
    sessionRef.current = session;
  }

  async function analyze(
    frames: CapturedFrame[],
    batch?: { current: number; total: number },
  ) {
    setStage("nova");
    setState("checking");
    setStatus(batch
      ? `Amazon Nova is analyzing batch ${batch.current} of ${batch.total}…`
      : `Amazon Nova is analyzing ${frames.length} sampled frame${frames.length === 1 ? "" : "s"}…`);
    const payload = frames.map(({ at_seconds, jpeg }) => ({ at_seconds, jpeg }));
    const result = mode === "public"
      ? await analyzePublicDemo(publicSessionRef.current!, payload)
      : await analyzeCloudFrames(sessionRef.current!, payload);
    setChecks((value) => value + 1);
    setLastResult(result);
    setStage(result.event ? "strands" : "complete");
    if (result.event) {
      const matched = frames[result.matched_frame_index ?? frames.length - 1] ?? frames.at(-1)!;
      const fields = cloudEventFields(result.event);
      const event: BrowserEvent = {
        id: result.event.source_event_id, at: matched.at_seconds, occurredAt: new Date().toISOString(),
        title: "Condition detected", visibility: 0, snapshot: matched.snapshot, ...fields,
        saved: mode === "account", summary: result.summary,
      };
      setEvents((current) => [event, ...current.filter((item) => item.id !== event.id)].slice(0, 10));
      notify(result.summary);
      setStage("complete");
      setStatus(mode === "account" ? "Condition detected — alert saved" : "Condition detected — Strands prepared the response");
    } else if (result.status === "no_match") {
      setStatus(recorded
        ? batch && batch.current < batch.total
          ? `No match in batch ${batch.current} — continuing through the video…`
          : "Condition not detected in the sampled video"
        : "No match — monitoring continues");
    } else if (result.status === "uncertain") {
      setStatus(recorded
        ? batch && batch.current < batch.total
          ? `Batch ${batch.current} was uncertain — continuing through the video…`
          : "Nova could not confirm the condition from this video"
        : "Nova was uncertain — monitoring continues");
    } else if (result.status === "unsupported") setStatus(result.summary);
    return result;
  }

  async function runWebcamCheck() {
    if (!runningRef.current || !videoRef.current || !canvasRef.current) return;
    try {
      const frame = { at_seconds: elapsed(startedAtRef.current), ...captureFrame(videoRef.current, canvasRef.current) };
      const result = await analyze([frame]);
      if (!runningRef.current) return;
      if (result.status === "unsupported" || (mode === "public" && result.checks_remaining === 0)) {
        stop(result.status === "unsupported" ? result.summary : "Public demo complete — start another run for more checks");
        return;
      }
      setState("watching");
      const due = Date.now() + intervalSeconds * 1000;
      setNextCheck(due);
      timerRef.current = window.setTimeout(() => void runWebcamCheck(), intervalSeconds * 1000);
    } catch (error) {
      runningRef.current = false;
      setState("error");
      setStatus(error instanceof Error ? error.message : "The visual check failed.");
    }
  }

  async function prepareVideo() {
    const video = videoRef.current;
    if (!video) throw new Error("The video preview is unavailable.");
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (source === "webcam") {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      streamRef.current = stream;
      video.src = "";
      video.srcObject = stream;
      video.loop = false;
      await video.play();
    } else {
      if (!video.src) throw new Error("Choose a video first.");
      video.srcObject = null;
      video.loop = false;
      await waitForVideo(video);
    }
    setStage("video");
  }

  async function start() {
    if (!prompt.trim()) { setState("error"); setStatus("Describe one visible condition to watch for."); return; }
    try {
      runningRef.current = true;
      setState("starting"); setStage("idle"); setStatus("Opening the video source…");
      setLastResult(null); setChecks(0); setNextCheck(null);
      if (mode === "public") setEvents([]);
      await prepareVideo();
      setStatus(mode === "public" ? "Opening a rate-limited AWS demo session…" : "Opening your account monitor…");
      await openSession();
      startedAtRef.current = Date.now();
      if (recorded) {
        setState("sampling"); setStatus("Sampling moments across the video…");
        const frames = await captureStoryboard(
          videoRef.current!,
          canvasRef.current!,
          (captured, total) => setStatus(`Sampling moment ${captured} of ${total} across the video…`),
        );
        setStage("frames");
        const batches = Array.from(
          { length: Math.ceil(frames.length / 8) },
          (_, index) => frames.slice(index * 8, index * 8 + 8),
        );
        for (let index = 0; index < batches.length; index += 1) {
          const result = await analyze(batches[index], {
            current: index + 1,
            total: batches.length,
          });
          if (result.event || result.status === "unsupported") break;
        }
        runningRef.current = false;
        setState("stopped");
      } else {
        setState("watching"); setStatus("Live monitor started");
        await runWebcamCheck();
      }
    } catch (error) {
      runningRef.current = false;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      setState("error");
      setStatus(error instanceof Error ? error.message : "Monitoring could not start.");
    }
  }

  function chooseSource(next: Source) {
    if (runningRef.current) return;
    const video = videoRef.current;
    setSource(next); setUploadName(""); setLastResult(null); setStage("idle");
    setStatus(next === "webcam" ? "Ready to monitor" : "Ready to analyze");
    if (next !== "webcam") setConfirmationCount(1);
    if (video) {
      video.pause(); video.srcObject = null; video.src = next === "sample" ? "/vision/samples/3d-print-failure.mp4" : "";
      if (next === "sample") setPrompt(PRINTER_PROMPT);
    }
  }

  function chooseUpload(file?: File) {
    if (!file || runningRef.current || !videoRef.current) return;
    if (uploadUrlRef.current) URL.revokeObjectURL(uploadUrlRef.current);
    uploadUrlRef.current = URL.createObjectURL(file);
    videoRef.current.srcObject = null;
    videoRef.current.src = uploadUrlRef.current;
    videoRef.current.loop = false;
    setSource("upload"); setUploadName(file.name); setLastResult(null); setStage("idle");
    if (mode === "public") setEvents([]);
    setStatus("Video ready — describe what to find");
  }

  async function enableNotifications() {
    if (typeof Notification === "undefined") return setNotificationState("unsupported");
    setNotificationState(await Notification.requestPermission());
  }

  const steps: { stage: Stage; label: string }[] = [
    { stage: "video", label: "Video ready" }, { stage: "frames", label: "Frames sampled" },
    { stage: "nova", label: "Nova analyzed" }, { stage: "strands", label: "Strands acted" },
  ];

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/" aria-label="Artae home">artae<span>VISION</span></Link>
        <div className={styles.headerStatus}><i className={running ? styles.liveDot : styles.dot} />{running ? "Analysis running" : "Ready"}</div>
      </header>

      <section className={styles.intro}>
        <div><p className={styles.eyebrow}>AI VIDEO AGENT</p><h1>Describe it. Artae finds it.</h1></div>
        <p>Upload a video or connect a camera. Amazon Nova checks your exact request, then a Strands agent prepares the alert and evidence.</p>
      </section>

      <section className={styles.workbench}>
        <section className={styles.builder} aria-label="Configure visual monitor">
          {mode === "public" && <div className={styles.demoNote}><strong>Live AWS demo</strong><span>No account required · up to 4 checks</span></div>}
          <div className={styles.step}>
            <div className={styles.stepTitle}><span>1</span><div><strong>Choose a video</strong><small>The example shows an active print. Upload any browser-playable clip to check your own event.</small></div></div>
            <div className={styles.sourceGrid}>
              <button className={source === "sample" ? styles.selected : ""} onClick={() => chooseSource("sample")} disabled={running}><FiPlay />Example</button>
              <label className={source === "upload" ? styles.selected : ""}><FiUpload />{uploadName || "Upload"}<input type="file" accept="video/*" onChange={(event) => chooseUpload(event.target.files?.[0])} disabled={running} /></label>
              <button className={source === "webcam" ? styles.selected : ""} onClick={() => chooseSource("webcam")} disabled={running}><FiCamera />Webcam</button>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepTitle}><span>2</span><div><strong>What should Artae find?</strong><small>Use one visible, observable condition.</small></div></div>
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} disabled={running} maxLength={500} rows={4} aria-label="Condition to watch for" />
            <div className={styles.presets}>{PRESETS.map((preset) => <button key={preset.label} onClick={() => setPrompt(preset.prompt)} disabled={running}>{preset.label}</button>)}</div>
          </div>

          <div className={styles.stepRow}>
            {recorded ? <div className={styles.storyboardHint}><FiCheck /><div><strong>Multi-pass video scan</strong><small>Up to 32 moments are checked across the clip in four Nova batches.</small></div></div> : <>
              <div className={styles.compactStep}><label htmlFor="interval"><FiClock /> Check every</label><select id="interval" value={intervalSeconds} onChange={(event) => setIntervalSeconds(Number(event.target.value))} disabled={running}><option value={5}>5 seconds</option><option value={15}>15 seconds</option><option value={30}>30 seconds</option><option value={60}>1 minute</option></select></div>
              <div className={styles.compactStep}><label htmlFor="confirmations"><FiCheck /> Confirm after</label><select id="confirmations" value={confirmationCount} onChange={(event) => setConfirmationCount(Number(event.target.value))} disabled={running}><option value={1}>1 match</option><option value={2}>2 matches</option><option value={3}>3 matches</option></select></div>
            </>}
            {!running ? <button className={styles.startButton} onClick={() => void start()}><FiPlay />{recorded ? "Analyze video" : "Start monitor"}</button> : <button className={styles.stopButton} onClick={() => stop()}><FiSquare />Stop</button>}
          </div>
        </section>

        <article className={styles.previewCard}>
          <div className={styles.cardHeader}><div><FiVideo /><strong>{source === "webcam" ? "Webcam" : source === "upload" ? uploadName || "Uploaded video" : "Active print example"}</strong></div><span className={running ? styles.livePill : styles.offPill}>{running ? "RUNNING" : "READY"}</span></div>
          <div className={styles.videoWrap}>
            <video ref={videoRef} src="/vision/samples/3d-print-failure.mp4" muted playsInline controls={!running} />
            {running && <div className={styles.videoBadge}>{state === "sampling" ? "SAMPLING VIDEO" : state === "checking" ? "NOVA ANALYZING" : "MONITORING"}</div>}
          </div>
          <canvas ref={canvasRef} hidden />
          <div className={styles.pipeline} aria-label="Analysis progress">
            {steps.map((item) => <div className={isStepDone(stage, item.stage, Boolean(lastResult?.event)) ? styles.pipelineDone : ""} key={item.stage}><i />{item.label}</div>)}
          </div>
          <div className={styles.runStatus} role="status"><i className={state === "error" ? styles.errorDot : running ? styles.liveDot : styles.dot} /><div><strong>{status}</strong><small>{checks ? `${checks} AWS check${checks === 1 ? "" : "s"} completed` : "No AWS checks yet"}{nextCheck ? ` · next at ${clock(nextCheck)}` : ""}</small></div></div>
          {lastResult && <div className={`${styles.lastDecision} ${lastResult.status === "match" ? styles.matchDecision : ""}`}><span>Nova decision</span><strong>{lastResult.status === "match" ? "Detected" : lastResult.status.replace("_", " ")}</strong><p>{lastResult.summary}</p></div>}
        </article>

        <aside className={styles.alertCard}>
          <div className={styles.cardHeader}><div><FiBell /><strong>{mode === "public" ? "This run" : "Latest run"}</strong></div><span className={styles.count}>{events.length}</span></div>
          <div className={styles.notificationRow}>
            <div><strong>In-app alerts are on</strong><small>{notificationState === "granted" ? "Browser notifications also enabled" : "Optional browser alerts work while this page is open"}</small></div>
            {notificationState === "default" && <button onClick={() => void enableNotifications()}>Enable</button>}
          </div>
          <div className={styles.alertList}>
            {events.length === 0 ? <div className={styles.empty}><FiBell /><strong>No match yet</strong><p>When Nova confirms your condition, the matching frame and Strands actions appear here.</p></div> : events.map((event) => (
              <article className={styles.alertItem} key={event.id}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                {event.snapshot && <img src={event.snapshot} alt="Frame that best supports the detected condition" />}
                <div><div className={styles.alertMeta}><span>DETECTED</span><time>{clock(event.occurredAt || event.at)}</time></div><h3>{event.title}</h3><p>{event.summary}</p><div className={styles.actionTags}>{(event.actions || []).map((action) => <span key={action}>{action.replaceAll("_", " ")}</span>)}</div><small>{event.saved ? "Saved to your account" : "Temporary demo result"} · human review recommended</small></div>
              </article>
            ))}
          </div>
        </aside>
      </section>
    </main>
  );
}
