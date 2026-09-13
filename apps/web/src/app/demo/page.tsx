import type { Metadata } from "next";

import { VisualWatch } from "@/components/visual-watch";

export const metadata: Metadata = {
  title: "Try the Artae demo",
  description: "Try Artae's AI caregiver assistant with a staged fall, uploaded video, or webcam.",
};

export default function DemoPage() {
  return <VisualWatch mode="public" />;
}
