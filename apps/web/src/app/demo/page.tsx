import type { Metadata } from "next";

import { InstantDemo } from "@/components/instant-demo";

export const metadata: Metadata = {
  title: "Try the Artae demo",
  description: "Run a guided Artae camera-agent example without installing the camera service.",
};

export default function DemoPage() {
  return <InstantDemo />;
}
