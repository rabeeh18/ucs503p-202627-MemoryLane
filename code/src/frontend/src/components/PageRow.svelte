<script>
  import LetterTile from './LetterTile.svelte';
  import TrashIcon from './TrashIcon.svelte';
  import { relativeTime } from '../lib/time.js';
  import { pageDeletes } from '../pageDeletes.js';

  /** @type {{ id: string, url: string, title: string, domain: string, timestamp: string }} */
  export let page;
</script>

<li class="row">
  <a class="link" href={page.url} target="_blank" rel="noopener noreferrer">
    <LetterTile domain={page.domain || page.url} />
    <span class="text">
      <span class="title-line">
        <span class="title">{page.title || page.url}</span>
        <span class="when mono">{relativeTime(page.timestamp)}</span>
      </span>
      <span class="domain">{page.domain}</span>
    </span>
  </a>
  <button
    type="button"
    class="delete"
    aria-label="Delete page"
    title="Delete page"
    on:click={() => pageDeletes.schedule(page.id)}
  >
    <TrashIcon />
  </button>
</li>

<style>
  .row {
    position: relative;
    display: flex;
    align-items: center;
    list-style: none;
    border-bottom: 1px solid var(--divider-soft);
  }

  .row:last-child {
    border-bottom: 0;
  }

  .link {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: flex-start;
    gap: 14px;
    padding: 14px 0;
    color: var(--text);
  }

  .link:hover .title {
    text-decoration: underline;
    text-underline-offset: 3px;
    text-decoration-color: var(--text-3);
  }

  .text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  /* The relative time sits on the title's line, aligned to its baseline. */
  .title-line {
    display: flex;
    align-items: baseline;
    gap: 16px;
    min-width: 0;
  }

  .title {
    flex: 1;
    min-width: 0;
    font-size: 15px;
    line-height: 28px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .when {
    flex: none;
    font-size: 12px;
    color: var(--text-3);
  }

  .domain {
    font-size: 13px;
    color: var(--text-3);
  }

  /* Shown on row hover and when it (or the row) has keyboard focus. */
  .delete {
    flex: none;
    width: 36px;
    height: 36px;
    margin-left: 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-2);
    opacity: 0;
  }

  .row:hover .delete,
  .row:focus-within .delete,
  .delete:focus-visible {
    opacity: 1;
  }

  .delete:hover {
    border-color: var(--border);
    background: var(--surface);
    color: var(--text);
  }

  @media (hover: none) {
    .delete {
      opacity: 1;
    }
  }
</style>
