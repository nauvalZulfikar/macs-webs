<script>
  import { onMount } from 'svelte'
  let { onClose } = $props()

  let data = $state(null)
  let days = $state(30)
  let loading = $state(true)

  async function refresh() {
    loading = true
    try {
      const r = await fetch(`/api/cost/summary?days=${days}`)
      if (r.ok) data = await r.json()
    } finally { loading = false }
  }

  onMount(refresh)

  function fmtUsd(n) { return `$${(n || 0).toFixed(4)}` }
  function fmtTok(n) { return (n || 0).toLocaleString() }
</script>

<div class="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4" data-testid="cost-modal">
  <div class="w-full max-w-2xl rounded-2xl border border-amber-500/40 bg-neutral-950 p-4 shadow-xl max-h-[90vh] flex flex-col">
    <div class="mb-3 flex items-center justify-between">
      <div class="flex items-center gap-2"><span class="text-lg">💸</span><span class="font-medium">Cost dashboard</span></div>
      <div class="flex items-center gap-2">
        <select bind:value={days} onchange={refresh} class="rounded-md border border-neutral-800 bg-neutral-900 px-2 py-1 text-xs">
          <option value={7}>7d</option>
          <option value={30}>30d</option>
          <option value={90}>90d</option>
        </select>
        <button class="text-neutral-400 hover:text-neutral-100" onclick={onClose}>✕</button>
      </div>
    </div>
    {#if loading}
      <div class="text-xs text-neutral-500">Loading…</div>
    {:else if data}
      <div class="mb-3 grid grid-cols-3 gap-2">
        <div class="rounded-lg border border-neutral-800 bg-neutral-900 p-2">
          <div class="text-[10px] uppercase text-neutral-500">Spend</div>
          <div class="text-lg font-medium text-emerald-300" data-testid="cost-total">{fmtUsd(data.total.cost_usd)}</div>
        </div>
        <div class="rounded-lg border border-neutral-800 bg-neutral-900 p-2">
          <div class="text-[10px] uppercase text-neutral-500">Streams</div>
          <div class="text-lg font-medium">{data.total.streams}</div>
        </div>
        <div class="rounded-lg border border-neutral-800 bg-neutral-900 p-2">
          <div class="text-[10px] uppercase text-neutral-500">Output tokens</div>
          <div class="text-lg font-medium">{fmtTok(data.total.output_tokens)}</div>
        </div>
      </div>
      <div class="overflow-y-auto rounded-lg border border-neutral-800 bg-neutral-900/50">
        <table class="w-full text-xs">
          <thead class="sticky top-0 bg-neutral-900 text-[10px] uppercase text-neutral-500">
            <tr><th class="px-2 py-1.5 text-left">Project</th><th class="px-2 py-1.5 text-right">Cost</th><th class="px-2 py-1.5 text-right">Out tokens</th><th class="px-2 py-1.5 text-right">Streams</th></tr>
          </thead>
          <tbody>
            {#each data.by_project as p}
              <tr class="border-t border-neutral-800" data-testid="cost-row-{p.project_id}">
                <td class="px-2 py-1.5">{p.name}</td>
                <td class="px-2 py-1.5 text-right text-emerald-300">{fmtUsd(p.cost_usd)}</td>
                <td class="px-2 py-1.5 text-right text-neutral-400">{fmtTok(p.output_tokens)}</td>
                <td class="px-2 py-1.5 text-right text-neutral-400">{p.streams}</td>
              </tr>
            {/each}
            {#if !data.by_project.length}
              <tr><td colspan="4" class="px-2 py-3 text-center text-neutral-500">No completed streams yet in window.</td></tr>
            {/if}
          </tbody>
        </table>
      </div>
    {/if}
  </div>
</div>
