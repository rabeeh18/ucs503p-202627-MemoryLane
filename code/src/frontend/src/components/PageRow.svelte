<script>
  import LetterTile from './LetterTile.svelte';
  import { relativeTime } from '../lib/time.js';

  /** @type {{ url: string, title: string, domain: string, timestamp: string }} */
  export let page;
</script>

<li>
  <a class="row" href={page.url} target="_blank" rel="noopener noreferrer">
    <LetterTile domain={page.domain} />
    <span class="text">
      <span class="title">{page.title || page.url}</span>
      <span class="domain">{page.domain}</span>
    </span>
    <span class="when mono">{relativeTime(page.timestamp)}</span>
  </a>
</li>

<style>
  li {
    list-style: none;
    border-bottom: 1px solid var(--divider-soft);
  }

  li:last-child {
    border-bottom: 0;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 14px 0;
    color: var(--text);
  }

  .row:hover .title {
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

  .title {
    font-size: 15px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .domain {
    margin-top: 2px;
    font-size: 13px;
    color: var(--text-3);
  }

  .when {
    flex: none;
    font-size: 12px;
    color: var(--text-3);
  }
</style>
