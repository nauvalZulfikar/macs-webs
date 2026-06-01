<script>
  import { onMount } from 'svelte'
  import WatcherCreateModal from './WatcherCreateModal.svelte'

  let { projects = [], onClose } = $props()

  let watchers = $state([])
  let firesByWatcher = $state({})
  let loading = $state(true)
  let error = $state(null)
  let createOpen = $state(false)
  let busy = $state(null)

  async function refresh() {
    try {
      const r = await fetch('/api/watchers')
      if (!r.ok) throw new Error(`watchers ${r.status}`)
      watchers = await r.json()
    } catch (e) { error = e?.message || String(e) }
    finally { loading = false }
  }

  async function loadFires(wid) {
    try {
      const r = await fetch(`/api/watchers/${wid}/fires?limit=8`)
      if (!r.ok) return
      firesByWatcher = { ...firesByWatcher, [wid]: await r.json() }
    } catch {}
  }

  async function toggle(w) {
    busy = w.id
    try {
      const r = await fetch(`/api/watchers/${w.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !w.enabled }),
      })
      if (!r.ok) error = `toggle failed: ${r.status}`
    } finally {
      busy = null
      await refresh()
    }
  }

  async function fireNow(w) {
    busy = w.id
    try {
      await fetch(`/api/watchers/${w.id}/fire-now`, { method: 'POST' })
      await loadFires(w.id)
      await refresh()
    } finally { busy = null }
  }

  async function deleteWatcher(w) {
    if (!confirm(`Delete watcher "${w.name}"? This cannot be undone.`)) return
    busy = w.id
    try {
      await fetch(`/api/watchers/${w.id}`, { method: 'DELETE' })
    } finally {
      busy = null
      await refresh()
    }
  }

  onMount(() => {
    refresh()
    const t = setInterval(refresh, 8000)
    return () => clearInterval(t)
  })

  function projectName(pid) {
    return projects.find((p) => p.id === pid)?.display_name
      || projects.find((p) => p.id === pid)?.name
      || `project ${pid}`
  }

  function triggerSummary(w) {
    const c = w.trigger_config || {}
    if (w.trigger_type === 'file_change') {
      const ps = (c.paths || []).join(', ')
      return `files: ${ps || c.project_path || '(project root)'}`
    }
    if (w.trigger_type === 'cron') return `cron: ${c.spec || '?'}`
    if (w.trigger_type === 'test_loop') return `every ${c.interval_s || 600}s: ${(c.cmd || '').slice(0,40)}`
    return 'manual'
  }
</script>

<div class="fixed inset-0 z-40 bg-black/60" onclick={onClose} role="presentation"></div>
<aside class="fixed inset-y-0 right-0 z-50 flex w-[min(640px,95vw)] flex-col border-l border-neutral-800 bg-neutral-950 shadow-xl" data-testid="watchers-drawer">
  <div class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
    <div class="flex items-center gap-2">
      <span class="text-lg">🔔</span>
      <span class="font-medium">Watchers</span>
      <span class="rounded-full bg-neutral-800 px-2 py-0.5 text-[10px] text-neutral-400">{watchers.length}</span>
    </div>
    <div class="flex items-center gap-2">
      <button class="rounded-md bg-emerald-600/20 px-2 py-1 text-xs text-emerald-300 hover:bg-emerald-600/40" onclick={() => createOpen = true} data-testid="watcher-new">+ New</button>
      <button class="text-neutral-400 hover:text-neutral-100" onclick={onClose}>✕</button>
    </div>
  </div>

  <div class="flex-1 overflow-y-auto p-2">
    {#if loading}
      <div class="p-3 text-xs text-neutral-500">Loading…</div>
    {:else if error}
      <div class="rounded-md border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-300">{error}</div>
    {:else if watchers.length === 0}
      <div class="p-4 text-center text-xs text-neutral-500">No watchers yet. Create one to auto-trigger an agent on file changes, cron, or test failures.</div>
    {:else}
      {#each watchers as w (w.id)}
        <div class="mb-1.5 rounded-md border border-neutral-800 bg-neutral-900/60 p-3" data-testid="watcher-row-{w.id}">
          <div class="flex items-start gap-3">
            <div class="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-amber-500/20 text-xs">
              {w.trigger_type === 'file_change' ? '📂' : w.trigger_type === 'cron' ? '⏰' : w.trigger_type === 'test_loop' ? '🧪' : '👆'}
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <span class="truncate text-sm font-medium">{w.name}</span>
                <span class="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">{projectName(w.project_id)}</span>
                {#if !w.enabled}
                  <span class="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-500">disabled</span>
                {/if}
              </div>
              <div class="mt-0.5 truncate text-[10px] text-neutral-500">{triggerSummary(w)}</div>
              <div class="mt-1 line-clamp-2 text-xs text-neutral-300">{w.action_prompt}</div>
              <div class="mt-1 flex items-center gap-3 text-[10px] text-neutral-500">
                <span>fired {w.fire_count}×</span>
                {#if w.last_fired_at}<span>last: {new Date(w.last_fired_at).toLocaleString()}</span>{/if}
              </div>
              {#if firesByWatcher[w.id]?.length}
                <details class="mt-1 text-[10px]">
                  <summary class="cursor-pointer text-neutral-500">Recent fires ({firesByWatcher[w.id].length})</summary>
                  <ul class="mt-1 space-y-1 pl-2">
                    {#each firesByWatcher[w.id] as f}
                      <li class="border-l border-neutral-800 pl-2">
                        <span class="text-neutral-400">{new Date(f.fired_at).toLocaleString()}</span>
                        <span class="ml-1 rounded bg-neutral-800 px-1 text-[9px] {f.status === 'done' ? 'text-emerald-300' : f.status === 'error' ? 'text-red-300' : 'text-amber-300'}">{f.status}</span>
                        {#if f.trigger_info?.paths}
                          <div class="text-neutral-500">paths: {f.trigger_info.paths.slice(0, 2).join(', ')}</div>
                        {/if}
                      </li>
                    {/each}
                  </ul>
                </details>
              {:else}
                <button class="mt-1 text-[10px] text-neutral-500 hover:text-neutral-300" onclick={() => loadFires(w.id)}>Load fires history</button>
              {/if}
            </div>
            <div class="flex shrink-0 flex-col gap-1">
              <button
                class="rounded bg-neutral-800 px-2 py-0.5 text-[10px] hover:bg-neutral-700 disabled:opacity-50"
                onclick={() => toggle(w)}
                disabled={busy === w.id}
                data-testid="watcher-toggle-{w.id}"
              >{w.enabled ? 'Disable' : 'Enable'}</button>
              <button
                class="rounded bg-emerald-600/20 px-2 py-0.5 text-[10px] text-emerald-300 hover:bg-emerald-600/40 disabled:opacity-50"
                onclick={() => fireNow(w)}
                disabled={busy === w.id}
                data-testid="watcher-fire-{w.id}"
              >Fire now</button>
              <button
                class="rounded bg-red-600/15 px-2 py-0.5 text-[10px] text-red-300 hover:bg-red-600/40 disabled:opacity-50"
                onclick={() => deleteWatcher(w)}
                disabled={busy === w.id}
              >Delete</button>
            </div>
          </div>
        </div>
      {/each}
    {/if}
  </div>
</aside>

{#if createOpen}
  <WatcherCreateModal
    {projects}
    onClose={() => createOpen = false}
    onCreated={() => { createOpen = false; refresh() }}
  />
{/if}
