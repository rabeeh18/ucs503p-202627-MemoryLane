<script>
  import AccountMenu from './AccountMenu.svelte';
  import { signIn } from '../auth.js';
  import { extensionInstalled } from '../lib/extension.js';
  import { link, route } from '../lib/router.js';

  /** true on signed-out screens: shows a Sign in link instead of the account menu. */
  export let signedOut = false;

  $: path = $route.path.replace(/\/+$/, '') || '/';
  $: active = path === '/map' ? 'map' : path === '/' || path === '/search' ? 'search' : null;
</script>

<header class="header">
  <div class="left">
    <a class="wordmark" href="/" use:link>MemoryLane</a>
    {#if !signedOut}
      <nav class="nav" aria-label="Main">
        <a href="/" use:link class:active={active === 'search'} aria-current={active === 'search' ? 'page' : undefined}>Search</a>
        <a href="/map" use:link class:active={active === 'map'} aria-current={active === 'map' ? 'page' : undefined}>Map</a>
      </nav>
    {/if}
  </div>
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

  .left {
    display: flex;
    align-items: center;
    gap: 36px;
    min-width: 0;
  }

  .wordmark {
    color: var(--text);
    font-size: 15px;
    font-weight: 500;
    letter-spacing: 0.02em;
  }

  .nav {
    display: flex;
    gap: 24px;
  }

  .nav a {
    position: relative;
    padding: 6px 0;
    font-size: 14px;
    color: var(--text-2);
  }

  .nav a:hover {
    color: var(--text);
  }

  .nav a.active {
    color: var(--text);
  }

  .nav a.active::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: -2px;
    height: 1px;
    background: var(--text);
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

    .left {
      gap: 20px;
    }

    .nav {
      gap: 16px;
    }

    .right {
      gap: 14px;
    }

    .get-extension {
      display: none;
    }
  }
</style>
