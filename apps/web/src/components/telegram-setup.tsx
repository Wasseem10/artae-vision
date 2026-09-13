"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, request } from "@/lib/api";
import type { IntegrationConnector, TelegramChat } from "@/lib/types";
import styles from "./visual-watch.module.css";

export function TelegramSetup({ account, disabled, selected, onChange }: {
  account: boolean; disabled: boolean; selected: string; onChange: (id: string) => void;
}) {
  const [connections, setConnections] = useState<IntegrationConnector[]>([]);
  const [token, setToken] = useState("");
  const [chats, setChats] = useState<TelegramChat[]>([]);
  const [chat, setChat] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [adding, setAdding] = useState(false);
  useEffect(() => {
    if (!account) return;
    void api.listConnectors().then((items) => setConnections(items.filter((item) => item.connector_type === "telegram" && item.enabled)))
      .catch(() => setMessage("Could not load Telegram connections. Sign in with the workspace owner account."));
  }, [account]);
  async function run(action: () => Promise<void>) {
    setBusy(true); setMessage("");
    try { await action(); } catch (error) { setMessage(error instanceof Error ? error.message : "Connection failed."); }
    finally { setBusy(false); }
  }
  return <div className={styles.smsSetup}>
    <strong>Telegram alerts + event clip</strong>
    {!account ? <p><small>Sign in to connect a caregiver’s Telegram chat and send private clip links.</small><Link href="/login?next=demo">Sign in to connect Telegram</Link></p> : <>
      <label>Send alerts to<select value={selected} disabled={disabled || busy} onChange={(e) => onChange(e.target.value)}>
        <option value="">Dashboard only</option>{connections.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      <small>When selected, a detected event sends its description, timestamp, and a short silent clip. Anyone with the clip link can view it for 24 hours. Only share footage you have permission to share.</small>
      {selected && <button disabled={disabled || busy} onClick={() => void run(async () => {
        const receipt = await request<{ message: string }>(`/browser-sessions/telegram/${selected}/test`, { method: "POST" });
        setMessage(receipt.message);
      })}>Send Telegram test</button>}
      <button disabled={disabled || busy} onClick={() => setAdding(!adding)}>{adding ? "Close setup" : "Connect a Telegram chat"}</button>
      {adding && <>
        <small>Use your existing @BotFather bot. Open that bot in Telegram and tap Start, then enter its token here. Tokens are encrypted on the server.</small>
        <label>Bot token<input type="password" autoComplete="off" value={token} disabled={busy} onChange={(e) => { setToken(e.target.value); setChats([]); setChat(""); }} /></label>
        <button disabled={busy || !token.trim()} onClick={() => void run(async () => {
          const found = await api.discoverTelegramChats(token.trim()); setChats(found);
          setMessage(found.length ? "Choose the caregiver chat below." : "No chats found. Send Start to your bot in Telegram, then try again.");
        })}>Find my Telegram chat</button>
        {!!chats.length && <label>Caregiver chat<select value={chat} onChange={(e) => setChat(e.target.value)}><option value="">Choose a chat</option>{chats.map((item) => <option key={item.chat_id} value={item.chat_id}>{item.title}</option>)}</select></label>}
        <details><summary>Chat not listed? Use a known chat ID</summary><small>If another integration consumes this bot’s updates, use your own verified Telegram chat ID.</small><label>Telegram chat ID<input inputMode="numeric" value={chat} onChange={(e) => setChat(e.target.value)} placeholder="Your numeric chat ID" /></label></details>
          <button disabled={busy || !/^-?\d+$/.test(chat) || !token.trim()} onClick={() => void run(async () => {
            const result = await api.createConnector({ name: `Caregiver — ${chats.find((item) => item.chat_id === chat)?.title || "Telegram"}`.slice(0, 110),
              connector_type: "telegram", credential: token.trim(), configuration: { chat_id: chat }, scopes: ["notifications:write"] });
            setConnections((items) => [...items, result]); onChange(result.id); setToken(""); setChats([]); setAdding(false);
            setMessage("Connected. Send a test to confirm it arrives on your phone.");
          })}>Save caregiver connection</button>
      </>}
      {message && <p role="status">{message}</p>}
    </>}
  </div>;
}
