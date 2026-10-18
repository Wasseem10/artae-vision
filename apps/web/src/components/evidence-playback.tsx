"use client";
import { useEffect, useRef, useState, type RefObject } from "react";
import styles from "./evidence-playback.module.css";

type Props = {
  url: string;
  seek: number;
  label: string;
  videoRef: RefObject<HTMLVideoElement | null>;
};

function PlaybackAttempt({ url, seek, label, videoRef, onRetry, focusOnMount }: Props & { onRetry: () => void; focusOnMount: boolean }) {
  const [loaded, setLoaded] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const timeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    const video = videoRef.current;
    if (focusOnMount) video?.focus();
    // Metadata can arrive from a cached recording before this effect runs.
    if (!video?.error && (video?.readyState ?? 0) < 1) {
      timeout.current = setTimeout(() => setProblem("This recording is taking too long to load."), 15000);
    }
    return () => { clearTimeout(timeout.current); video?.pause(); };
  }, [videoRef, focusOnMount]);
  return <div>
    <video ref={videoRef} controls playsInline src={url} aria-label={label}
      onLoadedMetadata={(event) => {
        clearTimeout(timeout.current);
        try {
          event.currentTarget.currentTime = seek;
          setLoaded(true);
          setProblem(null);
        } catch { setProblem("This recording could not be opened at the incident time."); }
      }}
      onError={(event) => {
        clearTimeout(timeout.current);
        const code = event.currentTarget.error?.code;
        setProblem(code === 2 ? "This recording could not be downloaded."
          : code === 3 || code === 4 ? "This recording is unavailable or cannot be decoded."
            : "This recording could not be played.");
      }} />
    {problem ? <div>
      <p role="alert">{problem} Retry loading it or choose another segment. Your incident and review notes are kept.</p>
      <button type="button" className={styles.retry} onClick={onRetry}>Retry playback</button>
    </div> : !loaded && <p role="status">Loading recording…</p>}
  </div>;
}

/** Each retry gets its own state so late errors from a removed player cannot
 * replace the new attempt's result. The parent keys this component by URL. */
export function EvidencePlayback(props: Props) {
  const [attempt, setAttempt] = useState(0);
  return <PlaybackAttempt key={attempt} {...props} focusOnMount={attempt > 0} onRetry={() => {
    props.videoRef.current?.pause();
    setAttempt((value) => value + 1);
  }} />;
}
