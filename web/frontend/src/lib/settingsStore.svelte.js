// Persistent UI prefs: density, pinned project ids, voice opts, toast on/off.
import { writable } from "svelte/store";

const KEY = "macs.settings.v1";

const DEFAULTS = {
  density: "comfy", // 'compact' | 'comfy'
  pinned: [], // array of project ids (order = visual order)
  voiceLang: "id-ID",
  toastsEnabled: true,
  reduceMotion: false, // user override on top of OS pref
  compactSessions: false, // collapse expanded sessions on click
  theme: "auto", // 'auto' | 'dark' | 'light'
  savedPrompts: [], // [{id, label, text}]
  audioCues: false, // play sound on stream complete
  starred: {}, // { "<sessionId>": [msgIdx, ...] } — bookmarked messages
};

function load() {
  if (typeof localStorage === "undefined") return { ...DEFAULTS };
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULTS };
    const parsed = JSON.parse(raw);
    return { ...DEFAULTS, ...parsed };
  } catch {
    return { ...DEFAULTS };
  }
}

function save(v) {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(KEY, JSON.stringify(v));
  } catch {}
}

export const settings = writable(load());

settings.subscribe((v) => save(v));

export function setDensity(d) {
  settings.update((s) => ({ ...s, density: d }));
}

export function toggleDensity() {
  settings.update((s) => ({
    ...s,
    density: s.density === "compact" ? "comfy" : "compact",
  }));
}

export function togglePin(projectId) {
  settings.update((s) => {
    const has = s.pinned.includes(projectId);
    return {
      ...s,
      pinned: has
        ? s.pinned.filter((x) => x !== projectId)
        : [...s.pinned, projectId],
    };
  });
}

export function isPinned(s, projectId) {
  return s.pinned.includes(projectId);
}

export function setToastsEnabled(v) {
  settings.update((s) => ({ ...s, toastsEnabled: !!v }));
}

export function setVoiceLang(lang) {
  settings.update((s) => ({ ...s, voiceLang: lang }));
}

export function setTheme(theme) {
  settings.update((s) => ({ ...s, theme }));
}

export function reorderPinned(fromIdx, toIdx) {
  settings.update((s) => {
    const arr = [...s.pinned];
    const [moved] = arr.splice(fromIdx, 1);
    arr.splice(toIdx, 0, moved);
    return { ...s, pinned: arr };
  });
}

export function addSavedPrompt(label, text) {
  settings.update((s) => ({
    ...s,
    savedPrompts: [
      ...s.savedPrompts,
      {
        id: `sp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        label,
        text,
      },
    ],
  }));
}

export function removeSavedPrompt(id) {
  settings.update((s) => ({
    ...s,
    savedPrompts: s.savedPrompts.filter((p) => p.id !== id),
  }));
}

export function setAudioCues(v) {
  settings.update((s) => ({ ...s, audioCues: !!v }));
}

export function toggleStar(sessionId, msgIdx) {
  if (!sessionId) return;
  settings.update((s) => {
    const list = s.starred[sessionId] || [];
    const has = list.includes(msgIdx);
    const next = has ? list.filter((x) => x !== msgIdx) : [...list, msgIdx];
    return { ...s, starred: { ...s.starred, [sessionId]: next } };
  });
}

export function isStarred(s, sessionId, msgIdx) {
  if (!sessionId) return false;
  return (s.starred[sessionId] || []).includes(msgIdx);
}

// Apply theme attribute to <html> — call from a root effect.
export function applyTheme(theme) {
  if (typeof document === "undefined") return;
  const resolved =
    theme === "auto"
      ? window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark"
      : theme;
  document.documentElement.dataset.theme = resolved;
}

// Play a tiny chime when stream finishes. Web Audio only — no asset fetch.
export function playChime() {
  if (typeof window === "undefined" || !window.AudioContext) return;
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(1320, ctx.currentTime + 0.12);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.4);
    setTimeout(() => ctx.close(), 600);
  } catch {}
}
