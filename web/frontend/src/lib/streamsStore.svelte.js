/**
 * Global active-stream store. Survives Chat component remount so navigating
 * between projects (or backgrounding the browser tab) doesn't kill the active
 * claude subprocess on the server.
 *
 * Stream key = `${projectId}:${sessionId || 'new'}` — stable per chat. The
 * server-side stream_id is opaque and tracked inside the value.
 */
import { writable } from "svelte/store";

function nowMs() {
  return Date.now();
}

function streamKeyOf(projectId, sessionId) {
  return `${projectId}:${sessionId || "new"}`;
}

function emptyState() {
  return /** @type {Map<string, StreamState>} */ (new Map());
}

/**
 * @typedef {Object} StreamState
 * @property {string} streamKey
 * @property {number} projectId
 * @property {string|null} sessionId
 * @property {string} streamId
 * @property {object[]} events  raw events streamed from backend (in arrival order)
 * @property {number} cursor    next index to render (kept in sync with events.length normally)
 * @property {number} startedAt epoch ms
 * @property {number} lastEventAt epoch ms
 * @property {boolean} done
 * @property {string|null} error
 * @property {string} userMessage
 * @property {AbortController|null} sseAbort
 * @property {boolean} reconnecting
 */

export const streams = writable(emptyState());

/**
 * Update one entry by key. Always swaps in a NEW StreamState object so Svelte
 * $derived selectors see a reference change and re-fire — in-place mutation
 * fails to invalidate downstream effects.
 */
function patch(key, fn) {
  streams.update((m) => {
    const s = m.get(key);
    if (!s) return m;
    const updated = { ...s };
    fn(updated);
    const n = new Map(m);
    n.set(key, updated);
    return n;
  });
}

function setStream(key, s) {
  streams.update((m) => {
    const n = new Map(m);
    n.set(key, s);
    return n;
  });
}

export function getStream(projectId, sessionId, snapshot) {
  return snapshot.get(streamKeyOf(projectId, sessionId)) || null;
}

export function activeStreams(snapshot) {
  return [...snapshot.values()].filter((s) => !s.done);
}

/**
 * Start a new chat send (or attach to an already-live one server-side).
 * Returns the StreamState (also stored in the writable).
 */
export async function startStream({
  projectId,
  sessionId,
  message,
  newConversation = false,
  elevated = false,
  onEvent,
}) {
  const key = streamKeyOf(projectId, sessionId);
  const resp = await fetch(`/api/projects/${projectId}/chat/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      new_conversation: newConversation,
      elevated,
    }),
  });
  if (resp.status === 409) {
    const body = await resp.json().catch(() => ({}));
    const err = new Error("stream_busy");
    err.code = "stream_busy";
    err.busyMessage = body.busy_message || "";
    err.activeStreamId = body.active_stream_id || null;
    throw err;
  }
  if (!resp.ok) throw new Error(`start ${resp.status}`);
  const data = await resp.json();
  const stream = {
    streamKey: key,
    projectId,
    sessionId: data.resume_session_id ?? sessionId ?? null,
    streamId: data.stream_id,
    events: [],
    cursor: 0,
    startedAt: data.started_at ? data.started_at * 1000 : nowMs(),
    lastEventAt: nowMs(),
    done: false,
    error: null,
    userMessage: message,
    sseAbort: null,
    reconnecting: false,
  };
  setStream(key, stream);
  // Fire-and-forget subscription. Reconnects on transient failures while !done.
  subscribeStream(key, onEvent).catch((e) => {
    patch(key, (s) => {
      s.error = e?.message || String(e);
    });
  });
  startPollingFallback(key);
  return stream;
}

/** Resume a server-side stream that started earlier (e.g. after page refresh). */
export async function attachExisting({ projectId, streamId, onEvent }) {
  const key = `${projectId}:attached:${streamId.slice(0, 6)}`;
  const stream = {
    streamKey: key,
    projectId,
    sessionId: null,
    streamId,
    events: [],
    cursor: 0,
    startedAt: nowMs(),
    lastEventAt: nowMs(),
    done: false,
    error: null,
    userMessage: "",
    sseAbort: null,
    reconnecting: false,
  };
  setStream(key, stream);
  subscribeStream(key, onEvent).catch((e) => {
    patch(key, (s) => {
      s.error = e?.message || String(e);
    });
  });
  startPollingFallback(key);
  return stream;
}

// Max time the client will wait between any two bytes from SSE before treating
// the socket as zombied (mobile cellular NAT silently drops idle TCP). Lower
// than the server-side 5s heartbeat × 2 so we don't false-positive.
const STALE_BYTES_MS = 15000;

async function subscribeStream(key, onEvent) {
  while (true) {
    let current;
    streams.update((m) => {
      current = m.get(key);
      return m;
    });
    if (!current || current.done) return;

    const from = current.events.length;
    const ctrl = new AbortController();
    let staleTimer = null;
    const resetStale = () => {
      if (staleTimer) clearTimeout(staleTimer);
      staleTimer = setTimeout(() => {
        // No bytes in too long → abort. Outer catch reconnects.
        try {
          ctrl.abort("stale-bytes-timeout");
        } catch {}
      }, STALE_BYTES_MS);
    };

    patch(key, (s) => {
      s.sseAbort = ctrl;
      s.reconnecting = false;
    });

    try {
      const resp = await fetch(
        `/api/streams/${current.streamId}/sse?from=${from}`,
        { signal: ctrl.signal },
      );
      if (resp.status === 404) {
        patch(key, (s) => {
          s.done = true;
          s.error = s.error || "stream expired";
        });
        return;
      }
      if (!resp.ok || !resp.body) throw new Error(`sse ${resp.status}`);
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      resetStale(); // arm watchdog on first read
      while (true) {
        const { done, value } = await reader.read();
        resetStale(); // any bytes (incl. heartbeats) reset the timer
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
          const chunk = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const line = chunk.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          let evt;
          try {
            evt = JSON.parse(line.slice(6));
          } catch {
            continue;
          }
          // Heartbeat events keep the stuck-stream detector honest: backend
          // emits them every ~10s while claude is mid-think (no content
          // events), so frontend never false-thinks "stale". They're not
          // stored in events[] and not surfaced to handlers — pure timestamp
          // bump.
          if (evt.type === "heartbeat") {
            patch(key, (s) => {
              s.lastEventAt = nowMs();
            });
            continue;
          }
          patch(key, (s) => {
            s.events = [...s.events, evt];
            s.lastEventAt = nowMs();
            if (evt.session_id) s.sessionId = evt.session_id;
            if (evt.type === "stream_done") s.done = true;
            if (evt.type === "error") s.error = evt.error || "unknown error";
          });
          try {
            onEvent?.(evt);
          } catch {}
          if (evt.type === "stream_done") {
            if (staleTimer) clearTimeout(staleTimer);
            return;
          }
        }
      }
      if (staleTimer) clearTimeout(staleTimer);
      let s2;
      streams.update((m) => {
        s2 = m.get(key);
        return m;
      });
      if (!s2 || s2.done) return;
      patch(key, (s) => {
        s.reconnecting = true;
      });
      await new Promise((r) => setTimeout(r, 800));
    } catch (e) {
      if (staleTimer) clearTimeout(staleTimer);
      // Aborted on purpose by visibilitychange or stale-bytes → fall through to reconnect
      const wasVoluntaryAbort =
        ctrl.signal.aborted &&
        (ctrl.signal.reason === "stale-bytes-timeout" ||
          ctrl.signal.reason === "visibility-resume" ||
          ctrl.signal.reason === "pageshow");
      if (ctrl.signal.aborted && !wasVoluntaryAbort) return;
      patch(key, (s) => {
        s.reconnecting = true;
      });
      await new Promise((r) => setTimeout(r, 800));
    }
  }
}

/**
 * Page Visibility / pageshow handler. When the mobile browser brings the tab
 * back to foreground (after app switch / lock screen), aggressively abort all
 * in-flight SSE readers so the reconnect loop fires with a fresh socket.
 * Without this, zombied TCP from cellular NAT keeps hanging reader.read().
 */
function installResumeHandlers() {
  if (typeof document === "undefined") return;
  if (window.__macsResumeInstalled) return;
  window.__macsResumeInstalled = true;

  const kickAll = (reason) => {
    streams.update((m) => {
      for (const s of m.values()) {
        if (s.done) continue;
        try {
          s.sseAbort?.abort(reason);
        } catch {}
      }
      return m;
    });
  };

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") kickAll("visibility-resume");
  });
  // iOS Safari fires pageshow when returning from BFCache
  window.addEventListener("pageshow", (e) => {
    if (e.persisted) kickAll("pageshow");
  });
  // Network may flap on cellular; resume on online event
  window.addEventListener("online", () => kickAll("network-online"));
}

installResumeHandlers();

/** Abort an active stream (server-side process kill). */
export async function abortStream(streamId) {
  await fetch(`/api/streams/${streamId}/abort`, { method: "POST" });
}

/**
 * Belt-and-suspenders polling. While SSE is the primary channel, mobile
 * cellular NAT silently kills idle TCP. This polls the JSON `/poll` endpoint
 * every ~4s while the stream is active so events ALWAYS surface within 4s,
 * regardless of SSE health. Idempotent — only merges events past current cursor.
 */
function startPollingFallback(key) {
  let stopped = false;
  const tick = async () => {
    if (stopped) return;
    let cur;
    streams.update((m) => {
      cur = m.get(key);
      return m;
    });
    if (!cur) {
      console.log("[poll]", key, "no stream in store, stopping");
      stopped = true;
      return;
    }
    if (cur.done) {
      console.log("[poll]", key, "stream done, stopping");
      stopped = true;
      return;
    }
    try {
      const url = `/api/streams/${cur.streamId}/poll?from=${cur.events.length}`;
      const r = await fetch(url);
      if (r.status === 404) {
        patch(key, (s) => {
          s.done = true;
          s.error = s.error || "stream expired";
        });
        stopped = true;
        return;
      }
      if (!r.ok) {
        console.log("[poll]", key, "non-ok status", r.status);
        return;
      }
      const data = await r.json();
      const fresh = data.events || [];
      console.log(
        "[poll]",
        key,
        "got events:",
        fresh.length,
        "done:",
        data.done,
        "total:",
        data.total_events,
      );
      if (fresh.length) {
        // Strip heartbeats — they're meant for liveness only, not state.
        const nonHb = fresh.filter((e) => e?.type !== "heartbeat");
        if (nonHb.length === 0) {
          // Only heartbeats came through — bump timestamp, skip merging.
          patch(key, (s) => {
            s.lastEventAt = nowMs();
          });
        } else {
          patch(key, (s) => {
            const have = s.events.length;
            const want = data.total_events;
            const need = want - have;
            if (need <= 0) return;
            const toAppend = nonHb.slice(-need);
            s.events = [...s.events, ...toAppend];
            s.lastEventAt = nowMs();
            for (const e of toAppend) {
              if (e.session_id) s.sessionId = e.session_id;
              if (e.type === "stream_done") s.done = true;
              if (e.type === "error") s.error = e.error || s.error;
            }
          });
        }
      } else if (data.done) {
        patch(key, (s) => {
          s.done = true;
        });
      }
    } catch (e) {
      console.log("[poll]", key, "tick error:", e?.message);
    }
  };
  const id = setInterval(() => {
    if (stopped) {
      clearInterval(id);
      return;
    }
    tick();
  }, 4000);
  console.log("[poll] started for", key);
}

/** Detach UI subscription without killing the server stream. */
export function detachClient(key) {
  patch(key, (s) => {
    try {
      s.sseAbort?.abort();
    } catch {}
  });
}

/**
 * On page load, fetch server-side active streams and attach them to the store
 * so the UI can resume showing running indicators / reconnect SSE.
 */
export async function resumeActiveStreams(onEventFactory) {
  try {
    const r = await fetch("/api/streams/active");
    if (!r.ok) return [];
    const live = await r.json();
    for (const s of live) {
      const key = `${s.project_id}:${s.session_id || "new"}`;
      // skip if we already have this stream tracked
      let already = false;
      streams.update((m) => {
        already = !!m.get(key);
        return m;
      });
      if (already) continue;
      const stream = {
        streamKey: key,
        projectId: s.project_id,
        sessionId: s.session_id || null,
        streamId: s.stream_id,
        events: [],
        cursor: 0,
        startedAt: (s.started_at || Date.now() / 1000) * 1000,
        lastEventAt: (s.last_event_at || Date.now() / 1000) * 1000,
        done: false,
        error: null,
        userMessage: s.user_message || "",
        sseAbort: null,
        reconnecting: false,
      };
      setStream(key, stream);
      const onEvt = onEventFactory ? onEventFactory(key) : null;
      subscribeStream(key, onEvt).catch((e) => {
        patch(key, (st) => {
          st.error = e?.message || String(e);
        });
      });
      startPollingFallback(key);
    }
    return live;
  } catch {
    return [];
  }
}

export { streamKeyOf };
