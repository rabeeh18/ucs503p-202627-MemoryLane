<script>
  import AccountMenu from './AccountMenu.svelte';
  import { signIn } from '../auth.js';
  import { extensionInstalled } from '../lib/extension.js';
  import { link } from '../lib/router.js';

  /** true on signed-out screens: shows a Sign in link instead of the account menu. */
  export let signedOut = false;
</script>

<header class="header">
  <a class="wordmark" href="/" use:link>MemoryLane</a>
  {#if signedOut}
    <button type="button" class="sign-in" on:click={() => signIn({})}>Sign in</button>
  {:else}
    <div class="right">
      {#if !$extensionInstalled}
        <a class="get-extension" href="/extension" use:link>Get the extension</a>
      {/if}
      <AccountMenu />
    </div>
  {/if}
</header>

<style>
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 68px;
    padding: 16px 32px;
  }

  .wordmark {
    color: var(--text);
    font-size: 15px;
    font-weight: 500;
    letter-spacing: 0.02em;
  }

  .right {
    display: flex;
    align-items: center;
    gap: 20px;
  }

  .get-extension {
    font-size: 13px;
  }

  .sign-in {
    min-height: 44px;
    padding: 0 4px;
    border: 0;
    background: none;
    color: var(--text-2);
    font-size: 13px;
  }

  .sign-in:hover {
    color: var(--text);
  }

  @media (max-width: 640px) {
    .header {
      padding: 12px 16px;
    }

    .right {
      gap: 14px;
    }
  }
</style>
