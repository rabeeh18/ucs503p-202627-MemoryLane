<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { searchQuery } from '../stores';

  export let sticky: boolean = false;

  const dispatch = createEventDispatcher<{
    submit: string;
    clear: void;
  }>();

  let hintVisible = false;

  function handleSubmit() {
    const trimmed = $searchQuery.trim();
    if (!trimmed) {
      // Empty query: don't call API, show a gentle inline hint instead.
      hintVisible = true;
      return;
    }
    hintVisible = false;
    dispatch('submit', trimmed);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      event.preventDefault();
      handleSubmit();
    } else if (event.key === 'Escape') {
      handleClear();
    }
  }

  function handleClear() {
    hintVisible = false;
    dispatch('clear');
  }

  function handleInput() {
    if (hintVisible && $searchQuery.trim()) {
      hintVisible = false;
    }
  }
</script>

<div class="search-wrap" class:sticky>
  <div class="search-row">
    <input
      type="text"
      class="search-input"
      bind:value={$searchQuery}
      on:keydown={handleKeydown}
      on:input={handleInput}
      placeholder="Search your memories..."
      aria-label="Search your memories"
      autocomplete="off"
      spellcheck="false"
    />

    {#if $searchQuery.length > 0}
      <button
        type="button"
        class="clear-btn"
        on:click={handleClear}
        aria-label="Clear search"
      >
        Clear
      </button>
    {/if}

    <button
      type="button"
      class="search-btn"
      on:click={handleSubmit}
      aria-label="Search"
    >
      Search
    </button>
  </div>

  {#if hintVisible}
    <p class="hint" role="alert">Please enter a search query</p>
  {/if}

  {#if !sticky}
    <p class="subtitle">Type to search across all saved webpages</p>
  {/if}
</div>

<style>
  .search-wrap {
    width: 100%;
  }

  .search-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .search-input {
    flex: 1;
    height: 44px;
    padding: 12px 16px;
    font-size: 16px;
    line-height: 1.5;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #ffffff;
    background: transparent;
    border: 1px solid #444444;
    border-radius: 6px;
    outline: none;
    transition: border-color 150ms ease, background-color 150ms ease;
  }

  .sticky .search-input {
    background: #222222;
  }

  .search-input::placeholder {
    color: #666666;
    opacity: 0.7;
  }

  .search-input:focus {
    outline: 2px solid #4a9eff;
    outline-offset: 1px;
    border-color: #4a9eff;
  }

  .search-btn,
  .clear-btn {
    height: 44px;
    padding: 0 18px;
    font-size: 14px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: transparent;
    border: 1px solid #444444;
    border-radius: 6px;
    color: #999999;
    cursor: pointer;
    white-space: nowrap;
    transition: color 150ms ease, border-color 150ms ease;
  }

  .search-btn:hover,
  .clear-btn:hover {
    color: #e0e0e0;
    border-color: #666666;
  }

  .search-btn:focus,
  .clear-btn:focus {
    outline: 2px solid #4a9eff;
    outline-offset: 1px;
  }

  .hint {
    margin: 8px 2px 0;
    font-size: 12px;
    color: #999999;
  }

  .subtitle {
    margin: 16px 0 0;
    text-align: center;
    font-size: 14px;
    color: #999999;
  }
</style>
