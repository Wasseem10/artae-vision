"use client";

import { useEffect, useState } from "react";

import { eventWebSocketUrl } from "@/lib/api";
import type { AgentTelemetry, CameraAgent, StreamStatus, VideoEvent } from "@/lib/types";

export function useEventStream(
  onEvent: (event: VideoEvent) => void,
  onTelemetry: (telemetry: AgentTelemetry) => void,
  onAgentStatus: (status: CameraAgent) => void,
): StreamStatus {
  const [status, setStatus] = useState<StreamStatus>(() =>
    eventWebSocketUrl() ? "connecting" : "offline",
  );

  useEffect(() => {
    const url = eventWebSocketUrl();
    if (!url) return;

    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const connect = (isRetry = false) => {
      if (isRetry) setStatus("connecting");
      socket = new WebSocket(url);
      socket.onopen = () => setStatus("live");
      socket.onmessage = (message) => {
        const payload = JSON.parse(message.data as string) as {
          type: string;
          data?: VideoEvent | AgentTelemetry | CameraAgent;
        };
        if (payload.type === "event.created" && payload.data) onEvent(payload.data as VideoEvent);
        if (payload.type === "agent.telemetry" && payload.data) {
          onTelemetry(payload.data as AgentTelemetry);
        }
        if (payload.type === "agent.status" && payload.data) {
          onAgentStatus(payload.data as CameraAgent);
        }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        setStatus("offline");
        if (!stopped) retry = setTimeout(() => connect(true), 3000);
      };
    };

    connect();
    return () => {
      stopped = true;
      if (retry) clearTimeout(retry);
      socket?.close();
    };
  }, [onAgentStatus, onEvent, onTelemetry]);

  return status;
}
