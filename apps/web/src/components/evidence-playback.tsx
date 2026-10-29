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
  const seekApplied = useRef(false);
  function acceptFrame(video: HTMLVideoElement) {
    // Metadata alone says nothing about whether the requested incident frame
    // has decoded. Keep the deadline while the initial seek is outstanding.
    if (!seekApplied.current || video.error || video.readyState < 2 || video.seeking) return;
    clearTimeout(timeout.current);
    setLoaded(true);
    setProblem(null);
  }
  useEffect(() => {
    const video = videoRef.current;
    if (focusOnMount) video?.focus();
    // Cached metadata may arrive before this effect. Only a decoded frame
    // with a completed initial seek can bypass the load deadline.
    if (!video?.error && (!seekApplied.current || (video?.readyState ?? 0) < 2 || video?.seeking)) {
      timeout.current = setTimeout(() => setProblem("This recording is taking too long to load."), 15000);
    }
    return () => { clearTimeout(timeout.current); video?.pause(); };
  }, [videoRef, focusOnMount]);
  return <div>
    <video ref={videoRef} controls playsInline src={url} aria-label={label}
      onLoadedMetadata={(event) => {
        try {
          event.currentTarget.currentTime = seek;
          seekApplied.current = true;
          acceptFrame(event.currentTarget);
        } catch {
          clearTimeout(timeout.current);
          setProblem("This recording could not be opened at the incident time.");
        }
      }}
      onLoadedData={(event) => acceptFrame(event.currentTarget)}
      onCanPlay={(event) => acceptFrame(event.currentTarget)}
      onSeeked={(event) => acceptFrame(event.currentTarget)}
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
