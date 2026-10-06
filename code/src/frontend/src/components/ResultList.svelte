<script lang="ts">
  import ResultCard from './ResultCard.svelte';
  import type { Webpage } from '../stores';

  export let results: Webpage[] = [];
  export let isLoading: boolean = false;
  export let error: string | null = null;

  let sortBy: 'relevance' | 'recent' = 'relevance';

  $: sortedResults = sortBy === 'recent' 
    ? [...results].sort((a, b) => new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime())
    : results;
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
    <div class="sort-controls">
      <label for="sort-select">Sort by:</label>
      <select id="sort-select" bind:value={sortBy}>
        <option value="relevance">Relevance</option>
        <option value="recent">Recently Visited</option>
      </select>
    </div>
    {#each sortedResults as item (item.id || item.url + item.timestamp)}
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

  .sort-controls {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 8px;
    margin-bottom: 20px;
    padding: 0 20px;
  }
  
  .sort-controls label {
    font-size: 14px;
    color: #999;
  }
  
  .sort-controls select {
    padding: 6px 12px;
    border-radius: 6px;
    background: #2a2a2a;
    color: #eee;
    border: 1px solid #444;
    font-size: 14px;
    outline: none;
    cursor: pointer;
  }
  
  .sort-controls select:focus {
    border-color: #666;
  }
</style>
