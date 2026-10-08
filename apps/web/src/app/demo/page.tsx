import type { Metadata } from "next";

import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Try the Artae demo",
  description: "Open the single Artae monitor to explore detection, recorded evidence, and human review.",
};

export default function DemoPage() {
  redirect("/live");
}
