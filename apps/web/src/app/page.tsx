import type { Metadata } from "next";
import Link from "next/link";
import { FiActivity, FiArrowRight, FiCheckCircle, FiEye, FiPlay, FiVideo } from "react-icons/fi";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Artae · Fall monitoring prototype",
  description: "Try a browser-based fall monitoring prototype with staged footage, on-device pose detection, recorded evidence, and human review. No account required.",
};

export default function Home() {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/" aria-label="Artae home"><FiActivity /><span>artae</span></Link>
        <nav aria-label="Primary navigation">
          <Link href="#how-it-works">How it works</Link>
          <Link href="/evaluation/fall">Evaluation</Link>
          <Link href="/login">Sign in</Link>
          <Link className={styles.navCta} href="/live">Open fall demo <FiArrowRight /></Link>
        </nav>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}><span /> FALL MONITORING PROTOTYPE</span>
          <h1>See a possible fall. Review the evidence. Decide what happened.</h1>
          <p>Artae runs pose detection in your browser on a staged clip, uploaded video, or webcam. When it flags a possible fall, you can replay the footage, record a review decision, and download an incident report.</p>
          <div className={styles.actions}>
            <Link className={styles.primary} href="/live"><FiPlay /> Try the fall demo <FiArrowRight /></Link>
            <Link className={styles.secondary} href="/evaluation/fall">See the evaluation</Link>
          </div>
          <p className={styles.access}><FiCheckCircle /> No account or installation needed for the staged demo.</p>
        </div>
        <div className={styles.preview}>
          <div className={styles.previewTop}><span><i /> STAGED SAMPLE</span><span>ON-DEVICE ANALYSIS</span></div>
          <video autoPlay loop muted playsInline preload="metadata" aria-label="Staged fall sample used by the browser demo">
            <source src="/vision/samples/fall-lateral.mp4" type="video/mp4" />
          </video>
          <div className={styles.previewBottom}><FiEye /><span>Run the demo to see detection, evidence, and review.</span><FiArrowRight /></div>
        </div>
      </section>

      <section className={styles.process} id="how-it-works">
        <div className={styles.sectionHeading}><span>THE WORKING FLOW</span><h2>One focused job, from video to review.</h2></div>
        <div className={styles.steps}>
          <article><span>01</span><FiVideo /><h3>Start with a sample</h3><p>Use the preselected staged fall. Then try the sitting clip as a negative control, or provide your own permitted video.</p></article>
          <article><span>02</span><FiActivity /><h3>Watch the detector</h3><p>A real MediaPipe pose loop and temporal rule run in the browser. Possible falls appear in the event log.</p></article>
          <article><span>03</span><FiEye /><h3>Review the incident</h3><p>Replay recorded evidence, mark a false alarm or reviewed event, and export the incident record.</p></article>
        </div>
      </section>

      <section className={styles.research}>
        <div><span>MEASURED, NOT ASSUMED</span><h2>A working prototype with documented limits.</h2><p>The fall detector has been tested on staged research clips. It still misses some falls and can flag ordinary activity, so every alert requires human review. This is a research prototype, not an emergency monitoring service.</p></div>
        <div className={styles.researchActions}><Link href="/evaluation/fall">Run the five-clip browser check <FiArrowRight /></Link><a href="https://github.com/Wasseem10/artae-vision/blob/977dae61d074ddb87bc047530e54de392579d814/docs/portfolio-fall-detection.md">Read the engineering case study <FiArrowRight /></a></div>
      </section>

      <footer className={styles.footer}><span>© 2026 Artae Vision</span><div><Link href="/live">Fall demo</Link><Link href="/platform">Broader platform concept</Link><Link href="/demo">Separate video analysis experiment</Link></div></footer>
    </main>
  );
}
