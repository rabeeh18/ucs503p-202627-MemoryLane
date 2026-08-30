<script lang="ts">
  import SearchBar from './components/SearchBar.svelte';
  import ResultList from './components/ResultList.svelte';
  import { searchQuery, results, isLoading, searchPerformed, error } from './stores';
  import { search } from './api.js';

  let activeController: AbortController | null = null;

  async function runSearch(query: string) {
    // Cancel any in-flight request before starting a new one.
    if (activeController) {
      activeController.abort();
    }
    const controller = new AbortController();
    activeController = controller;

    isLoading.set(true);
    searchPerformed.set(true);
    error.set(null);

    try {
      const data = await search(query, controller.signal);
      if (activeController !== controller) return; // superseded by a newer search
      results.set(data.webpages ?? []);
    } catch (err: any) {
      if (activeController !== controller) return;
      if (err?.name === 'CancelledError') {
        // A newer search superseded this one — nothing to show for it.
        return;
      }
      if (err?.name === 'TimeoutError') {
        error.set('Search took too long. Please try again.');
      } else if (err?.status && err.status >= 500) {
        error.set('Server error. Please try again later.');
      } else if (err?.status) {
        error.set('Something went wrong. Please try again.');
      } else {
        error.set('Network error. Please check your connection and try again.');
      }
      results.set([]);
    } finally {
      if (activeController === controller) {
        isLoading.set(false);
      }
    }
  }

  function handleSubmit(event: CustomEvent<string>) {
    runSearch(event.detail);
  }

  function handleClear() {
    if (activeController) {
      activeController.abort();
      activeController = null;
    }
    searchQuery.set('');
    results.set([]);
    searchPerformed.set(false);
    error.set(null);
    isLoading.set(false);
  }
</script>

<main class="page">
  <div class="search-shell" class:sticky={$searchPerformed}>
    <SearchBar sticky={$searchPerformed} on:submit={handleSubmit} on:clear={handleClear} />
  </div>

  {#if $searchPerformed}
    <div class="results-shell">
      <ResultList results={$results} isLoading={$isLoading} error={$error} />
    </div>
  {/if}
</main>

<style>
  :global(html, body) {
    margin: 0;
    padding: 0;
    background: #1a1a1a;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }

  :global(*) {
    box-sizing: border-box;
  }

  .page {
    min-height: 100vh;
    background: #1a1a1a;
    position: relative;
  }

  .search-shell {
    width: 60%;
    min-width: 300px;
    max-width: 800px;
    margin: 35vh auto 0;
    transition: margin 300ms ease-out, width 300ms ease-out, max-width 300ms ease-out;
  }

  .search-shell.sticky {
    position: sticky;
    top: 40px;
    margin: 0 auto;
    width: 100%;
    max-width: 900px;
    padding: 12px 20px 0;
    z-index: 10;
  }

  .results-shell {
    padding-top: 60px;
    padding-bottom: 60px;
  }

  @media (max-width: 640px) {
    .search-shell:not(.sticky) {
      width: calc(100% - 40px);
    }
    .search-shell.sticky {
      padding-left: 20px;
      padding-right: 20px;
    }
  }
</style>
