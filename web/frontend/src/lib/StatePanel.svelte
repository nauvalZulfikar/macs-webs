<script>
  import { onMount, onDestroy } from 'svelte'

  let { projectId, open = false, onClose } = $props()

  let content = $state(null)
  let loading = $state(false)
  let err = $state(null)
  let lastFetched = $state(0)

  async function load() {
    if (!projectId) return
    loading = true
    err = null
    try {
      const r = await fetch(
        `/api/projects/${projectId}/files/read?path=.macs/STATE.md`,
      )
      if (r.status === 404) {
        content = null
        return
      }
      if (!r.ok) throw new Error(`fetch ${r.status}`)
      const data = await r.json()
      content = data?.content ?? null
      lastFetched = Date.now()
    } catch (e) {
      err = String(e?.message || e)
      content = null
    } finally {
      loading = false
    }
  }

  let timer = null
  $effect(() => {
    if (!open) return
    load()
    timer = setInterval(load, 10000) // auto-refresh every 10s
    return () => { clearInterval(timer); timer = null }
  })

  function formatAgo(ms) {
    if (!ms) return ''
    const s = Math.floor((Date.now() - ms) / 1000)
    if (s < 60) return `${s}s ago`
    return `${Math.floor(s / 60)}m ${s % 60}s ago`
  }

  // Parse entries: split by `---` separators
  let entries = $derived.by(() => {
    if (!content) return []
    const blocks = content.split(/^---\s*$/m).map((b) => b.trim()).filter(Boolean)
    return blocks
  })
</script>

{#if open}
  <div
    class="fixed inset-0 z-40 flex items-stretch justify-end bg-black/40"
    onclick={onClose}
    role="presentation"
    data-testid="state-panel-backdrop"
  >
    <div
      class="flex w-full max-w-md flex-col border-l border-neutral-800 bg-neutral-950 shadow-2xl"
      onclick={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      data-testid="state-panel"
    >
      <div class="flex shrink-0 items-center justify-between border-b border-neutral-800 px-4 py-3">
        <div>
          <h2 class="text-sm font-semibold text-neutral-100">📋 STATE.md</h2>
          <p class="text-[10px] text-neutral-500">
            Snapshot per-turn dari <code>.macs/STATE.md</code>{lastFetched ? ` — ${formatAgo(lastFetched)}` : ''}
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button
            class="rounded-md px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
            onclick={load}
            disabled={loading}
            data-testid="state-panel-refresh"
            title="Refresh now"
          >{loading ? '…' : '↻'}</button>
          <button
            class="text-neutral-500 hover:text-neutral-200"
            onclick={onClose}
            data-testid="state-panel-close"
          >✕</button>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto px-4 py-3" data-testid="state-panel-body">
        {#if err}
          <div class="rounded-md border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-300">
            Error: {err}
          </div>
        {:else if loading && !content}
          <div class="text-xs text-neutral-500">Loading…</div>
        {:else if !content}
          <div class="rounded-md border border-neutral-800 bg-neutral-900/40 p-4 text-xs text-neutral-400">
            <div class="mb-1 font-medium text-neutral-200">Belum ada STATE.md</div>
            File <code>.macs/STATE.md</code> akan otomatis terisi setelah claude melakukan kerjaan substantif + nulis blok STATUS sesuai aturan di CLAUDE.md.
          </div>
        {:else if entries.length === 0}
          <pre class="whitespace-pre-wrap break-words text-xs text-neutral-300">{content}</pre>
        {:else}
          <ul class="space-y-3">
            {#each entries.slice().reverse() as block, i (i)}
              <li class="rounded-md border border-neutral-800 bg-neutral-900/40 p-3 text-xs">
                <pre class="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-neutral-300">{block}</pre>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </div>
  </div>
{/if}
