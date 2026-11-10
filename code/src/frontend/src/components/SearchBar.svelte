<script>
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import Kbd from './Kbd.svelte';
  import { searchQuery } from '../stores';

  /** Key hint shown inside the input ('/' on Home, 'Esc' on Results). */
  export let kbdHint = '/';
  export let autofocus = false;
  /** Example query shown in the empty box. */
  export let placeholder = 'that article about sleep and memory…';

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
  <!-- One box: search icon, the input, the key hint, the mic and the Search button,
       so the box is the whole row and lines up with the headline above it. -->
  <div class="box">
    <svg class="lens" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16l4.5 4.5" />
    </svg>
    <label for="search-input" class="visually-hidden">Search your saved pages</label>
    <input
      bind:this={input}
      id="search-input"
      type="text"
      bind:value={$searchQuery}
      on:keydown={handleKeydown}
      {placeholder}
      autocomplete="off"
      spellcheck="false"
      enterkeyhint="search"
      maxlength="500"
    />
    <span class="hint-key"><Kbd>{kbdHint}</Kbd></span>
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
    <button type="submit" class="btn btn-primary submit" aria-label="Search">
      <!-- Larger screens show the word; phones an arrow (the search icon is already on the left). -->
      <span class="label">Search</span>
      <svg class="arrow" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M5 12h14M13 6l6 6-6 6" />
      </svg>
    </button>
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

  .box {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    height: 56px;
    padding: 0 6px 0 16px;
    border: 1px solid var(--border-strong);
    border-radius: 12px;
    background: var(--surface);
  }

  /* The box shows focus, so the input itself needs no outline. */
  .box:focus-within {
    border-color: var(--text-3);
  }

  .lens {
    flex: none;
    margin-right: 4px;
    color: var(--text-3);
  }

  input {
    flex: 1;
    min-width: 0;
    height: 100%;
    padding: 0;
    border: 0;
    background: transparent;
    font-size: 15px;
  }

  input:focus-visible {
    outline: none;
  }

  input::placeholder {
    color: var(--text-3);
  }

  .hint-key {
    flex: none;
    margin-right: 4px;
    pointer-events: none;
  }

  .mic {
    flex: none;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-2);
  }

  .mic:hover {
    background: var(--surface-active);
    color: var(--text);
  }

  .mic.listening {
    background: var(--surface-active);
    color: var(--text);
  }

  .submit {
    flex: none;
    height: 42px;
    padding: 0 18px;
    border-radius: var(--radius-sm);
  }

  .arrow {
    display: none;
  }

  .message {
    margin: 10px 2px 0;
    font-size: 13px;
    color: var(--text-2);
  }

  /* Phones: the same box, a little shorter; no key hint, and an arrow button. */
  @media (max-width: 640px) {
    .box {
      height: 52px;
      gap: 2px;
      padding: 0 5px 0 14px;
    }

    .lens {
      margin-right: 8px;
    }

    .hint-key {
      display: none;
    }

    .submit {
      width: 40px;
      height: 40px;
      padding: 0;
    }

    .label {
      display: none;
    }

    .arrow {
      display: block;
    }
  }
</style>
