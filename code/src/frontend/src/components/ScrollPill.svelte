<script>
  // A floating scroll indicator that replaces the (visually hidden) native
  // scrollbar. Native wheel, touch and keyboard scrolling are untouched; the
  // pill only mirrors the page's scroll position and can be dragged.
  import { onDestroy, onMount } from 'svelte';

  const MIN_HEIGHT = 32;
  const EDGE = 6; // gap from the right edge and top/bottom
  const HOT_ZONE = 24; // pointer this close to the right edge shows the pill
  const HIDE_AFTER_MS = 1000;

  let visible = false;
  let hovering = false;
  let dragging = false;
  let overflow = false;
  let height = MIN_HEIGHT;
  let top = EDGE;
  let hideTimer;
  let dragStartY = 0;
  let dragStartScroll = 0;
  let frame = 0;

  const scroller = () => document.scrollingElement || document.documentElement;

  function measure() {
    frame = 0;
    const el = scroller();
    const viewport = window.innerHeight;
    const total = el.scrollHeight;
    overflow = total > viewport + 1;
    if (!overflow) return;
    const track = viewport - EDGE * 2;
    height = Math.max(MIN_HEIGHT, Math.round((viewport / total) * track));
    const progress = el.scrollTop / (total - viewport);
    top = EDGE + Math.round(Math.min(1, Math.max(0, progress)) * (track - height));
  }

  function schedule() {
    if (!frame) frame = requestAnimationFrame(measure);
  }

  function show() {
    visible = true;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      if (!hovering && !dragging) visible = false;
    }, HIDE_AFTER_MS);
  }

  function onScroll() {
    schedule();
    show();
  }

  function onPointerMove(event) {
    if (dragging || !overflow) return;
    if (event.clientX >= window.innerWidth - HOT_ZONE) show();
  }

  function onPointerDown(event) {
    event.preventDefault();
    dragging = true;
    dragStartY = event.clientY;
    dragStartScroll = scroller().scrollTop;
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      /* capture is a nicety; dragging still works while over the pill */
    }
  }

  function onDrag(event) {
    if (!dragging) return;
    const el = scroller();
    const viewport = window.innerHeight;
    const track = viewport - EDGE * 2 - height;
    if (track <= 0) return;
    const scrollable = el.scrollHeight - viewport;
    el.scrollTop = dragStartScroll + ((event.clientY - dragStartY) / track) * scrollable;
  }

  function onPointerUp(event) {
    if (!dragging) return;
    dragging = false;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    show();
  }

  let resizeObserver;
  onMount(() => {
    measure();
    resizeObserver = new ResizeObserver(schedule);
    resizeObserver.observe(document.body);
  });

  onDestroy(() => {
    clearTimeout(hideTimer);
    if (frame) cancelAnimationFrame(frame);
    resizeObserver?.disconnect();
  });
</script>

<svelte:window on:scroll|passive={onScroll} on:resize={schedule} on:pointermove={onPointerMove} />

{#if overflow}
  <div
    class="pill"
    class:visible={visible || dragging || hovering}
    class:active={hovering || dragging}
    style="height: {height}px; transform: translateY({top}px)"
    aria-hidden="true"
    on:pointerenter={() => { hovering = true; show(); }}
    on:pointerleave={() => { hovering = false; show(); }}
    on:pointerdown={onPointerDown}
    on:pointermove={onDrag}
    on:pointerup={onPointerUp}
    on:pointercancel={onPointerUp}
  ></div>
{/if}

<style>
  .pill {
    position: fixed;
    top: 0;
    right: 6px;
    z-index: 40;
    width: 5px;
    border-radius: 999px;
    background: var(--scroll-pill);
    opacity: 0;
    pointer-events: none;
    touch-action: none;
    transition: opacity 200ms ease, background-color 120ms ease;
  }

  /* A wider invisible grab area makes the 5px pill easy to drag. */
  .pill::before {
    content: '';
    position: absolute;
    inset: 0 -6px;
  }

  .pill.visible {
    opacity: 1;
    pointer-events: auto;
    cursor: grab;
  }

  .pill.active {
    background: var(--scroll-pill-hover);
  }

  @media (prefers-reduced-motion: reduce) {
    .pill {
      transition: none;
    }
  }
</style>
