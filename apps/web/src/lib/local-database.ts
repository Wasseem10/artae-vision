/** Bound connection setup only; transaction completion is handled by callers. */
export function openSessionDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open("artae-browser-sessions", 2);
    let settled = false;
    const fail = (error: unknown) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(error);
    };
    const timer = setTimeout(() => fail(new Error(
      "Browser storage did not respond. Close other Artae tabs and retry.",
    )), 15000);
    open.onupgradeneeded = () => {
      // IndexedDB open requests cannot be cancelled. A rejected request must
      // not perform a deferred upgrade after another tab releases its lock.
      if (settled) { open.transaction?.abort(); return; }
      const db = open.result;
      const sessions = db.objectStoreNames.contains("sessions")
        ? open.transaction!.objectStore("sessions")
        : db.createObjectStore("sessions", { keyPath: "key" });
      if (!sessions.indexNames.contains("scope")) sessions.createIndex("scope", "scope");
      if (!db.objectStoreNames.contains("clips")) db.createObjectStore("clips", { keyPath: "key" });
    };
    open.onblocked = () => fail(new Error("Close older Artae tabs to upgrade recording storage, then reload."));
    open.onerror = () => fail(open.error);
    open.onsuccess = () => {
      if (settled) { open.result.close(); return; }
      settled = true;
      clearTimeout(timer);
      open.result.onversionchange = () => open.result.close();
      resolve(open.result);
    };
  });
}
