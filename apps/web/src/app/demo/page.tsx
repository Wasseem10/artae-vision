import type { Metadata } from "next";

import { BrowserMonitor } from "@/components/browser-monitor";

export const metadata: Metadata = {
  title: "Try the Artae demo",
  description: "Run real on-device person and experimental pose-based fall detection without installing a camera service.",
};

export default function DemoPage() {
  return <BrowserMonitor />;
}
