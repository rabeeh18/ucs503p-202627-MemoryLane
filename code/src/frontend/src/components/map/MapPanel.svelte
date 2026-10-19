<script>
  // Right-hand panel of the map: the selected page (actions, topic, related
  // pages), the selected topic (its pages), or a hint when nothing is selected.
  import { createEventDispatcher, onDestroy } from 'svelte';
  import ScrollPill from '../ScrollPill.svelte';
  import { fetchSummary, getRelated } from '../../api.js';
  import { link } from '../../lib/router.js';
  import { relativeTime } from '../../lib/time.js';

  /** { mode, pageId, topicId } */
  export let panel;
  /** The map data (topics, pages) */
  export let data;
  /** Bottom-sheet presentation on narrow screens */
  export let sheet = false;

  const dispatch = createEventDispatcher();
  let scroller;

  $: pagesById = new Map(data.pages.map((p) => [p.id, p]));
  $: topicsById = new Map(data.topics.map((t) => [t.id, t]));
  $: page = panel.mode === 'page' ? pagesById.get(panel.pageId) : null;
  $: topic = panel.topicId ? topicsById.get(panel.topicId) : null;
  $: topicPages = panel.mode === 'topic' && topic ? data.pages.filter((p) => p.topic === topic.id) : [];

  const searchWithin = (id) => `/search?topic=${encodeURIComponent(id)}&q=`;

  function saved(at) {
    const when = relativeTime(at);
    if (!when) return '';
    return `saved ${/^[A-Z][a-z]+$/.test(when) ? when.toLowerCase() : when.charAt(0).toLowerCase() + when.slice(1)}`;
  }

  // ---- related pages -------------------------------------------------------------
  let related = { pageId: null, loading: false, items: [], error: '' };
  let relatedController;

  async function loadRelated(id) {
    relatedController?.abort();
    if (!id) {
      related = { pageId: null, loading: false, items: [], error: '' };
      return;
    }
    relatedController = new AbortController();
    const mine = relatedController;
    related = { pageId: id, loading: true, items: [], error: '' };
    try {
      const res = await getRelated(id, 5, mine.signal);
      if (mine === relatedController) related = { pageId: id, loading: false, items: res.related, error: '' };
    } catch (err) {
      if (mine !== relatedController || err?.name === 'CancelledError' || err?.status === 401) return;
      related = { pageId: id, loading: false, items: [], error: "Couldn't load related pages." };
    }
  }

  $: loadRelated(page?.id || null);

  // ---- summary --------------------------------------------------------------------
  let summary = { pageId: null, open: false, loading: false, text: '', error: '' };

  $: if (page && summary.pageId !== page.id) summary = { pageId: page.id, open: false, loading: false, text: '', error: '' };

  async function toggleSummary() {
    if (summary.open) {
      summary = { ...summary, open: false };
      return;
    }
    if (summary.text) {
      summary = { ...summary, open: true };
      return;
    }
    const id = page.id;
    summary = { pageId: id, open: true, loading: true, text: '', error: '' };
    try {
      const res = await fetchSummary({ query: page.title, id });
      if (summary.pageId === id) {
        summary = { ...summary, loading: false, text: res.summary || '', error: res.summary ? '' : 'No summary was returned.' };
      }
    } catch (err) {
      if (summary.pageId !== id) return;
      const error = err?.status === 503
        ? "Summaries aren't available right now."
        : err?.status === 429
          ? "You're summarising very fast. Wait a moment and try again."
          : "Couldn't summarise this page. Try again.";
      summary = { ...summary, loading: false, error };
    }
  }

  onDestroy(() => relatedController?.abort());
</script>

<aside class="panel" class:sheet aria-label="Selection details">
  <div class="scroll" bind:this={scroller}>
    <div class="inner">
      {#if sheet && panel.mode !== 'none'}
        <button type="button" class="close" aria-label="Close details" on:click={() => dispatch('close')}>×</button>
      {/if}
      {#if page}
        <p class="eyebrow mono">Selected page</p>
        <h2 class="title">{page.title}</h2>
        <p class="meta">{page.domain}{page.domain && saved(page.saved_at) ? ' · ' : ''}{saved(page.saved_at)}</p>
        <div class="actions">
          <a class="btn btn-primary" href={page.url} target="_blank" rel="noopener noreferrer">Open page</a>
          <button type="button" class="btn btn-outline" aria-expanded={summary.open} on:click={toggleSummary}>
            {summary.open ? 'Hide summary' : 'Summarise'}
          </button>
        </div>
        {#if summary.open}
          <div class="summary" aria-live="polite">
            {#if summary.loading}
              <p class="muted">Summarising…</p>
            {:else if summary.error}
              <p class="muted">{summary.error}</p>
            {:else}
              <p>{summary.text}</p>
            {/if}
          </div>
        {/if}

        <div class="divider"></div>
        <div class="topic-row">
          {#if topic}
            <span>Topic: {topic.label}</span>
            <a href={searchWithin(topic.id)} use:link>Search within</a>
          {:else}
            <span class="muted">Not in a topic</span>
          {/if}
        </div>

        <p class="eyebrow mono related-label">Related pages</p>
        {#if related.loading}
          <p class="muted small">Finding related pages…</p>
        {:else if related.error}
          <p class="muted small">{related.error}
            <button type="button" class="link-button" on:click={() => loadRelated(page.id)}>Try again</button>
          </p>
        {:else if !related.items.length}
          <p class="muted small">No closely related pages yet.</p>
        {:else}
          <ul class="rows">
            {#each related.items as r (r.id)}
              <li>
                <button type="button" class="row" on:click={() => dispatch('selectPage', r.id)}>
                  <span class="row-title">{r.title}</span>
                  <span class="row-domain">{r.domain}</span>
                  <span class="bar" aria-label="{Math.round(r.similarity * 100)}% similar">
                    <span class="fill" style="width: {Math.max(0, Math.min(1, r.similarity)) * 100}%"></span>
                  </span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      {:else if topic}
        <p class="eyebrow mono">Topic</p>
        <h2 class="title">{topic.label}</h2>
        <p class="meta">{topic.count} page{topic.count === 1 ? '' : 's'}</p>
        <div class="topic-row first">
          <span class="muted">Search only these pages</span>
          <a href={searchWithin(topic.id)} use:link>Search within</a>
        </div>
        <ul class="rows compact">
          {#each topicPages as p (p.id)}
            <li>
              <button type="button" class="row" on:click={() => dispatch('selectPage', p.id)}>
                <span class="row-title">{p.title}</span>
                <span class="row-domain">{p.domain}</span>
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="empty muted">Select a page or topic</p>
      {/if}
    </div>
  </div>
</aside>
<ScrollPill target={scroller} />

<style>
  .panel {
    width: 460px;
    flex: none;
    min-height: 0;
    border-left: 1px solid var(--divider);
    display: flex;
    flex-direction: column;
  }

  .scroll {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    scrollbar-width: none;
  }

  .scroll::-webkit-scrollbar {
    display: none;
  }

  .inner {
    padding: 32px 36px 40px;
  }

  .eyebrow {
    margin: 0;
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-3);
  }

  .title {
    margin: 10px 0 0;
    font-size: 22px;
    font-weight: 500;
    line-height: 1.3;
    overflow-wrap: anywhere;
  }

  .meta {
    margin: 8px 0 0;
    font-size: 14px;
    color: var(--text-2);
  }

  .actions {
    display: flex;
    gap: 10px;
    margin-top: 22px;
  }

  .actions .btn {
    height: 44px;
  }

  .summary {
    margin-top: 16px;
    font-size: 14px;
    line-height: 1.6;
  }

  .summary p {
    margin: 0;
  }

  .divider {
    height: 1px;
    margin: 28px 0 18px;
    background: var(--divider-soft);
  }

  .topic-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    font-size: 14px;
    color: var(--text-2);
  }

  .topic-row.first {
    margin-top: 20px;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--divider-soft);
  }

  .topic-row a {
    flex: none;
  }

  .related-label {
    margin-top: 28px;
  }

  .rows {
    margin: 10px 0 0;
    padding: 0;
    list-style: none;
  }

  .rows li + li {
    border-top: 1px solid var(--divider-soft);
  }

  .row {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 100%;
    padding: 14px 0;
    border: 0;
    background: none;
    text-align: left;
  }

  .compact .row {
    padding: 10px 0;
  }

  .row:hover .row-title {
    text-decoration: underline;
    text-underline-offset: 3px;
    text-decoration-color: var(--text-3);
  }

  .row-title {
    font-size: 15px;
    line-height: 1.4;
    color: var(--text);
  }

  .compact .row-title {
    font-size: 14px;
  }

  .row-domain {
    font-size: 13px;
    color: var(--text-3);
  }

  .bar {
    display: block;
    height: 2px;
    margin-top: 10px;
    background: var(--border);
  }

  .fill {
    display: block;
    height: 100%;
    background: var(--text-3);
  }

  .muted {
    color: var(--text-3);
  }

  .small {
    margin: 10px 0 0;
    font-size: 13px;
  }

  .empty {
    margin: 0;
    font-size: 14px;
  }

  /* Narrow screens: a bottom sheet over the map. */
  .panel.sheet {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 30;
    width: auto;
    max-height: 50vh;
    border-left: 0;
    border-top: 1px solid var(--border-strong);
    border-radius: var(--radius) var(--radius) 0 0;
    background: var(--bg);
    box-shadow: 0 -12px 32px rgba(0, 0, 0, 0.45);
  }

  .close {
    float: right;
    width: 36px;
    height: 36px;
    margin: -6px -6px 0 8px;
    border: 1px solid var(--border);
    border-radius: 50%;
    background: transparent;
    color: var(--text-2);
    font-size: 18px;
    line-height: 1;
  }

  .close:hover {
    color: var(--text);
  }

  .panel.sheet .inner {
    padding: 20px 16px 28px;
  }
</style>
