<script>
  import { onDestroy, onMount } from 'svelte';
  import Header from '../components/Header.svelte';
  import SearchBar from '../components/SearchBar.svelte';
  import PageRow from '../components/PageRow.svelte';
  import EmptyState from '../components/EmptyState.svelte';
  import { listMemories } from '../api.js';
  import { link, navigate } from '../lib/router.js';
  import { libraryVersion, recentError, recentPages, searchQuery } from '../stores';
  import { hiddenPageIds } from '../pageDeletes.js';

  let searchBar;
  let controller;

  async function loadRecent() {
    controller?.abort();
    controller = new AbortController();
    const mine = controller;
    recentError.set(null);
    try {
      const data = await listMemories(5, 0, mine.signal);
      if (mine === controller) recentPages.set(data.pages);
    } catch (err) {
      if (err?.name === 'CancelledError' || err?.status === 401 || mine !== controller) return;
      recentError.set("Couldn't load your recent pages.");
    }
  }

  onMount(() => {
    searchQuery.set('');
  });

  onDestroy(() => controller?.abort());

  // Reload on mount and whenever the library changes (e.g. after "Delete all").
  $: $libraryVersion, loadRecent();

  $: visibleRecent = ($recentPages || []).filter((page) => !$hiddenPageIds.has(page.id));

  function onSubmit(event) {
    navigate(`/?q=${encodeURIComponent(event.detail)}`);
  }

  function isTyping(target) {
    return target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
  }

  function onKeydown(event) {
    if (event.key === '/' && !isTyping(event.target) && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      searchBar?.focus();
    }
  }
</script>

<svelte:window on:keydown={onKeydown} />

<Header />

<main class="home">
  <h1>What are you trying to remember?</h1>
  <SearchBar bind:this={searchBar} kbdHint="/" autofocus on:submit={onSubmit} on:clear={() => searchQuery.set('')} />
  <p class="helper">Describe it in your own words. No exact title needed.</p>

  <section class="recent" aria-labelledby="recent-heading">
    {#if $recentError}
      <p class="error">{$recentError} <button type="button" class="link-button" on:click={loadRecent}>Try again</button></p>
    {:else if $recentPages && visibleRecent.length === 0}
      <EmptyState>
        Nothing saved yet. <a href="/extension" use:link>Install the extension</a> and press
        <strong>Remember this page</strong> on anything worth keeping.
      </EmptyState>
    {:else if $recentPages}
      <div class="section-head">
        <h2 id="recent-heading">Recently saved</h2>
        <a href="/library" use:link>View all</a>
      </div>
      <ul>
        {#each visibleRecent as page (page.id)}
          <PageRow {page} />
        {/each}
      </ul>
    {/if}
  </section>
</main>

<style>
  .home {
    flex: 1;
    width: 100%;
    max-width: 864px;
    margin: 0 auto;
    padding: 96px 32px 48px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  h1 {
    margin: 0 0 28px;
    font-size: 34px;
    font-weight: 500;
    line-height: 1.2;
    letter-spacing: -0.01em;
    text-align: center;
  }

  .helper {
    margin: 16px 0 0;
    font-size: 13px;
    color: var(--text-2);
    text-align: center;
  }

  .recent {
    width: 100%;
    margin-top: 72px;
  }

  .section-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--divider);
  }

  h2 {
    margin: 0;
    font-size: 12px;
    font-weight: 400;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-3);
  }

  .section-head a {
    font-size: 13px;
  }

  ul {
    margin: 0;
    padding: 0;
  }

  .error {
    font-size: 14px;
    color: var(--text-2);
  }

  :global(.home .recent strong) {
    font-weight: 500;
    color: var(--text);
  }

  @media (max-width: 640px) {
    .home {
      padding: 48px 16px 32px;
    }

    h1 {
      font-size: 26px;
    }

    .recent {
      margin-top: 48px;
    }
  }
</style>
