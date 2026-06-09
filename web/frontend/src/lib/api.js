/** Lightweight API helpers. */

export async function authMe() {
  const r = await fetch("/api/auth/me");
  if (!r.ok) return { authenticated: false };
  return r.json();
}

export async function authLogin(username, password) {
  const r = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return r.ok;
}

export async function authLogout() {
  await fetch("/api/auth/logout", { method: "POST" });
}

export async function listProjects() {
  const r = await fetch("/api/projects");
  if (!r.ok) throw new Error(`projects fetch ${r.status}`);
  return r.json();
}

export async function listSessions(projectId) {
  const r = await fetch(`/api/projects/${projectId}/sessions`);
  if (!r.ok) throw new Error(`sessions ${r.status}`);
  return r.json();
}

export async function loadSession(projectId, sessionId) {
  const r = await fetch(`/api/projects/${projectId}/sessions/${sessionId}`);
  if (!r.ok) throw new Error(`load session ${r.status}`);
  return r.json();
}

export async function renameProject(projectId, displayName) {
  const r = await fetch(`/api/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName }),
  });
  if (!r.ok) throw new Error(`rename project ${r.status}`);
  return r.json();
}

export async function renameSession(projectId, sessionId, displayName) {
  const r = await fetch(`/api/projects/${projectId}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName }),
  });
  if (!r.ok) throw new Error(`rename session ${r.status}`);
  return r.json();
}

export async function switchSession(projectId, sessionId) {
  const r = await fetch(`/api/projects/${projectId}/switch_session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!r.ok) throw new Error(`switch ${r.status}`);
  return r.json();
}

export async function createProject({
  name,
  stack = "empty",
  git_url = null,
  welcome = true,
}) {
  const r = await fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, stack, git_url, welcome }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = data?.detail || `create project ${r.status}`;
    throw new Error(msg);
  }
  return data;
}

export async function deleteProject(projectId) {
  const r = await fetch(`/api/projects/${projectId}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete project ${r.status}`);
  return r.json();
}

/** List active server-side streams (optionally filtered by project). */
export async function listActiveStreams(projectId) {
  const q = projectId != null ? `?pid=${projectId}` : "";
  const r = await fetch(`/api/streams/active${q}`);
  if (!r.ok) throw new Error(`active streams ${r.status}`);
  return r.json();
}

/* ── Project Tasks (Phase 5) ───────────────────────────────────────────────── */

export async function listProjectTasks(projectId, status = "all") {
  const r = await fetch(`/api/projects/${projectId}/tasks?status=${encodeURIComponent(status)}`);
  if (!r.ok) throw new Error(`tasks ${r.status}`);
  return r.json();
}

export async function createProjectTask(projectId, { title, description = null, priority = 0 }) {
  const r = await fetch(`/api/projects/${projectId}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, description, priority }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data?.detail || `create task ${r.status}`);
  return data;
}

export async function updateProjectTask(projectId, taskId, patch) {
  const r = await fetch(`/api/projects/${projectId}/tasks/${taskId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data?.detail || `update task ${r.status}`);
  return data;
}

export async function deleteProjectTask(projectId, taskId) {
  const r = await fetch(`/api/projects/${projectId}/tasks/${taskId}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete task ${r.status}`);
  return r.json();
}
