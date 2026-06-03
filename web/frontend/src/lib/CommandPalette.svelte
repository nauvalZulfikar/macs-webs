<script>
  import { tick } from 'svelte'

  let {
    open = false,
    projects = [],
    onClose,
    onPickProject,
    onPickSession,
    onOpenMissionLauncher,
    onOpenWatchers,
    onOpenCost,
    onOpenNotify,
    onNewProject,
    onOpenSettings,
    onLogout,
  } = $props()

  // Lazy-load sessions across all projects when palette opens
  let sessionsIndex = $state([])  // [{ project, session }]
  let sessionsLoaded = $state(false)
  let sessionsLoading = $state(false)
  async function ensureSessionsIndex() {
    if (sessionsLoaded || sessionsLoading) return
    sessionsLoading = true
    try {
      const results = await Promise.allSettled(
        projects.map(async (p) => {
          const r = await fetch(`/api/projects/${p.id}/sessions`)
          if (!r.ok) return { p, list: [] }
          const list = await r.json()
          return { p, list }
        })
      )
      const flat = []
      for (const r of results) {
        if (r.status !== 'fulfilled') continue
        for (const s of r.value.list) flat.push({ project: r.value.p, session: s })
      }
      sessionsIndex = flat
      sessionsLoaded = true
    } catch {} finally { sessionsLoading = false }
  }
  $effect(() => {
    if (open) ensureSessionsIndex()
  })

  let query = $state('')
  let highlight = $state(0)
  let inputEl

  const STATIC_COMMANDS = [
    { id: 'new-project', label: 'New project', hint: 'Scaffold + register', icon: '📦', run: () => onNewProject?.() },
    { id: 'new-mission', label: 'Launch mission', hint: 'Multi-agent prompt', icon: '🚀', run: () => onOpenMissionLauncher?.() },
    { id: 'watchers',    label: 'Open watchers',  hint: 'File / cron triggers', icon: '🔔', run: () => onOpenWatchers?.() },
    { id: 'cost',        label: 'Cost dashboard', hint: 'Token spend', icon: '💸', run: () => onOpenCost?.() },
    { id: 'notify',      label: 'Push notifications', hint: 'HP alerts config', icon: '📲', run: () => onOpenNotify?.() },
    { id: 'settings',    label: 'Settings',  hint: 'Density · toasts · voice · pins  (⌘,)', icon: '⚙️', run: () => onOpenSettings?.() },
    { id: 'compare',     label: 'Toggle compare-mode', hint: 'Split-screen 2 chats  (⌘\\)', icon: '⇆', run: () => {
      const ev = new KeyboardEvent('keydown', { key: '\\', metaKey: true, ctrlKey: true })
      window.dispatchEvent(ev)
    } },
    { id: 'logout',      label: 'Sign out', hint: '', icon: '🚪', run: () => onLogout?.() },
  ]

  function projectLabel(p) { return p.display_name || p.name }

  let items = $derived.by(() => {
    const q = query.trim().toLowerCase()
    const projItems = projects.map((p) => ({
      id: `p-${p.id}`,
      kind: 'project',
      icon: '💬',
      label: projectLabel(p),
      hint: p.path || '',
      raw: p,
      run: () => onPickProject?.(p),
    }))
    // Only show session items when the user has typed at least 2 chars
    // (avoids dumping hundreds of session rows by default)
    const sessionItems = q.length >= 2 ? sessionsIndex.map(({ project, session }) => ({
      id: `s-${project.id}-${session.session_id}`,
      kind: 'session',
      icon: '📜',
      label: (session.display_name || session.first_user_message || session.session_id.slice(0, 12)).slice(0, 80),
      hint: `${projectLabel(project)} · ${session.message_count} msgs`,
      raw: { project, session },
      run: () => onPickSession?.(project, session),
    })) : []
    const all = [...projItems, ...sessionItems, ...STATIC_COMMANDS.map((c) => ({ ...c, kind: 'cmd' }))]
    if (!q) return all.slice(0, 20)
    // Simple fuzzy: every char from q must appear in order in label or hint
    const matchScore = (text) => {
      const t = (text || '').toLowerCase()
      let ti = 0, score = 0, lastMatch = -1
      for (const ch of q) {
        const idx = t.indexOf(ch, ti)
        if (idx === -1) return -1
        score += idx === lastMatch + 1 ? 2 : 1
        lastMatch = idx
        ti = idx + 1
      }
      return score
    }
    return all
      .map((it) => ({ it, s: Math.max(matchScore(it.label), matchScore(it.hint)) }))
      .filter((x) => x.s >= 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 20)
      .map((x) => x.it)
  })

  $effect(() => {
    // Reset highlight on items change
    if (highlight >= items.length) highlight = 0
  })

  $effect(() => {
    if (open) {
      tick().then(() => inputEl?.focus())
    } else {
      query = ''
      highlight = 0
    }
  })

  function pick(it) {
    onClose?.()
    queueMicrotask(() => it?.run?.())
  }

  function onKey(e) {
    if (!open) return
    if (e.key === 'Escape') { e.preventDefault(); onClose?.() }
    else if (e.key === 'ArrowDown') { e.preventDefault(); highlight = Math.min(highlight + 1, items.length - 1) }
    else if (e.key === 'ArrowUp')   { e.preventDefault(); highlight = Math.max(highlight - 1, 0) }
    else if (e.key === 'Enter')     { e.preventDefault(); pick(items[highlight]) }
  }
</script>

<svelte:window onkeydown={onKey} />

{#if open}
  <div
    class="palette-backdrop fixed inset-0 z-[90] grid place-items-start justify-items-center bg-black/60 px-4 pt-[8vh] backdrop-blur-sm"
    onclick={onClose}
    role="presentation"
    data-testid="palette-backdrop"
  >
    <div
      class="palette-card w-full max-w-xl overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-950/95 shadow-2xl"
      onclick={(e) => e.stopPropagation()}
      role="dialog"
      aria-label="Command palette"
      data-testid="command-palette"
    >
      <div class="flex items-center gap-2 border-b border-neutral-800 px-3 py-3">
        <span class="text-neutral-500">⌘</span>
        <input
          bind:this={inputEl}
          bind:value={query}
          placeholder="Cari project, jalanin command…"
          class="flex-1 bg-transparent text-sm text-neutral-100 placeholder-neutral-500 focus:outline-none"
          data-testid="palette-input"
        />
        <kbd class="rounded border border-neutral-700 bg-neutral-900 px-1.5 py-0.5 text-[10px] text-neutral-400">esc</kbd>
      </div>
      <ul class="max-h-[55vh] overflow-y-auto py-1" data-testid="palette-list">
        {#each items as it, i (it.id)}
          <li>
            <button
              class="flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition {i === highlight ? 'bg-emerald-500/10 text-emerald-100' : 'text-neutral-200 hover:bg-neutral-900'}"
              onmouseenter={() => highlight = i}
              onclick={() => pick(it)}
              data-testid="palette-item"
            >
              <span class="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-neutral-900 text-sm">{it.icon}</span>
              <div class="min-w-0 flex-1">
                <div class="truncate font-medium">{it.label}</div>
                {#if it.hint}
                  <div class="truncate text-[11px] text-neutral-500">{it.hint}</div>
                {/if}
              </div>
              {#if i === highlight}
                <kbd class="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-300">↵</kbd>
              {/if}
            </button>
          </li>
        {/each}
        {#if items.length === 0}
          <li class="px-3 py-6 text-center text-xs text-neutral-500">No matches for "{query}"</li>
        {/if}
      </ul>
      <div class="flex items-center justify-between border-t border-neutral-800 bg-neutral-950/80 px-3 py-2 text-[10px] text-neutral-500">
        <span class="flex items-center gap-2">
          <kbd class="rounded border border-neutral-700 px-1">↑</kbd>
          <kbd class="rounded border border-neutral-700 px-1">↓</kbd>
          navigate
        </span>
        <span>{items.length} item{items.length === 1 ? '' : 's'}</span>
      </div>
    </div>
  </div>
{/if}

<style>
  .palette-backdrop { animation: fade-in 0.15s ease-out; }
  .palette-card     { animation: pop-in 0.18s cubic-bezier(0.2, 0.8, 0.2, 1); }
  @keyframes fade-in { from { opacity: 0 } to { opacity: 1 } }
  @keyframes pop-in {
    from { transform: translateY(-8px) scale(0.97); opacity: 0; }
    to   { transform: translateY(0) scale(1); opacity: 1; }
  }
</style>
