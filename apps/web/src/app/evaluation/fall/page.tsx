import type { Metadata } from "next";
import { FallEvaluationRunner } from "@/components/fall-evaluation-runner";

export const metadata: Metadata = {
  title: "Fall detector evaluation · Artae Engineering",
  description: "Local repeatable benchmark for Artae's browser fall detector.",
  robots: { index: false, follow: false },
};

export default function FallEvaluationPage() {
  return <FallEvaluationRunner />;
}
