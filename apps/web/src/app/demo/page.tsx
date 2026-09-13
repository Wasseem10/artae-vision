import type { Metadata } from "next";

import { BrowserMonitor } from "@/components/browser-monitor";

export const metadata: Metadata = {
  title: "Try the Artae demo",
  description: "Try Artae's plain-language visual monitor with a sample, upload, or webcam.",
};

export default function DemoPage() {
  return <BrowserMonitor experience="senior-safety" />;
}
