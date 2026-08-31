import type { Metadata } from "next";

import { DashboardGate } from "@/components/dashboard-gate";

export const metadata: Metadata = {
  title: "Workspace · Artae Vision",
};

export default function AppWorkspace() {
  return <DashboardGate />;
}
