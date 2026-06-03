// Global toast queue. Push from anywhere with toast.push({kind, title, body, duration})
import { writable } from "svelte/store";

let nextId = 1;
export const toasts = writable([]);

export function pushToast({
  kind = "info",
  title = "",
  body = "",
  duration = 3500,
} = {}) {
  const id = nextId++;
  toasts.update((arr) => [...arr, { id, kind, title, body }]);
  if (duration > 0) {
    setTimeout(() => dismissToast(id), duration);
  }
  return id;
}

export function dismissToast(id) {
  toasts.update((arr) => arr.filter((t) => t.id !== id));
}
