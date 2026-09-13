import type { Metadata } from "next";

import { BrowserMonitor } from "@/components/browser-monitor";

export const metadata: Metadata = {
  title: "Live fall monitor · Artae Vision",
  description: "Run Artae's continuous on-device pose monitor with AWS incident review and caregiver actions.",
};

export default function LiveMonitorPage() {
  return <BrowserMonitor experience="senior-safety" />;
}
