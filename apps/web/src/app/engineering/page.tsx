import type { Metadata } from "next";
import Link from "next/link";
import { ProductHeader, ProductFooter } from "@/components/marketing-page";
import styles from "@/components/marketing-page.module.css";

export const metadata: Metadata = { title: "Engineering · Artae Vision", description: "Architecture, measured limitations, evaluation evidence, and engineering decisions behind the Artae Vision prototype." };
const repo = "https://github.com/Wasseem10/artae-vision";
export default function EngineeringPage() {
  return <main className={styles.page}><ProductHeader /><article className={styles.document}>
    <small>ENGINEERING CASE STUDY / OCTOBER 2026</small>
    <h1>A camera event is only useful when you can inspect it.</h1>
    <p className={styles.lede}>Artae Vision connects real browser inference to recorded evidence and a human review workflow. Fall detection is the research focus, with substantial accuracy limitations still unresolved.</p>
    <div className={styles.heroActions}><Link className={styles.heroPrimary} href="/live">Run the sample</Link><a className={styles.heroSecondary} href={repo}>Read the source</a></div>
    <h2>The live pipeline</h2>
    <ol className={styles.pipeline}><li><b>01 / Observe</b>Video frames → MediaPipe pose inference in a browser worker.</li><li><b>02 / Track</b>A primary pose path and additional person tracks → independent temporal fall rules.</li><li><b>03 / Preserve</b>Possible-fall event → recording segments, timestamps, and delivery status.</li><li><b>04 / Review</b>Playable clip → reviewer notes, outcome, persisted history, and incident report.</li></ol>
    <p>A learned pose-window model adds device-only, unverified review suggestions. It cannot send caregiver notifications. Optional Amazon Bedrock Nova and Strands enrichment adds context to eligible events; the local fall path continues when that service is unavailable.</p>
    <h2>The stack and why it is here</h2>
    <ul><li><strong>Next.js, React, TypeScript:</strong> one monitor for guests and accounts, explicit session state, and typed incident data.</li><li><strong>MediaPipe + Web Workers:</strong> body landmarks and pose inference run on the device. Tracking IDs are session-local and do not identify a person.</li><li><strong>MediaRecorder + IndexedDB:</strong> independently playable segments and local review history. Account saves use Supabase Auth, Postgres, and storage through the API.</li><li><strong>Python + browser evaluation:</strong> pinned media hashes, source/model revisions, per-clip results, and training/runtime comparisons.</li><li><strong>Vitest + Playwright:</strong> rules and persistence checks, plus an end-to-end alert → evidence → review → reload test with cloud failures.</li></ul>
    <h2>What evaluation actually found</h2>
    <p>553 staged fall and daily-activity clips across six research sources have been examined. These are clip-level results, with different splits and previously examined regression sets. They cannot be combined into a single field accuracy score.</p>
    <div className={styles.tableWrap}><table><caption>Selected documented results; counts are clips, not people or frames.</caption><thead><tr><th scope="col">Evaluation</th><th scope="col">Fall clips detected</th><th scope="col">Activity clips alerted</th><th scope="col">Meaning</th></tr></thead><tbody>
      <tr><th scope="row"><a href={repo + "/blob/main/docs/urfall-browser-benchmark.md"}>UR Fall reserved clips</a></th><td>2 / 20</td><td>1 / 30</td><td>Early temporal rule; unseen-scene gap.</td></tr>
      <tr><th scope="row"><a href={repo + "/blob/main/docs/gmdcsa24-browser-validation.md"}>GMDCSA subjects 3–4</a></th><td>24 / 38</td><td>2 / 42</td><td>Learned candidate; now review-only. Temporal rule: 17 / 38 and 1 / 42.</td></tr>
      <tr><th scope="row"><a href={repo + "/blob/main/docs/caucafall-multiperson-regression.md"}>CAUCAFall regression</a></th><td>20 / 50</td><td>1 / 50</td><td>Fused browser path on already examined single-person clips.</td></tr>
      <tr><th scope="row"><a href={repo + "/blob/main/docs/mpfdd-first-look-result.md"}>MPFDD shared frame</a></th><td>2 / 22</td><td>0 / 6</td><td>Harder multi-person scenes; only 63 seconds of negative footage.</td></tr>
    </tbody></table></div>
    <p className={styles.notice}>The staged demo shows the workflow. It does not establish real-world recall, an acceptable false-alert rate, or readiness for unattended monitoring. The combined negative footage across four audited sources is only about 0.49 hours.</p>
    <h2>Engineering decisions</h2>
    <ul><li><strong>Keep alerts separate from suggestions.</strong> Model candidates that failed cross-source validation stayed outside the caregiver alert path.</li><li><strong>Preserve the primary observer.</strong> A four-pose-only pipeline regressed on CAUCAFall. Fusing it with the original primary observer recovered some detections while adding one false alert.</li><li><strong>Save reviews before claiming success.</strong> Local and account save failures stay visible; optional enrichment must preserve a review completed while the cloud response was in flight.</li><li><strong>Diagnose observation before tuning thresholds.</strong> The next accuracy step is to label visible people and compare raw poses, retained tracks, and event timing on failed shared-frame clips, then evaluate changes on untouched clips and hard negatives.</li></ul>
    <h2>Explore the evidence</h2>
    <ul><li><a href={repo + "/blob/main/docs/portfolio-fall-detection.md"}>Full portfolio case study and source-specific evaluation reports</a></li><li><a href={repo + "/blob/main/docs/fall-product-plan.md"}>Product plan and remaining validation gates</a></li><li><a href={repo + "/blob/main/apps/web/src/lib/multi-person-fall.ts"}>Browser tracking and fall-rule implementation</a></li><li><a href={repo + "/blob/main/scripts/check-live-fall-demo.cjs"}>Reproducible demo and review smoke test</a></li></ul>
  </article><ProductFooter /></main>;
}
