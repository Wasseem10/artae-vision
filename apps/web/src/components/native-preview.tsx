"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";

import { api } from "@/lib/api";

interface NativePreviewProps {
  cameraId: string;
  name: string;
  onAvailabilityChange: (available: boolean) => void;
}

export function NativePreview({ cameraId, name, onAvailabilityChange }: NativePreviewProps) {
  const [source, setSource] = useState<string | null>(null);
  const currentSource = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function refresh() {
      const blob = await api.getCameraPreview(cameraId).catch(() => null);
      if (cancelled) return;
      if (blob === null) {
        const previous = currentSource.current;
        currentSource.current = null;
        setSource(null);
        onAvailabilityChange(false);
        if (previous) URL.revokeObjectURL(previous);
        return;
      }
      const nextSource = URL.createObjectURL(blob);
      const previous = currentSource.current;
      currentSource.current = nextSource;
      setSource(nextSource);
      onAvailabilityChange(true);
      if (previous) URL.revokeObjectURL(previous);
    }

    void refresh();
    const interval = window.setInterval(() => void refresh(), 500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
      onAvailabilityChange(false);
      if (currentSource.current) URL.revokeObjectURL(currentSource.current);
      currentSource.current = null;
    };
  }, [cameraId, onAvailabilityChange]);

  if (source === null) return null;
  return (
    <Image
      alt={`${name} live preview`}
      className="livePlayer"
      fill
      sizes="(max-width: 900px) 100vw, 60vw"
      src={source}
      unoptimized
    />
  );
}
