import type { Metadata } from "next";

import { DemoGate } from "@/components/demo-gate";

export const metadata: Metadata = {
  title: "Try the Artae demo",
  description: "Upload permitted video or connect a webcam and let Nova and Strands review a visible care condition.",
};

export default function DemoPage() {
  return <DemoGate />;
}
