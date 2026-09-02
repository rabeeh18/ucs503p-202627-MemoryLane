<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { searchQuery } from '../stores';

  export let sticky: boolean = false;

  const dispatch = createEventDispatcher<{
    submit: string;
    clear: void;
  }>();

  let hintVisible = false;
  let isListening = false;
  let recognition: any = null;
  let speechTimeout: ReturnType<typeof setTimeout> | null = null;

  onMount(() => {
    const w = window as any;
    const SpeechRecognition = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (SpeechRecognition) {
      recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;

      recognition.onstart = () => {
        isListening = true;
        if (speechTimeout) clearTimeout(speechTimeout);
      };

      recognition.onresult = (event: any) => {
        let transcript = '';
        let isFinal = false;

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          transcript += event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            isFinal = true;
          }
        }

        if (transcript) {
          searchQuery.set(transcript);
        }

        if (speechTimeout) clearTimeout(speechTimeout);

        if (isFinal) {
          speechTimeout = setTimeout(() => {
            handleSubmit();
          }, 800);
        }
      };

      recognition.onerror = (event: any) => {
        console.error('Speech recognition error', event.error);
        isListening = false;
      };

      recognition.onend = () => {
        isListening = false;
      };
    }
  });

  function toggleVoiceSearch() {
    if (!recognition) {
      alert("Voice search is not supported in this browser.");
      return;
    }
    if (isListening) {
      recognition.stop();
    } else {
      searchQuery.set('');
      recognition.start();
    }
  }

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
    
    <!-- Microphone Button -->
    <button
      type="button"
      class="mic-btn {isListening ? 'listening' : ''}"
      on:click={toggleVoiceSearch}
      aria-label="Voice Search"
      title="Voice Search"
    >
      {#if isListening}
        <!-- Recording icon -->
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="2" width="6" height="12" rx="3"></rect>
          <path d="M5 10v2a7 7 0 0 0 14 0v-2"></path>
          <line x1="12" y1="19" x2="12" y2="22"></line>
        </svg>
      {:else}
        <!-- Default mic icon -->
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"></path>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
          <line x1="12" y1="19" x2="12" y2="22"></line>
        </svg>
      {/if}
    </button>

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
  .clear-btn:focus,
  .mic-btn:focus {
    outline: 2px solid #4a9eff;
    outline-offset: 1px;
  }
  
  .mic-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    background: transparent;
    border: 1px solid #444444;
    border-radius: 6px;
    color: #999999;
    cursor: pointer;
    transition: all 150ms ease;
  }
  
  .mic-btn:hover {
    color: #e0e0e0;
    border-color: #666666;
  }
  
  .mic-btn.listening {
    color: #ff4a4a;
    border-color: #ff4a4a;
    background-color: rgba(255, 74, 74, 0.1);
    animation: pulse 1.5s infinite;
  }
  
  @keyframes pulse {
    0% {
      box-shadow: 0 0 0 0 rgba(255, 74, 74, 0.4);
    }
    70% {
      box-shadow: 0 0 0 6px rgba(255, 74, 74, 0);
    }
    100% {
      box-shadow: 0 0 0 0 rgba(255, 74, 74, 0);
    }
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
