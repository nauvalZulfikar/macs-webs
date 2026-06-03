<script>
  import { toasts, dismissToast } from './toastStore.svelte.js'
  let snap = $state([])
  $effect(() => {
    const unsub = toasts.subscribe((v) => { snap = v })
    return unsub
  })
  function kindStyles(k) {
    if (k === 'success') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
    if (k === 'error')   return 'border-red-500/40 bg-red-500/10 text-red-200'
    if (k === 'warn')    return 'border-amber-500/40 bg-amber-500/10 text-amber-200'
    return 'border-neutral-700 bg-neutral-900 text-neutral-200'
  }
  function kindIcon(k) {
    if (k === 'success') return '✓'
    if (k === 'error')   return '✕'
    if (k === 'warn')    return '!'
    return 'i'
  }
</script>

<div
  class="pointer-events-none fixed bottom-4 right-4 z-[80] flex w-[min(380px,90vw)] flex-col gap-2"
  aria-live="polite"
  aria-atomic="false"
  data-testid="toast-host"
>
  {#each snap as t (t.id)}
    <div
      class="toast-item pointer-events-auto flex items-start gap-2 rounded-xl border px-3 py-2.5 text-sm shadow-xl backdrop-blur-md {kindStyles(t.kind)}"
      data-testid="toast"
    >
      <span class="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-black/30 text-[11px] font-bold">{kindIcon(t.kind)}</span>
      <div class="min-w-0 flex-1">
        {#if t.title}<div class="font-medium leading-tight">{t.title}</div>{/if}
        {#if t.body}<div class="mt-0.5 text-xs opacity-90">{t.body}</div>{/if}
      </div>
      <button
        class="text-base leading-none opacity-50 hover:opacity-100"
        onclick={() => dismissToast(t.id)}
        aria-label="Dismiss"
      >×</button>
    </div>
  {/each}
</div>

<style>
  .toast-item {
    animation: toast-in 0.22s ease-out;
  }
  @keyframes toast-in {
    from { transform: translateY(8px) scale(0.97); opacity: 0; }
    to   { transform: translateY(0) scale(1); opacity: 1; }
  }
</style>
