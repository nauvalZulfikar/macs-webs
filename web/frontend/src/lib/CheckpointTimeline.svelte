<script>
  /** Vertical timeline of git-stash checkpoints created during a stream's
   *  tool_use lifecycle. Each node clickable → POST /rewind/{id}. */
  let { streamId, onRewound } = $props()
  let items = $state([])
  let busy = $state(null)
  let error = $state(null)

  async function refresh() {
    if (!streamId) return
    try {
      const r = await fetch(`/api/streams/${streamId}/checkpoints`)
      if (r.ok) items = await r.json()
    } catch {}
  }

  $effect(() => {
    const sid = streamId
    if (!sid) { items = []; return }
    refresh()
    const t = setInterval(refresh, 4000)
    return () => clearInterval(t)
  })

  async function rewind(c) {
    if (!confirm(`Rewind to "${c.label}"? This will abort the current claude stream and revert ${c.files_changed.length} file(s). A pre-rewind backup will be saved automatically.`)) return
    busy = c.id
    try {
      const r = await fetch(`/api/streams/${streamId}/rewind/${c.id}`, { method: 'POST' })
      if (!r.ok) {
        const e = await r.json().catch(() => ({}))
        throw new Error(e.detail || `rewind ${r.status}`)
      }
      onRewound?.(c)
      await refresh()
    } catch (e) { error = e?.message || String(e) }
    finally { busy = null }
  }
</script>

{#if items.length}
  <div class="mx-auto my-2 max-w-2xl rounded-lg border border-neutral-800 bg-neutral-950/70 p-2" data-testid="checkpoint-timeline">
    <div class="mb-1 flex items-center gap-1 px-1 text-[10px] uppercase tracking-wide text-neutral-500">
      <span>↶ Checkpoints</span>
      <span class="text-neutral-600">({items.length})</span>
    </div>
    <ol class="space-y-1">
      {#each items as c (c.id)}
        <li class="flex items-center gap-2 rounded-md px-2 py-1 hover:bg-neutral-900" data-testid="checkpoint-{c.id}">
          <span class="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-emerald-500/30 text-[10px]">●</span>
          <div class="min-w-0 flex-1">
            <div class="truncate text-[11px] text-neutral-200">{c.label}</div>
            <div class="text-[9px] text-neutral-500">{new Date(c.created_at).toLocaleTimeString()} · {c.files_changed.length} file{c.files_changed.length === 1 ? '' : 's'}</div>
          </div>
          <button class="rounded bg-amber-500/15 px-2 py-0.5 text-[10px] text-amber-300 hover:bg-amber-500/30 disabled:opacity-50"
            onclick={() => rewind(c)} disabled={busy === c.id}
            data-testid="checkpoint-rewind-{c.id}">{busy === c.id ? '…' : '↶ Rewind'}</button>
        </li>
      {/each}
    </ol>
    {#if error}
      <div class="mt-1 rounded border border-red-500/40 bg-red-500/10 p-1 text-[10px] text-red-300">{error}</div>
    {/if}
  </div>
{/if}
