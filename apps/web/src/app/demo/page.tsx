import type { Metadata } from "next";

import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Try the Artae demo",
  description: "Upload permitted video or connect a webcam and let Nova and Strands review a visible care condition.",
};

export default function DemoPage() {
  redirect("/live");
}
