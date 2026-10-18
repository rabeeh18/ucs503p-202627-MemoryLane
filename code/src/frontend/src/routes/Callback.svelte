<script>
  import { onMount } from 'svelte';
  import { handleCallback, signIn } from '../auth.js';
  import { navigate } from '../lib/router.js';

  let failed = false;

  onMount(async () => {
    try {
      await handleCallback();
      navigate('/', { replace: true });
    } catch {
      failed = true;
    }
  });
</script>

<main class="callback">
  {#if failed}
    <p>Sign-in didn't complete.</p>
    <button type="button" class="btn btn-primary" on:click={() => signIn({})}>Try again</button>
  {:else}
    <p role="status">Signing you in…</p>
  {/if}
</main>

<style>
  .callback {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 20px;
    padding: 32px 16px;
  }

  p {
    margin: 0;
    color: var(--text-2);
    font-size: 15px;
  }
</style>
