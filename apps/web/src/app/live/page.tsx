import type { Metadata } from "next";

import { BrowserMonitor } from "@/components/browser-monitor";

export const metadata: Metadata = {
  title: "Live camera monitor · Artae Vision",
  description: "Monitor for possible falls across multiple people or describe another visible condition in one workspace.",
};

export default function LiveMonitorPage() {
  return <BrowserMonitor experience="senior-safety" />;
}
