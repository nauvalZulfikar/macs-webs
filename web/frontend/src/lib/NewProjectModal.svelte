<script>
  import { createProject } from './api.js'

  let { open = false, onClose, onCreated } = $props()

  let name = $state('')
  let stack = $state('empty')
  let gitUrl = $state('')
  let welcome = $state(true)
  let busy = $state(false)
  let errMsg = $state('')

  function reset() {
    name = ''
    stack = 'empty'
    gitUrl = ''
    welcome = true
    busy = false
    errMsg = ''
  }

  function close() {
    if (busy) return
    reset()
    onClose?.()
  }

  function isNameValid(s) {
    if (!s) return false
    if (s.startsWith('.') || s.startsWith('-')) return false
    if (/[\/\\]/.test(s)) return false
    return /^[A-Za-z0-9_.-]+$/.test(s)
  }

  async function submit() {
    errMsg = ''
    const n = name.trim()
    if (!isNameValid(n)) {
      errMsg = 'Nama invalid (huruf/angka/_-., no slash, no leading dot/dash)'
      return
    }
    if (stack === 'git' && !gitUrl.trim()) {
      errMsg = 'Git URL wajib untuk stack=git'
      return
    }
    busy = true
    try {
      const res = await createProject({
        name: n,
        stack,
        git_url: stack === 'git' ? gitUrl.trim() : null,
        welcome,
      })
      onCreated?.(res)
      reset()
    } catch (e) {
      errMsg = String(e?.message || e)
    } finally {
      busy = false
    }
  }

  function onKey(ev) {
    if (ev.key === 'Escape') close()
    if (ev.key === 'Enter' && !ev.shiftKey && (ev.target?.tagName !== 'TEXTAREA')) {
      ev.preventDefault()
      submit()
    }
  }
</script>

{#if open}
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    onclick={close}
    role="presentation"
    data-testid="newproj-backdrop"
  >
    <div
      class="w-full max-w-md rounded-xl border border-neutral-800 bg-neutral-950 p-5 shadow-2xl"
      onclick={(e) => e.stopPropagation()}
      onkeydown={onKey}
      role="dialog"
      aria-modal="true"
      data-testid="newproj-modal"
    >
      <div class="mb-4 flex items-center justify-between">
        <h2 class="text-base font-semibold text-neutral-100">+ New Project</h2>
        <button
          class="text-neutral-500 hover:text-neutral-200"
          onclick={close}
          disabled={busy}
          data-testid="newproj-close"
        >✕</button>
      </div>

      <div class="space-y-3">
        <div>
          <label class="block text-[11px] uppercase tracking-wide text-neutral-500" for="np-name">Name</label>
          <input
            id="np-name"
            bind:value={name}
            placeholder="my-new-project"
            disabled={busy}
            class="mt-1 w-full rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none"
            data-testid="newproj-name"
          />
          <p class="mt-1 text-[10px] text-neutral-500">Folder dibuat di <code>~/coding-projects/{name || '<name>'}/</code></p>
        </div>

        <div>
          <label class="block text-[11px] uppercase tracking-wide text-neutral-500" for="np-stack">Stack</label>
          <select
            id="np-stack"
            bind:value={stack}
            disabled={busy}
            class="mt-1 w-full rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none"
            data-testid="newproj-stack"
          >
            <option value="empty">Empty (README.md only)</option>
            <option value="python">Python (uv init)</option>
            <option value="node">Node (npm init -y)</option>
            <option value="git">Clone from Git URL</option>
          </select>
        </div>

        {#if stack === 'git'}
          <div>
            <label class="block text-[11px] uppercase tracking-wide text-neutral-500" for="np-git">Git URL</label>
            <input
              id="np-git"
              bind:value={gitUrl}
              placeholder="https://github.com/user/repo.git"
              disabled={busy}
              class="mt-1 w-full rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none"
              data-testid="newproj-git-url"
            />
          </div>
        {/if}

        <label class="flex items-center gap-2 text-xs text-neutral-300">
          <input type="checkbox" bind:checked={welcome} disabled={busy} class="accent-emerald-500" data-testid="newproj-welcome" />
          Spawn welcome chat (claude baca folder + kasih saran)
        </label>

        {#if errMsg}
          <div class="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300" data-testid="newproj-error">
            {errMsg}
          </div>
        {/if}
      </div>

      <div class="mt-5 flex items-center justify-end gap-2">
        <button
          class="rounded-md px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800 disabled:opacity-50"
          onclick={close}
          disabled={busy}
        >Cancel</button>
        <button
          class="rounded-md bg-emerald-600/80 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
          onclick={submit}
          disabled={busy || !name.trim()}
          data-testid="newproj-submit"
        >
          {busy ? 'Creating…' : 'Create'}
        </button>
      </div>
    </div>
  </div>
{/if}
