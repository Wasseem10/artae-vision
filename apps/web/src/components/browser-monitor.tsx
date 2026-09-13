"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  BrowserPoseRule,
  POSE_CONNECTIONS,
  poseFeatures,
  type Landmark,
} from "@/lib/browser-pose";
import {
  createCloudSession,
  createPublicDemo,
  analyzeCloudFrames,
  analyzePublicDemo,
  cloudEventFields,
  formatTime,
  loadBrowserWorkspace,
  saveBrowserJob,
  loadCloudSession,
  loadLocalSession,
  mergeSession,
  reviewCloudEvent,
  saveCloudClip,
  saveCloudEvent,
  saveLocal,
  sessionMetadata,
  type BrowserClip,
  type BrowserSession,
  type BrowserEvent,
  type ReviewOutcome,
  type SavedBrowserJob,
  type MonitoringJob,
  type PublicDemoSession,
} from "@/lib/browser-sessions";
import {
  getSupabaseBrowserClient,
  isSupabaseConfigured,
  syncApiSession,
} from "@/lib/supabase";
import styles from "./instant-demo.module.css";

export function BrowserMonitor({ workspace = false, experience = "general" }: { workspace?: boolean; experience?: "general" | "senior-safety" }) {
  const seniorSafety = experience === "senior-safety";
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
    [source, setSource] = useState<"sample" | "file" | "webcam">(workspace ? "webcam" : "sample"),
    [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<MonitoringJob>(seniorSafety ? "fall" : "presence"),
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
  const [inferenceMs, setInferenceMs] = useState(0);
  const [authReady, setAuthReady] = useState(!isSupabaseConfigured());
  const [loadedScope, setLoadedScope] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [jobs, setJobs] = useState<SavedBrowserJob[]>([]);
  const [agentName, setAgentName] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<string | undefined>();
  const [savingJob, setSavingJob] = useState(false);
  const [sessionMinutes, setSessionMinutes] = useState(2);
  const [prompt, setPrompt] = useState("");
  const [cloudConsent, setCloudConsent] = useState(false);
  const [visualStatus, setVisualStatus] = useState("");
  const [visualFrames, setVisualFrames] = useState(0);
  const [caregiverPhone, setCaregiverPhone] = useState("");
  const [smsEnabled, setSmsEnabled] = useState(false);
  const [notificationState, setNotificationState] = useState<NotificationPermission | "unsupported">("default");

  function notifyCaregiver(summary: string) {
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      new Notification("Artae Senior Safety · possible fall", {
        body: `${summary} Check the person immediately.`,
        tag: "artae-possible-fall",
      });
    }
  }

  async function enableBrowserNotifications() {
    if (typeof Notification === "undefined") return setNotificationState("unsupported");
    setNotificationState(await Notification.requestPermission());
  }

  async function saveAgent() {
    if (scope === "guest" || !agentName.trim() || savingJob || running) return;
    const owner = scope;
    setSavingJob(true);
    try {
      const saved = await saveBrowserJob({ id: crypto.randomUUID(), name: agentName.trim(), job, prompt: job === "custom" ? prompt.trim() : "" });
      if (accountScope.current !== owner) return;
      setJobs((rows) => [saved, ...rows]);
      setSelectedAgent(saved.id);
      setPhase("Agent saved to your account · ready to start");
    } catch (e) {
      setSaveProblem(e instanceof Error ? e.message : "Could not save agent.");
    } finally { setSavingJob(false); }
  }

  async function reviewIncident(event: BrowserEvent, outcome: ReviewOutcome) {
    const s = current.current;
    if (!s || reviewing || s.scope !== accountScope.current) return;
    const previousReview = event.review;
    setReviewing(event.id);
    try {
      if (s.scope === "guest") {
        event.review = {
          status: outcome === "acknowledged" ? "acknowledged" : "resolved",
          outcome, reviewed_at: new Date().toISOString(),
        };
      } else {
        // Wait for the account's create/event queue; never claim a remote save optimistically.
        await cloudQueue.current;
        if (!event.saved || s.scope !== accountScope.current)
          throw new Error("Save this alert to your account before reviewing it.");
        Object.assign(event, cloudEventFields(await reviewCloudEvent(s, event, outcome)));
      }
      // Guest reviews require a committed device copy before success. Account
      // reviews were already committed remotely; local storage is optional.
      if (s.scope === "guest") await saveLocal(s);
      persist(s);
    } catch (e) {
      if (s.scope === "guest") event.review = previousReview;
      setSaveProblem(e instanceof Error ? e.message : "Review could not be saved. Please retry.");
    } finally {
      setReviewing(null);
    }
  }

  useEffect(() => {
    mounted.current = true;
    const notificationTimer = window.setTimeout(
      () => setNotificationState(typeof Notification === "undefined" ? "unsupported" : Notification.permission),
      0,
    );
    let unsubscribe = () => {};
    if (isSupabaseConfigured()) {
      const {
        data: { subscription },
      } = getSupabaseBrowserClient().auth.onAuthStateChange((_event, s) => {
        const next = s?.user.id ?? "guest";
        if (next !== accountScope.current) {
          stopRef.current();
          accountScope.current = next;
          setSelectedAgent(undefined);
          setAgentName("");
          setJobs([]);
          // Clear the previous owner's data before asynchronous account loading.
          setHistory([]);
          setSession(null);
          setReplay(null);
          setLoadedScope(null);
          current.current = null;
          const canvas = canvasRef.current;
          canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
          const playback = playbackRef.current;
          if (playback) {
            playback.pause();
            playback.removeAttribute("src");
            playback.load();
          }
          setMetrics({ frames: 0, people: 0, seconds: 0, state: "Waiting for video" });
          setInferenceMs(0);
          setVisualStatus("");
          setVisualFrames(0);
          setPhase("Ready");
          setSessionMinutes(2);
          setCloudConsent(false);
          setPrompt("");
          if (mounted.current) setScope(next);
        }
        syncApiSession(s);
        if (mounted.current) setAuthReady(true);
      });
      unsubscribe = () => subscription.unsubscribe();
    }
    return () => {
      mounted.current = false;
      window.clearTimeout(notificationTimer);
      unsubscribe();
      stopRef.current();
      void audio.current?.close();
    };
  }, []);
  useEffect(() => {
    let cancelled = false;
    if (!authReady) return;
    void loadBrowserWorkspace(scope)
      .then((loaded) => {
        if (!cancelled) {
          setHistory(loaded.history);
          setJobs(loaded.jobs);
          setSaveProblem(loaded.warning);
          setSession(null);
          setReplay(null);
          current.current = null;
        }
      })
      .catch(() => {
        if (!cancelled)
          setSaveProblem(
            "History could not fully load. Any available local history is kept; retry Load account history.",
          );
      }).finally(() => { if (!cancelled) setLoadedScope(scope); });
    return () => {
      cancelled = true;
    };
  }, [scope, authReady]);
  useEffect(
    () => () => {
      if (replay?.owned) URL.revokeObjectURL(replay.url);
    },
    [replay],
  );
  useEffect(() => {
    const video = playbackRef.current;
    // Selecting another event in the same cloud clip does not reload metadata.
    // Seek immediately when that clip is already loaded.
    if (replay && video && video.readyState >= 1 && video.currentSrc === replay.url) {
      video.currentTime = replay.seek;
    }
  }, [replay]);
  function persist(s: BrowserSession) {
    if (mounted.current && accountScope.current === s.scope) {
      setSession({ ...s, events: [...s.events], clips: [...s.clips] });
      setHistory((rows) => [sessionMetadata(s), ...rows.filter((r) => r.id !== s.id)]);
    }
    void saveLocal(s).catch(() => {
      if (mounted.current && accountScope.current === s.scope)
        setSaveProblem(
          s.cloud
            ? "Device storage is unavailable. Uploaded account footage is kept; check that remaining uploads finish before leaving."
            : "Local history could not be saved. Storage may be full. Download your recording before leaving.",
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
    if (job === "custom" && (scope === "guest" || !cloudConsent || !prompt.trim())) {
      setProblem("Sign in, describe a visible condition, and allow AWS frame analysis before starting.");
      return;
    }
    if (source === "file" && !file) {
      setProblem("Choose a video file first.");
      return;
    }
    if (smsEnabled && !/^\+[1-9]\d{7,14}$/.test(caregiverPhone.trim())) {
      setProblem("Enter the caregiver phone in international format, such as +12065550142.");
      return;
    }
    active.current = true;
    setRunning(true);
    setProblem(null);
    setSaveProblem(null);
    setReplay(null);
    setPhase("Loading pose model…");
    setVisualStatus("");
    setVisualFrames(0);
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
      agentId: selectedAgent,
      prompt: job === "custom" ? prompt.trim() : "",
      caregiverPhone: job === "fall" && scope !== "guest" && smsEnabled ? caregiverPhone.trim() : undefined,
      createdAt: new Date().toISOString(),
      events: [],
      clips: [],
    };
    if (selectedAgent && agentName.trim()) s.name = `${agentName.trim()} · ${s.name}`;
    current.current = s;
    persist(s);
    let worker: Worker | null = null,
      media: MediaStream | null = null,
      recordingStream: MediaStream | null = null,
      recorder: MediaRecorder | null = null;
    let animation: ReturnType<typeof setInterval> | undefined,
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
    const engine = new BrowserPoseRule(job === "custom" ? "presence" : job);
    const frameCanvas = document.createElement("canvas");
    const visualBuffer: { at_seconds: number; jpeg: string }[] = [];
    let visualPending = false, lastVisualSample = -1, lastVisualCheck = -5;
    const fallVisualBuffer: { at_seconds: number; jpeg: string }[] = [];
    let lastFallVisualSample = -1;
    let publicFallSession: PublicDemoSession | null = null;
    const now = () =>
      source === "webcam"
        ? (performance.now() - startTime) / 1000
        : video.currentTime;
    const stop = () => {
      if (stopped) return;
      stopped = true;
      active.current = false;
      cancelLoading?.();
      clearInterval(animation);
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
      if (scope === "guest" && job === "fall") {
        setVisualStatus("Opening the AWS fall-review agent…");
        publicFallSession = await createPublicDemo(
          "A person transitions from upright to the floor and remains down. Distinguish this from normal sitting, kneeling, or bending.",
        );
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
        setInferenceMs(Math.round(data.inferenceMs ?? 0));
        points = data.landmarks;
        frames++;
        const f = poseFeatures(points, canvas.width, canvas.height);
        if (job !== "custom" && engine.update(f, lastSent) && s.events.length < 20) {
          const event = {
            id: crypto.randomUUID(),
            at: lastSent,
            title:
              job === "fall"
                ? "Possible fall — please review"
                : "Person detected",
            visibility: f?.visibility ?? 0,
            review: { status: "open", outcome: null } as const,
          };
          s.events.push(event);
          persist(s);
          beep();
          notifyCaregiver(event.title);
          if (scope === "guest" && job === "fall" && publicFallSession && fallVisualBuffer.length) {
            visualPending = true;
            setVisualStatus("Amazon Nova is reviewing the possible fall sequence…");
            const batch = fallVisualBuffer.slice(-8);
            void analyzePublicDemo(publicFallSession, batch).then((result) => {
              setVisualFrames((n) => n + result.frames_analyzed);
              event.title = result.status === "match" ? "Possible fall — caregiver check requested" : "Possible fall candidate — human review required";
              Object.assign(event, result.event ? cloudEventFields(result.event) : { summary: result.summary });
              setVisualStatus(result.event
                ? "Nova confirmed the visible sequence and Strands prepared the caregiver response."
                : `Nova result: ${result.summary} The local candidate remains available for human review.`);
              persist(s);
            }).catch((error) => {
              setVisualStatus(error instanceof Error ? `AWS review unavailable: ${error.message}` : "AWS review unavailable; local alert kept.");
            }).finally(() => { visualPending = false; });
          } else {
            queueCloud(s, async () => {
              await createCloudSession(s);
              const result = await saveCloudEvent(s, event);
              Object.assign(event, cloudEventFields(result));
              s.cloud = true;
              persist(s);
            });
          }
          if (s.events.length >= 20) {
            stop();
            setPhase("Stopped at the 20-alert session limit · logs and footage kept");
          }
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
        if (lastAt >= (scope === "guest" ? 120 : sessionMinutes * 60)) {
          stop();
          return;
        }
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        if (job === "fall" && video.readyState >= 2 && lastAt - lastFallVisualSample >= 0.35) {
          lastFallVisualSample = lastAt;
          const scale = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight));
          frameCanvas.width = Math.round(video.videoWidth * scale);
          frameCanvas.height = Math.round(video.videoHeight * scale);
          frameCanvas.getContext("2d")!.drawImage(video, 0, 0, frameCanvas.width, frameCanvas.height);
          fallVisualBuffer.push({ at_seconds: lastAt, jpeg: frameCanvas.toDataURL("image/jpeg", .72).split(",")[1] });
          if (fallVisualBuffer.length > 12) fallVisualBuffer.shift();
        }
        if (job === "custom" && video.readyState >= 2 && lastAt - lastVisualSample >= 1) {
          lastVisualSample = lastAt;
          const scale = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight));
          frameCanvas.width = Math.round(video.videoWidth * scale);
          frameCanvas.height = Math.round(video.videoHeight * scale);
          frameCanvas.getContext("2d")!.drawImage(video, 0, 0, frameCanvas.width, frameCanvas.height);
          visualBuffer.push({ at_seconds: lastAt, jpeg: frameCanvas.toDataURL("image/jpeg", .7).split(",")[1] });
          if (visualBuffer.length > 4) visualBuffer.shift();
          if (visualBuffer.length === 4 && !visualPending && lastAt - lastVisualCheck >= 5) {
            visualPending = true;
            lastVisualCheck = lastAt;
            const batch = [...visualBuffer];
            setVisualStatus("AWS is checking four sampled frames…");
            queueCloud(s, async () => {
              try {
                await createCloudSession(s);
                const result = await analyzeCloudFrames(s, batch);
                if (accountScope.current !== s.scope) return;
                setVisualFrames((n) => n + result.frames_analyzed);
                setVisualStatus(`${result.status === "match" ? "Condition matched" : result.status === "no_match" ? "Not seen" : result.status === "uncertain" ? "Uncertain" : "Unsupported request"}: ${result.summary}${result.cooldown ? " (duplicate alert suppressed)" : ""}`);
                if (result.event) {
                  s.events.push({ id: result.event.source_event_id, at: result.event.occurred_at_seconds,
                    title: "Visual condition matched", visibility: 0, ...cloudEventFields(result.event) });
                  s.cloud = true;
                  persist(s);
                  if (!stopped) beep();
                }
                if (result.status === "unsupported" || s.events.length >= 20) {
                  stop();
                  setProblem(result.status === "unsupported" ? result.summary : "20-alert limit reached. Start another run when ready.");
                }
              } catch (e) {
                stop();
                setVisualStatus("Visual analysis stopped because the last check failed.");
                setProblem(e instanceof Error ? e.message : "AWS visual analysis failed; this job has stopped.");
              } finally {
                // The server's cooldown starts when the result commits, not
                // when capture began. Never immediately enqueue another check.
                lastVisualCheck = now();
                visualPending = false;
              }
            });
          }
        }
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
      };
      draw();
      // Sampling must not depend on browser paint callbacks. Chrome may reduce
      // requestAnimationFrame cadence for embedded/occluded previews to ~1 FPS.
      // Inference remains bounded to ~8 FPS; the recorder gets 20 FPS updates.
      animation = setInterval(draw, 50);
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
          Object.assign(e, cloudEventFields(result));
        }
      for (const clip of s.clips)
        if (!clip.saved && clip.blob) await saveCloudClip(s, clip);
      persist(s);
    });
  }
  async function accountHistory() {
    try {
      const owner = scope;
      const loaded = await loadBrowserWorkspace(owner);
      if (accountScope.current !== owner) return;
      setHistory(loaded.history);
      setJobs(loaded.jobs);
      setSaveProblem(loaded.warning);
    } catch (e) {
      setSaveProblem(
        e instanceof Error ? e.message : "Could not load account history.",
      );
    }
  }
  async function openSession(s: BrowserSession, cloudOnly = false) {
    if (running || saving || reviewing) return;
    setSaveProblem(null);
    let loaded = s;
    if (!cloudOnly) {
      try { loaded = await loadLocalSession(s); }
      catch { setSaveProblem("Local footage could not load. Trying the account copy if available."); }
    }
    if (s.cloud)
      try {
        const remote = await loadCloudSession(s);
        loaded = cloudOnly ? remote : mergeSession(loaded, remote);
      } catch {
        setSaveProblem(
          cloudOnly
            ? "Could not open the account copy. Your local recording has not been removed."
            : "Account history is unavailable right now. Showing any recordings saved on this device.",
        );
        if (cloudOnly) return;
      }
    current.current = loaded;
    setSession(loaded);
    setReplay(null);
    setPhase(cloudOnly ? "Account copy · streamed from cloud storage" : "Saved session");
    if (loaded.clips[0]) playClip(loaded.clips[0]);
  }
  return (
    <main className={`${styles.page} ${seniorSafety ? styles.seniorPage : ""}`}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/">
          artae.
        </Link>
        <div>
          <Link href="#saved-agents">My agents</Link>
          <Link href="#history">Past footage</Link>
          {scope === "guest" ? <Link href="/login?next=demo">Sign in to save</Link> :
            <button disabled={running || saving > 0 || savingJob} onClick={() => void getSupabaseBrowserClient().auth.signOut()}>Sign out</button>}
        </div>
      </header>
      <section className={styles.intro}>
        <small>{seniorSafety ? "COMMUNITY SENIOR SAFETY · HUMAN REVIEW REQUIRED" : "REAL DETECTION · NO INSTALLATION"}</small>
        <h1>
          {seniorSafety ? <>Help caregivers notice<br />a possible fall sooner.</> : <>Give your camera<br />one clear job.</>}
        </h1>
        <p>
          {seniorSafety
            ? "Artae watches permitted shared-space footage, flags a possible fall, preserves the moment, and asks an on-duty caregiver to check the person."
            : "Choose a job, connect video, and watch real detections appear. Start with person detection to check your setup."}
        </p>
      </section>
      <section id="monitor-setup" className={styles.workspace}>
        {scope !== "guest" && <div className={styles.savedJobSetup}>
          <label>Agent name <input maxLength={80} value={agentName} placeholder="e.g. Hallway safety" disabled={running || savingJob} onChange={(e) => { setAgentName(e.target.value); setSelectedAgent(undefined); }} /></label>
          <button disabled={running || savingJob || !agentName.trim() || !!selectedAgent} onClick={() => void saveAgent()}>
            {savingJob ? "Saving agent…" : selectedAgent ? "Agent saved" : "Save this agent"}
          </button>
        </div>}
        <div className={styles.setup}>
          {!seniorSafety && <label>
            1. What should it watch for?
            <select
              value={job}
              disabled={running || saving > 0}
              onChange={(e) => { setJob(e.target.value as MonitoringJob); setSelectedAgent(undefined); }}
            >
              <option value="presence">A person in view</option>
              <option value="fall">A possible fall · experimental</option>
              <option value="custom" disabled={scope === "guest"}>Describe a visual condition · AWS · sign-in required</option>
            </select>
          </label>}
          {seniorSafety && <div className={styles.fixedJob}><small>1. CARE JOB</small><strong>Possible fall in a shared room</strong><span>On-device pose candidate + AWS review + caregiver response</span></div>}
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
            {running ? "Stop agent" : !authReady ? "Checking account…" : loadedScope !== scope ? "Loading your workspace…" : saving > 0 ? "Finishing uploads…" : "Start agent"}
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
          {scope !== "guest" && <label>
            Session duration
            <select value={sessionMinutes} disabled={running || saving > 0} onChange={(e) => setSessionMinutes(Number(e.target.value))}>
              <option value={2}>2 minutes</option>
              <option value={15}>15 minutes</option>
              <option value={60}>60 minutes</option>
            </select>
          </label>}
        </div>
        {seniorSafety && <div className={styles.caregiverSetup}>
          <div><strong>3. Choose how the caregiver is alerted</strong><p>The live incident feed and sound always work while this page is open.</p></div>
          <button type="button" onClick={() => void enableBrowserNotifications()} disabled={notificationState === "granted" || notificationState === "unsupported"}>
            {notificationState === "granted" ? "Browser alert enabled" : notificationState === "unsupported" ? "Browser alerts unavailable" : "Enable browser alert"}
          </button>
          {scope === "guest" ? <span className={styles.smsNotice}>Sign in to connect a verified caregiver phone for AWS SMS.</span> : <>
            <label className={styles.smsToggle}><input type="checkbox" checked={smsEnabled} disabled={running} onChange={(event) => setSmsEnabled(event.target.checked)} /> Send AWS SMS on a possible fall</label>
            {smsEnabled && <label className={styles.phoneField}>Caregiver phone in international format<input type="tel" inputMode="tel" placeholder="+12065550142" value={caregiverPhone} disabled={running} onChange={(event) => setCaregiverPhone(event.target.value)} /><small>AWS sandbox accounts can text verified numbers only.</small></label>}
          </>}
        </div>}
        {job === "custom" && <div className={styles.customJob}>
          <label>What visible condition should trigger an in-app alert?
            <textarea maxLength={500} value={prompt} disabled={running || saving > 0} placeholder="e.g. Someone is holding a red bottle" onChange={(e) => { setPrompt(e.target.value); setSelectedAgent(undefined); }} />
          </label>
          <div className={styles.clipList}>
            {["A person is raising a hand", "A person is wearing a blue top", "A worker is not wearing a hard hat"].map((example) => <button key={example} disabled={running || saving > 0} onClick={() => { setPrompt(example); setSelectedAgent(undefined); }}>{example}</button>)}
          </div>
          <label className={styles.consent}><input type="checkbox" checked={cloudConsent} disabled={running} onChange={(e) => setCloudConsent(e.target.checked)} /> Allow sampled video frames to be sent to Amazon Bedrock for this job. Use footage you have permission to share.</label>
          <p>Four frames are sampled over about four seconds, then checked by AWS. Checks depend on network/model speed and can miss brief actions. Only an in-app alert is sent—no phone calls, identity recognition, or medical decisions.</p>
        </div>}
        <p className={styles.note}>
          {job === "custom" ? "Describe one observable condition. Clear lighting and an unobstructed view improve results. An AI match still needs your review." : job === "fall"
            ? "Keep one person’s full body visible. A possible fall requires upright posture, descent, then a sustained horizontal posture. Use a recorded clip; do not fall to test this. This is experimental, not an emergency monitoring system."
            : "A visible body pose sustained for one second creates an alert. One person is tracked at a time; small or obscured people may not be detected."}{" "}
          This run stops after {scope === "guest" ? 2 : sessionMinutes} minutes, 20 alerts, or when you press Stop. No audio is recorded. The browser must stay open; closing your laptop stops monitoring.
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
                {job === "custom" ? "AWS visual checks · real pose overlay" : "MediaPipe pose · on-device"}
              </span>
            </div>
            <div className={styles.controls}>
              <span>
                {metrics.frames} frames analyzed · {metrics.people} person ·{" "}
                {formatTime(metrics.seconds)}
              </span>
              <span>{metrics.state}</span>
            </div>
            <p className={styles.note}>Model processing: {inferenceMs} ms/frame. Keep this tab visible while monitoring.</p>
            {(job === "custom" || (seniorSafety && scope === "guest")) && <p className={styles.note} role="status">{visualFrames} frames checked by AWS. {visualStatus || (job === "fall" ? "AWS will review a sequence when the local pose detector finds a candidate." : "Collecting the first four frames…")}</p>}
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
                        {formatTime(event.at)} · {event.visibility > 0 ? `Landmark visibility ${Math.round(event.visibility * 100)}%` : "AWS visual observation · review required"}
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
                      {event.summary && <p className={styles.incidentSummary}>{event.summary}</p>}
                      {event.notification?.message && <p className={styles.incidentSummary}>In-app notification: {event.notification.message}</p>}
                      {event.actions?.length ? <details className={styles.actionTrace}>
                        <summary>Agent actions</summary>
                        <ul>{Array.from(new Set(event.actions)).map((action) => <li key={action}>
                          {action === "preserve_evidence" ? "Evidence requested" : action === "notify_responder" ? "In-app alert saved" : action === "request_human_review" ? "Added to review queue" : action.replaceAll("_", " ")}
                        </li>)}</ul>
                        <p>{session.clips.some((clip) => clip.saved && clip.start <= event.at && clip.start + clip.duration >= event.at)
                          ? "Account footage available for this event." : "Waiting for this event’s recording upload."}</p>
                      </details> : null}
                      <span>
                        {event.review?.status === "resolved"
                          ? event.review.outcome === "false_alarm" ? "Closed · marked as false alarm" : "Closed · reviewed"
                          : event.review?.status === "acknowledged" ? "Acknowledged · awaiting resolution" : "Needs review"}
                      </span>
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
                      <div className={styles.reviewActions}>
                        {event.review?.status !== "resolved" && (
                          <>
                            {event.review?.status !== "acknowledged" && <button disabled={reviewing !== null} onClick={() => void reviewIncident(event, "acknowledged")}>Acknowledge</button>}
                            <button disabled={reviewing !== null} onClick={() => void reviewIncident(event, "resolved")}>Mark reviewed</button>
                            <button disabled={reviewing !== null} onClick={() => void reviewIncident(event, "false_alarm")}>False alarm</button>
                          </>
                        )}
                      </div>
                      {event.sms && <small>SMS: {event.sms.status.replaceAll("_", " ")}{event.sms.destination ? ` · ${event.sms.destination}` : ""}{event.sms.error ? ` · ${event.sms.error}` : ""}</small>}
                      <small>{reviewing === event.id ? "Saving review…" : event.review?.reviewed_at ? `Review saved ${scope === "guest" ? "on this device" : "to account"}` : event.sms?.status === "accepted" ? "AWS accepted the caregiver text; carrier delivery is not guaranteed." : "Awaiting caregiver review."}</small>
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
          {scope !== "guest" && session?.cloud && (
            <button
              disabled={saving > 0 || running}
              onClick={() => void openSession(session, true)}
            >
              Replay account copy
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
      <section id="saved-agents" className={styles.history}>
        <header><h2>My agents</h2></header>
        <p>{scope === "guest" ? "Sign in to keep named agents in your account." : "Choose a saved job, connect your video, then press Start agent. Saved does not mean it is running."}</p>
        <div>{jobs.map((saved) => <button key={saved.id} disabled={running || saving > 0 || savingJob} onClick={() => {
          setJob(saved.job); setAgentName(saved.name); setSelectedAgent(saved.id); setPrompt(saved.prompt ?? "");
          setPhase(`${saved.name} selected · press Start agent`);
          document.getElementById("monitor-setup")?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}><strong>{saved.name}</strong><span>{saved.job === "custom" ? saved.prompt : saved.job === "fall" ? "Possible fall · experimental" : "Person in view"} · In-app alert</span></button>)}</div>
        {scope !== "guest" && !jobs.length && <p>Name your first agent above to save it for next time.</p>}
      </section>
      <section id="history" className={styles.history}>
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
                {s.job === "custom" ? "Custom visual job" : s.job === "fall" ? "Possible fall" : "Person detection"} ·{" "}
                {s.cloud ? "Account" : "This device"}
              </span>
            </button>
          ))}
        </div>
      </section>
      <footer className={styles.attribution}><Link href="/app/native">Installed camera workspace (requires the camera service)</Link> · Browser monitoring is not an emergency response service.</footer>
    </main>
  );
}
