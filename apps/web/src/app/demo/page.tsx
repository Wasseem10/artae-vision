import type { Metadata } from "next";

import { VisualWatch } from "@/components/visual-watch";

export const metadata: Metadata = {
  title: "Try the Artae demo",
  description: "Try Artae's plain-language visual monitor with a sample, upload, or webcam.",
};

export default function DemoPage() {
  return <VisualWatch />;
}
