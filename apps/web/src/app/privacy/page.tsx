import type { Metadata } from "next";
import Link from "next/link";
import { ProductHeader, ProductFooter } from "@/components/marketing-page";
import styles from "@/components/marketing-page.module.css";
export const metadata: Metadata = { title: "Data & privacy · Artae Vision" };
export default function PrivacyPage() {
  return <main className={styles.page}><ProductHeader /><article className={styles.document}>
    <small>DATA HANDLING / PROTOTYPE</small><h1>Know where your video goes.</h1>
    <p className={styles.lede}>Use only footage you have permission to process. This page describes the current workflow; it is not a claim of enterprise certification or regulatory compliance.</p>
    <h2>Guest monitoring</h2><p>Pose inference runs in your browser. Recordings, events, and review notes are stored locally with IndexedDB. Guest history stays in this browser profile; clearing site data removes it. Browser storage may be evicted or become full. Download important evidence before leaving.</p>
    <h2>Account monitoring</h2><p>Sign in before starting to enable account saves. Agent settings, recording segments, event metadata, and reviews may be uploaded to the configured backend. The interface reports pending uploads and failures. A failed save is not a cloud backup.</p>
    <h2>Optional cloud analysis</h2><p>The staged guest fall demo can send sampled frames around a local alert to Amazon Bedrock for optional review when the service is available. Guest uploads and webcams use local fall detection. A described visual condition requires consent to send sampled frames to AWS. Cloud analysis is probabilistic and may miss events or return incorrect descriptions.</p>
    <h2>Recording and notifications</h2><p>The monitor records video without audio. Sound alerts are generated on your device. Browser notifications require your permission. SMS is shown only when the workspace supports it and a caregiver phone is configured; acceptance by AWS does not guarantee carrier delivery. Guest runs do not send texts or phone calls.</p>
    <h2>Runtime and identity limits</h2><p>The browser must remain open and visible; closing your laptop stops monitoring. Person track numbers last only within the session and are not identity recognition. Multi-person and fall accuracy are experimental. The prototype is not an emergency response service.</p>
    <h2>Retention and access</h2><p>Guest history has no guaranteed retention period. The account workflow does not yet expose self-service deletion or configurable retention. Avoid uploading sensitive footage until its handling meets your requirements. See the repository for the storage and authorization implementation.</p>
    <div className={styles.heroActions}><Link className={styles.heroPrimary} href="/live">Open monitor</Link><a className={styles.heroSecondary} href="https://github.com/Wasseem10/artae-vision">Inspect the source</a></div>
  </article><ProductFooter /></main>;
}
