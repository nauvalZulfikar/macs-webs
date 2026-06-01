<script>
  let { projects = [], onClose, onCreated } = $props()

  let name = $state('')
  let projectId = $state(projects[0]?.id ?? null)
  let triggerType = $state('file_change')
  let actionPrompt = $state('')
  let elevated = $state(false)
  let paths = $state('')
  let cronSpec = $state('*/30 * * * *')
  let cmd = $state('pytest -x')
  let intervalS = $state(600)
  let creating = $state(false)
  let error = $state(null)

  let canCreate = $derived(
    !creating && name.trim() && projectId && actionPrompt.trim() && (
      triggerType !== 'cron' || cronSpec.trim()
    ) && (
      triggerType !== 'test_loop' || cmd.trim()
    )
  )

  async function create() {
    if (!canCreate) return
    creating = true
    error = null
    let cfg = {}
    if (triggerType === 'file_change') {
      cfg.paths = paths.split(',').map((s) => s.trim()).filter(Boolean)
      cfg.debounce_s = 2
    } else if (triggerType === 'cron') {
      cfg.spec = cronSpec.trim()
    } else if (triggerType === 'test_loop') {
      cfg.cmd = cmd
      cfg.interval_s = Number(intervalS) || 600
    }
    try {
      const r = await fetch('/api/watchers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          name: name.trim(),
          trigger_type: triggerType,
          trigger_config: cfg,
          action_prompt: actionPrompt.trim(),
          enabled: true,
          elevated,
        }),
      })
      if (!r.ok) {
        const e = await r.json().catch(() => ({}))
        throw new Error(e.detail || `${r.status}`)
      }
      onCreated?.()
    } catch (e) {
      error = e?.message || String(e)
    } finally { creating = false }
  }
</script>

<div class="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4" data-testid="watcher-create-modal">
  <div class="w-full max-w-md rounded-2xl border border-amber-500/40 bg-neutral-950 p-4 shadow-xl max-h-[90vh] flex flex-col">
    <div class="mb-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="text-lg">🔔</span>
        <span class="font-medium">New Watcher</span>
      </div>
      <button class="text-neutral-400 hover:text-neutral-100" onclick={onClose}>✕</button>
    </div>

    <div class="space-y-3 overflow-y-auto pr-1">
      <div>
        <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Name</label>
        <input bind:value={name} placeholder="auto-test on save"
          class="mt-1 w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none"
          data-testid="watcher-name" />
      </div>
      <div>
        <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Project</label>
        <select bind:value={projectId}
          class="mt-1 w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none"
          data-testid="watcher-project">
          {#each projects as p (p.id)}
            <option value={p.id}>{p.display_name || p.name}</option>
          {/each}
        </select>
      </div>
      <div>
        <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Trigger</label>
        <select bind:value={triggerType}
          class="mt-1 w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none"
          data-testid="watcher-trigger-type">
          <option value="file_change">📂 File change</option>
          <option value="cron">⏰ Cron schedule</option>
          <option value="test_loop">🧪 Test loop (fire on non-zero exit)</option>
          <option value="manual">👆 Manual only</option>
        </select>
      </div>

      {#if triggerType === 'file_change'}
        <div>
          <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Watch paths (comma-separated; defaults to project root)</label>
          <input bind:value={paths} placeholder="src, tests"
            class="mt-1 w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none" />
        </div>
      {:else if triggerType === 'cron'}
        <div>
          <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Cron spec</label>
          <input bind:value={cronSpec} placeholder="*/30 * * * *"
            class="mt-1 w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm font-mono focus:border-emerald-600/60 focus:outline-none" />
          <div class="mt-1 text-[10px] text-neutral-500">min hr day mon dow — e.g. `0 9 * * 1-5` weekday 9am</div>
        </div>
      {:else if triggerType === 'test_loop'}
        <div>
          <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Command</label>
          <input bind:value={cmd} placeholder="pytest -x"
            class="mt-1 w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm font-mono focus:border-emerald-600/60 focus:outline-none" />
        </div>
        <div>
          <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Interval (seconds)</label>
          <input type="number" bind:value={intervalS} min="30"
            class="mt-1 w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none" />
        </div>
      {/if}

      <div>
        <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Action prompt (what claude does when triggered)</label>
        <textarea bind:value={actionPrompt} rows="4"
          placeholder="check the failing tests, summarize the cause, propose a fix"
          class="mt-1 w-full resize-none rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none"
          data-testid="watcher-prompt"></textarea>
      </div>

      <label class="flex items-center gap-2 text-xs text-neutral-400">
        <input type="checkbox" bind:checked={elevated} />
        Elevated permissions
      </label>

      {#if error}
        <div class="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-300">{error}</div>
      {/if}
    </div>

    <div class="mt-3 flex gap-2 border-t border-neutral-800 pt-3">
      <button class="flex-1 rounded-lg bg-neutral-800 px-3 py-2 text-sm text-neutral-200 hover:bg-neutral-700" onclick={onClose} disabled={creating}>Cancel</button>
      <button class="flex-1 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:bg-neutral-700" onclick={create} disabled={!canCreate} data-testid="watcher-create-btn">
        {creating ? 'Creating…' : 'Create'}
      </button>
    </div>
  </div>
</div>
