<script lang="ts">
  import ResultCard from './ResultCard.svelte';
  import type { Webpage } from '../stores';

  export let results: Webpage[] = [];
  export let isLoading: boolean = false;
  export let error: string | null = null;
</script>

<div class="result-list" aria-live="polite" aria-busy={isLoading}>
  {#if isLoading}
    <div class="status-block">
      <div class="spinner" aria-hidden="true"></div>
      <p class="status-text">Searching...</p>
    </div>
  {:else if error}
    <div class="status-block">
      <p class="status-text error-text" role="alert">{error}</p>
    </div>
  {:else if results.length === 0}
    <div class="status-block">
      <p class="status-text">No memories found. Try a different search.</p>
    </div>
  {:else}
    {#each results as item (item.id || item.url + item.timestamp)}
      <ResultCard
        id={item.id}
        url={item.url}
        title={item.title}
        timestamp={item.timestamp}
      />
    {/each}
  {/if}
</div>

<style>
  .result-list {
    display: flex;
    flex-direction: column;
    max-width: 900px;
    margin: 0 auto;
  }

  .result-list > :global(.result) + :global(.result) {
    margin-top: 40px;
  }

  .status-block {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 20px;
    text-align: center;
  }

  .status-text {
    margin-top: 12px;
    font-size: 14px;
    color: #999999;
  }

  .error-text {
    color: #999999;
  }

  .spinner {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    border: 2px solid #444444;
    border-top-color: #999999;
    animation: spin 800ms linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .spinner {
      animation-duration: 1600ms;
    }
  }
</style>
