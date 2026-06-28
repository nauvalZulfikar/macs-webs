<script>
  import { onMount } from 'svelte'
  let { onClose } = $props()

  let cfg = $state(null)
  let qrUrl = $state(null)
  let copied = $state(false)
  let testing = $state(false)

  onMount(async () => {
    try {
      const r = await fetch('/api/notify/config')
      cfg = await r.json()
      qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(cfg.subscribe_url)}`
    } catch {}
  })

  async function copy() {
    if (!cfg) return
    try { await navigator.clipboard.writeText(cfg.subscribe_url); copied = true; setTimeout(() => copied = false, 1500) } catch {}
  }

  async function test() {
    testing = true
    try { await fetch('/api/notify/test', { method: 'POST' }) } finally { testing = false }
  }

  function onKey(e) {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose?.()
    }
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4" data-testid="notify-modal" onclick={() => onClose?.()} role="presentation">
  <div class="w-full max-w-md rounded-2xl border border-amber-500/40 bg-neutral-950 p-4 shadow-xl" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Push notifications">
    <div class="mb-3 flex items-center justify-between">
      <div class="flex items-center gap-2"><span class="text-lg">📲</span><span class="font-medium">Push notifications</span></div>
      <button class="text-neutral-400 hover:text-neutral-100" onclick={onClose}>✕</button>
    </div>
    {#if !cfg}
      <div class="text-xs text-neutral-500">Loading…</div>
    {:else}
      <p class="text-xs text-neutral-400">
        MACS uses <a href="https://ntfy.sh" target="_blank" rel="noreferrer" class="text-amber-300">ntfy.sh</a> for push notifications.
        Install the <strong>ntfy</strong> app on your phone (iOS / Android) and subscribe to this topic — you'll get pushes when watchers fire.
      </p>
      <div class="my-3 grid place-items-center">
        {#if qrUrl}
          <img src={qrUrl} alt="QR" class="rounded-lg bg-white p-2" />
        {/if}
      </div>
      <div class="rounded-lg border border-neutral-800 bg-neutral-900 p-2">
        <div class="text-[10px] uppercase tracking-wide text-neutral-500">Subscribe URL</div>
        <code class="block break-all text-[11px] text-neutral-200" data-testid="notify-url">{cfg.subscribe_url}</code>
      </div>
      <div class="mt-3 flex gap-2">
        <button class="flex-1 rounded-md bg-neutral-800 px-3 py-2 text-xs hover:bg-neutral-700" onclick={copy}>
          {copied ? '✓ Copied' : 'Copy URL'}
        </button>
        <button class="flex-1 rounded-md bg-amber-500/30 px-3 py-2 text-xs text-amber-200 hover:bg-amber-500/50 disabled:opacity-50" onclick={test} disabled={testing} data-testid="notify-test">
          {testing ? 'Sending…' : 'Send test push'}
        </button>
      </div>
    {/if}
  </div>
</div>
