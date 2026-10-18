<script>
  import { createEventDispatcher } from 'svelte';
  import LetterTile from './LetterTile.svelte';
  import { highlight } from '../lib/highlight.js';
  import { relativeTime } from '../lib/time.js';

  /** @type {{ id: string, url: string, title: string, domain: string, timestamp: string, snippet: string | null }} */
  export let result;
  export let query = '';
  export let selected = false;
  /** @type {{ open: boolean, loading: boolean, text: string, error: string }} */
  export let summary = { open: false, loading: false, text: '', error: '' };

  const dispatch = createEventDispatcher();
  let titleLink;

  export function focusTitle() {
    titleLink?.focus();
  }

  $: parts = highlight(result.snippet || '', query);
  $: summaryId = `summary-${result.id}`;
</script>

<!-- svelte-ignore a11y-no-noninteractive-element-interactions a11y-mouse-events-have-key-events -->
<article
  class="result"
  class:selected
  on:mouseenter={() => dispatch('select')}
  on:focusin={() => dispatch('select')}
>
  <div class="body">
    <div class="meta">
      <LetterTile domain={result.domain} size={20} />
      <span class="domain">{result.domain}</span>
      <span aria-hidden="true">·</span>
      <span class="mono when">{relativeTime(result.timestamp)}</span>
    </div>
    <h2 class="title">
      <a bind:this={titleLink} href={result.url} target="_blank" rel="noopener noreferrer">
        {result.title || result.url}
      </a>
    </h2>
    {#if parts.length}
      <p class="snippet">
        {#each parts as part}{#if part.match}<strong>{part.text}</strong>{:else}{part.text}{/if}{/each}
      </p>
    {/if}

    {#if summary.open}
      <div class="summary" id={summaryId} aria-live="polite">
        {#if summary.loading}
          <p class="summary-text muted">Summarising…</p>
        {:else if summary.error}
          <p class="summary-text muted">{summary.error}</p>
        {:else}
          <p class="summary-text">{summary.text}</p>
        {/if}
        <button type="button" class="link-button hide" on:click={() => dispatch('summary')}>Hide</button>
      </div>
    {/if}
  </div>

  {#if selected && !summary.open}
    <button
      type="button"
      class="btn btn-small btn-outline summarise"
      aria-controls={summaryId}
      aria-expanded="false"
      on:click={() => dispatch('summary')}
    >
      Summarise
    </button>
  {/if}
</article>

<style>
  .result {
    display: flex;
    gap: 16px;
    align-items: flex-start;
    padding: 16px;
    border: 1px solid transparent;
    border-radius: var(--radius);
  }

  .result.selected {
    background: var(--surface);
    border-color: var(--border-strong);
  }

  .body {
    flex: 1;
    min-width: 0;
  }

  .meta {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-3);
    min-width: 0;
  }

  .domain {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .when {
    flex: none;
    font-size: 12px;
  }

  .title {
    margin: 8px 0 0;
    font-size: 17px;
    font-weight: 500;
    line-height: 1.35;
  }

  .title a {
    color: var(--text);
  }

  .title a:hover {
    text-decoration: underline;
    text-underline-offset: 3px;
    text-decoration-color: var(--text-3);
  }

  .snippet {
    margin: 6px 0 0;
    font-size: 14px;
    line-height: 1.55;
    color: var(--text-2);
    overflow-wrap: anywhere;
  }

  .snippet strong {
    font-weight: 600;
    color: var(--text);
  }

  .summary {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--divider);
  }

  .summary-text {
    margin: 0;
    font-size: 14px;
    line-height: 1.6;
    color: var(--text);
    white-space: pre-line;
  }

  .summary-text.muted {
    color: var(--text-2);
  }

  .hide {
    margin-top: 8px;
    font-size: 13px;
  }

  .summarise {
    flex: none;
  }

  @media (max-width: 640px) {
    .result {
      flex-direction: column;
      gap: 12px;
      padding: 14px 12px;
    }
  }
</style>
