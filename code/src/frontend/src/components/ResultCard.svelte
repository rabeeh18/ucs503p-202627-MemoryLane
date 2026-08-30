<script lang="ts">
  import { formatTimestamp } from '../utils.js';
  import { searchQuery } from '../stores';
  import { fetchSummary } from '../api.js';

  export let id: string = '';
  export let url: string;
  export let title: string;
  export let timestamp: string;

  $: relativeTime = formatTimestamp(timestamp);

  let summaryVisible = false;
  let summaryLoading = false;
  let summaryText: string | null = null;
  let summaryError: string | null = null;

  async function toggleSummary() {
    if (summaryVisible) {
      summaryVisible = false;
      summaryError = null;
      return;
    }

    if (summaryText) {
      summaryVisible = true;
      return;
    }

    summaryLoading = true;
    summaryError = null;
    try {
      const data = await fetchSummary({
        query: $searchQuery.trim() || title,
        id,
      });
      summaryText = data.summary || null;
      if (!summaryText) {
        summaryError = 'No summary available.';
        summaryVisible = true;
      } else {
        summaryVisible = true;
      }
    } catch (_err) {
      summaryError = 'Could not generate a summary.';
      summaryVisible = true;
    } finally {
      summaryLoading = false;
    }
  }
</script>

<article class="result">
  <div class="result-top">
    <a
      class="result-title"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${title} — opens in a new tab`}
    >
      {title}
    </a>
    <time class="result-timestamp" datetime={timestamp}>{relativeTime}</time>
  </div>
  <a
    class="result-url"
    href={url}
    target="_blank"
    rel="noopener noreferrer"
    aria-label="Open in new tab"
  >
    {url}
  </a>

  {#if id}
    <div class="summary-row">
      <button
        type="button"
        class="summary-btn"
        on:click={toggleSummary}
        disabled={summaryLoading}
        aria-expanded={summaryVisible}
      >
        {#if summaryLoading}
          Summarising...
        {:else if summaryVisible}
          Hide summary
        {:else}
          Summarise
        {/if}
      </button>
      {#if summaryVisible && summaryError}
        <p class="summary-text" role="alert">{summaryError}</p>
      {:else if summaryVisible && summaryText}
        <p class="summary-text">{summaryText}</p>
      {/if}
    </div>
  {/if}
</article>

<style>
  .result {
    min-height: 60px;
    padding: 0 20px;
  }

  .result-top {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 16px;
  }

  .result-title {
    font-size: 18px;
    font-weight: 700;
    line-height: 1.4;
    color: #ffffff;
    text-decoration: none;
    transition: color 150ms ease;
  }

  .result-timestamp {
    flex-shrink: 0;
    font-size: 11px;
    font-weight: 400;
    color: #666666;
    white-space: nowrap;
    transition: color 150ms ease;
  }

  .result-url {
    display: block;
    margin-top: 2px;
    font-size: 13px;
    font-weight: 400;
    line-height: 1.3;
    color: #999999;
    text-decoration: none;
    word-break: break-all;
    transition: color 150ms ease;
  }

  .summary-row {
    margin-top: 8px;
  }

  .summary-btn {
    padding: 0;
    font-size: 12px;
    font-family: inherit;
    font-weight: 400;
    line-height: 1.3;
    color: #666666;
    background: transparent;
    border: none;
    cursor: pointer;
    transition: color 150ms ease;
  }

  .summary-btn:hover:not(:disabled) {
    color: #e0e0e0;
  }

  .summary-btn:disabled {
    cursor: default;
    color: #666666;
  }

  .summary-btn:focus {
    outline: 2px solid #4a9eff;
    outline-offset: 2px;
  }

  .summary-text {
    margin: 6px 0 0;
    font-size: 13px;
    font-weight: 400;
    line-height: 1.4;
    color: #999999;
  }

  .result:hover .result-title,
  .result:hover .result-url,
  .result:hover .result-timestamp {
    color: #e0e0e0;
  }

  .result-title:focus,
  .result-url:focus {
    outline: 2px solid #4a9eff;
    outline-offset: 2px;
  }
</style>
