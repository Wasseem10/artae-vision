"use client";

import { useEffect, useRef } from "react";

interface BrowserWebcamPreviewProps {
  name: string;
  onAvailabilityChange: (available: boolean) => void;
}

export function BrowserWebcamPreview({ name, onAvailabilityChange }: BrowserWebcamPreviewProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    let media: MediaStream | null = null;

    void navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 1920 },
        height: { ideal: 1080 },
        aspectRatio: { ideal: 16 / 9 },
        frameRate: { ideal: 30 },
      },
      audio: false,
    }).then((stream) => {
      if (cancelled) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      media = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      onAvailabilityChange(true);
    }).catch(() => onAvailabilityChange(false));

    return () => {
      cancelled = true;
      onAvailabilityChange(false);
      media?.getTracks().forEach((track) => track.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
    };
  }, [onAvailabilityChange]);

  return <video aria-label={`${name} live browser preview`} autoPlay className="livePlayer" muted playsInline ref={videoRef} />;
}
