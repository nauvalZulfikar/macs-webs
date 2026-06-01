<script>
  import { onMount, onDestroy } from 'svelte'
  import { EditorState, Compartment } from '@codemirror/state'
  import { EditorView, lineNumbers, highlightActiveLine, keymap } from '@codemirror/view'
  import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
  import { javascript } from '@codemirror/lang-javascript'
  import { python } from '@codemirror/lang-python'
  import { markdown } from '@codemirror/lang-markdown'
  import { oneDark } from '@codemirror/theme-one-dark'

  let { projectId, path = null, onClose, recentlyEditedFiles = [] } = $props()

  let view = null
  let host
  let loaded = $state(null) // {path, content, size, mtime}
  let dirty = $state(false)
  let saving = $state(false)
  let error = $state(null)
  let currentPath = $state(path)

  const langCompartment = new Compartment()

  function langFor(p) {
    if (!p) return []
    const ext = p.split('.').pop()?.toLowerCase()
    if (['js','jsx','ts','tsx','mjs','cjs'].includes(ext)) return javascript({ jsx: true, typescript: ext.startsWith('ts') })
    if (ext === 'py') return python()
    if (['md','mdx','markdown'].includes(ext)) return markdown()
    return []
  }

  function setupView(content) {
    if (view) view.destroy()
    view = new EditorView({
      state: EditorState.create({
        doc: content || '',
        extensions: [
          lineNumbers(),
          highlightActiveLine(),
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          langCompartment.of(langFor(currentPath)),
          oneDark,
          EditorView.lineWrapping,
          EditorView.updateListener.of((u) => {
            if (u.docChanged) dirty = true
          }),
        ],
      }),
      parent: host,
    })
  }

  async function load(p) {
    currentPath = p
    error = null
    if (!p) { loaded = null; if (view) view.destroy(); view = null; return }
    try {
      const r = await fetch(`/api/projects/${projectId}/files/read?path=${encodeURIComponent(p)}`)
      if (!r.ok) throw new Error(`read ${r.status}`)
      loaded = await r.json()
      dirty = false
      setupView(loaded.content)
    } catch (e) {
      error = e?.message || String(e)
      loaded = null
    }
  }

  async function save() {
    if (!currentPath || !view) return
    saving = true; error = null
    try {
      const content = view.state.doc.toString()
      const r = await fetch(`/api/projects/${projectId}/files/write`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentPath, content }),
      })
      if (!r.ok) throw new Error(`write ${r.status}`)
      dirty = false
    } catch (e) { error = e?.message || String(e) }
    finally { saving = false }
  }

  function onKey(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); save() }
  }

  onMount(() => {
    if (currentPath) load(currentPath)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  onDestroy(() => view?.destroy())

  $effect(() => {
    if (path && path !== currentPath) load(path)
  })
</script>

<div class="flex h-full min-h-0 flex-col border-l border-neutral-800 bg-neutral-950" data-testid="editor-pane">
  <div class="flex items-center gap-2 border-b border-neutral-800 px-2 py-1.5">
    <span class="text-sm">📄</span>
    {#if currentPath}
      <span class="truncate text-xs font-medium" data-testid="editor-path">{currentPath}</span>
      {#if dirty}<span class="rounded-full bg-amber-500/20 px-1.5 text-[10px] text-amber-300">unsaved</span>{/if}
      {#if loaded?.truncated}<span class="rounded-full bg-red-500/20 px-1.5 text-[10px] text-red-300">truncated</span>{/if}
    {:else}
      <span class="truncate text-xs text-neutral-500">No file open</span>
    {/if}
    <div class="ml-auto flex items-center gap-1">
      {#if currentPath}
        <button class="rounded bg-emerald-600/20 px-2 py-0.5 text-[10px] text-emerald-300 hover:bg-emerald-600/40 disabled:opacity-50"
          onclick={save} disabled={!dirty || saving} data-testid="editor-save">{saving ? '…' : '💾 Save (⌘S)'}</button>
      {/if}
      <button class="rounded px-2 py-0.5 text-[10px] text-neutral-400 hover:text-neutral-100" onclick={onClose} data-testid="editor-close">✕</button>
    </div>
  </div>

  {#if recentlyEditedFiles.length > 0 && !currentPath}
    <div class="border-b border-neutral-800 bg-neutral-950/70 px-2 py-1.5">
      <div class="text-[10px] uppercase tracking-wide text-neutral-500">Recently edited by claude</div>
      <div class="mt-1 flex flex-wrap gap-1">
        {#each recentlyEditedFiles.slice(0, 8) as f}
          <button class="rounded bg-neutral-900 px-2 py-0.5 text-[10px] text-blue-300 hover:bg-neutral-800" onclick={() => load(f)}>{f}</button>
        {/each}
      </div>
    </div>
  {/if}

  {#if error}
    <div class="m-2 rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-300">{error}</div>
  {/if}

  <div class="flex-1 overflow-hidden" bind:this={host}></div>
</div>
