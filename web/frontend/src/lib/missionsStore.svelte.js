/**
 * Mission Control store. Holds active missions and per-mission summaries.
 * Polls /api/missions/active every ~5s while any consumer is mounted.
 */
import { writable } from "svelte/store";
import { resumeActiveStreams } from "./streamsStore.svelte.js";

export const missions = writable([]);
let pollTimer = null;
let consumers = 0;

async function refreshOnce() {
  try {
    const r = await fetch("/api/missions/active");
    if (!r.ok) return;
    const data = await r.json();
    missions.set(data);
    // Side-effect: ensure each agent's stream is attached in streamsStore so
    // tiles can render live progress without per-tile subscriptions.
    resumeActiveStreams();
  } catch {
    // ignore
  }
}

export function startPolling() {
  consumers++;
  if (pollTimer) return;
  refreshOnce();
  pollTimer = setInterval(refreshOnce, 5000);
}

export function stopPolling() {
  consumers = Math.max(0, consumers - 1);
  if (consumers === 0 && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

export async function createMission({
  name,
  sharedPrompt,
  agents,
  mode = "parallel",
}) {
  const r = await fetch("/api/missions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      shared_prompt: sharedPrompt || null,
      agents,
      mode,
    }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || `mission create ${r.status}`);
  }
  const data = await r.json();
  await refreshOnce();
  return data;
}

export async function abortMission(missionId) {
  await fetch(`/api/missions/${missionId}/abort`, { method: "POST" });
  await refreshOnce();
}

export async function archiveMission(missionId) {
  await fetch(`/api/missions/${missionId}/archive`, { method: "POST" });
  await refreshOnce();
}

export async function getMission(missionId) {
  const r = await fetch(`/api/missions/${missionId}`);
  if (!r.ok) throw new Error(`mission ${missionId}: ${r.status}`);
  return r.json();
}

export async function planMission({ goal, maxAgents = 4, projectIds = null }) {
  const r = await fetch("/api/missions/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      goal,
      max_agents: maxAgents,
      project_ids: projectIds,
    }),
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.detail || `plan ${r.status}`);
  }
  return r.json();
}
