"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { FiActivity, FiArrowRight, FiCheck } from "react-icons/fi";

import styles from "./login-page.module.css";
import { isLocalDemoHost, isLocalDemoLogin, LOCAL_DEMO_EMAIL, LOCAL_DEMO_PASSWORD } from "@/lib/demo-auth";
import { getSupabaseBrowserClient, isGoogleAuthAvailable, isSupabaseConfigured, syncApiSession } from "@/lib/supabase";

export function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [working, setWorking] = useState(false);
  const [googleAvailable, setGoogleAvailable] = useState<boolean | null>(null);
  const [localDemoAvailable, setLocalDemoAvailable] = useState(false);

  useEffect(() => {
    let active = true;
    const demoTimer = window.setTimeout(() => {
      if (active) setLocalDemoAvailable(isLocalDemoHost(window.location.hostname));
    }, 0);
    void isGoogleAuthAvailable().then((available) => {
      if (active) setGoogleAvailable(available);
    });
    return () => {
      active = false;
      window.clearTimeout(demoTimer);
    };
  }, []);

  async function signInWithGoogle() {
    setError("");
    setMessage("");
    setWorking(true);
    try {
      if (!isSupabaseConfigured()) throw new Error("Supabase authentication is not configured.");
      if (!googleAvailable) throw new Error("Google sign-in still needs to be enabled in Supabase.");
      const { error: oauthError } = await getSupabaseBrowserClient().auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${window.location.origin}/app` },
      });
      if (oauthError) throw oauthError;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Google sign-in failed. Please try again.");
      setWorking(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setError("Enter your email address first.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setWorking(true);
    try {
      if (isLocalDemoLogin(email, password, window.location.hostname)) {
        sessionStorage.removeItem("access_token");
        sessionStorage.setItem("artae_demo_session", JSON.stringify({ email: LOCAL_DEMO_EMAIL, signedInAt: new Date().toISOString() }));
        router.replace("/app");
        return;
      }

      if (!isSupabaseConfigured()) {
        sessionStorage.setItem("artae_demo_session", JSON.stringify({ email, signedInAt: new Date().toISOString() }));
        router.push("/app");
        return;
      }

      const supabase = getSupabaseBrowserClient();
      if (mode === "signup") {
        const { data, error: signUpError } = await supabase.auth.signUp({ email, password });
        if (signUpError) throw signUpError;
        syncApiSession(data.session);
        if (!data.session) {
          setMessage("Check your email to confirm your account, then log in.");
          setMode("login");
          return;
        }
      } else {
        const { data, error: loginError } = await supabase.auth.signInWithPassword({ email, password });
        if (loginError) throw loginError;
        syncApiSession(data.session);
      }
      router.replace("/app");
    } catch (failure) {
      const detail = failure instanceof Error ? failure.message : "Authentication failed. Please try again.";
      setError(
        mode === "login" && detail.toLowerCase().includes("invalid login credentials")
          ? "No account was found with those details. Choose Create account if this is your first time."
          : detail,
      );
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.visual}>
        <Image src="/assets/camera-loading-dock.png" alt="Loading dock camera analyzed by Artae Vision" fill priority sizes="(max-width: 820px) 100vw, 54vw" />
        <div className={styles.visualShade} />
        <Link className={styles.wordmark} href="/"><span><FiActivity /></span>artae</Link>
        <div className={styles.analysisBar}><span><i /> Artae Vision scanning</span><b>CAM-02 · Loading dock</b></div>
        <div className={styles.trackingBox}><span>delivery truck · 97%</span></div>
        <div className={styles.arrivalMarker}><span>arrival line</span></div>
        <div className={styles.scanBeam} />
        <div className={styles.visualCopy}>
          <p>AI VIDEO AGENTS</p>
          <h1>Give every<br />camera a job.</h1>
          <span>Tell Artae what to watch for. Get the evidence, alert, and action when it happens.</span>
          <div className={styles.visualSteps}><span><FiCheck /> Connect video</span><span><FiCheck /> Describe the event</span><span><FiCheck /> Start the agent</span></div>
        </div>
      </section>

      <section className={styles.formSide}>
        <Link className={styles.back} href="/">← Back to home</Link>
        <div className={styles.formWrap}>
          <p className={styles.eyebrow}>ACCOUNT ACCESS</p>
          <h2>{mode === "login" ? "Welcome back." : "Create your account."}</h2>
          <p className={styles.intro}>{mode === "login" ? "Sign in to see your cameras, agents, saved footage, and alert history." : "Create one workspace for your cameras, agents, footage, alerts, and connected actions."}</p>
          <div className={styles.authMode} role="group" aria-label="Authentication mode">
            <button className={mode === "login" ? styles.activeMode : ""} onClick={() => { setMode("login"); setError(""); setMessage(""); }} type="button">Log in</button>
            <button className={mode === "signup" ? styles.activeMode : ""} onClick={() => { setMode("signup"); setError(""); setMessage(""); }} type="button">Create account</button>
          </div>
          {isSupabaseConfigured() && googleAvailable === true ? (
            <>
              <button className={styles.googleButton} disabled={working} onClick={signInWithGoogle} type="button">
                <svg aria-hidden="true" viewBox="0 0 24 24">
                  <path d="M21.6 12.23c0-.71-.06-1.4-.18-2.07H12v3.92h5.38a4.6 4.6 0 0 1-2 3.02v2.54h3.24c1.9-1.75 2.98-4.33 2.98-7.41Z" fill="#4285F4" />
                  <path d="M12 22c2.7 0 4.98-.9 6.63-2.43l-3.24-2.54c-.9.6-2.05.97-3.39.97-2.61 0-4.82-1.76-5.61-4.13H3.04v2.62A10 10 0 0 0 12 22Z" fill="#34A853" />
                  <path d="M6.39 13.87A6 6 0 0 1 6.07 12c0-.65.11-1.28.32-1.87V7.51H3.04A10 10 0 0 0 2 12c0 1.61.38 3.14 1.04 4.49l3.35-2.62Z" fill="#FBBC05" />
                  <path d="M12 6c1.47 0 2.79.51 3.83 1.5l2.87-2.87A9.62 9.62 0 0 0 12 2a10 10 0 0 0-8.96 5.51l3.35 2.62C7.18 7.76 9.39 6 12 6Z" fill="#EA4335" />
                </svg>
                Continue with Google
              </button>
              <div className={styles.divider}><span>or use email</span></div>
            </>
          ) : null}
          {mode === "login" ? (
            <p className={styles.previewNote}>First time here? Choose <strong>Create account</strong> above, then use your email and a new password.</p>
          ) : null}
          <form onSubmit={submit} noValidate>
            <label>
              <span>Work email</span>
              <input autoComplete="email" inputMode="email" onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" type="email" value={email} />
            </label>
            <label>
              <span>Password</span>
              <input autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} placeholder="8+ characters" type="password" value={password} />
            </label>
            {error ? <p className={styles.error} role="alert">{error}</p> : null}
            {message ? <p className={styles.success} role="status">{message}</p> : null}
            <button disabled={working} type="submit">{working ? "Please wait…" : mode === "login" ? "Continue to workspace" : "Create account"} <span><FiArrowRight /></span></button>
          </form>
          {localDemoAvailable ? <p className={styles.previewNote}>Local demo account: <strong>{LOCAL_DEMO_EMAIL}</strong> / <strong>{LOCAL_DEMO_PASSWORD}</strong></p> : null}
          {!isSupabaseConfigured() ? <p className={styles.previewNote}>Local preview mode is active. Configure Supabase to enable persistent production accounts.</p> : null}
        </div>
        <p className={styles.legal}>By continuing, you agree to the Terms and Privacy Policy.</p>
      </section>
    </main>
  );
}
