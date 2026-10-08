"use client";
import Link from "next/link";
import { useState } from "react";
import { FiActivity, FiArrowRight, FiBell, FiCheckCircle, FiFileText, FiGithub, FiMenu, FiVideo, FiX } from "react-icons/fi";
import styles from "./marketing-page.module.css";

export function ProductHeader() {
  const [open, setOpen] = useState(false);
  return <header className={styles.header}>
    <Link className={styles.brand} href="/" aria-label="Artae home"><span className={styles.brandMark}><FiActivity /></span><strong>artae</strong></Link>
    <nav className={styles.desktopNav} aria-label="Primary navigation"><Link href="/#workflow">How it works</Link><Link href="/engineering">Engineering</Link><Link href="/privacy">Data & privacy</Link></nav>
    <div className={styles.headerActions}><Link href="/login?next=live">Sign in</Link><Link className={styles.downloadButton} href="/live">Open monitor <FiArrowRight /></Link></div>
    <button className={styles.menuButton} type="button" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} aria-controls="product-menu" onClick={() => setOpen(!open)}>{open ? <FiX /> : <FiMenu />}</button>
    {open && <nav id="product-menu" className={styles.mobileNav} aria-label="Mobile navigation" onClick={() => setOpen(false)}><Link href="/#workflow">How it works</Link><Link href="/engineering">Engineering</Link><Link href="/privacy">Data & privacy</Link><Link href="/login?next=live">Sign in</Link><Link className={styles.downloadButton} href="/live">Open monitor <FiArrowRight /></Link></nav>}
  </header>;
}
export function ProductFooter() {
  return <footer className={styles.footer}><Link className={styles.brand} href="/">artae.</Link><p>A computer-vision engineering prototype. Human review required.</p><nav aria-label="Footer navigation"><Link href="/engineering">Engineering</Link><Link href="/privacy">Data & privacy</Link><a href="https://github.com/Wasseem10/artae-vision">GitHub <FiGithub /></a></nav><small>© 2026 Artae Vision</small></footer>;
}
const questions = [
  ["What can I try today?", "Use a staged sample, your own permitted recording, or a webcam. The same monitor supports experimental fall detection, person presence, and optional account-connected AWS checks for a described visible condition. Fall detection is the evaluated engineering focus."],
  ["Do I need an account?", "No. The guest demo keeps recordings and reviews in this browser. Sign in before starting to save agents and upload footage to your account. Account history depends on successful saves; a local recording is not a cloud backup."],
  ["Is this ready for unattended monitoring?", "No. Evaluation has exposed substantial missed falls across different scenes. The browser must stay open and visible. Use the sample recordings to explore the workflow; this prototype is not an emergency response service."],
  ["Are alerts and AI summaries the same thing?", "A temporal pose rule creates possible-fall alerts. A trained motion model can add unverified review suggestions without caregiver notifications. Optional cloud summaries add context; they do not establish that a fall happened."],
];
export function MarketingPage() {
  return <main className={styles.page} id="top">
    <a className={styles.skipLink} href="#main-content">Skip to content</a><ProductHeader />
    <aside className={styles.saleBar}><span>LIVE + RECORDED VIDEO</span><strong>One monitor. Evidence you can review.</strong><Link href="/engineering">See the engineering <FiArrowRight /></Link></aside>
    <section className={styles.hero} id="main-content">
      <div className={styles.heroEyebrow}><i /> Experimental computer vision · human review required</div>
      <h1>Give your camera one clear job.<br /><span>See the moment. Review the evidence.</span></h1>
      <p>Watch for a possible fall, keep the relevant footage, and record a human review. Explore the complete workflow with a staged sample, directly in your browser.</p>
      <div className={styles.heroActions}><Link className={styles.heroPrimary} href="/live"><FiVideo /> Try the live demo <FiArrowRight /></Link><Link className={styles.heroSecondary} href="/engineering">Explore the build</Link></div>
      <small className={styles.heroHint}>No account or camera permission needed for the sample.</small>
      <div className={styles.heroSteps} aria-label="Workflow"><span><b>01</b> Connect video</span><FiArrowRight /><span><b>02</b> Watch detections</span><FiArrowRight /><span><b>03</b> Review evidence</span></div>
      <ul className={styles.heroEvidence}>
        <li><FiActivity /><strong>On-device pose AI</strong><small>Visible body landmarks</small></li><li><FiBell /><strong>Possible-fall alerts</strong><small>Experimental temporal rules</small></li><li><FiVideo /><strong>Recorded evidence</strong><small>Replay the surrounding moment</small></li><li><FiFileText /><strong>Human review</strong><small>Notes, outcomes, incident reports</small></li>
      </ul>
    </section>
    <section className={styles.numberedSection} id="workflow">
      <header className={styles.sectionIntro}><span className={styles.sectionNumber}>01</span><div><small>The workflow</small><p>One workspace, start to finish</p></div><div><h2>From an alert to a reviewable incident.</h2><p>Choose a source, run the monitor, and open an event to inspect its footage. Acknowledge it, mark it reviewed, or record a false alarm.</p></div></header>
      <div className={styles.overviewVideo}><video controls preload="none" playsInline poster="/media/fall-monitor-walkthrough.png" aria-label="Recorded demonstration of the fall monitor"><source src="/media/fall-monitor-walkthrough.webm" type="video/webm" /></video></div>
      <p className={styles.caption}>Recorded workflow demonstration using a staged sample. The interface may differ from the latest version; detections are generated from video frames.</p>
      <div className={styles.productFlow}><article><span>01 / SET UP</span><FiVideo /><h3>Start with a sample</h3><p>Test a staged fall, sitting, or bending before connecting your own permitted video.</p></article><article><span>02 / INSPECT</span><FiActivity /><h3>See the model work</h3><p>Watch pose landmarks, person tracks, frame counts, and processing time as the video runs.</p></article><article><span>03 / REVIEW</span><FiCheckCircle /><h3>Close the loop</h3><p>Replay the event, save reviewer notes, and export an incident report. Stopping keeps the session history.</p></article></div>
    </section>
    <section className={styles.numberedSection} id="engineering">
      <header className={styles.sectionIntro}><span className={styles.sectionNumber}>02</span><div><small>Behind the demo</small><p>Code, evaluation, tradeoffs</p></div><div><h2>Built to be inspected.</h2><p>The project includes a real browser inference pipeline, persisted evidence, and reproducible evaluation. Its limitations are documented alongside its results.</p></div></header>
      <div className={styles.engineeringCard}><div><small>INDEPENDENT EVALUATION</small><h3>The sample is a starting point.</h3><p>Cross-scene tests revealed missed falls. Multi-person tracking is implemented, but its accuracy needs further work. See per-source results, rejected model candidates, and the next validation gate.</p><Link className={styles.heroPrimary} href="/engineering">Read the case study <FiArrowRight /></Link></div><div className={styles.stack}><span>Next.js / React / TypeScript</span><span>MediaPipe pose workers</span><span>IndexedDB / Supabase</span><span>Python evaluation / Vitest / Playwright</span><a href="https://github.com/Wasseem10/artae-vision">Explore the repository <FiGithub /></a></div></div>
    </section>
    <section className={styles.numberedSection} id="faq"><header className={styles.sectionIntro}><span className={styles.sectionNumber}>03</span><div><small>Before you start</small><p>Capabilities & limits</p></div><div><h2>Clear expectations.</h2><p>Try the workflow with recorded samples. Real monitoring needs stronger independent validation.</p></div></header><div className={styles.faqBody}>{questions.map(([question, answer]) => <details key={question}><summary>{question}</summary><p>{answer}</p></details>)}</div></section>
    <ProductFooter />
  </main>;
}
