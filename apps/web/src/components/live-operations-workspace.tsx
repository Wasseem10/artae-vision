"use client";

import Image from "next/image";
import { useMemo, useState } from "react";

import { Icon } from "@/components/icon";
import { LiveStreamPlayer } from "@/components/live-stream-player";
import { NativePreview } from "@/components/native-preview";
import { api } from "@/lib/api";
import { formatLocalTimestamp } from "@/lib/dates";
import type {
  AlertIncident,
  Camera,
  CameraAgent,
  CameraStream,
  Rule,
  RuleCompilation,
} from "@/lib/types";

interface LiveOperationsWorkspaceProps {
  agent: CameraAgent | null;
  alerts: AlertIncident[];
  busy: boolean;
  cameras: Camera[];
  loading: boolean;
  onAddWebcam: () => Promise<void>;
  onClarify: (compilationId: string, answer: string) => Promise<RuleCompilation>;
  onCompile: (input: { camera_id: string; prompt: string }) => Promise<RuleCompilation>;
  onOpenAdvanced: (sectionId: string) => void;
  onRuleCreated: (rule: Rule) => void;
  onSelectCamera: (cameraId: string) => void;
  onStart: () => Promise<void>;
  onStop: () => Promise<void>;
  selectedCamera: Camera | null;
  stream: CameraStream | null;
}

interface DemoCamera {
  id: string;
  name: string;
  location: string;
  detail: string;
  image: string;
}

const demoCameras: DemoCamera[] = [
  {
    id: "demo-parking",
    name: "Parking Lot – North",
    location: "North campus",
    detail: "Entrance · Camera 01",
    image: "/assets/camera-parking-lot.png",
  },
  {
    id: "demo-aisle",
    name: "Main Warehouse Aisle",
    location: "Distribution center",
    detail: "Aisle 12 · Camera 04",
    image: "/assets/camera-warehouse-aisle.png",
  },
  {
    id: "demo-dock",
    name: "Logistics Truck Bay",
    location: "Dock west",
    detail: "Dock West · Camera 02",
    image: "/assets/camera-loading-dock.png",
  },
  {
    id: "demo-entrance",
    name: "Employee Entrance",
    location: "Main campus",
    detail: "Lobby · Camera 01",
    image: "/assets/camera-employee-entrance.png",
  },
  {
    id: "demo-office",
    name: "Shipping Office",
    location: "Distribution center",
    detail: "Interior · Camera 03",
    image: "/assets/camera-shipping-office.png",
  },
  {
    id: "demo-gate",
    name: "Perimeter – East Gate",
    location: "Main campus",
    detail: "Gate · Camera 05",
    image: "/assets/camera-east-gate.png",
  },
];

const fallbackImages = [
  "/assets/camera-loading-dock.png",
  "/assets/camera-parking-lot.png",
  "/assets/camera-warehouse-aisle.png",
];

function sentenceCase(value: string) {
  const normalized = value.replaceAll("_", " ");
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function incidentTitle(alert: AlertIncident) {
  if (alert.event.object_class === "visual_event") return "Activity matched camera job";
  if (alert.event.object_class === "person") return "Person detected in monitored area";
  return `${sentenceCase(alert.event.object_class)} detected`;
}

function incidentLocation(alert: AlertIncident) {
  return alert.event.zone_name.toLowerCase().includes("full frame")
    ? "Full camera view"
    : alert.event.zone_name;
}

export function LiveOperationsWorkspace({
  agent,
  alerts,
  busy,
  cameras,
  loading,
  onAddWebcam,
  onClarify,
  onCompile,
  onOpenAdvanced,
  onRuleCreated,
  onSelectCamera,
  onStart,
  onStop,
  selectedCamera,
  stream,
}: LiveOperationsWorkspaceProps) {
  const [cameraSearch, setCameraSearch] = useState("");
  const [demoCameraId, setDemoCameraId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [clarification, setClarification] = useState("");
  const [compilation, setCompilation] = useState<RuleCompilation | null>(null);
  const [previewReady, setPreviewReady] = useState(false);
  const [working, setWorking] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const selectedDemo = demoCameras.find((camera) => camera.id === demoCameraId) ?? null;
  const selectedCameraIndex = Math.max(
    0,
    cameras.findIndex((camera) => camera.id === selectedCamera?.id),
  );
  const fallbackImage = selectedDemo?.image ?? fallbackImages[selectedCameraIndex % fallbackImages.length];
  const running = agent?.desired_status === "running";
  const streamReady = Boolean(stream?.ready && stream.whep_url);
  const nativePreviewEnabled =
    process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "native" && running && Boolean(selectedCamera);
  const selectedName = selectedDemo?.name ?? selectedCamera?.name ?? "Choose a camera";
  const selectedLocation = selectedDemo?.location ?? (selectedCamera?.source_type === "webcam" ? "This computer" : "Primary site");
  const selectedDetail = selectedDemo?.detail ?? (selectedCamera?.source_type === "webcam" ? "Local device · Camera 01" : "Camera 01");

  const cameraRows = useMemo(() => {
    const query = cameraSearch.trim().toLowerCase();
    const realRows = cameras.map((camera, index) => ({
      id: camera.id,
      name: camera.name,
      location: camera.source_type === "webcam" ? "This computer" : camera.source_type === "file" ? "Recorded source" : "Primary site",
      detail: camera.source_type === "webcam" ? "Local device" : camera.source_type.toUpperCase(),
      image: fallbackImages[index % fallbackImages.length],
      status: camera.status,
      demo: false,
    }));
    const demoRows = cameras.length < 4
      ? demoCameras.map((camera) => ({ ...camera, status: "online" as const, demo: true }))
      : [];
    return [...realRows, ...demoRows].filter((camera) =>
      !query || `${camera.name} ${camera.location} ${camera.detail}`.toLowerCase().includes(query),
    );
  }, [cameraSearch, cameras]);

  const visibleAlerts = alerts.slice(0, 2);

  async function submitPrompt() {
    if (!selectedCamera || prompt.trim().length < 5) return;
    setWorking(true);
    setSavedMessage(null);
    try {
      setCompilation(await onCompile({ camera_id: selectedCamera.id, prompt: prompt.trim() }));
    } finally {
      setWorking(false);
    }
  }

  async function submitClarification() {
    if (!compilation || !clarification.trim()) return;
    setWorking(true);
    try {
      setCompilation(await onClarify(compilation.id, clarification.trim()));
      setClarification("");
    } finally {
      setWorking(false);
    }
  }

  async function saveCameraJob() {
    if (!compilation) return;
    setWorking(true);
    try {
      const rule = await api.acceptRuleCompilation(compilation.id);
      onRuleCreated(rule);
      setCompilation(null);
      setPrompt("");
      setSavedMessage("Camera job saved. Review its plan and evidence gate in Intelligence before deployment.");
    } finally {
      setWorking(false);
    }
  }

  if (!selectedCamera && cameras.length === 0) {
    return (
      <section className="liveOpsEmpty">
        <span><Icon name="camera" /></span>
        <h1>Connect your first camera</h1>
        <p>Start with the webcam on this computer, then add network cameras from Systems.</p>
        <button className="liveOpsPrimaryButton" disabled={busy} onClick={() => void onAddWebcam()} type="button">
          {busy ? "Connecting…" : "Use my webcam"}
        </button>
      </section>
    );
  }

  return (
    <div className="liveOperationsWorkspace">
      <div className="liveOpsTitleRow">
        <div>
          <h1>Live Operations</h1>
        </div>
        <span className={`liveOpsSystemState ${loading ? "isLoading" : ""}`}>
          <i /> {loading ? "Connecting" : `${cameras.filter((camera) => camera.status === "online").length || cameras.length} camera${cameras.length === 1 ? "" : "s"} connected`}
        </span>
      </div>

      <div className="liveOpsGrid">
        <div className="liveOpsMainColumn">
          <section className="liveOpsViewer" aria-label={`${selectedName} live view`}>
            <header>
              <div>
                <strong>{selectedName}</strong>
                <span>{selectedLocation} <b>•</b> {selectedDetail}</span>
              </div>
              <span className="liveOpsLiveState"><i /> {previewReady || streamReady ? "Live" : selectedDemo ? "Demo feed" : running ? "Connecting" : "Standby"}</span>
              <button aria-label="Open camera settings" onClick={() => onOpenAdvanced("cameras")} type="button"><Icon name="settings" /></button>
            </header>

            <div className="liveOpsVideoFrame">
              <Image alt="Logistics camera view" height={941} priority sizes="(max-width: 900px) 100vw, 72vw" src={fallbackImage} width={1672} />
              {!selectedDemo && selectedCamera && streamReady && stream?.whep_url && (
                <LiveStreamPlayer name={selectedCamera.name} whepUrl={stream.whep_url} />
              )}
              {!selectedDemo && selectedCamera && nativePreviewEnabled && (
                <NativePreview cameraId={selectedCamera.id} name={selectedCamera.name} onAvailabilityChange={setPreviewReady} />
              )}
              <span className="liveOpsFeedBadge"><i /> {previewReady || streamReady ? "LIVE" : selectedDemo ? "DEMO" : "READY"}</span>
            </div>

            <div className="liveOpsPlaybackBar" aria-label="Camera playback controls">
              <button aria-label={running ? "Stop live feed" : "Start live feed"} disabled={busy || selectedDemo !== null} onClick={() => void (running ? onStop() : onStart())} type="button">
                {running ? "Stop live feed" : "Start live feed"}
              </button>
              <span>{running ? "LIVE" : "STANDBY"}</span>
              <i><b /></i>
              <button aria-label="Open recordings" onClick={() => onOpenAdvanced("recordings")} type="button"><Icon name="clock" /></button>
              <button aria-label="Open camera settings" onClick={() => onOpenAdvanced("cameras")} type="button"><Icon name="settings" /></button>
            </div>

            <div className="liveOpsAskComposer">
              <Icon name="spark" />
              <input
                aria-label="Ask this camera"
                disabled={!selectedCamera || selectedDemo !== null}
                onChange={(event) => setPrompt(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void submitPrompt();
                }}
                placeholder={selectedDemo ? "Choose a connected camera to create a job" : "Ask this camera..."}
                value={prompt}
              />
              <button aria-label="Send camera instruction" disabled={working || prompt.trim().length < 5 || !selectedCamera || selectedDemo !== null} onClick={() => void submitPrompt()} type="button">
                <Icon name="chevron" />
              </button>
            </div>
          </section>

          {compilation && (
            <section className="liveOpsReview" aria-live="polite">
              <span><Icon name="spark" /></span>
              <div>
                <small>{compilation.status === "needs_clarification" ? "One quick question" : "Camera job ready to review"}</small>
                <strong>{compilation.status === "needs_clarification" ? compilation.clarification_question : compilation.execution_plan?.summary ?? compilation.prompt}</strong>
                {compilation.warnings.length > 0 && <p>{compilation.warnings[0]}</p>}
              </div>
              {compilation.status === "needs_clarification" ? (
                <div className="liveOpsClarification">
                  <input aria-label="Clarification answer" onChange={(event) => setClarification(event.target.value)} placeholder="Type your answer" value={clarification} />
                  <button disabled={working || !clarification.trim()} onClick={() => void submitClarification()} type="button">Continue</button>
                </div>
              ) : (
                <button className="liveOpsPrimaryButton" disabled={working} onClick={() => void saveCameraJob()} type="button">Save camera job</button>
              )}
            </section>
          )}

          {savedMessage && (
            <section className="liveOpsSaved" aria-live="polite">
              <Icon name="shield" />
              <span><strong>Saved safely</strong>{savedMessage}</span>
              <button onClick={() => onOpenAdvanced("rules")} type="button">Open Intelligence</button>
            </section>
          )}

          <section className="liveOpsIncidents">
            <header>
              <strong>{visibleAlerts.length || 0} camera{visibleAlerts.length === 1 ? "" : "s"} need attention</strong>
              <button onClick={() => onOpenAdvanced("alerts")} type="button">See all incidents</button>
            </header>
            {visibleAlerts.length > 0 ? visibleAlerts.map((alert, index) => (
              <article key={`${alert.id}-${index}`}>
                <span className="liveOpsIncidentMarker" />
                <Image alt="Incident camera thumbnail" height={64} src={index % 2 === 0 ? "/assets/camera-parking-lot.png" : "/assets/camera-warehouse-aisle.png"} width={108} />
                <div>
                  <strong>{incidentTitle(alert)}</strong>
                  <span>{incidentLocation(alert)} · {formatLocalTimestamp(alert.event.occurred_at)}</span>
                </div>
                <button onClick={() => onOpenAdvanced("alerts")} type="button">Open incident</button>
              </article>
            )) : (
              <div className="liveOpsNoIncidents"><Icon name="shield" /><span><strong>No incidents need attention</strong>New alerts will appear here without interrupting the live view.</span></div>
            )}
          </section>
        </div>

        <aside className="liveOpsCameraRail">
          <header>
            <div><strong>Cameras &amp; locations</strong><span>{cameraRows.length} available feeds</span></div>
            <button aria-label="Configure cameras" onClick={() => onOpenAdvanced("cameras")} type="button"><Icon name="settings" /></button>
          </header>
          <label className="liveOpsCameraSearch">
            <Icon name="search" />
            <input aria-label="Search cameras" onChange={(event) => setCameraSearch(event.target.value)} placeholder="Search cameras" value={cameraSearch} />
          </label>
          <div className="liveOpsCameraList">
            {cameraRows.map((camera) => {
              const active = camera.demo ? demoCameraId === camera.id : !demoCameraId && selectedCamera?.id === camera.id;
              return (
                <button
                  className={active ? "isActive" : ""}
                  key={`${camera.demo ? "demo" : "real"}-${camera.id}`}
                  onClick={() => {
                    if (camera.demo) setDemoCameraId(camera.id);
                    else {
                      setDemoCameraId(null);
                      onSelectCamera(camera.id);
                    }
                  }}
                  type="button"
                >
                  <Image alt="" height={72} src={camera.image} width={116} />
                  <span><strong>{camera.name}</strong><small>{camera.location} · {camera.detail}</small><i className={camera.status === "online" ? "isOnline" : ""}>{camera.status === "online" ? "Online" : camera.demo ? "Demo" : sentenceCase(camera.status)}</i></span>
                  <Icon name="chevron" />
                </button>
              );
            })}
          </div>
          <button className="liveOpsManageCameras" onClick={() => onOpenAdvanced("camera-discovery")} type="button"><Icon name="plus" /> Add or discover cameras</button>
        </aside>
      </div>
    </div>
  );
}
