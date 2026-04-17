/**
 * Attachment cache backed by IndexedDB on web, falls back to a no-op on
 * environments where IndexedDB is unavailable (e.g. old native webview).
 *
 * Keeps AsyncStorage clean — binary blobs don't belong in localStorage.
 */

const DB_NAME = "kaydet_attachments";
const DB_VERSION = 1;
const STORE = "blobs";

function openDB(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === "undefined") return Promise.resolve(null);
  return new Promise((resolve) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => resolve(null);
  });
}

let _db: IDBDatabase | null | undefined; // undefined = not yet opened

async function getDB(): Promise<IDBDatabase | null> {
  if (_db !== undefined) return _db;
  _db = await openDB();
  return _db;
}

export async function getAttachmentCache(filename: string): Promise<string | null> {
  const db = await getDB();
  if (!db) return null;
  return new Promise((resolve) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).get(filename);
    req.onsuccess = () => resolve(req.result ?? null);
    req.onerror = () => resolve(null);
  });
}

export async function setAttachmentCache(filename: string, base64: string): Promise<void> {
  const db = await getDB();
  if (!db) return;
  return new Promise((resolve) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(base64, filename);
    tx.oncomplete = () => resolve();
    tx.onerror = () => resolve(); // fail silently
  });
}
