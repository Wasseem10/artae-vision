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
  type ConditionResult,
} from "@/lib/browser-sessions";
import { mergeConditions, readConditions } from "@/lib/condition-results";
import { detailedTimes, episodes, mergeObservations, refinementWindows, timeLabel, type Timeline } from "@/lib/video-timeline";
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
  isActive: () => boolean,
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
    if (!isActive()) throw new Error("Scan stopped");
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
  const runIdRef = useRef(0);
  const resultsRef = useRef<ConditionResult[]>([]);
  const timelineRef = useRef<Timeline>({});
  const sessionRef = useRef<BrowserSession | null>(null);
  const publicSessionRef = useRef<PublicDemoSession | null>(null);
  const startedAtRef = useRef(0);
  const uploadUrlRef = useRef<string | null>(null);

  const [source, setSource] = useState<Source>("sample");
  const [uploadName, setUploadName] = useState("");
  const [prompt, setPrompt] = useState(PRINTER_PROMPT);
  const [intervalSeconds, setIntervalSeconds] = useState(5);
  const [confirmationCount, setConfirmationCount] = useState(1);
  const [scanMode, setScanMode] = useState("quick");
  const [sampleInterval, setSampleInterval] = useState(2);
  const [timeline, setTimeline] = useState<Timeline>({});
  const [state, setState] = useState<RunState>("idle");
  const [stage, setStage] = useState<Stage>("idle");
  const [status, setStatus] = useState("Ready to analyze");
  const [lastResult, setLastResult] = useState<VisualCheckResult | null>(null);
  const [conditionResults, setConditionResults] = useState<ConditionResult[]>([]);
  const [scanComplete, setScanComplete] = useState(false);
  const [events, setEvents] = useState<BrowserEvent[]>([]);
  const [checks, setChecks] = useState(0);
  const [nextCheck, setNextCheck] = useState<number | null>(null);
  const [notificationState, setNotificationState] = useState<NotificationPermission | "unsupported">("default");
  const running = state === "starting" || state === "sampling" || state === "checking" || state === "watching";
  const recorded = source !== "webcam";
  const detailed = recorded && scanMode === "detailed";

  const stop = useCallback((message = "Monitor stopped") => {
    runIdRef.current += 1;
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
      publicSessionRef.current = await createPublicDemo(prompt.trim(), detailed);
      return;
    }
    const session: BrowserSession = {
      id: crypto.randomUUID(), scope: "account", name: prompt.trim().slice(0, 80), job: "custom",
      prompt: prompt.trim(), createdAt: new Date().toISOString(), events: [], clips: [], cloud: true,
      checkIntervalSeconds: intervalSeconds, confirmationCount: recorded ? 1 : confirmationCount,
    };
    await createCloudSession(session);
    sessionRef.current = session;
  }

  async function analyze(
    frames: CapturedFrame[],
    batch?: { current: number; total: number },
    refinement = false,
  ) {
    const runId = runIdRef.current;
    setStage("nova");
    setState("checking");
    setStatus(batch
      ? `Amazon Nova is analyzing batch ${batch.current} of ${batch.total}…`
      : `Amazon Nova is analyzing ${frames.length} sampled frame${frames.length === 1 ? "" : "s"}…`);
    const payload = frames.map(({ at_seconds, jpeg }) => ({ at_seconds, jpeg }));
    const result = mode === "public"
      ? await analyzePublicDemo(publicSessionRef.current!, payload, refinement)
      : await analyzeCloudFrames(sessionRef.current!, payload, detailed, refinement);
    if (runId !== runIdRef.current || !runningRef.current) return result;
    const answers = (result.conditions || []).map((item) => ({
      ...item,
      at_seconds: item.matched_frame_index == null ? undefined : frames[item.matched_frame_index]?.at_seconds,
    }));
    resultsRef.current = mergeConditions(resultsRef.current, answers);
    setConditionResults(resultsRef.current);
    if (detailed) {
      const updated = { ...timelineRef.current };
      for (let index = 0; index < readConditions(prompt).length; index++) {
        const answer = answers.find((item) => item.condition_index === index);
        const valid = !answer?.subject_ambiguous && answer?.frame_states?.length === frames.length;
        updated[index] = mergeObservations(updated[index] || [], frames.map((frame, i) => ({
          at: frame.at_seconds, state: valid ? answer!.frame_states![i] : "uncertain",
        })));
      }
      timelineRef.current = updated;
      setTimeline(updated);
    }
    setChecks((value) => value + 1);
    setLastResult(result);
    setStage("frames");
    if (result.event) {
      const matched = result.matched_frame_index == null ? undefined : frames[result.matched_frame_index];
      const fields = cloudEventFields(result.event);
      const event: BrowserEvent = {
        id: result.event.source_event_id, at: matched?.at_seconds ?? frames[0].at_seconds, occurredAt: new Date().toISOString(),
        title: "Conditions detected", visibility: 0, snapshot: matched?.snapshot, ...fields,
        saved: mode === "account", summary: result.summary,
      };
      setEvents((current) => [event, ...current.filter((item) => item.id !== event.id)].slice(0, 10));
      notify(result.summary);
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
    const runId = runIdRef.current;
    try {
      const frame = { at_seconds: elapsed(startedAtRef.current), ...captureFrame(videoRef.current, canvasRef.current) };
      const result = await analyze([frame]);
      if (!runningRef.current || runId !== runIdRef.current) return;
      if (result.status === "unsupported" || (mode === "public" && result.checks_remaining === 0)) {
        stop(result.status === "unsupported" ? result.summary : "Public demo complete — start another run for more checks");
        return;
      }
      setState("watching");
      const due = Date.now() + intervalSeconds * 1000;
      setNextCheck(due);
      timerRef.current = window.setTimeout(() => void runWebcamCheck(), intervalSeconds * 1000);
    } catch (error) {
      if (runId !== runIdRef.current) return;
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
    const conditions = readConditions(prompt);
    if (!conditions.length || conditions.length > 5) {
      setState("error"); setStatus("Enter one to five conditions, each on its own line."); return;
    }
    const runId = ++runIdRef.current;
    try {
      runningRef.current = true;
      setState("starting"); setStage("idle"); setStatus("Opening the video source…");
      setLastResult(null); setChecks(0); setNextCheck(null);
      setConditionResults([]); resultsRef.current = []; setScanComplete(false); setEvents([]);
      setTimeline({}); timelineRef.current = {};
      await prepareVideo();
      if (runId !== runIdRef.current) return;
      // Validate before opening a paid run. Never silently stretch the user's cadence.
      const times = detailed ? detailedTimes(videoRef.current!.duration, sampleInterval) : [];
      setStatus(mode === "public" ? "Opening a rate-limited AWS demo session…" : "Opening your account monitor…");
      await openSession();
      if (runId !== runIdRef.current) return;
      startedAtRef.current = Date.now();
      if (recorded) {
        if (detailed) {
          const active = () => runId === runIdRef.current && runningRef.current;
          const video = videoRef.current!, canvas = canvasRef.current!;
          video.pause();
          const captureTimes = async (points: number[]) => {
            const batchFrames: CapturedFrame[] = [];
            setState("sampling");
            for (const at of points) {
              if (!active()) return [];
              await seek(video, at);
              if (!active()) return [];
              batchFrames.push({ at_seconds: at, ...captureFrame(video, canvas) });
            }
            return batchFrames;
          };
          const total = Math.max(1, Math.ceil((times.length - 1) / 7));
          for (let batch = 0; batch < total; batch++) {
            if (batch > 0 && mode === "account") await new Promise((resolve) => window.setTimeout(resolve, 3100));
            if (!active()) return;
            setStatus(`Detailed scan ${batch + 1} of ${total} — sampling every ${sampleInterval}s…`);
            const frames = await captureTimes(times.slice(batch * 7, batch * 7 + 8));
            if (!active()) return;
            await analyze(frames, { current: batch + 1, total });
          }
          if (!active()) return;
          const windows = refinementWindows(timelineRef.current);
          for (let i = 0; i < windows.length; i++) {
            if (mode === "account") await new Promise((resolve) => window.setTimeout(resolve, 3100));
            if (!active()) return;
            const [from, to] = windows[i];
            setStatus(`Refining event boundary ${i + 1} of ${windows.length}…`);
            const frames = await captureTimes(Array.from({ length: 8 }, (_, j) => from + (to - from) * j / 7));
            if (!active()) return;
            await analyze(frames, undefined, true);
          }
          if (!active()) return;
          await seek(video, 0);
          if (!active()) return;
          runningRef.current = false;
          setState("stopped"); setStage("complete"); setScanComplete(true);
          setStatus(`Detailed scan complete — ${times.length} samples plus ${windows.length} boundary rechecks. Review timing estimates below.`);
          return;
        }
        setState("sampling"); setStatus("Sampling moments across the video…");
        const frames = await captureStoryboard(
          videoRef.current!,
          canvasRef.current!,
          (captured, total) => setStatus(`Sampling moment ${captured} of ${total} across the video…`),
          () => runId === runIdRef.current && runningRef.current,
        );
        setStage("frames");
        const batches = Array.from(
          { length: Math.ceil(frames.length / 8) },
          (_, index) => frames.slice(index * 8, index * 8 + 8),
        );
        for (let index = 0; index < batches.length; index += 1) {
          if (index > 0 && mode === "account") await new Promise((resolve) => window.setTimeout(resolve, 3100));
          if (runId !== runIdRef.current || !runningRef.current) return;
          await analyze(batches[index], {
            current: index + 1,
            total: batches.length,
          });
          if (runId !== runIdRef.current || !runningRef.current) return;
        }
        runningRef.current = false;
        setState("stopped"); setStage("complete"); setScanComplete(true);
        const found = resultsRef.current.filter((item) => item.status === "match").length;
        setStatus(`Scan complete — ${found} of ${conditions.length} conditions detected in sampled frames`);
      } else {
        setState("watching"); setStatus("Live monitor started");
        await runWebcamCheck();
      }
    } catch (error) {
      if (runId !== runIdRef.current) return;
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
    setConditionResults([]); setScanComplete(false);
    setTimeline({}); timelineRef.current = {};
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
    setConditionResults([]); setScanComplete(false);
    setTimeline({}); timelineRef.current = {};
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
          {mode === "public" && <div className={styles.demoNote}><strong>Live AWS demo</strong><span>No account required · up to {detailed ? 32 : 4} checks</span></div>}
          <div className={styles.step}>
            <div className={styles.stepTitle}><span>1</span><div><strong>Choose a video</strong><small>The example shows an active print. Upload any browser-playable clip to check your own event.</small></div></div>
            <div className={styles.sourceGrid}>
              <button className={source === "sample" ? styles.selected : ""} onClick={() => chooseSource("sample")} disabled={running}><FiPlay />Example</button>
              <label className={source === "upload" ? styles.selected : ""}><FiUpload />{uploadName || "Upload"}<input type="file" accept="video/*" onChange={(event) => chooseUpload(event.target.files?.[0])} disabled={running} /></label>
              <button className={source === "webcam" ? styles.selected : ""} onClick={() => chooseSource("webcam")} disabled={running}><FiCamera />Webcam</button>
            </div>
          </div>

          <div className={styles.step}>
            <div className={styles.stepTitle}><span>2</span><div><strong>What should Artae find?</strong><small>Check up to 5 conditions. Put each on a separate line.</small></div></div>
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} disabled={running} maxLength={500} rows={5} aria-label="Conditions to watch for" placeholder={"A person wearing blue is visible.\nA person is lying on the floor."} />
            <small className={styles.conditionCount}>{readConditions(prompt).length} / 5 conditions · 500 characters total</small>
            <div className={styles.presets}>{PRESETS.map((preset) => <button key={preset.label} onClick={() => setPrompt(preset.prompt)} disabled={running}>{preset.label}</button>)}</div>
          </div>

          <div className={styles.stepRow}>
            {recorded ? <>
              <div className={styles.compactStep}><label htmlFor="scan-mode">Scan mode</label><select id="scan-mode" value={scanMode} onChange={(event) => setScanMode(event.target.value)} disabled={running}><option value="quick">Quick — check conditions</option><option value="detailed">Detailed — event timeline & duration</option></select></div>
              {detailed && <div className={styles.compactStep}><label htmlFor="sample-interval">Sample video every</label><select id="sample-interval" value={sampleInterval} onChange={(event) => setSampleInterval(Number(event.target.value))} disabled={running}>{[0.5, 1, 2, 5, 10].map((value) => <option key={value} value={value}>{value} seconds</option>)}</select></div>}
              <div className={styles.storyboardHint}><FiClock /><div><strong>{detailed ? "Timing estimates, not exact measurements" : "Multi-pass video scan"}</strong><small>{detailed ? "One clearly described subject, fixed camera. Up to 192 samples / 10 minutes, with up to 4 closer boundary checks. May take several minutes. Occlusion and missing boundaries remain unknown. Shorter intervals cost more AWS checks." : "Up to 32 moments are checked across the clip in four Nova batches."}</small></div></div>
              {detailed && <div className={styles.presets}><button disabled={running} onClick={() => setPrompt("How long is the single car stationary in the parking space? Measure from stopping until it moves away.")}>Car parked duration</button><button disabled={running} onClick={() => setPrompt("How long does the single person take to get back up? Measure from first visibly on the ground until standing upright again.")}>Time to stand up</button></div>}
            </> : <>
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
            {steps.map((item) => <div className={isStepDone(stage, item.stage, events.some((event) => event.coordinator === "completed")) ? styles.pipelineDone : ""} key={item.stage}><i />{item.label}</div>)}
          </div>
          <div className={styles.runStatus} role="status"><i className={state === "error" ? styles.errorDot : running ? styles.liveDot : styles.dot} /><div><strong>{status}</strong><small>{checks ? `${checks} AWS check${checks === 1 ? "" : "s"} completed` : "No AWS checks yet"}{nextCheck ? ` · next at ${clock(nextCheck)}` : ""}</small></div></div>
          {conditionResults.map((item) => <div className={`${styles.lastDecision} ${item.status === "match" ? styles.matchDecision : ""}`} key={item.condition_index}>
            <span>Condition {item.condition_index + 1}</span>
            <strong>{item.status === "match" ? "Detected" : item.status === "no_match" ? scanComplete ? "Not detected in sampled frames" : "Not seen yet" : item.status === "uncertain" ? "Uncertain" : "Unsupported"}</strong>
            <h3>{item.condition}</h3><p>{item.summary}</p>
            {timeline[item.condition_index] && <div className={styles.timing}>
              <p><strong>Event timeline {scanComplete ? "— sampled estimates" : "— provisional"}</strong></p>
              {item.interval_definition && <p>Measured interval: {item.interval_definition}</p>}
              <p>{timeline[item.condition_index].length} sampled timestamps · {timeline[item.condition_index].filter((point) => point.state === "uncertain").length} uncertain</p>
              {episodes(timeline[item.condition_index]).length === 0 && <p>No measurable active interval established. Unknown observations are not proof of absence.</p>}
              {episodes(timeline[item.condition_index]).map((episode, index) => <section key={episode.first} className={styles.episode}>
                <strong>Interval {index + 1}</strong>
                <p>{episode.maxDuration === null
                  ? `Observed active span: ${episode.minDuration.toFixed(1)}s. Full duration unknown — a boundary is outside the recording, obscured, or not yet checked.`
                  : `Estimated duration: ${episode.minDuration.toFixed(1)}–${episode.maxDuration.toFixed(1)} seconds.`}</p>
                <p>Start: {episode.startAfter === null ? `already active or unclear before ${timeLabel(episode.first)}` : `${timeLabel(episode.startAfter)}–${timeLabel(episode.first)}`}. End: {episode.endBy === null ? `still active or unclear after ${timeLabel(episode.last)}` : `${timeLabel(episode.last)}–${timeLabel(episode.endBy)}`}.</p>
                <button className={styles.momentButton} disabled={running || !recorded} onClick={() => { if (videoRef.current) videoRef.current.currentTime = episode.first; }}>Review start {timeLabel(episode.first)}</button>{" "}
                <button className={styles.momentButton} disabled={running || !recorded} onClick={() => { if (videoRef.current) videoRef.current.currentTime = episode.endBy ?? episode.last; }}>Review end {timeLabel(episode.endBy ?? episode.last)}</button>
              </section>)}
              <p>Assumes the same subject and a continuous event between samples. Brief changes can be missed. A person standing up does not establish their safety.</p>
              <details><summary>Inspect frame observations</summary><div className={styles.observations}>{timeline[item.condition_index].map((point) => <button key={point.at} disabled={running || !recorded} onClick={() => { if (videoRef.current) videoRef.current.currentTime = point.at; }}>{timeLabel(point.at)} · {point.state}</button>)}</div></details>
            </div>}
            {item.at_seconds !== undefined && <button className={styles.momentButton} onClick={() => { if (!running && videoRef.current && recorded) videoRef.current.currentTime = item.at_seconds!; }} disabled={running || !recorded}>View at {Math.floor(item.at_seconds / 60)}:{Math.floor(item.at_seconds % 60).toString().padStart(2, "0")}</button>}
          </div>)}
          {lastResult && !conditionResults.length && <div className={styles.lastDecision}><p>{lastResult.summary}</p></div>}
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
