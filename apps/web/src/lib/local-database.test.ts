import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { openSessionDatabase } from "./local-database";

function setup() {
  const db = { close: vi.fn(), onversionchange: null as null | (() => void) };
  const request = { result: db, error: new Error("Storage failed"),
    transaction: { abort: vi.fn() }, onsuccess: null as null | (() => void),
    onerror: null as null | (() => void), onblocked: null as null | (() => void),
    onupgradeneeded: null as null | (() => void) };
  vi.stubGlobal("indexedDB", { open: vi.fn(() => request) });
  return { request, db };
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it("rejects stalled setup at the deadline and closes a late connection", async () => {
  const { request, db } = setup();
  const result = openSessionDatabase();
  const rejection = expect(result).rejects.toThrow("Browser storage did not respond");
  vi.advanceTimersByTime(15000);
  await rejection;
  request.onsuccess!();
  expect(db.close).toHaveBeenCalledOnce();
  expect(vi.getTimerCount()).toBe(0);
});

it("cancels the deadline after success and releases the connection on version change", async () => {
  const { request, db } = setup();
  const result = openSessionDatabase();
  vi.advanceTimersByTime(14999);
  request.onsuccess!();
  expect(await result).toBe(db);
  expect(vi.getTimerCount()).toBe(0);
  expect(db.close).not.toHaveBeenCalled();
  db.onversionchange!();
  expect(db.close).toHaveBeenCalledOnce();
});

it("rejects blocked setup immediately and aborts a deferred upgrade", async () => {
  const { request } = setup();
  const result = openSessionDatabase();
  const rejection = expect(result).rejects.toThrow("Close older Artae tabs");
  request.onblocked!();
  await rejection;
  request.onupgradeneeded!();
  expect(request.transaction.abort).toHaveBeenCalledOnce();
  request.onerror!();
  expect(vi.getTimerCount()).toBe(0);
});

it("does not upgrade storage when the open request has already timed out", async () => {
  const { request } = setup();
  const result = openSessionDatabase();
  const rejection = expect(result).rejects.toThrow("did not respond");
  vi.advanceTimersByTime(15000);
  await rejection;
  request.onupgradeneeded!();
  expect(request.transaction.abort).toHaveBeenCalledOnce();
});

it("cleans up the deadline on an open error and allows a fresh request", async () => {
  const { request } = setup();
  const result = openSessionDatabase();
  const rejection = expect(result).rejects.toThrow("Storage failed");
  request.onerror!();
  await rejection;
  expect(vi.getTimerCount()).toBe(0);
  const retry = openSessionDatabase();
  request.onsuccess!();
  await expect(retry).resolves.toBe(request.result);
  expect(vi.getTimerCount()).toBe(0);
});
