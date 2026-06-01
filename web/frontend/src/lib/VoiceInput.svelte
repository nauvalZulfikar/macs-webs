<script>
  /** Voice input via Web Speech API. Indonesian default. Continuous mode. */
  let { onTranscript, lang = 'id-ID' } = $props()

  let listening = $state(false)
  let unsupported = $state(false)
  let interim = $state('')
  let recog = null

  function init() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { unsupported = true; return null }
    const r = new SR()
    r.continuous = true
    r.interimResults = true
    r.lang = lang
    r.onresult = (ev) => {
      let finalChunk = ''
      let interimChunk = ''
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const t = ev.results[i][0].transcript
        if (ev.results[i].isFinal) finalChunk += t
        else interimChunk += t
      }
      if (finalChunk) {
        interim = ''
        onTranscript?.(finalChunk.trim())
      } else {
        interim = interimChunk
      }
    }
    r.onerror = () => {}
    r.onend = () => { listening = false; interim = '' }
    return r
  }

  function toggle() {
    if (unsupported) return
    if (listening) {
      try { recog?.stop() } catch {}
      listening = false
      return
    }
    if (!recog) recog = init()
    if (!recog) return
    try {
      recog.start()
      listening = true
    } catch {
      listening = false
    }
  }
</script>

{#if !unsupported}
  <button
    type="button"
    class="inline-flex h-9 items-center gap-1 rounded-xl px-2 text-sm transition {listening ? 'bg-red-500/20 text-red-300' : 'bg-neutral-800 text-neutral-300 hover:bg-neutral-700'}"
    onclick={toggle}
    title={listening ? 'Stop listening' : 'Voice input (id-ID)'}
    data-testid="voice-btn"
  >
    <span class="text-base">{listening ? '🔴' : '🎙'}</span>
    {#if interim}
      <span class="max-w-[180px] truncate text-[11px] text-red-300">{interim}</span>
    {/if}
  </button>
{/if}
