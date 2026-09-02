"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  FiActivity,
  FiArrowRight,
  FiBell,
  FiCheck,
  FiChevronDown,
  FiCpu,
  FiDownload,
  FiEye,
  FiFileText,
  FiGrid,
  FiMenu,
  FiMessageCircle,
  FiSearch,
  FiShield,
  FiTrendingDown,
  FiVideo,
  FiX,
  FiZap,
} from "react-icons/fi";

import styles from "./marketing-page.module.css";

type AgentKey = "safety" | "dock" | "after-hours" | "plate" | "occupancy" | "upload";

const agents: Record<AgentKey, { name: string; description: string; condition: string; action: string; image: string }> = {
  safety: { name: "PPE safety", description: "When PPE is missing, save evidence and alert the safety lead.", condition: "worker_without_hard_hat", action: "telegram + incident", image: "/assets/camera-hard-hat-compliance.png" },
  dock: { name: "Dock arrival", description: "When a delivery truck arrives, notify the dock team with a clip.", condition: "truck_entered_dock_3", action: "operations alert", image: "/assets/camera-loading-dock.png" },
  "after-hours": { name: "After hours", description: "When a person enters after hours, notify the security contact.", condition: "person_after_10pm", action: "security alert", image: "/assets/camera-employee-entrance.png" },
  plate: { name: "Plate access", description: "Match an arriving vehicle to the membership list and open the gate.", condition: "approved_plate_seen", action: "gate webhook", image: "/assets/camera-east-gate.png" },
  occupancy: { name: "Occupancy", description: "Watch a waiting area and alert when it exceeds its safe limit.", condition: "occupancy_above_12", action: "manager alert", image: "/assets/camera-shipping-office.png" },
  upload: { name: "Video review", description: "Review uploaded footage and save every matching moment.", condition: "blocked_emergency_route", action: "investigation log", image: "/assets/camera-warehouse-aisle.png" },
};

const faqGroups = [
  { title: "the product", items: [
    ["What is Artae?", "Artae gives live cameras and recorded footage plain-language jobs. Each visual agent watches for one condition, keeps reviewable evidence, and performs an approved action."],
    ["What can Artae actually detect today?", "The dependable live demo supports fall detection through local YOLO pose, plus people, common vehicles, object counts, and zone entry or exit through local YOLO tracking. PPE, license plates, and broader semantic requests remain experimental and are not presented as dependable live jobs."],
    ["Can I use existing cameras?", "Yes. Artae is designed for computer webcams, uploaded recordings, and supported IP camera feeds."],
    ["Does footage save to my account?", "When cloud recording is enabled, clips and their metadata are stored against the signed-in account so they can be viewed on another device."],
    ["Can I exclude sensitive cameras or hours?", "Yes. Recording and agent schedules can be limited by camera, workspace policy, and operating hours."],
    ["What should I expect from storage use?", "Storage depends on resolution, frame rate, retention, and whether you keep continuous footage or only event clips."],
  ]},
  { title: "getting useful work back", items: [
    ["What should I do first after signing in?", "Connect one camera, describe one important event, choose an alert action, and test the agent before expanding to more cameras."],
    ["How does the owner receive alerts?", "A confirmed event can create an in-app alert, send a Telegram message, or call a connected webhook."],
    ["Can Artae review uploaded video?", "Yes. Uploaded recordings use the same rule, evidence, and log workflow as a live camera."],
    ["Can an agent perform a real action?", "Yes. Approved actions can call external webhooks and integrations after the visual condition is confirmed."],
    ["Is Artae only for safety monitoring?", "No. Teams can create agents for deliveries, access, queues, vehicles, occupancy, quality checks, and many other operational events."],
  ]},
  { title: "for teams", items: [
    ["Can multiple people use the same workspace?", "The account-backed data model supports saved agents, footage metadata, events, and permissions across devices and team members."],
    ["Can a company deploy without exposing every camera?", "Workspace roles and camera-level access can limit who sees feeds, clips, agents, and alert history."],
  ]},
];

export function MarketingPage() {
  const [exploreOpen, setExploreOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [mobileExploreOpen, setMobileExploreOpen] = useState(false);
  const [withArtae, setWithArtae] = useState(true);
  const [modelOpen, setModelOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState<AgentKey>("safety");
  const [runStep, setRunStep] = useState(0);
  const [openFaq, setOpenFaq] = useState<Record<string, boolean>>({ "What is Artae?": true });
  const agent = agents[activeAgent];

  useEffect(() => {
    if (runStep < 1 || runStep >= 4) return;
    const timer = window.setTimeout(() => setRunStep((step) => step + 1), 780);
    return () => window.clearTimeout(timer);
  }, [runStep]);

  return (
    <main className={styles.page} id="top">
      <header className={styles.header}>
        <Link className={styles.brand} href="#top" aria-label="Artae home"><span className={styles.brandMark}><FiActivity /></span><strong>artae</strong></Link>
        <nav className={styles.desktopNav} aria-label="Primary navigation">
          <button type="button" aria-expanded={exploreOpen} onClick={() => setExploreOpen((value) => !value)}>Explore <FiChevronDown /></button>
          <a href="#use-cases">Use cases</a><a href="#features">Pricing</a><a href="#features">Enterprise</a><a href="#faq">Security</a>
        </nav>
        <div className={styles.headerActions}><Link href="/demo">Try demo</Link><Link href="/login">Sign in</Link><Link className={styles.downloadButton} href="/login"><FiDownload /> Open Artae</Link></div>
        <button className={styles.menuButton} type="button" aria-label="Toggle menu" aria-expanded={mobileOpen} onClick={() => setMobileOpen((value) => !value)}>{mobileOpen ? <FiX /> : <FiMenu />}</button>
        {exploreOpen && <div className={styles.megaMenu}>
          <div className={styles.megaIntro}><strong>Explore Artae</strong><p>Connect video, find what matters, and give every camera a job.</p></div>
          <a href="#agents"><FiZap /><span><b>Visual agents</b><small>Run recurring jobs on live camera context.</small></span></a>
          <a href="#remember"><FiSearch /><span><b>Video search</b><small>Find useful moments across saved footage.</small></span></a>
          <a href="#features"><FiGrid /><span><b>Operations workflows</b><small>Turn events into alerts, actions, and logs.</small></span></a>
          <a href="#faq"><FiShield /><span><b>Security and privacy</b><small>Control recording, retention, and access.</small></span></a>
        </div>}
      </header>

      {mobileOpen && <nav className={styles.mobileNav} aria-label="Mobile navigation">
        <button type="button" aria-expanded={mobileExploreOpen} onClick={() => setMobileExploreOpen((value) => !value)}><span>Explore</span><b>{mobileExploreOpen ? "−" : "+"}</b></button>
        {mobileExploreOpen && <div className={styles.mobileExplore}><a href="#agents">Visual agents</a><a href="#remember">Video search</a><a href="#features">Operations workflows</a><a href="#faq">Security and privacy</a></div>}
        <Link href="/demo">Try the demo <FiArrowRight /></Link><a href="#use-cases">Use cases <FiArrowRight /></a><a href="#features">Pricing <FiArrowRight /></a><a href="#features">Enterprise <FiArrowRight /></a><a href="#faq">Security <FiArrowRight /></a><Link href="/login">Sign in <FiArrowRight /></Link><Link className={styles.downloadButton} href="/login">Open Artae</Link>
      </nav>}

      <aside className={styles.saleBar}><span>● &nbsp; LIVE + RECORDED VIDEO</span><strong>Describe the event. Artae watches for it.</strong><code>SEE IT WORK</code><span>SAVE EVIDENCE · SEND ALERTS · RUN ACTIONS <FiArrowRight /></span></aside>

      <section className={styles.hero}>
        <div className={styles.heroEyebrow}><i /> AI video agents for safety and operations</div>
        <h1>Tell your cameras what to watch for.<br /><span>Artae alerts you and takes action.</span></h1>
        <p>Connect a live camera or upload video, then describe the event in plain language. Artae watches for it, saves the evidence, and sends an alert or triggers the action you choose.</p>
        <div className={styles.heroActions}><Link className={styles.heroPrimary} href="/login"><FiVideo /> Give a camera a job</Link><Link className={styles.heroSecondary} href="/demo"><FiEye /> Run the no-install demo <b>→</b></Link></div>
        <div className={styles.heroSteps} aria-label="How Artae works">
          <span><b>01</b> Connect video</span><FiArrowRight /><span><b>02</b> Describe the event</span><FiArrowRight /><span><b>03</b> Get alerts and actions</span>
        </div>
        <ul className={styles.heroEvidence} aria-label="Examples of events Artae can detect and act on">
          <li><span className={styles.heroEvidenceArt}><Image src="/marketing/hero-event-ppe.png" alt="Illustration of Artae verifying a worker's hard hat" width={220} height={220} priority /></span><div><strong>PPE checked</strong><small>Safety rule verified</small></div></li>
          <li><span className={styles.heroEvidenceArt}><Image src="/marketing/hero-event-truck.png" alt="Illustration of Artae detecting a delivery truck arrival" width={220} height={220} priority /></span><div><strong>Truck arrived</strong><small>Dock team notified</small></div></li>
          <li><span className={styles.heroEvidenceArt}><Image src="/marketing/hero-event-fall.png" alt="Illustration of Artae detecting a person falling" width={220} height={220} priority /></span><div><strong>Fall alert sent</strong><small>Help notified instantly</small></div></li>
          <li><span className={styles.heroEvidenceArt}><Image src="/marketing/hero-event-vehicle.png" alt="Illustration of Artae detecting and acting on a stopped vehicle" width={220} height={220} priority /></span><div><strong>Vehicle stopped</strong><small>Action triggered</small></div></li>
        </ul>
        <form className={styles.mobileEmail} onSubmit={(event) => event.preventDefault()}><strong>Send the workspace link</strong><input aria-label="Email address" placeholder="you@example.com" type="email" /><button type="submit">Email me the link</button><small>We will send the access link and occasional product updates.</small></form>
      </section>

      <section className={styles.numberedSection} id="overview">
        <header className={styles.sectionIntro}><span className={styles.sectionNumber}>00</span><div><small>Overview</small><p>Film · 44 seconds</p></div><div><h2>From camera feed to real-world action.</h2><p>Artae detects the moment you described, saves the relevant clip, records what happened, and triggers the response you chose.</p></div></header>
        <div className={styles.overviewVideo}>
          <video autoPlay controls loop muted playsInline poster="/assets/camera-loading-dock.png"><source src="/marketing/warehouse-forklift-hero.mp4" type="video/mp4" /></video>
          <div className={styles.liveAnalysis}><span><i /> Artae Vision analyzing</span><b>CAM-04 · Warehouse floor</b></div>
          <div className={styles.overviewTrack}><span>forklift · 96%</span></div>
          <div className={styles.overviewZone}><span>restricted route</span></div>
          <div className={styles.scanSweep} />
        </div>
      </section>

      <section className={`${styles.numberedSection} ${styles.investigateSection}`} id="remember">
        <header className={styles.sectionIntro}><span className={styles.sectionNumber}>01</span><div><small>Investigate</small><p>Interactive comparison · AI context</p></div><div><h2>Ask your cameras what happened.</h2><p>Search saved video in plain language and get a direct answer with the exact clip and event record behind it.</p></div></header>
        <div className={styles.comparison}>
          <div className={styles.compareHeader}>
            <div className={styles.previewBrand}><i /><span>Artae investigation</span><small>Example event</small></div>
            <div className={styles.compareTabs} role="group" aria-label="Compare AI with and without Artae"><button aria-pressed={withArtae} className={withArtae ? styles.tabActive : ""} onClick={() => setWithArtae(true)}>With Artae</button><button aria-pressed={!withArtae} className={!withArtae ? styles.tabActive : ""} onClick={() => setWithArtae(false)}>Without Artae</button></div>
            <div className={styles.modelPicker}><button type="button" aria-expanded={modelOpen} onClick={() => setModelOpen((value) => !value)}><FiCpu /> Gemini Vision Pro <FiChevronDown /></button>{modelOpen && <div><button onClick={() => setModelOpen(false)}><b>Gemini Vision Pro</b><small>Cloud · best reasoning</small></button><button onClick={() => setModelOpen(false)}><b>GPT Vision</b><small>Cloud · OpenAI</small></button><button onClick={() => setModelOpen(false)}><b>Local vision</b><small>Local · private</small></button></div>}</div>
          </div>
          <div className={styles.compareWorkspace}>
            <div className={styles.chatPanel}>
              <div className={styles.panelMeta}><span>CAM-02 · Loading dock</span><div className={styles.memoryBadge}>{withArtae ? "14 days connected" : "no camera context"}</div></div>
              <div className={styles.question}>When did the delivery truck arrive, and was the dock clear?</div>
              <div className={styles.answer}>{withArtae ? <>
                <div className={styles.evidenceCard}>
                  <div className={styles.evidenceVisual}><Image src="/assets/camera-loading-dock.png" alt="Example loading dock camera evidence" width={420} height={236} /><span className={styles.clipStatus}><i /> Artae scanning</span><time>09:14 AM</time><div className={styles.evidenceTrack}><span>delivery truck · 97%</span></div><div className={styles.arrivalLine}><span>arrival line crossed</span></div><div className={styles.evidenceSweep} /></div>
                  <div className={styles.evidenceCopy}><small>Verified answer</small><p>The truck entered <b>Dock 3 at 9:14 AM.</b> The bay was clear when it crossed the arrival line.</p></div>
                </div>
                <div className={styles.sourceRows}><span><FiCheck /> Arrival event <b>confirmed</b></span><span><FiVideo /> CAM-02 clip <b>00:38 saved</b></span></div>
              </> : <div className={styles.emptyAnswer}><FiEye /><small>No visual context</small><p>I can’t see your camera or its history. Connect the footage to answer this question.</p></div>}</div>
              <div className={styles.fakeInput}>Ask anything about what your cameras saw… <FiArrowRight /></div><div className={styles.promptChips}>{["Who entered after hours?", "Show every missing hard hat", "When did the truck arrive?", "Was the gate opened?"].map((text) => <button key={text}>{text}</button>)}</div>
            </div>
            <aside className={styles.contextPanel}><small>Agent context</small>{withArtae ? <><h3>Grounded in your operation</h3><ul><li><span>Camera history</span><b>14 days</b></li><li><span>Visual agents</span><b>6 active</b></li><li><span>Saved events</span><b>128</b></li><li><span>Actions</span><b>3 connected</b></li></ul><div className={styles.connected}><span><FiBell /> Telegram</span><span><FiZap /> Webhook</span></div><p>Every answer links back to the camera, timestamp, saved clip, and agent decision that produced it.</p></> : <><h3>Only this conversation</h3><ul><li><span>Camera history</span><b>none</b></li><li><span>Event logs</span><b>none</b></li><li><span>Saved clips</span><b>none</b></li><li><span>Actions</span><b>none</b></li></ul><p>The model only knows what you paste into this conversation.</p></>}</aside>
          </div>
        </div>
      </section>

      <section className={styles.numberedSection} id="agents">
        <header className={styles.sectionIntro}><span className={styles.sectionNumber}>02</span><div><small>Act</small><p>Interactive product preview · Agents</p></div><div><h2>Every camera can run its own agent.</h2><p>Give each feed a job. Its agent watches for one condition, verifies the evidence, and alerts or acts when it happens.</p></div></header>
        <div className={styles.agentPreview}>
          <div className={styles.agentBar}><span>Agent · {agent.name}</span><b><i /> ACCOUNT-SAVED</b></div>
          <div className={styles.agentTabs}>{(Object.keys(agents) as AgentKey[]).map((key) => <button key={key} className={activeAgent === key ? styles.agentTabActive : ""} disabled={runStep > 0 && runStep < 4} onClick={() => { setActiveAgent(key); setRunStep(0); }}>{agents[key].name}</button>)}</div>
          <div className={styles.agentBody}>
            <div className={styles.agentCopy}><h3>{agent.name}</h3><p>{agent.description}</p><div className={styles.ruleFile}><span><FiFileText /> agent.rule</span><code>---<br />name: {agent.name.toLowerCase().replaceAll(" ", "-")}<br />trigger: {agent.condition}<br />action: {agent.action}<br />---<br /><br />When the condition is confirmed,<br />save evidence and run the action.</code></div><div className={styles.runTrack}>{["Detected", "Confirmed", "Acted"].map((label, index) => <span key={label} className={runStep > index ? styles.done : ""}><i>{runStep > index ? <FiCheck /> : index + 1}</i>{label}</span>)}</div><button className={styles.simulate} disabled={runStep > 0 && runStep < 4} onClick={() => setRunStep(1)}>{runStep === 4 ? "Run again" : runStep > 0 ? "Processing…" : "Simulate event"}<FiArrowRight /></button></div>
            <div className={styles.agentCamera}><Image src={agent.image} alt={`${agent.name} camera preview`} fill sizes="(max-width: 760px) 100vw, 52vw" /><div className={styles.cameraBar}><span><i /> ARTAE VISION · SCANNING</span><time>09:14:37</time></div><div className={styles.agentTrack}><span>{agent.condition.replaceAll("_", " ")} · 94%</span></div><div className={styles.agentSweep} />{runStep > 1 && <div className={styles.detection}><FiEye /> condition confirmed</div>}</div>
          </div>
          {runStep === 4 && <div className={styles.notification}><FiBell /><span><b>{agent.name} alert</b>{agent.action} completed with saved evidence.</span><button onClick={() => setRunStep(0)} aria-label="Dismiss"><FiX /></button></div>}
        </div>
      </section>

      <section className={styles.features} id="features">
        <header className={`${styles.sectionIntro} ${styles.featuresIntro}`}><span className={styles.sectionNumber}>03</span><div><small>What Artae does</small><p>Live capabilities + workflow concepts</p></div><div><h2>Turn a camera into a focused visual agent.</h2><p>The live demo currently handles falls, people, common vehicles, counts, and zone events. The broader examples below show the product direction.</p></div></header>

        <div className={styles.productFlow} aria-label="How Artae works">
          <div><span>01</span><FiVideo /><strong>Connect the video</strong><p>Use a live camera, an IP feed, or upload recorded footage.</p></div>
          <div><span>02</span><FiEye /><strong>Choose a supported job</strong><p>Watch for a fall, a person or vehicle, an object count, or entry into a camera zone.</p></div>
          <div><span>03</span><FiZap /><strong>Choose what happens</strong><p>Send an alert, save the clip, create an incident, or call a connected webhook.</p></div>
        </div>

        <article className={styles.featureStory}>
          <div className={styles.jobVisual}>
            <Image src="/assets/camera-warehouse-aisle.png" alt="Factory camera watching a production line for a growing bottleneck" fill sizes="(max-width: 760px) 100vw, 58vw" />
            <div className={styles.jobCameraBar}><span><i /> ARTAE VISION · LIVE</span><b>LINE 4</b></div>
            <div className={styles.bottleneckZone}><span>QUEUE GROWING</span></div>
            <div className={styles.queueCount}><FiTrendingDown /><span><b>12 items waiting</b>4m 12s above target</span></div>
            <div className={styles.jobSweep} />
          </div>
          <div className={styles.jobCopy}>
            <small>Workflow concept · factory operations</small>
            <h3>Catch a bottleneck before it stops the line.</h3>
            <p>The camera agent watches Station 4 continuously, confirms that the queue is actually growing, and sends the shift manager the exact moment that needs attention.</p>
            <div className={styles.jobRule}>
              <div><b>WATCH</b><span>Parts waiting at Station 4 for more than 2 minutes</span></div>
              <div><b>DO</b><span><FiMessageCircle /> Send a WhatsApp alert via webhook and save the evidence clip</span></div>
            </div>
            <div className={styles.jobResults}><span><FiCheck /> event verified</span><span><FiVideo /> footage saved</span><span><FiMessageCircle /> manager notified</span></div>
          </div>
        </article>

        <div className={styles.useCaseDirectory}>
          <header><small>What teams use Artae for</small><h3>One platform. Many camera jobs.</h3><p>Start with one useful job, then add more agents to the cameras and footage you already have.</p></header>
          <div className={styles.useCaseRows}>
            <div><FiShield /><span><b>Workplace safety</b><small>Detect missing hard hats, blocked exits, unsafe zones, and PPE violations.</small></span><em>Alert safety lead</em></div>
            <div><FiActivity /><span><b>Factory flow</b><small>Spot bottlenecks, stalled work, growing queues, and abnormal downtime.</small></span><em>Notify shift manager</em></div>
            <div><FiCheck /><span><b>Process compliance</b><small>Confirm required checks, handoffs, cleaning steps, and operating procedures.</small></span><em>Create incident log</em></div>
            <div><FiGrid /><span><b>Loading docks</b><small>Know when trucks arrive, bays become blocked, or loading runs late.</small></span><em>Message operations</em></div>
            <div><FiEye /><span><b>Security + vehicle access</b><small>Watch after-hours entry, tailgating, vehicles, and approved license plates.</small></span><em>Trigger access webhook</em></div>
            <div><FiSearch /><span><b>Recorded footage search</b><small>Ask what happened and jump to the matching clip, camera, and timestamp.</small></span><em>Find evidence fast</em></div>
          </div>
        </div>
      </section>

      <section className={styles.downloadCta} id="use-cases"><h2>See the complete camera-agent flow.</h2><p>Known sample video · visible detection · event log · in-app alert</p><Link className={styles.heroPrimary} href="/demo"><FiVideo /> Run the no-install demo</Link></section>

      <section className={styles.faqSection} id="faq">
        <header className={`${styles.sectionIntro} ${styles.faqIntro}`}><span className={styles.sectionNumber}>04</span><div><small>FAQ</small><p>Clear answers</p></div><div><h2>Questions before you give a camera a job.</h2><p>How Artae handles cameras, footage, alerts, actions, accounts, and team access.</p></div></header>
        <div className={styles.faqBody}>{faqGroups.map((group, groupIndex) => <div className={styles.faqGroup} key={group.title}><div className={styles.faqCategory}><span>0{groupIndex + 1}</span><h3>{group.title}</h3></div><div>{group.items.map(([question, answer], itemIndex) => <details key={question} open={Boolean(openFaq[question])}><summary onClick={(event) => { event.preventDefault(); setOpenFaq((current) => ({ ...current, [question]: !current[question] })); }}><span className={styles.faqNumber}>{String(itemIndex + 1).padStart(2, "0")}</span><b>{question}</b><FiChevronDown /></summary><p>{answer}</p></details>)}</div></div>)}</div>
        <div className={styles.contactLine}><div><FiActivity /><span><small>Need a specific answer?</small><b>Talk through your camera setup with us.</b></span></div><a href="mailto:hello@artae.ai">hello@artae.ai <FiArrowRight /></a></div>
      </section>

      <footer className={styles.footer}>
        <section className={styles.footerCta}><p>See it before you install it</p><h2>Run a camera agent from start to alert.</h2><span>The guided sample makes the product flow testable in any modern browser. Live cameras use the local Artae YOLO service.</span><div><Link className={styles.heroPrimary} href="/demo">Try the demo</Link><Link href="/login">Open workspace</Link></div></section>
        <div className={styles.footerGrid}><div className={styles.footerBrand}><Link className={styles.brand} href="#top"><span className={styles.brandMark}><FiActivity /></span><strong>artae</strong></Link><p>Visual intelligence powered by everything your cameras have seen.</p><small>Account-saved · live · recorded</small></div>{[
          ["Product", ["Overview", "Agents", "Footage", "Alerts"]], ["Solutions", ["Workplace safety", "Loading docks", "Vehicle access", "Video review"]], ["Company", ["About", "Principles", "Contact", "Sign in"]], ["Trust", ["Security", "Privacy", "Retention", "Evidence review"]]
        ].map(([title, links]) => <nav key={title as string}><h3>{title}</h3>{(links as string[]).map((link) => <a href={link === "Sign in" ? "/login" : "#top"} key={link}>{link}</a>)}</nav>)}</div>
        <div className={styles.legal}><span>© 2026 Artae Vision. All rights reserved.</span><span>Terms &nbsp; Privacy &nbsp; Security</span></div>
      </footer>
    </main>
  );
}
