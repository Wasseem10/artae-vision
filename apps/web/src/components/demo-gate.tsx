"use client";

import { useEffect, useState } from "react";
import { VisualWatch } from "@/components/visual-watch";
import { getSupabaseBrowserClient, isSupabaseConfigured, syncApiSession } from "@/lib/supabase";

export function DemoGate() {
  const [mode, setMode] = useState<"account" | "public" | null>(null);
  useEffect(() => {
    if (!isSupabaseConfigured()) {
      const timer = window.setTimeout(() => setMode("public"), 0);
      return () => window.clearTimeout(timer);
    }
    const client = getSupabaseBrowserClient();
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      syncApiSession(session);
      setMode(session ? "account" : "public");
    });
    return () => data.subscription.unsubscribe();
  }, []);
  if (!mode) return <main style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}><p role="status">Opening your video workspace…</p></main>;
  return <VisualWatch key={mode} mode={mode} />;
}
