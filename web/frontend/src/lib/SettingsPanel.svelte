<script>
  import { settings, setDensity, setToastsEnabled, setVoiceLang, setTheme, addSavedPrompt, removeSavedPrompt, setAudioCues, playChime } from './settingsStore.svelte.js'

  let { open = false, onClose } = $props()

  let snap = $state({ density: 'comfy', toastsEnabled: true, voiceLang: 'id-ID', pinned: [], theme: 'auto', savedPrompts: [], audioCues: false, starred: {} })
  let newPromptLabel = $state('')
  let newPromptText = $state('')
  $effect(() => {
    const unsub = settings.subscribe((v) => { snap = v })
    return unsub
  })

  function onKey(e) {
    if (e.key === 'Escape' && open) {
      e.preventDefault()
      onClose?.()
    }
  }

  function clearPinned() {
    settings.update((s) => ({ ...s, pinned: [] }))
  }

  const VOICE_LANGS = [
    { code: 'id-ID', label: 'Bahasa Indonesia' },
    { code: 'en-US', label: 'English (US)' },
    { code: 'en-GB', label: 'English (UK)' },
  ]
</script>

<svelte:window onkeydown={onKey} />

{#if open}
  <div
    class="settings-backdrop fixed inset-0 z-[85] grid place-items-start justify-items-center bg-black/60 px-4 pt-[10vh] backdrop-blur-sm"
    onclick={onClose}
    role="presentation"
    data-testid="settings-backdrop"
  >
    <div
      class="settings-card w-full max-w-md overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-950/95 shadow-2xl"
      onclick={(e) => e.stopPropagation()}
      role="dialog"
      aria-label="Settings"
      data-testid="settings-panel"
    >
      <div class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
        <div class="flex items-center gap-2 text-sm font-semibold text-neutral-100">
          <span>⚙️</span>
          <span>Settings</span>
        </div>
        <button
          class="text-neutral-500 hover:text-neutral-200"
          onclick={onClose}
          aria-label="Close"
        >✕</button>
      </div>

      <div class="max-h-[70vh] space-y-5 overflow-y-auto p-4 text-sm">
        <!-- Theme -->
        <div>
          <div class="mb-1.5 font-medium text-neutral-200">Theme</div>
          <div class="mb-2 text-xs text-neutral-500">Auto = follow OS preference.</div>
          <div class="inline-flex rounded-lg border border-neutral-800 bg-neutral-900 p-0.5" role="radiogroup" aria-label="Theme">
            {#each [['auto','🌗 Auto'],['dark','🌑 Dark'],['light','☀️ Light']] as [val, lbl]}
              <button
                class="rounded-md px-3 py-1.5 text-xs transition {snap.theme === val ? 'bg-emerald-500/15 text-emerald-200' : 'text-neutral-400 hover:text-neutral-200'}"
                onclick={() => setTheme(val)}
                data-testid="theme-{val}"
                role="radio"
                aria-checked={snap.theme === val}
              >{lbl}</button>
            {/each}
          </div>
        </div>

        <!-- Density -->
        <div>
          <div class="mb-1.5 font-medium text-neutral-200">Density</div>
          <div class="mb-2 text-xs text-neutral-500">Sidebar row size + spacing.</div>
          <div class="inline-flex rounded-lg border border-neutral-800 bg-neutral-900 p-0.5" role="radiogroup" aria-label="Density">
            <button
              class="rounded-md px-3 py-1.5 text-xs transition {snap.density === 'comfy' ? 'bg-emerald-500/15 text-emerald-200' : 'text-neutral-400 hover:text-neutral-200'}"
              onclick={() => setDensity('comfy')}
              data-testid="density-comfy"
              role="radio"
              aria-checked={snap.density === 'comfy'}
            >Comfy</button>
            <button
              class="rounded-md px-3 py-1.5 text-xs transition {snap.density === 'compact' ? 'bg-emerald-500/15 text-emerald-200' : 'text-neutral-400 hover:text-neutral-200'}"
              onclick={() => setDensity('compact')}
              data-testid="density-compact"
              role="radio"
              aria-checked={snap.density === 'compact'}
            >Compact</button>
          </div>
        </div>

        <!-- Toasts -->
        <div>
          <div class="mb-1.5 font-medium text-neutral-200">Notifikasi (toast)</div>
          <div class="mb-2 text-xs text-neutral-500">Toast saat stream selesai, error, dll.</div>
          <label class="inline-flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={snap.toastsEnabled}
              onchange={(e) => setToastsEnabled(e.currentTarget.checked)}
              class="h-4 w-4 accent-emerald-500"
              data-testid="toggle-toasts"
            />
            <span class="text-xs text-neutral-300">{snap.toastsEnabled ? 'Enabled' : 'Disabled'}</span>
          </label>
        </div>

        <!-- Audio cues -->
        <div>
          <div class="mb-1.5 font-medium text-neutral-200">Audio cue</div>
          <div class="mb-2 text-xs text-neutral-500">Chime ketika stream selesai (background reply notifier).</div>
          <div class="flex items-center gap-2">
            <label class="inline-flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={snap.audioCues}
                onchange={(e) => setAudioCues(e.currentTarget.checked)}
                class="h-4 w-4 accent-emerald-500"
                data-testid="toggle-audio"
              />
              <span class="text-xs text-neutral-300">{snap.audioCues ? 'Enabled' : 'Disabled'}</span>
            </label>
            <button
              class="rounded-md border border-neutral-700 px-2 py-0.5 text-[11px] text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200"
              onclick={playChime}
              data-testid="audio-test"
            >Test chime</button>
          </div>
        </div>

        <!-- Voice -->
        <div>
          <div class="mb-1.5 font-medium text-neutral-200">Voice input language</div>
          <select
            value={snap.voiceLang}
            onchange={(e) => setVoiceLang(e.currentTarget.value)}
            class="rounded-md border border-neutral-800 bg-neutral-900 px-3 py-1.5 text-xs text-neutral-200 focus:border-emerald-600/60 focus:outline-none"
            data-testid="select-voice-lang"
          >
            {#each VOICE_LANGS as v}
              <option value={v.code}>{v.label}</option>
            {/each}
          </select>
        </div>

        <!-- Pinned -->
        <div>
          <div class="mb-1.5 flex items-center justify-between font-medium text-neutral-200">
            <span>Pinned projects</span>
            <span class="text-[10px] font-normal text-neutral-500">{snap.pinned.length} pinned</span>
          </div>
          <div class="mb-2 text-xs text-neutral-500">Click 📌 in sidebar to pin · drag to reorder.</div>
          {#if snap.pinned.length > 0}
            <button
              class="rounded-md border border-red-500/30 bg-red-500/10 px-2.5 py-1 text-[11px] text-red-300 hover:bg-red-500/20"
              onclick={clearPinned}
              data-testid="clear-pinned"
            >Clear all pins</button>
          {/if}
        </div>

        <!-- Saved prompts -->
        <div>
          <div class="mb-1.5 flex items-center justify-between font-medium text-neutral-200">
            <span>Saved prompts</span>
            <span class="text-[10px] font-normal text-neutral-500">{snap.savedPrompts.length} saved</span>
          </div>
          <div class="mb-2 text-xs text-neutral-500">Quick-insert via ⌘P in composer.</div>
          {#if snap.savedPrompts.length > 0}
            <ul class="mb-2 space-y-1">
              {#each snap.savedPrompts as p (p.id)}
                <li class="flex items-center justify-between gap-2 rounded-md border border-neutral-800 bg-neutral-900/50 px-2 py-1.5">
                  <div class="min-w-0 flex-1">
                    <div class="truncate text-xs font-medium text-neutral-200">{p.label}</div>
                    <div class="truncate text-[10px] text-neutral-500">{p.text}</div>
                  </div>
                  <button
                    class="text-xs text-neutral-500 hover:text-red-300"
                    onclick={() => removeSavedPrompt(p.id)}
                    aria-label="Delete saved prompt"
                  >✕</button>
                </li>
              {/each}
            </ul>
          {/if}
          <div class="flex flex-col gap-1.5">
            <input
              bind:value={newPromptLabel}
              placeholder="Label (e.g. 'PR review')"
              class="rounded-md border border-neutral-800 bg-neutral-900 px-2 py-1 text-xs focus:border-emerald-600/60 focus:outline-none"
            />
            <textarea
              bind:value={newPromptText}
              rows="2"
              placeholder="Prompt text…"
              class="rounded-md border border-neutral-800 bg-neutral-900 px-2 py-1 text-xs focus:border-emerald-600/60 focus:outline-none"
            ></textarea>
            <button
              class="self-start rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-40"
              disabled={!newPromptLabel.trim() || !newPromptText.trim()}
              onclick={() => { addSavedPrompt(newPromptLabel.trim(), newPromptText.trim()); newPromptLabel = ''; newPromptText = '' }}
            >+ Add prompt</button>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between border-t border-neutral-800 bg-neutral-950/80 px-4 py-2.5 text-[10px] text-neutral-500">
        <span>Saved locally · per browser</span>
        <span>Press <kbd class="rounded border border-neutral-700 px-1">Esc</kbd> to close</span>
      </div>
    </div>
  </div>
{/if}

<style>
  .settings-backdrop { animation: fade-in 0.15s ease-out; }
  .settings-card     { animation: pop-in 0.18s cubic-bezier(0.2, 0.8, 0.2, 1); }
  @keyframes fade-in { from { opacity: 0 } to { opacity: 1 } }
  @keyframes pop-in {
    from { transform: translateY(-8px) scale(0.97); opacity: 0; }
    to   { transform: translateY(0) scale(1); opacity: 1; }
  }
</style>
