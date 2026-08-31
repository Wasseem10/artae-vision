"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Dashboard } from "@/components/dashboard";
import { isLocalDemoHost } from "@/lib/demo-auth";
import { getSupabaseBrowserClient, isSupabaseConfigured, syncApiSession } from "@/lib/supabase";

export function DashboardGate() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (isLocalDemoHost(window.location.hostname) && sessionStorage.getItem("artae_demo_session")) {
      const timer = window.setTimeout(() => setReady(true), 0);
      return () => window.clearTimeout(timer);
    }

    if (!isSupabaseConfigured()) {
      const timer = window.setTimeout(() => {
        if (!sessionStorage.getItem("artae_demo_session")) {
          router.replace("/login");
          return;
        }
        setReady(true);
      }, 0);
      return () => window.clearTimeout(timer);
    }

    const supabase = getSupabaseBrowserClient();
    let active = true;
    const requireLogin = () => {
      if (!active) return;
      syncApiSession(null);
      setReady(false);
      void supabase.auth.signOut({ scope: "local" }).finally(() => {
        if (active) router.replace("/login?reason=session-expired");
      });
    };
    window.addEventListener("artae:auth-required", requireLogin);
    void supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      syncApiSession(data.session);
      if (!data.session) {
        router.replace("/login");
        return;
      }
      setReady(true);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      syncApiSession(session);
      if (!session) {
        setReady(false);
        router.replace("/login");
      }
    });
    return () => {
      active = false;
      window.removeEventListener("artae:auth-required", requireLogin);
      listener.subscription.unsubscribe();
    };
  }, [router]);

  if (!ready) {
    return <main aria-label="Loading workspace" style={{ minHeight: "100vh", background: "#101212" }} />;
  }

  return <Dashboard />;
}
