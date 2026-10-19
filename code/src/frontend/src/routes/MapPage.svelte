<script>
  import { onDestroy, onMount } from 'svelte';
  import Header from '../components/Header.svelte';
  import MapCanvas from '../components/map/MapCanvas.svelte';
  import MapPanel from '../components/map/MapPanel.svelte';
  import MapList from '../components/map/MapList.svelte';
  import MapSkeleton from '../components/map/MapSkeleton.svelte';
  import { mapSearch } from '../api.js';
  import { link } from '../lib/router.js';
  import { EMPTY_PANEL, findState, panelReducer } from '../lib/mapView.js';
  import { loadMap, mapState } from '../mapStore.js';
  import { committedDeletes, hiddenPageIds, pageDeletes } from '../pageDeletes.js';
  import { libraryVersion } from '../stores';

  const narrow = () => window.matchMedia('(max-width: 640px)').matches;

  let mode = narrow() ? 'list' : 'map';
  let panel = EMPTY_PANEL;
  let canvas;
  let sheet = window.matchMedia('(max-width: 900px)').matches;

  const dispatch = (action) => (panel = panelReducer(panel, action));

  // ---- loading ------------------------------------------------------------------------

  async function refresh() {
    try {
      await loadMap({ force: true });
    } catch {
      pageDeletes.notify("Couldn't load your map. Try again.");
    }
  }

  onMount(refresh);

  // Refetch after deletes the server confirmed, and after "Delete all my data".
  let seenDeletes = $committedDeletes;
  let seenLibrary = $libraryVersion;
  $: if ($committedDeletes !== seenDeletes) {
    seenDeletes = $committedDeletes;
    refresh();
  }
  $: if ($libraryVersion !== seenLibrary) {
    seenLibrary = $libraryVersion;
    refresh();
  }

  $: status = $mapState.status;
  $: raw = $mapState.data?.status === 'ok' ? $mapState.data : null;
  // Pages being deleted disappear at once, before the map is rebuilt.
  $: data = raw && {
    ...raw,
    pages: raw.pages.filter((p) => !$hiddenPageIds.has(p.id)),
    edges: raw.edges.filter((e) => !$hiddenPageIds.has(e.a) && !$hiddenPageIds.has(e.b)),
  };
  $: if (raw) dispatch({ type: 'map', pages: data.pages, topics: data.topics });
  $: counts = data ? `${data.pages.length} page${data.pages.length === 1 ? '' : 's'} · ${data.topics.length} topic${data.topics.length === 1 ? '' : 's'}` : '';

  // ---- find a topic ---------------------------------------------------------------------

  let findQuery = '';
  let findResult = null;
  let findTimer;
  let findController;

  $: find = findState(findQuery, findResult);

  function onFindInput() {
    clearTimeout(findTimer);
    findController?.abort();
    if (!findQuery.trim()) {
      findResult = null;
      return;
    }
    findTimer = setTimeout(runFind, 250);
  }

  async function runFind() {
    const q = findQuery.trim();
    if (!q) return;
    findController = new AbortController();
    const mine = findController;
    try {
      const result = await mapSearch(q, mine.signal);
      if (mine !== findController || findQuery.trim() !== q) return;
      findResult = result;
      const best = result.topics[0];
      if (best) {
        dispatch({ type: 'topic', id: best.id });
        canvas?.focusTopic(best.id);
      }
    } catch (err) {
      if (err?.name === 'CancelledError' || mine !== findController) return;
      findResult = { topics: [], pages: [] };
    }
  }

  function onFindKeydown(event) {
    if (event.key === 'Escape' && findQuery) {
      event.preventDefault();
      event.stopPropagation();
      findQuery = '';
      onFindInput();
    } else if (event.key === 'Enter') {
      clearTimeout(findTimer);
      runFind();
    }
  }

  // ---- selection --------------------------------------------------------------------------

  function selectPage(id, topicId) {
    const page = data?.pages.find((p) => p.id === id);
    dispatch({ type: 'page', id, topicId: topicId ?? page?.topic ?? null });
    canvas?.focusPage(id);
  }

  function onKeydown(event) {
    if (event.key !== 'Escape' || mode !== 'map') return;
    if (document.querySelector('dialog[open]')) return;
    dispatch({ type: 'clear' });
  }

  function onResize() {
    sheet = window.matchMedia('(max-width: 900px)').matches;
  }

  onDestroy(() => {
    clearTimeout(findTimer);
    findController?.abort();
  });
</script>

<svelte:window on:keydown={onKeydown} on:resize={onResize} />

<div class="screen" class:fixed={mode === 'map' && status === 'ok'}>
  <Header />

  <main class="map-page">
    <div class="work">
      <div class="toolbar">
        <div class="segmented" role="radiogroup" aria-label="View">
          <button type="button" role="radio" aria-checked={mode === 'map'} class:on={mode === 'map'}
            on:click={() => (mode = 'map')}>Map</button>
          <button type="button" role="radio" aria-checked={mode === 'list'} class:on={mode === 'list'}
            on:click={() => (mode = 'list')}>List</button>
        </div>

        <div class="find">
          <label for="find-topic" class="visually-hidden">Find a topic</label>
          <input
            id="find-topic"
            type="search"
            placeholder="Find a topic…"
            autocomplete="off"
            spellcheck="false"
            bind:value={findQuery}
            on:input={onFindInput}
            on:keydown={onFindKeydown}
            disabled={!data}
          />
          {#if find.message}
            <p class="find-message" role="status">{find.message}</p>
          {/if}
        </div>

        <p class="counts">{counts}</p>
      </div>

      {#if status === 'loading' || status === 'idle'}
        <div class="stage"><MapSkeleton /></div>
      {:else if status === 'too_few'}
        <div class="stage center">
          <p class="state">
            Save a few more pages to see your map.
            <a href="/extension" use:link>Get the extension</a>
          </p>
        </div>
      {:else if status === 'error'}
        <div class="stage center">
          <p class="state">Couldn't load your map. <button type="button" class="link-button" on:click={refresh}>Try again</button></p>
        </div>
      {:else if data && mode === 'map'}
        <div class="stage">
          <MapCanvas
            bind:this={canvas}
            {data}
            {panel}
            {find}
            on:selectPage={(e) => selectPage(e.detail.id, e.detail.topicId)}
            on:selectTopic={(e) => dispatch({ type: 'topic', id: e.detail })}
            on:clear={() => dispatch({ type: 'clear' })}
          />
        </div>
        <p class="hint">Scroll to zoom · Drag to pan · Click a topic to search inside it</p>
      {:else if data}
        <MapList {data} />
      {/if}
    </div>

    {#if data && mode === 'map' && (!sheet || panel.mode !== 'none')}
      <MapPanel {panel} {data} {sheet} on:selectPage={(e) => selectPage(e.detail)} on:close={() => dispatch({ type: 'clear' })} />
    {/if}
  </main>
</div>

<style>
  .screen {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* Map view fills exactly one screen; the panel scrolls on its own. */
  .screen.fixed {
    height: 100vh;
    height: 100dvh;
    overflow: hidden;
  }

  .map-page {
    flex: 1;
    min-height: 0;
    display: flex;
    border-top: 1px solid var(--divider-soft);
  }

  .work {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    padding: 24px 32px 16px;
  }

  .toolbar {
    display: grid;
    grid-template-columns: auto minmax(0, 320px) 1fr;
    align-items: start;
    gap: 20px;
  }

  .segmented {
    display: inline-flex;
    padding: 4px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }

  .segmented button {
    height: 36px;
    padding: 0 16px;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-2);
    font-size: 14px;
  }

  .segmented button.on {
    background: var(--surface-active);
    color: var(--text);
  }

  .segmented button:not(.on):hover {
    color: var(--text);
  }

  .find input {
    width: 100%;
    height: 46px;
    padding: 0 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    font-size: 14px;
  }

  .find input::placeholder {
    color: var(--text-3);
  }

  .find input:disabled {
    opacity: 0.5;
  }

  .find-message {
    margin: 6px 2px 0;
    font-size: 12px;
    color: var(--text-3);
  }

  .counts {
    margin: 0;
    justify-self: end;
    align-self: center;
    font-size: 14px;
    color: var(--text-3);
    white-space: nowrap;
  }

  .stage {
    position: relative;
    flex: 1;
    min-height: 320px;
    margin-top: 12px;
  }

  .stage.center {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .state {
    margin: 0;
    font-size: 15px;
    color: var(--text-2);
    text-align: center;
  }

  .state a {
    display: block;
    margin-top: 8px;
    color: var(--text);
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .hint {
    margin: 8px 0 0;
    text-align: center;
    font-size: 13px;
    color: var(--text-3);
  }

  :global(.map-page .list) {
    width: 100%;
    margin-top: 24px;
  }

  @media (max-width: 900px) {
    .work {
      padding: 16px 16px 12px;
    }

    .toolbar {
      grid-template-columns: auto 1fr;
    }

    .counts {
      grid-column: 1 / -1;
      justify-self: start;
    }
  }

  @media (max-width: 640px) {
    .toolbar {
      grid-template-columns: 1fr;
    }

    .hint {
      display: none;
    }
  }
</style>
