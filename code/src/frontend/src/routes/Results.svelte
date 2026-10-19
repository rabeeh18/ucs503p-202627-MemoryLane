<script>
  import { onDestroy, tick } from 'svelte';
  import Header from '../components/Header.svelte';
  import SearchBar from '../components/SearchBar.svelte';
  import ResultRow from '../components/ResultRow.svelte';
  import Kbd from '../components/Kbd.svelte';
  import { fetchSummary, search } from '../api.js';
  import { navigate } from '../lib/router.js';
  import { results, resultsError, resultsLoading, searchQuery } from '../stores';
  import { hiddenPageIds, pageDeletes } from '../pageDeletes.js';
  import { loadMap, topicById } from '../mapStore.js';

  /** The query from ?q= in the URL. */
  export let query = '';
  /** Optional map topic id from ?topic=: search only that topic's pages. */
  export let topic = '';

  let topicLabel = '';
  let topicGone = false;

  /** URL for a query, keeping the topic filter when there is one. */
  function searchUrl(q, t = topic) {
    const params = new URLSearchParams();
    if (t) params.set('topic', t);
    params.set('q', q);
    return t ? `/search?${params}` : (q ? `/?q=${encodeURIComponent(q)}` : '/');
  }

  async function resolveTopicLabel(t) {
    topicLabel = topicById(t)?.label || '';
    if (t && !topicLabel) {
      try {
        await loadMap();
        topicLabel = topicById(t)?.label || '';
      } catch {
        /* label stays empty; the chip says "in this topic" */
      }
    }
  }

  $: if (topic) resolveTopicLabel(topic);
  $: if (!topic) topicLabel = '';

  /** The map changed under us (409): find the same topic by name and retry once. */
  async function recoverTopic(q) {
    const label = topicLabel;
    try {
      const map = await loadMap({ force: true });
      const same = label && map?.topics?.find((t) => t.label === label);
      if (same) {
        navigate(searchUrl(q, same.id), { replace: true });
        return true;
      }
    } catch {
      /* fall through */
    }
    topicGone = true;
    navigate(searchUrl(q, ''), { replace: true });
    return false;
  }

  let searchBar;
  let rows = [];
  let selected = 0;
  let controller;
  const CLOSED = { open: false, loading: false, text: '', error: '' };
  /** Per-result summary state, keyed by page id. */
  let summaries = {};

  async function run(q, t) {
    controller?.abort();
    if (!q) {
      // /search?topic=…&q= with nothing typed yet: wait for a query.
      searchQuery.set('');
      results.set([]);
      resultsError.set(null);
      resultsLoading.set(false);
      return;
    }
    controller = new AbortController();
    const mine = controller;
    searchQuery.set(q);
    resultsLoading.set(true);
    resultsError.set(null);
    summaries = {};
    selected = 0;
    try {
      const data = await search(q, mine.signal, { topic: t || null });
      if (mine !== controller) return;
      results.set(data.results);
    } catch (err) {
      if (mine !== controller || err?.name === 'CancelledError' || err?.status === 401) return;
      if (err?.status === 409 && t) {
        await recoverTopic(q);
        return;
      }
      results.set([]);
      resultsError.set({ message: err?.message || 'Search failed', status: err?.status || 0 });
    } finally {
      if (mine === controller) resultsLoading.set(false);
    }
  }

  $: run(query, topic);
  $: if (topic) topicGone = false;
  onDestroy(() => controller?.abort());

  function onSubmit(event) {
    if (event.detail === query) run(query, topic);
    else navigate(searchUrl(event.detail));
  }

  function clear() {
    searchQuery.set('');
    navigate('/');
  }

  async function toggleSummary(result) {
    const current = summaries[result.id];
    if (current?.open) {
      summaries = { ...summaries, [result.id]: { ...current, open: false } };
      return;
    }
    if (current?.text) {
      summaries = { ...summaries, [result.id]: { ...current, open: true } };
      return;
    }
    summaries = { ...summaries, [result.id]: { open: true, loading: true, text: '', error: '' } };
    let next;
    try {
      const data = await fetchSummary({ query, id: result.id });
      next = { open: true, loading: false, text: data.summary || '', error: data.summary ? '' : 'No summary was returned.' };
    } catch (err) {
      const error = err?.status === 503
        ? "Summaries aren't available right now."
        : err?.status === 429
          ? "You're summarising very fast. Wait a moment and try again."
          : "Couldn't summarise this page. Try again.";
      next = { open: true, loading: false, text: '', error };
    }
    if (summaries[result.id]?.open) summaries = { ...summaries, [result.id]: next };
  }

  function isTyping(target) {
    return target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
  }

  $: visible = $results.filter((result) => !$hiddenPageIds.has(result.id));
  $: if (selected > 0 && selected >= visible.length) selected = Math.max(0, visible.length - 1);

  async function deleteResult(index) {
    const result = visible[index];
    if (!result) return;
    pageDeletes.schedule(result.id);
    await tick();
    rows[Math.min(index, visible.length - 1)]?.focusTitle();
  }

  async function move(delta) {
    if (!visible.length) return;
    selected = Math.max(0, Math.min(visible.length - 1, selected + delta));
    await tick();
    rows[selected]?.focusTitle();
  }

  function onKeydown(event) {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const typing = isTyping(event.target);
    if (event.key === '/' && !typing) {
      event.preventDefault();
      searchBar?.focus();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      move(typing ? 0 : 1);
    } else if (event.key === 'ArrowUp' && !typing) {
      event.preventDefault();
      move(-1);
    } else if (event.key === 'Delete' && event.shiftKey && !typing) {
      event.preventDefault();
      deleteResult(selected);
    } else if (event.key === 'Enter' && !typing) {
      const result = visible[selected];
      if (result && !(event.target instanceof HTMLButtonElement)) {
        event.preventDefault();
        window.open(result.url, '_blank', 'noopener');
      }
    } else if (event.key === 's' && !typing) {
      const result = visible[selected];
      if (result) {
        event.preventDefault();
        toggleSummary(result);
      }
    } else if (event.key === 'Escape' && !typing && !document.querySelector('dialog[open]')) {
      clear();
    }
  }

  $: count = visible.length;
</script>

<svelte:window on:keydown={onKeydown} />

<Header />

<main class="results">
  <h1 class="visually-hidden">Search results</h1>
  <SearchBar bind:this={searchBar} kbdHint="Esc" autofocus={!query} on:submit={onSubmit} on:clear={clear} />
  {#if topic}
    <div class="scope">
      <span class="chip">
        in {topicLabel || 'this topic'}
        <button type="button" aria-label="Search all pages instead" on:click={() => navigate(searchUrl(query, ''))}>×</button>
      </span>
    </div>
  {:else if topicGone}
    <p class="state">That topic changed after your library was updated, so this searches all pages.</p>
  {/if}

  {#if $resultsLoading}
    <div class="skeletons" aria-busy="true" aria-label="Loading results">
      {#each [0, 1, 2] as _}
        <div class="skeleton">
          <span class="bar meta-bar"></span>
          <span class="bar title-bar"></span>
          <span class="bar text-bar"></span>
        </div>
      {/each}
    </div>
  {:else if $resultsError}
    <p class="state">
      {#if $resultsError.status === 429}
        You're searching very fast. Wait a moment and try again.
      {:else}
        Something went wrong while searching.
      {/if}
      <button type="button" class="link-button" on:click={() => run(query, topic)}>Try again</button>
    </p>
  {:else if !query}
    <p class="state">Type what you're looking for{topicLabel ? ` in ${topicLabel}` : ''}.</p>
  {:else if count === 0}
    <p class="state">No matches. Try describing the idea instead of exact words.</p>
  {:else}
    <p class="count" role="status">{count} result{count === 1 ? '' : 's'}</p>
    <div class="list">
      {#each visible as result, i (result.id)}
        <ResultRow
          bind:this={rows[i]}
          {result}
          {query}
          selected={i === selected}
          summary={summaries[result.id] || CLOSED}
          on:select={() => (selected = i)}
          on:summary={() => toggleSummary(result)}
          on:delete={() => deleteResult(i)}
        />
      {/each}
    </div>
  {/if}
</main>

<footer class="keys">
  <span><Kbd>↑ ↓</Kbd> navigate</span>
  <span><Kbd>Enter</Kbd> open</span>
  <span><Kbd>/</Kbd> search</span>
  <span><Kbd>Shift Del</Kbd> delete</span>
  <span><Kbd>Esc</Kbd> clear</span>
</footer>

<style>
  .results {
    flex: 1;
    width: 100%;
    max-width: 800px;
    margin: 0 auto;
    padding: 40px 32px 24px;
  }

  .scope {
    margin-top: 12px;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    height: 30px;
    padding: 0 4px 0 12px;
    border: 1px solid var(--border-strong);
    border-radius: 999px;
    background: var(--surface);
    font-size: 13px;
    color: var(--text);
  }

  .chip button {
    width: 24px;
    height: 24px;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: var(--text-2);
    font-size: 16px;
    line-height: 1;
  }

  .chip button:hover {
    background: var(--surface-active);
    color: var(--text);
  }

  .count {
    margin: 28px 0 12px;
    font-size: 13px;
    color: var(--text-3);
  }

  .list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .state {
    margin: 28px 0 0;
    font-size: 14px;
    color: var(--text-2);
  }

  .skeletons {
    margin-top: 52px;
    display: flex;
    flex-direction: column;
    gap: 28px;
  }

  .skeleton {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 0 16px;
  }

  .bar {
    display: block;
    height: 12px;
    border-radius: var(--radius-xs);
    background: var(--surface);
  }

  .meta-bar { width: 30%; }
  .title-bar { width: 65%; height: 16px; }
  .text-bar { width: 90%; }

  .keys {
    display: flex;
    justify-content: center;
    gap: 24px;
    padding: 16px 32px;
    border-top: 1px solid var(--divider-soft);
    font-size: 12px;
    color: var(--text-3);
  }

  .keys span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  @media (max-width: 640px) {
    .results {
      padding: 24px 16px;
    }

    .keys {
      display: none;
    }
  }
</style>
