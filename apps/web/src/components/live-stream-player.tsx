"use client";

import { useEffect, useRef } from "react";

interface ReaderOptions {
  url: string;
  onError?: (error: string) => void;
  onTrack?: (event: RTCTrackEvent) => void;
}

interface MediaMTXReader {
  close: () => void;
}

interface MediaMTXReaderConstructor {
  new (options: ReaderOptions): MediaMTXReader;
}

declare global {
  interface Window {
    MediaMTXWebRTCReader?: MediaMTXReaderConstructor;
  }
}

const readerScripts = new Map<string, Promise<void>>();

export function readerScriptUrl(whepUrl: string): string {
  return new URL("/reader.js", whepUrl).toString();
}

function loadReaderScript(url: string): Promise<void> {
  if (window.MediaMTXWebRTCReader) return Promise.resolve();
  const current = readerScripts.get(url);
  if (current) return current;

  const loading = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.async = true;
    script.src = url;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Could not load the MediaMTX WebRTC reader."));
    document.head.appendChild(script);
  }).catch((error) => {
    readerScripts.delete(url);
    throw error;
  });
  readerScripts.set(url, loading);
  return loading;
}

interface LiveStreamPlayerProps {
  name: string;
  whepUrl: string;
}

export function LiveStreamPlayer({ name, whepUrl }: LiveStreamPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let cancelled = false;
    let reader: MediaMTXReader | null = null;
    const video = videoRef.current;

    void loadReaderScript(readerScriptUrl(whepUrl)).then(() => {
      const Reader = window.MediaMTXWebRTCReader;
      if (cancelled || !Reader || !video) return;
      reader = new Reader({
        url: whepUrl,
        onError: (error) => video.setAttribute("data-stream-error", error),
        onTrack: (event) => {
          video.srcObject = event.streams[0] ?? null;
          void video.play().catch(() => undefined);
        },
      });
    }).catch(() => {
      video?.setAttribute("data-stream-error", "reader-unavailable");
    });

    return () => {
      cancelled = true;
      reader?.close();
      if (video) video.srcObject = null;
    };
  }, [whepUrl]);

  return (
    <video
      aria-label={`${name} live video`}
      autoPlay
      className="livePlayer"
      disablePictureInPicture
      muted
      playsInline
      ref={videoRef}
    />
  );
}
