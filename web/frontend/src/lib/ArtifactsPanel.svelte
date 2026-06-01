<script>
  import { onMount } from 'svelte'

  let { streamId, onClose } = $props()

  let data = $state(null)
  let loading = $state(true)
  let error = $state(null)
  let expanded = $state(new Set())
  let busy = $state(null) // path being mutated

  async function refresh() {
    if (!streamId) return
    loading = true
    try {
      const r = await fetch(`/api/streams/${streamId}/artifacts`)
      if (!r.ok) throw new Error(`artifacts ${r.status}`)
      data = await r.json()
    } catch (e) {
      error = e?.message || String(e)
    } finally {
      loading = false
    }
  }

  onMount(refresh)

  function toggle(path) {
    const n = new Set(expanded)
    if (n.has(path)) n.delete(path); else n.add(path)
    expanded = n
  }

  async function rejectHunk(file, hunk) {
    busy = file.path
    try {
      const r = await fetch(`/api/streams/${streamId}/artifacts/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: file.path, hunk_indices: [hunk.index] }),
      })
      const result = await r.json()
      if (!result.ok) error = `reject failed: ${result.message}`
    } finally {
      busy = null
      await refresh()
    }
  }

  async function restoreFile(file) {
    if (!confirm(`Restore ${file.path} to HEAD? All changes will be lost.`)) return
    busy = file.path
    try {
      await fetch(`/api/streams/${streamId}/artifacts/restore-file`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: file.path }),
      })
    } finally {
      busy = null
      await refresh()
    }
  }

  function lineClass(line) {
    if (line.startsWith('+') && !line.startsWith('+++')) return 'bg-emerald-500/10 text-emerald-300'
    if (line.startsWith('-') && !line.startsWith('---')) return 'bg-red-500/10 text-red-300'
    if (line.startsWith('@@')) return 'bg-neutral-800/60 text-amber-400'
    return 'text-neutral-400'
  }

  function fileStatusBadge(status) {
    const m = {
      modified: 'bg-blue-500/20 text-blue-300',
      added: 'bg-emerald-500/20 text-emerald-300',
      deleted: 'bg-red-500/20 text-red-300',
      renamed: 'bg-purple-500/20 text-purple-300',
      untracked: 'bg-amber-500/20 text-amber-300',
    }
    return m[status] || 'bg-neutral-700 text-neutral-300'
  }
</script>

<div class="fixed inset-0 z-40 bg-black/60" onclick={onClose} role="presentation" data-testid="artifacts-overlay"></div>
<aside class="fixed inset-y-0 right-0 z-50 flex w-[min(560px,95vw)] flex-col border-l border-neutral-800 bg-neutral-950 shadow-xl" data-testid="artifacts-drawer">
  <div class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
    <div>
      <div class="font-medium">Files changed</div>
      {#if data && data.git_repo}
        <div class="text-[10px] text-neutral-500">base: {data.base_sha?.slice(0, 8) || 'HEAD'} · {data.files.length} files</div>
      {/if}
    </div>
    <button class="text-neutral-400 hover:text-neutral-100" onclick={onClose}>✕</button>
  </div>

  <div class="flex-1 overflow-y-auto p-2">
    {#if loading}
      <div class="p-3 text-xs text-neutral-500">Loading diff…</div>
    {:else if error}
      <div class="m-2 rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-300">{error}</div>
    {:else if !data?.git_repo}
      <div class="p-3 text-xs text-neutral-500">Not a git repository — artifacts unavailable for this project.</div>
    {:else if data.files.length === 0}
      <div class="p-3 text-xs text-neutral-500">No changes since stream started.</div>
    {:else}
      {#each data.files as f (f.path)}
        {@const isOpen = expanded.has(f.path)}
        <div class="mb-1.5 rounded-md border border-neutral-800 bg-neutral-900/60">
          <button
            class="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-neutral-900"
            onclick={() => toggle(f.path)}
            data-testid="artifact-file-{f.path}"
          >
            <div class="flex min-w-0 items-center gap-2">
              <span class="rounded px-1.5 py-0.5 text-[10px] uppercase {fileStatusBadge(f.status)}">{f.status}</span>
              <span class="truncate text-xs">{f.path}</span>
            </div>
            <div class="shrink-0 flex items-center gap-2 text-[10px]">
              {#if f.additions}<span class="text-emerald-400">+{f.additions}</span>{/if}
              {#if f.deletions}<span class="text-red-400">-{f.deletions}</span>{/if}
              <span class="text-neutral-600">{isOpen ? '▾' : '▸'}</span>
            </div>
          </button>
          {#if isOpen}
            <div class="border-t border-neutral-800 px-2 py-1.5">
              {#if f.binary}
                <div class="px-2 py-1 text-xs text-neutral-500">(binary file — no preview)</div>
              {:else if f.status === 'untracked'}
                <button
                  class="rounded-md bg-red-600/20 px-2 py-1 text-xs text-red-300 hover:bg-red-600/40 disabled:opacity-50"
                  onclick={() => restoreFile(f)}
                  disabled={busy === f.path}
                  data-testid="artifact-delete-{f.path}"
                >Delete untracked file</button>
              {:else}
                {#each f.hunks as h (h.index)}
                  <div class="mb-1.5 rounded-md border border-neutral-800">
                    <div class="flex items-center justify-between border-b border-neutral-800 bg-neutral-950/60 px-2 py-1">
                      <span class="text-[10px] text-amber-400">{h.header.trim()}</span>
                      <button
                        class="rounded bg-red-600/20 px-2 py-0.5 text-[10px] text-red-300 hover:bg-red-600/40 disabled:opacity-50"
                        onclick={() => rejectHunk(f, h)}
                        disabled={busy === f.path}
                        data-testid="artifact-reject-{f.path}-{h.index}"
                      >Revert hunk</button>
                    </div>
                    <pre class="overflow-x-auto px-2 py-1 text-[11px] leading-tight font-mono">{#each h.lines as line, li (li)}<div class="{lineClass(line)}">{line || ' '}</div>{/each}</pre>
                  </div>
                {/each}
                <button
                  class="mt-1 w-full rounded-md bg-red-600/15 px-2 py-1 text-xs text-red-300 hover:bg-red-600/30 disabled:opacity-50"
                  onclick={() => restoreFile(f)}
                  disabled={busy === f.path}
                  data-testid="artifact-restore-{f.path}"
                >Restore whole file to HEAD</button>
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    {/if}
  </div>

  <div class="border-t border-neutral-800 px-3 py-2">
    <button class="w-full rounded-md bg-neutral-800 px-3 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700" onclick={refresh}>Refresh</button>
  </div>
</aside>
