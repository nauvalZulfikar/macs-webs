<script>
  import { listProjects } from './api.js'
  import { onMount } from 'svelte'

  let { onSelect, onLogout } = $props()
  let projects = $state([])
  let loading = $state(true)
  let error = $state(null)

  onMount(async () => {
    try {
      projects = await listProjects()
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  })
</script>

<div class="mx-auto max-w-2xl px-4 py-6">
  <header class="mb-6 flex items-center justify-between">
    <div>
      <h1 class="text-xl font-semibold tracking-tight">MACS</h1>
      <p class="text-sm text-neutral-400">Tap a project to chat with Claude in that workspace.</p>
    </div>
    <div class="flex items-center gap-2">
      <span class="rounded-full bg-emerald-500/15 px-2 py-1 text-xs text-emerald-300" data-testid="status">online</span>
      <button class="rounded-md px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100" onclick={onLogout} data-testid="logout-btn">Log out</button>
    </div>
  </header>

  {#if loading}
    <div class="space-y-2" data-testid="loading-skeleton">
      {#each Array(4) as _}
        <div class="h-16 animate-pulse rounded-xl border border-neutral-800 bg-neutral-900/60"></div>
      {/each}
    </div>
  {:else if error}
    <div class="rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300" data-testid="list-error">
      Failed to load projects: {error}
    </div>
  {:else if projects.length === 0}
    <div class="rounded-xl border border-neutral-800 bg-neutral-900 p-6 text-center text-sm text-neutral-400" data-testid="empty-list">
      No projects configured.
    </div>
  {:else}
    <ul class="space-y-2" data-testid="project-list">
      {#each projects as p (p.id)}
        <li>
          <button
            class="flex w-full items-center justify-between rounded-xl border border-neutral-800 bg-neutral-900 px-4 py-3 text-left transition hover:border-neutral-700 hover:bg-neutral-800/70 active:scale-[0.99]"
            onclick={() => onSelect(p)}
            data-testid="project-item-{p.id}"
          >
            <div class="min-w-0">
              <div class="truncate font-medium">{p.name}</div>
              <div class="truncate text-xs text-neutral-500">{p.path}</div>
            </div>
            <div class="ml-3 flex flex-col items-end gap-1">
              {#if p.last_session_id}
                <span class="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">resume</span>
              {/if}
              <span class="text-neutral-500" aria-hidden="true">›</span>
            </div>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>
