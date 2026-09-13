"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { FiBell, FiCamera, FiCheck, FiClock, FiLoader, FiPlay, FiSquare, FiUpload, FiVideo } from "react-icons/fi";

import {
  analyzeCloudFrames,
  analyzePublicDemo,
  cloudEventFields,
  createCloudSession,
  createPublicDemo,
  getNotificationCapabilities,
  sendTestSms,
  listCloudSessions,
  loadCloudSession,
  type BrowserEvent,
  type BrowserSession,
  type PublicDemoSession,
  type VisualCheckResult,
  type ConditionResult,
} from "@/lib/browser-sessions";
import { mergeConditions, readConditions } from "@/lib/condition-results";
import { DETAILED_INTERVALS, MAX_VIDEO_DURATION_SECONDS, detailedTimes, episodes, mergeObservations, recommendedDetailedInterval, refinementWindows, timeLabel, timelineStatus, type Timeline } from "@/lib/video-timeline";
import styles from "./visual-watch.module.css";

type Source = "upload" | "webcam";
type RunState = "idle" | "starting" | "sampling" | "checking" | "watching" | "stopped" | "error";
type Stage = "idle" | "video" | "frames" | "nova" | "strands" | "complete";
type UploadState = "empty" | "preparing" | "ready" | "error";
type CapturedFrame = { at_seconds: number; jpeg: string; snapshot: string };

const FALL_PROMPT = "Alert me if the person transitions from upright to the floor and appears to remain down. Distinguish this from normal sitting, kneeling, or bending.";
const PRESETS = [
  { label: "Possible fall", prompt: FALL_PROMPT },
  { label: "Still on floor", prompt: "Alert me if the person is visibly lying on the floor and has not returned to an upright position." },
  { label: "Needs assistance", prompt: "Alert me if the person is on the floor or visibly reaching upward for assistance." },
  { label: "Unsafe exit", prompt: "Alert me if the person approaches or crosses the room exit without visible assistance." },
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
  if (video.duration > MAX_VIDEO_DURATION_SECONDS) throw new Error("For this demo, choose a video up to four hours long.");
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

  const [source, setSource] = useState<Source>("upload");
  const [uploadName, setUploadName] = useState("");
  const [uploadState, setUploadState] = useState<UploadState>("empty");
  const [prompt, setPrompt] = useState("");
  const [intervalSeconds, setIntervalSeconds] = useState(5);
  const [confirmationCount, setConfirmationCount] = useState(1);
  const [scanMode, setScanMode] = useState("quick");
  const [sampleInterval, setSampleInterval] = useState(2);
  const [videoDuration, setVideoDuration] = useState(0);
  const [timeline, setTimeline] = useState<Timeline>({});
  const [state, setState] = useState<RunState>("idle");
  const [stage, setStage] = useState<Stage>("idle");
  const [status, setStatus] = useState("Upload a video to begin");
  const [lastResult, setLastResult] = useState<VisualCheckResult | null>(null);
  const [conditionResults, setConditionResults] = useState<ConditionResult[]>([]);
  const [scanComplete, setScanComplete] = useState(false);
  const [events, setEvents] = useState<BrowserEvent[]>([]);
  const [storyboardFrames, setStoryboardFrames] = useState<CapturedFrame[]>([]);
  const [checks, setChecks] = useState(0);
  const [nextCheck, setNextCheck] = useState<number | null>(null);
  const [notificationState, setNotificationState] = useState<NotificationPermission | "unsupported">("default");
  const [smsAvailable, setSmsAvailable] = useState(false);
  const [smsEnabled, setSmsEnabled] = useState(false);
  const [caregiverPhone, setCaregiverPhone] = useState("");
  const [testingSms, setTestingSms] = useState(false);
  const [testReceipt, setTestReceipt] = useState<BrowserEvent["sms"]>();
  const running = state === "starting" || state === "sampling" || state === "checking" || state === "watching";
  const recorded = source !== "webcam";
  const detailed = recorded && scanMode === "detailed";
  const effectiveSampleInterval = detailed && videoDuration > 0 && videoDuration <= MAX_VIDEO_DURATION_SECONDS
    ? recommendedDetailedInterval(videoDuration, sampleInterval)
    : sampleInterval;

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
      void getNotificationCapabilities()
        .then((value) => setSmsAvailable(value.sms))
        .catch(() => setSmsAvailable(false));
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
      new Notification("Artae caregiver review requested", { body: summary, tag: "artae-care-alert" });
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
      caregiverPhone: smsEnabled ? caregiverPhone.trim() : undefined,
    };
    await createCloudSession(session);
    sessionRef.current = session;
  }

  async function testText() {
    const phone = caregiverPhone.trim();
    if (!/^\+[1-9]\d{7,14}$/.test(phone)) {
      setTestReceipt({ status: "failed", provider: "aws_sns", message: "Enter your number with its country code, such as +12065550142." });
      return;
    }
    setTestingSms(true);
    setTestReceipt(undefined);
    try {
      const testSession: BrowserSession = {
        id: crypto.randomUUID(), scope: "account", name: "Text alert connection test", job: "custom",
        prompt: "Check for a possible fall", createdAt: new Date().toISOString(), events: [], clips: [], cloud: true,
        caregiverPhone: phone,
      };
      await createCloudSession(testSession);
      setTestReceipt(await sendTestSms(testSession));
    } catch (error) {
      setTestReceipt({ status: "failed", provider: "aws_sns", message: error instanceof Error ? error.message : "The text could not be requested." });
    } finally { setTestingSms(false); }
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
      resultsRef.current = resultsRef.current.map((item) => {
        if (item.status === "unsupported") return item;
        const points = updated[item.condition_index] || [];
        const status = timelineStatus(points);
        return { ...item, status, at_seconds: points.find((point) => point.state === "active")?.at,
          summary: status === item.status ? item.summary : status === "uncertain"
            ? "Observations conflict or are incomplete; no active timestamp is currently established."
            : status === "no_match" ? "The condition is absent in the sampled observations." : "The condition is visible at the highlighted timestamps.",
        };
      });
      setConditionResults(resultsRef.current);
    }
    setChecks((value) => value + 1);
    setLastResult(result);
    setStage("frames");
    if (result.event) {
      const matched = result.matched_frame_index == null ? undefined : frames[result.matched_frame_index];
      const fields = cloudEventFields(result.event);
      const event: BrowserEvent = {
        id: result.event.source_event_id, at: matched?.at_seconds ?? frames[0].at_seconds, occurredAt: new Date().toISOString(),
        title: "Care event needs review", visibility: 0, snapshot: matched?.snapshot, ...fields,
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
    if (smsEnabled && !/^\+[1-9]\d{7,14}$/.test(caregiverPhone.trim())) {
      setState("error"); setStatus("Enter the caregiver phone in international format, such as +12065550142."); return;
    }
    const runId = ++runIdRef.current;
    try {
      runningRef.current = true;
      setState("starting"); setStage("idle"); setStatus("Opening the video source…");
      setLastResult(null); setChecks(0); setNextCheck(null);
      setConditionResults([]); resultsRef.current = []; setScanComplete(false); setEvents([]); setStoryboardFrames([]);
      setTimeline({}); timelineRef.current = {};
      await prepareVideo();
      if (runId !== runIdRef.current) return;
      // Adapt long clips to an explicitly displayed cadence before opening a paid run.
      const activeSampleInterval = detailed
        ? recommendedDetailedInterval(videoRef.current!.duration, sampleInterval)
        : sampleInterval;
      if (detailed && activeSampleInterval !== sampleInterval) setSampleInterval(activeSampleInterval);
      const times = detailed ? detailedTimes(videoRef.current!.duration, activeSampleInterval) : [];
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
            setStatus(`Detailed scan ${batch + 1} of ${total} — sampling every ${activeSampleInterval}s…`);
            const frames = await captureTimes(times.slice(batch * 7, batch * 7 + 8));
            if (!active()) return;
            setStoryboardFrames(frames);
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
            setStoryboardFrames(frames);
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
        setStoryboardFrames(frames);
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
    setSource(next); setUploadName(""); setUploadState("empty"); setVideoDuration(0); setLastResult(null); setStage("idle");
    setConditionResults([]); setScanComplete(false);
    setTimeline({}); timelineRef.current = {}; setStoryboardFrames([]);
    setStatus(next === "webcam" ? "Ready to monitor" : "Ready to analyze");
    if (next !== "webcam") setConfirmationCount(1);
    if (video) {
      video.pause(); video.srcObject = null; video.removeAttribute("src"); video.load();
    }
  }

  function chooseUpload(file?: File) {
    if (!file || runningRef.current || !videoRef.current) return;
    if (uploadUrlRef.current) URL.revokeObjectURL(uploadUrlRef.current);
    uploadUrlRef.current = URL.createObjectURL(file);
    videoRef.current.srcObject = null;
    videoRef.current.src = uploadUrlRef.current;
    videoRef.current.loop = false;
    videoRef.current.load();
    setSource("upload"); setUploadName(file.name); setUploadState("preparing"); setVideoDuration(0); setLastResult(null); setStage("idle");
    setConditionResults([]); setScanComplete(false);
    setTimeline({}); timelineRef.current = {}; setStoryboardFrames([]);
    if (mode === "public") setEvents([]);
    setStatus("Preparing video preview…");
  }

  async function enableNotifications() {
    if (typeof Notification === "undefined") return setNotificationState("unsupported");
    setNotificationState(await Notification.requestPermission());
  }

  const steps: { stage: Stage; label: string }[] = [
    { stage: "video", label: "Video ready" }, { stage: "frames", label: "Frames sampled" },
    { stage: "nova", label: "Nova analyzed" }, { stage: "strands", label: "Strands acted" },
  ];
  const evidenceFrames = storyboardFrames.length <= 7
    ? storyboardFrames
    : Array.from({ length: 7 }, (_, index) => storyboardFrames[Math.round(index * (storyboardFrames.length - 1) / 6)]);
  const hasVideoSource = source === "webcam" || Boolean(uploadName);
  const sourceReady = source === "webcam" || uploadState === "ready";
  const canStart = hasVideoSource && sourceReady && readConditions(prompt).length > 0;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/" aria-label="Artae home">artae<span>VISION</span></Link>
        <div className={styles.headerMeta}>
          {mode === "public" && <Link className={styles.modeLink} href="/live"><FiCamera />Continuous fall monitor</Link>}
          {mode === "public" && <><strong>Live AWS demo</strong><span>No account required · up to {detailed ? 32 : 4} checks</span></>}
          <div className={styles.headerStatus}><i className={running ? styles.liveDot : styles.dot} />{running ? "Analysis running" : "Ready"}</div>
        </div>
      </header>

      <section className={styles.intro}>
        <div><p className={styles.eyebrow}>AI CAREGIVER ASSISTANT</p><h1>A second set of eyes for senior care.</h1></div>
        <p>Upload permitted shared-space video or connect a camera. Amazon Nova reviews possible falls, then a Strands agent prepares evidence and asks a caregiver to check.</p>
      </section>

      <section className={styles.workbench}>
        <section className={styles.builder} aria-label="Configure visual monitor">
          <div className={styles.step}>
            <div className={styles.stepTitle}><span>1</span><div><strong>Upload care footage</strong><small>Choose a permitted browser-playable video, or connect a webcam for live monitoring.</small></div></div>
            <div className={styles.sourceGrid}>
              <label className={source === "upload" ? styles.selected : ""}><FiUpload />Upload video<input type="file" accept="video/*" onChange={(event) => chooseUpload(event.target.files?.[0])} disabled={running} /></label>
              <button className={source === "webcam" ? styles.selected : ""} onClick={() => chooseSource("webcam")} disabled={running}><FiCamera />Webcam</button>
            </div>
            {uploadName && <div className={`${styles.uploadedFile} ${uploadState === "preparing" ? styles.uploadPreparingFile : uploadState === "error" ? styles.uploadErrorFile : ""}`}>
              {uploadState === "preparing" ? <FiLoader className={styles.spinner} /> : <FiCheck />}
              <span>{uploadName}</span>
              <small>{uploadState === "preparing" ? "Preparing preview" : uploadState === "error" ? "Could not open" : "Ready to analyze"}</small>
            </div>}
          </div>

          <div className={styles.step}>
            <div className={styles.stepTitle}><span>2</span><div><strong>What should the care agent watch for?</strong><small>Describe up to 5 visible safety conditions, one per line.</small></div></div>
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} disabled={running} maxLength={500} rows={5} aria-label="Conditions to watch for" placeholder="Type the visible condition Artae should watch for…" />
            <small className={styles.conditionCount}>{readConditions(prompt).length} / 5 conditions · 500 characters total</small>
            <div className={styles.presets}>{PRESETS.map((preset) => <button key={preset.label} onClick={() => setPrompt(preset.prompt)} disabled={running}>{preset.label}</button>)}</div>
          </div>

          <div className={styles.stepRow}>
            <div className={styles.stepTitle}><span>3</span><div><strong>{recorded ? "Choose how to scan" : "Set the monitoring cadence"}</strong><small>{recorded ? "Quickly check conditions or estimate when an event happened." : "Choose how often the care camera should check the scene."}</small></div></div>
            {recorded ? <>
              <div className={styles.compactStep}><label htmlFor="scan-mode">Scan mode</label><select id="scan-mode" value={scanMode} onChange={(event) => setScanMode(event.target.value)} disabled={running}><option value="quick">Quick — check conditions</option><option value="detailed">Detailed — event timeline & duration</option></select></div>
              {detailed && <div className={styles.compactStep}><label htmlFor="sample-interval">Sample video every</label><select id="sample-interval" value={sampleInterval} onChange={(event) => setSampleInterval(Number(event.target.value))} disabled={running}>{DETAILED_INTERVALS.map((value) => <option key={value} value={value}>{value} seconds</option>)}</select></div>}
              <div className={styles.storyboardHint}><FiClock /><div><strong>{detailed ? "Timing estimates, not exact measurements" : "Multi-pass video scan"}</strong><small>{detailed ? `Up to 192 samples across clips up to 4 hours. ${effectiveSampleInterval !== sampleInterval ? `For this video, Artae will automatically sample about every ${effectiveSampleInterval}s to stay within that limit. ` : ""}Up to 4 closer boundary checks refine detected events; brief events between samples can be missed.` : "Up to 32 moments are checked across the clip in four Nova batches."}</small></div></div>
              {detailed && <div className={styles.presets}><button disabled={running} onClick={() => setPrompt("How long does the single person remain on the floor? Measure from first visibly on the ground until standing upright again.")}>Time on floor</button><button disabled={running} onClick={() => setPrompt("How long does the single person take to get back up? Measure from first visibly on the ground until standing upright again.")}>Time to stand up</button></div>}
            </> : <>
              <div className={styles.compactStep}><label htmlFor="interval"><FiClock /> Check every</label><select id="interval" value={intervalSeconds} onChange={(event) => setIntervalSeconds(Number(event.target.value))} disabled={running}><option value={5}>5 seconds</option><option value={15}>15 seconds</option><option value={30}>30 seconds</option><option value={60}>1 minute</option></select></div>
              <div className={styles.compactStep}><label htmlFor="confirmations"><FiCheck /> Confirm after</label><select id="confirmations" value={confirmationCount} onChange={(event) => setConfirmationCount(Number(event.target.value))} disabled={running}><option value={1}>1 match</option><option value={2}>2 matches</option><option value={3}>3 matches</option></select></div>
            </>}
            {!running ? <button className={styles.startButton} onClick={() => void start()} disabled={!canStart}><FiPlay />{!hasVideoSource ? "Upload a video to continue" : !sourceReady ? "Preparing video…" : !readConditions(prompt).length ? "Describe what to watch for" : recorded ? "Analyze video" : "Start monitor"}</button> : <button className={styles.stopButton} onClick={() => stop()}><FiSquare />Stop</button>}
          </div>
        </section>

        <article className={styles.previewCard}>
          <div className={styles.cardHeader}><div><FiVideo /><strong>{source === "webcam" ? "Care camera" : uploadName || "Uploaded care footage"}</strong></div><span className={running ? styles.livePill : styles.offPill}>{running ? "RUNNING" : uploadName || source === "webcam" ? "READY" : "WAITING"}</span></div>
          <div className={`${styles.videoWrap} ${uploadState === "ready" ? styles.videoReady : ""} ${running ? styles.videoProcessing : ""}`} aria-busy={uploadState === "preparing" || running}>
            <video ref={videoRef} muted playsInline controls={hasVideoSource && !running} onLoadedMetadata={(event) => {
              setVideoDuration(event.currentTarget.duration);
              setUploadState("ready");
              if (!runningRef.current) setStatus("Video ready — describe what to find");
            }} onError={() => {
              if (source !== "upload") return;
              setUploadState("error");
              if (!runningRef.current) setStatus("This browser could not open the selected video. Try MP4 (H.264) or WebM.");
            }} />
            {!uploadName && source === "upload" && <label className={styles.videoEmpty}><FiUpload /><strong>Upload footage to begin</strong><span>MP4, WebM, or another browser-playable video · up to 4 hours</span><input type="file" accept="video/*" onChange={(event) => chooseUpload(event.target.files?.[0])} disabled={running} /></label>}
            {uploadState === "preparing" && <div className={styles.uploadOverlay}><div className={styles.processingOrb}><FiVideo /></div><strong>Preparing your footage</strong><span>Reading the video securely in this browser</span><div className={styles.loadingBar}><i /></div></div>}
            {running && <div className={styles.analysisOverlay}><div className={styles.analysisStatus}><span className={styles.processingOrb}><FiLoader /></span><div><strong>{state === "sampling" ? "Building the evidence timeline" : state === "checking" ? "Amazon Nova is reviewing the evidence" : "Care monitor is active"}</strong><small>{state === "sampling" ? "Sampling moments across the full recording" : state === "checking" ? "The video remains on this device; sampled frames are being checked" : "Artae will surface only a possible care event"}</small></div></div><div className={styles.analysisPulse}><i /><i /><i /></div></div>}
            {running && <div className={styles.videoBadge}>{state === "sampling" ? "SAMPLING VIDEO" : state === "checking" ? "NOVA ANALYZING" : "MONITORING"}</div>}
          </div>
          <canvas ref={canvasRef} hidden />
          <section className={styles.evidenceTimeline} aria-label="Sampled video evidence">
            <div className={styles.timelineHeading}><strong>Evidence timeline</strong><span>{evidenceFrames.length ? `${storyboardFrames.length} moments sampled from this video` : "Sampled frames will appear here during analysis"}</span></div>
            {evidenceFrames.length ? <div className={styles.frameTrack}>{evidenceFrames.map((frame) => <button key={frame.at_seconds} disabled={running || !recorded} onClick={() => { if (videoRef.current) videoRef.current.currentTime = frame.at_seconds; }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={frame.snapshot} alt={`Sampled frame at ${timeLabel(frame.at_seconds)}`} /><span>{timeLabel(frame.at_seconds)}</span>
            </button>)}</div> : uploadState === "preparing" || running ? <div className={styles.timelineSkeleton} aria-label="Preparing evidence timeline">{Array.from({ length: 7 }, (_, index) => <i key={index} />)}</div> : <div className={styles.timelineEmpty}><FiClock />Upload a video and select Analyze video to create its evidence timeline.</div>}
          </section>
          <div className={styles.pipeline} aria-label="Analysis progress">
            {steps.map((item) => {
              const done = isStepDone(stage, item.stage, events.some((event) => event.coordinator === "completed"));
              const active = !done && ((item.stage === "video" && uploadState === "preparing") || (item.stage === "frames" && state === "sampling") || (item.stage === "nova" && state === "checking"));
              return <div className={done ? styles.pipelineDone : active ? styles.pipelineActive : ""} key={item.stage}><i />{item.label}</div>;
            })}
          </div>
          <div className={styles.runStatus} role="status"><i className={state === "error" ? styles.errorDot : running ? styles.liveDot : styles.dot} /><div><strong>{status}</strong><small>{checks ? `${checks} AWS check${checks === 1 ? "" : "s"} completed` : "No AWS checks yet"}{nextCheck ? ` · next at ${clock(nextCheck)}` : ""}</small></div></div>
          {conditionResults.map((item) => <div className={`${styles.lastDecision} ${item.status === "match" ? styles.matchDecision : ""}`} key={item.condition_index}>
            <span>Condition {item.condition_index + 1}</span>
            <strong>{item.status === "match" ? "Detected" : item.status === "no_match" ? scanComplete ? "Not detected in sampled frames" : "Not seen yet" : item.status === "uncertain" ? "Uncertain" : "Unsupported"}</strong>
            <h3>{item.condition}</h3><p>{item.summary}</p>
            {timeline[item.condition_index] && <div className={styles.timing}>
              <p><strong>Event timeline {scanComplete ? "— sampled estimates" : "— provisional"}</strong></p>
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
          <div className={styles.cardHeader}><div><FiBell /><strong>Caregiver event log</strong><span className={styles.cardDescription}>Detected conditions and agent actions appear here.</span></div><span className={styles.count}>{events.length}</span></div>
          <div className={styles.alertControls}>
            <div className={styles.notificationRow}>
              <div><strong>Dashboard alerts are on</strong><small>{notificationState === "granted" ? "Browser notifications also enabled" : "Enable browser alerts while this page is open"}</small></div>
              {notificationState === "default" && <button onClick={() => void enableNotifications()}>Enable</button>}
            </div>
            <div className={styles.smsSetup}>
              {mode === "public" ? <p><strong>Text me what happened</strong><small>Sign in to add your phone. A detected event sends its description and video timestamp by text.</small><Link href="/login?next=demo">Sign in for text alerts</Link></p> : !smsAvailable ? <p><strong>SMS needs deployment setup</strong><small>Dashboard and browser alerts work now. AWS SMS is not enabled on this deployment.</small></p> : <>
                <label><input type="checkbox" checked={smsEnabled} disabled={running} onChange={(event) => setSmsEnabled(event.target.checked)} /> Text a caregiver after a confirmed event</label>
                {smsEnabled && <><label>Your phone number<input type="tel" inputMode="tel" placeholder="+12065550142" value={caregiverPhone} disabled={running || testingSms} onChange={(event) => { setCaregiverPhone(event.target.value); setTestReceipt(undefined); }} /><small>Include your country code. We text what was detected and where it happened in the video.</small></label><button type="button" disabled={running || testingSms || !caregiverPhone.trim()} onClick={() => void testText()}>{testingSms ? "Sending test…" : "Send test text"}</button><small>Texting currently requires an AWS-verified destination.</small>{testReceipt && <p role="status">{testReceipt.status === "accepted" ? "AWS accepted the test text. Check your phone to confirm it arrived." : testReceipt.message || "The test failed. Check your number and AWS text messaging setup."}</p>}</>}
              </>}
            </div>
          </div>
          <div className={styles.alertList}>
            {events.length === 0 ? <div className={styles.empty}><FiBell /><strong>No care event detected</strong><p>If Nova confirms a visible safety condition, the matching frame and Strands caregiver actions appear here.</p></div> : events.map((event) => (
              <article className={styles.alertItem} key={event.id}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                {event.snapshot && <img src={event.snapshot} alt="Frame that best supports the detected condition" />}
                <div><div className={styles.alertMeta}><span>CAREGIVER REVIEW</span><time>{clock(event.occurredAt || event.at)}</time></div><h3>{event.title}</h3><p>{event.summary}</p><div className={styles.actionTags}>{(event.actions || []).map((action) => <span key={action}>{action.replaceAll("_", " ")}</span>)}</div>{event.sms && <div className={`${styles.deliveryReceipt} ${event.sms.status === "accepted" ? styles.deliveryAccepted : styles.deliveryFailed}`}><FiBell /><div><strong>{event.sms.status === "accepted" ? "Caregiver text accepted by AWS" : "Caregiver text needs attention"}</strong><small>{event.sms.status === "accepted" ? `Submitted for delivery to ${event.sms.destination || "your phone"}` : event.sms.message || (event.sms.error ? `Delivery error: ${event.sms.error.replaceAll("_", " ")}` : "Check the AWS SMS configuration")}</small></div></div>}<small>{event.saved ? "Saved to your account" : "Temporary demo result"} · human review required</small></div>
              </article>
            ))}
          </div>
        </aside>
      </section>
    </main>
  );
}
