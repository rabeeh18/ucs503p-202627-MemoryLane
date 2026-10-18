<script>
  import { createEventDispatcher, tick } from 'svelte';
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
  let moreButton;
  let menu;
  let menuOpen = false;

  $: if (!selected) menuOpen = false;

  async function toggleMenu() {
    menuOpen = !menuOpen;
    if (menuOpen) {
      await tick();
      menu?.querySelector('[role="menuitem"]')?.focus();
    }
  }

  function closeMenu(restoreFocus = true) {
    menuOpen = false;
    if (restoreFocus) moreButton?.focus();
  }

  function onMenuKeydown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeMenu();
    } else if (event.key === 'Tab') {
      closeMenu(false);
    }
  }

  function onWindowClick(event) {
    if (menuOpen && !menu?.contains(event.target) && !moreButton?.contains(event.target)) closeMenu(false);
  }

  function deleteFromLibrary() {
    closeMenu(false);
    dispatch('delete');
  }

  export function focusTitle() {
    titleLink?.focus();
  }

  $: parts = highlight(result.snippet || '', query);
  $: summaryId = `summary-${result.id}`;
</script>

<svelte:window on:click={onWindowClick} />

<!-- svelte-ignore a11y-no-noninteractive-element-interactions a11y-mouse-events-have-key-events -->
<article
  class="result"
  class:selected
  on:mouseenter={() => dispatch('select')}
  on:focusin={() => dispatch('select')}
>
  <div class="body">
    <div class="meta">
      <LetterTile domain={result.domain || result.url} size={20} />
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

  {#if selected}
    <div class="actions">
      {#if !summary.open}
        <button
          type="button"
          class="btn btn-small btn-outline"
          aria-controls={summaryId}
          aria-expanded="false"
          on:click={() => dispatch('summary')}
        >
          Summarise
        </button>
      {/if}
      <div class="more">
        <button
          bind:this={moreButton}
          type="button"
          class="btn btn-small btn-outline more-button"
          aria-label="More actions"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          on:click={toggleMenu}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <circle cx="5" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="19" cy="12" r="1.6" />
          </svg>
        </button>
        {#if menuOpen}
          <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
          <div bind:this={menu} class="menu" role="menu" tabindex="-1" aria-label="Page actions" on:keydown={onMenuKeydown}>
            <button type="button" role="menuitem" on:click={deleteFromLibrary}>Delete from library</button>
          </div>
        {/if}
      </div>
    </div>
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
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
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

  .actions {
    flex: none;
    display: flex;
    gap: 6px;
  }

  .more {
    position: relative;
  }

  .more-button {
    width: 36px;
    padding: 0;
  }

  .menu {
    position: absolute;
    right: 0;
    top: calc(100% + 6px);
    z-index: 20;
    min-width: 200px;
    padding: 6px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
  }

  .menu button {
    display: block;
    width: 100%;
    min-height: 40px;
    padding: 0 10px;
    border: 0;
    border-radius: var(--radius-xs);
    background: transparent;
    text-align: left;
    font-size: 14px;
  }

  .menu button:hover,
  .menu button:focus-visible {
    background: var(--surface-active);
  }

  @media (max-width: 640px) {
    .result {
      flex-direction: column;
      gap: 12px;
      padding: 14px 12px;
    }
  }
</style>
