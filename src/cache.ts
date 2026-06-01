import { createHash } from "node:crypto";

interface CacheEntry {
  response: string;
  timestamp: number;
}

const store = new Map<string, CacheEntry>();
const TTL = 10 * 60 * 1000; // 10 minutes
const MAX_SIZE = 100;

function key(model: string, prompt: string, system?: string): string {
  return createHash("md5")
    .update(`${model}:${system ?? ""}:${prompt}`)
    .digest("hex");
}

export function get(
  model: string,
  prompt: string,
  system?: string,
): string | null {
  const k = key(model, prompt, system);
  const entry = store.get(k);
  if (!entry) return null;
  if (Date.now() - entry.timestamp > TTL) {
    store.delete(k);
    return null;
  }
  return entry.response;
}

export function set(
  model: string,
  prompt: string,
  response: string,
  system?: string,
): void {
  if (store.size >= MAX_SIZE) {
    const oldest = store.keys().next().value!;
    store.delete(oldest);
  }
  store.set(key(model, prompt, system), { response, timestamp: Date.now() });
}

export function stats(): {
  entries: number;
  maxSize: number;
  ttlMinutes: number;
} {
  return { entries: store.size, maxSize: MAX_SIZE, ttlMinutes: TTL / 60000 };
}
