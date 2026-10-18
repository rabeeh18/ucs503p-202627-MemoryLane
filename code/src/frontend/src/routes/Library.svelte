<script>
  import { onDestroy } from 'svelte';
  import Header from '../components/Header.svelte';
  import PageRow from '../components/PageRow.svelte';
  import EmptyState from '../components/EmptyState.svelte';
  import { listMemories } from '../api.js';
  import { libraryVersion } from '../stores';
  import { hiddenPageIds, pageDeletes } from '../pageDeletes.js';
  import { link } from '../lib/router.js';

  const PAGE_SIZE = 20;

  let pages = [];
  let total = 0;
  let loading = false;
  let loaded = false;
  let error = '';
  let controller;

  async function load(reset) {
    controller?.abort();
    controller = new AbortController();
    const mine = controller;
    loading = true;
    error = '';
    try {
      // Pages already deleted on the server no longer count towards the offset.
      const deleted = pages.filter((p) => $hiddenPageIds.has(p.id) && !pageDeletes.isPending(p.id)).length;
      const data = await listMemories(PAGE_SIZE, reset ? 0 : pages.length - deleted, mine.signal);
      if (!reset) data.pages = data.pages.filter((p) => !pages.some((q) => q.id === p.id));
      if (mine !== controller) return;
      pages = reset ? data.pages : [...pages, ...data.pages];
      total = data.total;
      loaded = true;
    } catch (err) {
      if (mine !== controller || err?.name === 'CancelledError' || err?.status === 401) return;
      error = "Couldn't load your saved pages.";
    } finally {
      if (mine === controller) loading = false;
    }
  }

  $: $libraryVersion, load(true);
  $: visible = pages.filter((page) => !$hiddenPageIds.has(page.id));
  $: shownTotal = Math.max(0, total - (pages.length - visible.length));
  onDestroy(() => controller?.abort());
</script>

<Header />

<main class="library">
  <h1>All saved pages {#if loaded}<span class="total mono">{shownTotal}</span>{/if}</h1>

  {#if loaded && shownTotal === 0}
    <EmptyState>
      Nothing saved yet. <a href="/extension" use:link>Install the extension</a> and press
      <strong>Remember this page</strong> on anything worth keeping.
    </EmptyState>
  {:else}
    <ul>
      {#each visible as page (page.id)}
        <PageRow {page} />
      {/each}
    </ul>
  {/if}

  {#if error}
    <p class="state">{error} <button type="button" class="link-button" on:click={() => load(pages.length === 0)}>Try again</button></p>
  {:else if loading}
    <p class="state">Loading…</p>
  {:else if pages.length < total}
    <div class="more">
      <button type="button" class="btn btn-outline" on:click={() => load(false)}>Load more</button>
    </div>
  {/if}
</main>

<style>
  .library {
    flex: 1;
    width: 100%;
    max-width: 800px;
    margin: 0 auto;
    padding: 40px 32px 48px;
  }

  h1 {
    margin: 0 0 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--divider);
    font-size: 22px;
    font-weight: 500;
    display: flex;
    align-items: baseline;
    gap: 12px;
  }

  .total {
    font-size: 13px;
    font-weight: 400;
    color: var(--text-3);
  }

  ul {
    margin: 0;
    padding: 0;
  }

  .state {
    margin: 20px 0 0;
    font-size: 14px;
    color: var(--text-2);
  }

  .more {
    margin-top: 24px;
    display: flex;
    justify-content: center;
  }

  @media (max-width: 640px) {
    .library {
      padding: 24px 16px 32px;
    }
  }
</style>
