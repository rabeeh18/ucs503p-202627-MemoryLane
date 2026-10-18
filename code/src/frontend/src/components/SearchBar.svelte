<script>
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import Kbd from './Kbd.svelte';
  import { searchQuery } from '../stores';

  /** Key hint shown inside the input ('/' on Home, 'Esc' on Results). */
  export let kbdHint = '/';
  export let autofocus = false;

  const dispatch = createEventDispatcher();

  let input;
  let hintVisible = false;
  let voiceSupported = false;
  let isListening = false;
  let isStarting = false;
  let voiceError = '';
  let recognition = null;
  let speechTimeout = null;

  export function focus() {
    input?.focus();
    input?.select();
  }

  onMount(() => {
    if (autofocus) input?.focus();

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;
    voiceSupported = true;
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = navigator.language || 'en-US';

    recognition.onstart = () => {
      isStarting = false;
      isListening = true;
      voiceError = '';
      if (speechTimeout) clearTimeout(speechTimeout);
    };

    recognition.onresult = (event) => {
      let transcript = '';
      let isFinal = false;
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        transcript += event.results[i][0].transcript;
        if (event.results[i].isFinal) isFinal = true;
      }
      if (transcript) searchQuery.set(transcript);
      if (speechTimeout) clearTimeout(speechTimeout);
      if (isFinal) speechTimeout = setTimeout(handleSubmit, 800);
    };

    recognition.onerror = (event) => {
      isStarting = false;
      isListening = false;
      switch (event.error) {
        case 'not-allowed':
        case 'service-not-allowed':
          voiceError = "Microphone access is blocked. Allow it in your browser's site settings and reload the page.";
          break;
        case 'network':
          voiceError = "Voice search couldn't reach the browser's speech service. Try Chrome or Edge.";
          break;
        case 'audio-capture':
          voiceError = 'No microphone was found. Check your input device.';
          break;
        case 'no-speech':
          voiceError = "Didn't hear anything. Please try again.";
          break;
        case 'aborted':
          break;
        default:
          voiceError = 'Voice search failed. Please try again.';
      }
    };

    recognition.onend = () => {
      isStarting = false;
      isListening = false;
    };
  });

  onDestroy(() => {
    if (speechTimeout) clearTimeout(speechTimeout);
    try {
      recognition?.abort();
    } catch {
      /* ignore */
    }
  });

  function toggleVoiceSearch() {
    if (isListening || isStarting) {
      try {
        recognition.abort();
      } catch {
        /* ignore */
      }
      isListening = false;
      isStarting = false;
      return;
    }
    voiceError = '';
    searchQuery.set('');
    isStarting = true;
    try {
      recognition.start();
    } catch {
      // "recognition has already started": reset so the next click works
      try {
        recognition.abort();
      } catch {
        /* ignore */
      }
      isStarting = false;
      isListening = false;
    }
  }

  function handleSubmit() {
    const trimmed = $searchQuery.trim();
    if (!trimmed) {
      hintVisible = true;
      return;
    }
    hintVisible = false;
    dispatch('submit', trimmed);
  }

  function handleKeydown(event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      handleSubmit();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      hintVisible = false;
      dispatch('clear');
    }
  }

  $: if (hintVisible && $searchQuery.trim()) hintVisible = false;
</script>

<form class="search" role="search" on:submit|preventDefault={handleSubmit}>
  <div class="row">
    <div class="field">
      <label for="search-input" class="visually-hidden">Search your saved pages</label>
      <input
        bind:this={input}
        id="search-input"
        type="text"
        bind:value={$searchQuery}
        on:keydown={handleKeydown}
        placeholder="that article about sleep and memory…"
        autocomplete="off"
        spellcheck="false"
        enterkeyhint="search"
      />
      <span class="hint-key"><Kbd>{kbdHint}</Kbd></span>
    </div>
    <div class="buttons">
      {#if voiceSupported}
        <button
          type="button"
          class="mic"
          class:listening={isListening}
          on:click={toggleVoiceSearch}
          aria-label={isListening ? 'Stop voice search' : 'Search by voice'}
          aria-pressed={isListening}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
          </svg>
        </button>
      {/if}
      <button type="submit" class="btn btn-primary">Search</button>
    </div>
  </div>

  {#if hintVisible}
    <p class="message" role="alert">Type what you're looking for first.</p>
  {/if}
  {#if isListening}
    <p class="message" role="status">Listening…</p>
  {/if}
  {#if voiceError}
    <p class="message" role="alert">{voiceError}</p>
  {/if}
</form>

<style>
  .search {
    width: 100%;
  }

  .row {
    display: flex;
    gap: 8px;
    align-items: stretch;
  }

  .field {
    position: relative;
    flex: 1;
    min-width: 0;
  }

  input {
    width: 100%;
    height: 48px;
    padding: 0 56px 0 16px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface);
    font-size: 15px;
  }

  input::placeholder {
    color: var(--text-3);
  }

  .hint-key {
    position: absolute;
    right: 14px;
    top: 50%;
    transform: translateY(-50%);
    pointer-events: none;
  }

  .buttons {
    display: flex;
    gap: 8px;
  }

  .mic {
    flex: none;
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: transparent;
    color: var(--text);
  }

  .mic:hover {
    background: var(--surface);
  }

  .mic.listening {
    border-color: var(--text-2);
    background: var(--surface-active);
  }

  .message {
    margin: 10px 2px 0;
    font-size: 13px;
    color: var(--text-2);
  }

  @media (max-width: 640px) {
    .row {
      flex-wrap: wrap;
    }

    .field {
      flex-basis: 100%;
    }

    .buttons {
      flex: 1;
      justify-content: flex-end;
    }

    .buttons .btn {
      flex: 1;
    }
  }
</style>
