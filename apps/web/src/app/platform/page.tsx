import type { Metadata } from "next";
import { MarketingPage } from "@/components/marketing-page";

export const metadata: Metadata = {
  title: "Artae · Broader camera-agent concept",
  description: "Explore the broader Artae camera-agent platform concept and its video analysis experiments.",
};

export default function PlatformPage() {
  return <MarketingPage />;
}
