import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabasePublishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

let browserClient: SupabaseClient | null = null;

export function isSupabaseConfigured(): boolean {
  return Boolean(supabaseUrl && supabasePublishableKey);
}

export async function isGoogleAuthAvailable(): Promise<boolean> {
  if (!supabaseUrl || !supabasePublishableKey) return false;
  try {
    const response = await fetch(`${supabaseUrl}/auth/v1/settings`, {
      cache: "no-store",
      headers: { apikey: supabasePublishableKey },
    });
    if (!response.ok) return false;
    const settings = (await response.json()) as { external?: { google?: boolean } };
    return settings.external?.google === true;
  } catch {
    return false;
  }
}

export function getSupabaseBrowserClient(): SupabaseClient {
  if (!supabaseUrl || !supabasePublishableKey) {
    throw new Error("Supabase authentication is not configured.");
  }
  browserClient ??= createClient(supabaseUrl, supabasePublishableKey, {
    auth: {
      autoRefreshToken: true,
      detectSessionInUrl: true,
      persistSession: true,
    },
  });
  return browserClient;
}

export function syncApiSession(session: Session | null): void {
  if (typeof window === "undefined") return;
  if (session?.access_token) {
    sessionStorage.setItem("access_token", session.access_token);
  } else {
    sessionStorage.removeItem("access_token");
  }
}

export async function signOut(): Promise<void> {
  if (isSupabaseConfigured()) {
    await getSupabaseBrowserClient().auth.signOut();
  }
  if (typeof window !== "undefined") {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("artae_demo_session");
  }
}
