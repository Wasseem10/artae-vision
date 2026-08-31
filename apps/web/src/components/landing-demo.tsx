"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import styles from "./marketing-page.module.css";

const steps = [
  { label: "Watching camera", detail: "Warehouse aisle · Camera 03" },
  { label: "Condition confirmed", detail: "Person detected without a hard hat" },
  { label: "Alert prepared", detail: "Evidence ready for the safety manager" },
];

export function LandingDemo() {
  const [phase, setPhase] = useState(0);
  const [runId, setRunId] = useState(0);

  const replay = useCallback(() => {
    setPhase(0);
    setRunId((value) => value + 1);
  }, []);

  useEffect(() => {
    const detected = window.setTimeout(() => setPhase(1), 1250);
    const alerted = window.setTimeout(() => setPhase(2), 2750);

    return () => {
      window.clearTimeout(detected);
      window.clearTimeout(alerted);
    };
  }, [runId]);

  return (
    <div className={styles.demoShell}>
      <div className={styles.demoChrome}>
        <div>
          <span className={styles.demoPulse} />
          INTERACTIVE EXAMPLE
        </div>
        <span>SAMPLE CAMERA · 12:41:08 PM</span>
      </div>

      <div className={styles.demoBody}>
        <div className={styles.demoVisual}>
          <Image
            alt="Sample warehouse camera view with a worker walking near forklifts"
            fill
            sizes="(max-width: 820px) 100vw, 66vw"
            src="/assets/camera-hard-hat-compliance.png"
          />
          <div className={styles.demoImageShade} />
          <div className={`${styles.demoDetection} ${phase >= 1 ? styles.demoDetectionVisible : ""}`}>
            <span>PERSON · NO HARD HAT</span>
          </div>
          <div className={styles.demoPrompt}>
            <small>WATCH FOR</small>
            <strong>Tell me when someone enters this aisle without a hard hat.</strong>
          </div>
        </div>

        <div className={styles.demoPanel}>
          <div className={styles.demoPanelHeading}>
            <small>HOW IT RESPONDS</small>
            <strong>From video to action</strong>
          </div>

          <div className={styles.demoSteps} aria-live="polite">
            {steps.map((step, index) => (
              <div className={index <= phase ? styles.demoStepActive : ""} key={step.label}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <p><strong>{step.label}</strong><small>{step.detail}</small></p>
                <i>{index < phase ? "DONE" : index === phase ? "ACTIVE" : "WAITING"}</i>
              </div>
            ))}
          </div>

          <div className={`${styles.demoAlert} ${phase >= 2 ? styles.demoAlertVisible : ""}`}>
            <small>ALERT READY</small>
            <strong>Safety manager</strong>
            <span>Snapshot and reason attached</span>
          </div>

          <button className={styles.demoReplay} onClick={replay} type="button">Replay example</button>
        </div>
      </div>

      <div className={styles.demoFooter}>
        <p><span>01</span> Describe the condition in plain language.</p>
        <p><span>02</span> Artae watches live or uploaded video.</p>
        <p><span>03</span> The right person gets the evidence.</p>
        <Link href="/login">Build your own visual agent <span>↗</span></Link>
      </div>
    </div>
  );
}
