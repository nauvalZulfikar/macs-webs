<script>
  import { authLogin } from './api.js'

  let { onSuccess } = $props()
  let username = $state('')
  let password = $state('')
  let pending = $state(false)
  let error = $state(null)

  async function submit(e) {
    e.preventDefault()
    if (pending || !username || !password) return
    pending = true
    error = null
    try {
      const ok = await authLogin(username.trim().toLowerCase(), password)
      if (ok) {
        password = ''
        onSuccess()
      } else {
        error = 'Wrong username or password.'
      }
    } catch (e) {
      error = e.message
    } finally {
      pending = false
    }
  }
</script>

<div class="flex min-h-dvh items-center justify-center px-4">
  <form
    class="w-full max-w-sm rounded-2xl border border-neutral-800 bg-neutral-950 p-6"
    onsubmit={submit}
    data-testid="login-form"
  >
    <h1 class="mb-1 text-lg font-semibold">MACS</h1>
    <p class="mb-5 text-sm text-neutral-400">Multi-Agent Orchestration System · sign in to continue.</p>
    <input
      type="text"
      bind:value={username}
      placeholder="Username"
      autocomplete="username"
      autocapitalize="off"
      autocorrect="off"
      spellcheck="false"
      class="mb-3 block w-full rounded-xl border border-neutral-800 bg-neutral-900 px-3 py-2 text-base focus:border-neutral-600 focus:outline-none"
      data-testid="login-username"
    />
    <input
      type="password"
      bind:value={password}
      placeholder="Password"
      autocomplete="current-password"
      class="mb-3 block w-full rounded-xl border border-neutral-800 bg-neutral-900 px-3 py-2 text-base focus:border-neutral-600 focus:outline-none"
      data-testid="login-input"
    />
    {#if error}
      <div class="mb-3 rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-300">{error}</div>
    {/if}
    <button
      type="submit"
      class="block w-full rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:bg-neutral-700"
      disabled={pending || !username || !password}
      data-testid="login-btn"
    >
      {pending ? 'Signing in…' : 'Sign in'}
    </button>
  </form>
</div>
