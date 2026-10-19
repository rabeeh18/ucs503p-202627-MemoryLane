<script>
  // The library map. Two stacked SVG layers share one view transform:
  //  - the drawing (role="img" with a summary label): ellipses, links, dots,
  //    and the hovered / selected page title;
  //  - the hit layer: topic labels and one focusable button per page, plus the
  //    pointer handling for zoom, pan, click and double-click.
  // Sizes that should stay constant on screen (dots, strokes) are divided by
  // the zoom so panning only changes one transform attribute per layer.
  import { createEventDispatcher, onDestroy } from 'svelte';
  import {
    WORLD, clampView, contentBounds, dotState, fitBounds, easeInOut, fitView, lerpView, neighboursOf, panBy, toScreen, toWorld,
    viewForTopic, zoomAt,
  } from '../../lib/mapView.js';

  /** @type {{ topics: any[], pages: any[], edges: any[] }} */
  export let data;
  /** Panel selection: { mode, pageId, topicId } */
  export let panel;
  /** Find-a-topic state from findState() */
  export let find = null;

  const dispatch = createEventDispatcher();
  const DRAG_THRESHOLD = 4;

  let width = 0;
  let height = 0;
  let view = { k: 1, tx: 0, ty: 0 };
  let fittedFor = null;
  let hoverPageId = null;
  let hoverTopicId = null;
  let animation = 0;
  let drag = null;
  let hitSvg;

  $: viewport = { width, height };
  $: pagesById = new Map(data.pages.map((p) => [p.id, p]));
  $: topicsById = new Map(data.topics.map((t) => [t.id, t]));
  $: world = data.pages.map((p) => ({ ...p, ...toWorld(p.x, p.y) }));
  $: worldById = new Map(world.map((p) => [p.id, p]));

  // Fit the whole map whenever a new map arrives. When the canvas is resized
  // (window resize, the panel appearing), re-fit too, unless the user has
  // zoomed or panned since the last fit; then just keep the view valid.
  let fittedSize = '';
  let userMoved = false;
  $: if (width && height) onSize(width, height, data.version ?? data);

  function onSize(w, h, version) {
    const size = `${w}x${h}`;
    if (fittedFor !== version || (!userMoved && fittedSize !== size)) {
      fittedFor = version;
      fittedSize = size;
      userMoved = false;
      view = fitBounds(contentBounds(data), { width: w, height: h });
    } else if (fittedSize !== size) {
      fittedSize = size;
      view = clampView(view, { width: w, height: h });
    }
  }

  $: selectedId = panel.mode === 'page' ? panel.pageId : null;
  $: activeTopicId = panel.topicId;
  $: neighbourIds = neighboursOf(selectedId, data.edges);
  $: context = { selectedId, neighbourIds, find, topicId: panel.mode === 'topic' ? panel.topicId : null };
  $: k = view.k || 1;

  $: summary = `Map of ${data.pages.length} saved page${data.pages.length === 1 ? '' : 's'} in `
    + `${data.topics.length} topic${data.topics.length === 1 ? '' : 's'}`
    + (data.topics.length ? `: ${data.topics.map((t) => `${t.label} (${t.count})`).join(', ')}` : '')
    + '.';

  // ---- view changes ----------------------------------------------------------------

  const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  function animateTo(target, duration = 450) {
    cancelAnimationFrame(animation);
    if (reducedMotion()) {
      view = target;
      return;
    }
    const from = view;
    const start = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      view = lerpView(from, target, easeInOut(t));
      if (t < 1) animation = requestAnimationFrame(step);
    };
    animation = requestAnimationFrame(step);
  }

  export function fit() {
    userMoved = false;
    animateTo(fitBounds(contentBounds(data), viewport));
  }

  export function focusTopic(topicId) {
    const topic = topicsById.get(topicId);
    if (topic && width) {
      userMoved = true;
      animateTo(viewForTopic(topic, viewport));
    }
  }

  /** Bring a page into view (only moves if it is off screen or near the edge). */
  export function focusPage(pageId) {
    const p = worldById.get(pageId);
    if (!p || !width) return;
    const s = toScreen(p, view);
    const margin = 60;
    if (s.x > margin && s.x < width - margin && s.y > margin && s.y < height - margin) return;
    animateTo(clampView({ k: view.k, tx: width / 2 - p.x * view.k, ty: height / 2 - p.y * view.k }, viewport));
  }

  onDestroy(() => cancelAnimationFrame(animation));

  // ---- pointer: zoom, pan, click ---------------------------------------------------

  function onWheel(event) {
    event.preventDefault();
    cancelAnimationFrame(animation);
    const rect = hitSvg.getBoundingClientRect();
    const factor = Math.exp(-event.deltaY * (event.deltaMode === 1 ? 0.05 : 0.0015));
    userMoved = true;
    view = zoomAt(view, factor, { x: event.clientX - rect.left, y: event.clientY - rect.top }, viewport);
  }

  /** Svelte action: a non-passive wheel listener (so the page doesn't scroll). */
  function wheel(node) {
    node.addEventListener('wheel', onWheel, { passive: false });
    return { destroy: () => node.removeEventListener('wheel', onWheel) };
  }

  function onPointerDown(event) {
    if (event.button !== 0) return;
    cancelAnimationFrame(animation);
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, moved: false, target: event.target };
  }

  function onPointerMove(event) {
    if (!drag || drag.id !== event.pointerId) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    if (!drag.moved) {
      drag.moved = true;
      try {
        hitSvg.setPointerCapture(event.pointerId);
      } catch {
        /* optional */
      }
    }
    userMoved = true;
    view = panBy(view, dx, dy, viewport);
    drag.x = event.clientX;
    drag.y = event.clientY;
  }

  function onPointerUp(event) {
    if (!drag || drag.id !== event.pointerId) return;
    const wasClick = !drag.moved;
    const target = drag.target;
    drag = null;
    if (!wasClick) return;
    const pageId = target?.closest?.('[data-page]')?.dataset.page;
    const topicId = target?.closest?.('[data-topic]')?.dataset.topic;
    if (pageId) selectPage(pageId);
    else if (topicId) dispatch('selectTopic', topicId);
    else dispatch('clear');
  }

  function onDoubleClick(event) {
    const pageId = event.target?.closest?.('[data-page]')?.dataset.page;
    const page = pageId && pagesById.get(pageId);
    if (page) window.open(page.url, '_blank', 'noopener');
  }

  function selectPage(pageId) {
    dispatch('selectPage', { id: pageId, topicId: pagesById.get(pageId)?.topic ?? null });
  }

  function onKey(event, action) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      action();
    }
  }

  function onCanvasKeydown(event) {
    if (event.key === 'Escape') dispatch('clear');
  }

  // ---- drawing helpers ----------------------------------------------------------------

  function edgeClass(edge) {
    const touches = selectedId && (edge.a === selectedId || edge.b === selectedId);
    const dim = find?.active && !(find.matchIds.has(edge.a) && find.matchIds.has(edge.b));
    return `edge ${edge.kind}${touches ? ' lit' : ''}${dim ? ' dim' : ''}`;
  }

  function topicLabelPos(t, v) {
    const c = toScreen(toWorld(t.x, t.y), v);
    return { x: c.x, y: c.y - t.ry * WORLD.height * v.k - 12 };
  }

  $: titlePage = (hoverPageId && worldById.get(hoverPageId)) || (selectedId && worldById.get(selectedId)) || null;
  $: titlePos = titlePage ? toScreen(titlePage, view) : null;
</script>

<div
  class="canvas"
  bind:clientWidth={width}
  bind:clientHeight={height}
  on:keydown={onCanvasKeydown}
  role="presentation"
>
  {#if width && height}
    <svg class="drawing" {width} {height} role="img" aria-label={summary}>
      <g transform="translate({view.tx} {view.ty}) scale({k})">
        {#each data.topics as t (t.id)}
          <ellipse
            class="topic"
            class:active={t.id === activeTopicId || t.id === hoverTopicId}
            cx={t.x * WORLD.width}
            cy={t.y * WORLD.height}
            rx={t.rx * WORLD.width}
            ry={t.ry * WORLD.height}
          />
        {/each}
        {#each data.edges as e (e.a + '|' + e.b)}
          {@const a = worldById.get(e.a)}
          {@const b = worldById.get(e.b)}
          {#if a && b}
            <line class={edgeClass(e)} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
          {/if}
        {/each}
        {#each world as p (p.id)}
          {@const state = dotState(p, context)}
          {#if state === 'selected'}
            <circle class="ring" cx={p.x} cy={p.y} r={9 / k} stroke-width={1 / k} />
          {/if}
          <circle
            class="dot {state}"
            class:hover={p.id === hoverPageId}
            cx={p.x}
            cy={p.y}
            r={(state === 'selected' ? 3.5 : state === 'outlier' ? 2 : 2.5) / k}
          />
        {/each}
      </g>
      {#if titlePage && titlePos}
        {@const flip = titlePos.x + 12 + titlePage.title.length * 6.6 > width - 8}
        <text
          class="page-title"
          x={flip ? titlePos.x - 12 : titlePos.x + 12}
          y={titlePos.y + 4}
          text-anchor={flip ? 'end' : 'start'}
        >{titlePage.title}</text>
      {/if}
    </svg>

    <svg
      bind:this={hitSvg}
      class="hits"
      {width}
      {height}
      role="group"
      aria-label="Topics and pages"
      use:wheel
      on:pointerdown={onPointerDown}
      on:pointermove={onPointerMove}
      on:pointerup={onPointerUp}
      on:pointercancel={() => (drag = null)}
      on:dblclick={onDoubleClick}
    >
      <g transform="translate({view.tx} {view.ty}) scale({k})">
        {#each data.topics as t (t.id)}
          <!-- svelte-ignore a11y-no-static-element-interactions -->
          <ellipse
            class="topic-hit"
            data-topic={t.id}
            cx={t.x * WORLD.width}
            cy={t.y * WORLD.height}
            rx={t.rx * WORLD.width}
            ry={t.ry * WORLD.height}
            on:pointerenter={() => (hoverTopicId = t.id)}
            on:pointerleave={() => (hoverTopicId = null)}
          />
        {/each}
        {#each world as p (p.id)}
          {@const topic = p.topic ? topicsById.get(p.topic) : null}
          <circle
            class="dot-hit"
            data-page={p.id}
            cx={p.x}
            cy={p.y}
            r={8 / k}
            stroke-width={2 / k}
            role="button"
            tabindex="0"
            aria-label="{p.title}, {topic ? topic.label : 'no topic'}"
            aria-pressed={p.id === selectedId}
            on:pointerenter={() => (hoverPageId = p.id)}
            on:pointerleave={() => (hoverPageId = null)}
            on:focus={() => (hoverPageId = p.id)}
            on:blur={() => (hoverPageId = null)}
            on:keydown={(event) => onKey(event, () => selectPage(p.id))}
          />
        {/each}
      </g>
      {#each data.topics as t (t.id)}
        {@const pos = topicLabelPos(t, view)}
        <text
          class="topic-label"
          class:active={t.id === activeTopicId || t.id === hoverTopicId}
          data-topic={t.id}
          x={pos.x}
          y={pos.y}
          role="button"
          tabindex="0"
          aria-label="{t.label}, {t.count} pages"
          aria-pressed={panel.mode === 'topic' && t.id === panel.topicId}
          on:pointerenter={() => (hoverTopicId = t.id)}
          on:pointerleave={() => (hoverTopicId = null)}
          on:keydown={(event) => onKey(event, () => dispatch('selectTopic', t.id))}
        ><tspan class="name">{t.label}</tspan><tspan class="count">{" · "}{t.count} page{t.count === 1 ? '' : 's'}</tspan></text>
      {/each}
    </svg>

    <button type="button" class="fit" on:click={fit}>Fit</button>
  {/if}
</div>

<style>
  .canvas {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: hidden;
    touch-action: none;
    user-select: none;
  }

  svg {
    position: absolute;
    inset: 0;
    display: block;
  }

  .drawing {
    pointer-events: none;
  }

  .hits {
    cursor: grab;
  }

  .hits:active {
    cursor: grabbing;
  }

  /* Topics: one step above the background, hairline border. */
  .topic {
    fill: var(--map-topic);
    stroke: var(--map-topic-border);
    stroke-width: 1px;
    vector-effect: non-scaling-stroke;
    transition: fill 120ms ease, stroke 120ms ease;
  }

  .topic.active {
    fill: var(--map-topic-active);
    stroke: var(--map-topic-border-active);
  }

  .edge {
    stroke: var(--map-edge);
    stroke-width: 1px;
    vector-effect: non-scaling-stroke;
  }

  .edge.cross {
    stroke: var(--map-edge-cross);
    stroke-dasharray: 3 4;
  }

  .edge.lit {
    stroke: var(--map-edge-lit);
  }

  .edge.dim {
    opacity: 0.35;
  }

  .dot {
    fill: var(--map-dot);
    transition: fill 120ms ease, opacity 120ms ease;
  }

  .dot.outlier {
    fill: var(--map-dot-outlier);
  }

  .dot.neighbour,
  .dot.match,
  .dot.hover {
    fill: var(--map-dot-lit);
  }

  .dot.selected {
    fill: var(--text);
  }

  .dot.dim {
    opacity: 0.25;
  }

  .ring {
    fill: none;
    stroke: var(--map-ring);
  }

  /* Titles stay readable over links and dots: a background-coloured outline. */
  .page-title,
  .topic-label {
    font-family: var(--font-sans);
    paint-order: stroke;
    stroke: var(--bg);
    stroke-width: 4px;
    stroke-linejoin: round;
  }

  .page-title {
    fill: var(--text);
    font-size: 13px;
  }

  .topic-hit {
    fill: transparent;
    cursor: pointer;
  }

  .dot-hit {
    fill: transparent;
    stroke: transparent;
    cursor: pointer;
    outline: none;
  }

  .dot-hit:focus-visible {
    stroke: var(--text-2);
  }

  .topic-label {
    font-size: 13px;
    text-anchor: middle;
    cursor: pointer;
    outline: none;
  }

  .topic-label .name {
    fill: var(--text-2);
  }

  .topic-label .count {
    fill: var(--text-3);
  }

  .topic-label.active .name {
    fill: var(--text);
    font-weight: 500;
  }

  .topic-label:focus-visible .name {
    text-decoration: underline;
  }

  .fit {
    position: absolute;
    right: 12px;
    bottom: 12px;
    height: 30px;
    padding: 0 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--bg);
    color: var(--text-2);
    font-size: 12px;
  }

  .fit:hover {
    color: var(--text);
    border-color: var(--border-strong);
  }

  @media (prefers-reduced-motion: reduce) {
    .topic,
    .dot {
      transition: none;
    }
  }
</style>
