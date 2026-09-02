"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { FiActivity, FiArrowLeft, FiCheck, FiPlay, FiRotateCcw, FiSquare } from "react-icons/fi";

import styles from "./instant-demo.module.css";

type DemoPhase = "ready" | "watching" | "detected" | "alerted" | "paused";

export function InstantDemo() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [phase, setPhase] = useState<DemoPhase>("ready");
  const [problem, setProblem] = useState<string | null>(null);
  const detectionVisible = phase === "detected" || phase === "alerted";
  const hasEvent = phase === "alerted";

  async function runDemo() {
    const video = videoRef.current;
    if (!video) return;
    setProblem(null);
    setPhase("watching");
    video.currentTime = 0;
    try {
      await video.play();
    } catch {
      setPhase("ready");
      setProblem("Your browser blocked video playback. Press Run demo again.");
    }
  }

  function stopDemo() {
    videoRef.current?.pause();
    setPhase((current) => current === "ready" ? current : "paused");
  }

  function updateDemo() {
    const video = videoRef.current;
    if (!video || phase === "ready" || phase === "paused") return;
    if (video.currentTime >= 3.4) setPhase("alerted");
    else if (video.currentTime >= 1.4) setPhase("detected");
    else setPhase("watching");
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/"><FiActivity /><strong>artae</strong></Link>
        <div><Link href="/"><FiArrowLeft /> Back to site</Link><Link className={styles.signIn} href="/login">Sign in</Link></div>
      </header>

      <section className={styles.intro}>
        <small>NO-INSTALL GUIDED DEMO</small>
        <h1>See one camera job work<br />from start to finish.</h1>
        <p>This public sample demonstrates the exact operator flow: watch the video, detect the condition, save the event, and create an alert.</p>
        <div className={styles.disclosure}><strong>Guided sample</strong><span>This uses a known prerecorded warehouse scenario so anyone can test the product flow. Live cameras use the Artae local YOLO service.</span></div>
      </section>

      <section className={styles.workspace}>
        <div className={styles.ruleBar}>
          <div><small>CAMERA JOB</small><strong>Alert operations when a forklift is in the loading bay.</strong></div>
          <span className={phase === "watching" || detectionVisible ? styles.live : ""}><i />{phase === "ready" ? "READY" : phase === "paused" ? "PAUSED" : phase === "alerted" ? "ACTION COMPLETE" : "AI WATCHING"}</span>
        </div>

        <div className={styles.content}>
          <section className={styles.camera}>
            <div className={styles.videoStage}>
              <video muted onEnded={() => setPhase("alerted")} onTimeUpdate={updateDemo} playsInline preload="metadata" ref={videoRef}>
                <source src="/marketing/warehouse-forklift-hero.mp4" type="video/mp4" />
              </video>
              <div className={styles.cameraLabel}><i /> CAM-04 · WAREHOUSE</div>
              {detectionVisible && <div className={styles.detection}><span>forklift · 96%</span></div>}
              {phase === "watching" && <div className={styles.scanning}>YOLO scanning every frame…</div>}
              {phase === "ready" && <button className={styles.playOverlay} onClick={() => void runDemo()} type="button"><FiPlay /><span><strong>Run camera agent</strong><small>No account or installation required</small></span></button>}
            </div>
            <div className={styles.controls}>
              <span><i className={phase === "watching" || detectionVisible ? styles.live : ""} />{phase === "ready" ? "Ready to run" : phase === "paused" ? "Agent paused" : phase === "alerted" ? "Event saved" : "Analyzing video"}</span>
              {phase === "ready" ? <button onClick={() => void runDemo()} type="button"><FiPlay /> Run demo</button> : phase === "paused" || phase === "alerted" ? <button onClick={() => void runDemo()} type="button"><FiRotateCcw /> Run again</button> : <button onClick={stopDemo} type="button"><FiSquare /> Stop</button>}
            </div>
          </section>

          <aside className={styles.log}>
            <header><div><small>DETECTION LOG</small><strong>What the agent saw</strong></div><span>{hasEvent ? 1 : 0}</span></header>
            {hasEvent ? <article><i /><div><strong>Forklift detected in loading bay</strong><small>CAM-04 · 96% confidence</small><span><FiCheck /> In-app alert created</span></div></article> : <div className={styles.empty}><FiActivity /><strong>{phase === "ready" ? "Ready for a real product walkthrough" : phase === "paused" ? "Demo paused" : "Watching for the selected condition"}</strong><p>{phase === "ready" ? "Press Run camera agent. The event and action will appear here." : "Artae is following the forklift across the camera feed."}</p></div>}
          </aside>
        </div>

        <div className={styles.steps}>
          <span className={phase !== "ready" ? styles.done : ""}><i>{phase !== "ready" ? <FiCheck /> : "1"}</i><b>Video connected</b></span>
          <span className={detectionVisible ? styles.done : ""}><i>{detectionVisible ? <FiCheck /> : "2"}</i><b>Condition detected</b></span>
          <span className={hasEvent ? styles.done : ""}><i>{hasEvent ? <FiCheck /> : "3"}</i><b>Evidence logged</b></span>
          <span className={hasEvent ? styles.done : ""}><i>{hasEvent ? <FiCheck /> : "4"}</i><b>Alert created</b></span>
        </div>
        {problem && <p className={styles.problem} role="alert">{problem}</p>}
      </section>

      <section className={styles.next}>
        <div><small>LIVE CAMERA MODE</small><h2>Ready to use your own webcam?</h2><p>The installed Artae camera service runs YOLO locally, saves video segments, and sends real detections to your account.</p></div>
        <Link href="/login">Open the workspace</Link>
      </section>
    </main>
  );
}
