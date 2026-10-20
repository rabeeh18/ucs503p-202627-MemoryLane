// Pure helpers for the library map: view transform (zoom / pan / fit),
// semantic zoom, which links to draw, find-a-topic dimming, and the side
// panel's selection state. No DOM here, so every rule is unit-tested
// (mapView.test.js).

/** World size the 0..1 layout is drawn into (wider than tall, like the canvas). */
export const WORLD = { width: 1400, height: 900 };

/** Zoom limits, relative to the "fit" scale. */
export const MIN_ZOOM = 0.6;
export const MAX_ZOOM = 8;

/** Padding around the content when fitting (px). */
export const FIT_PADDING = 48;

/** How much of the content must stay on screen when panning (px). */
const PAN_MARGIN = 80;

/** Semantic zoom: past this zoom (relative to fit) dots and links are at full strength. */
export const DETAIL_ZOOM = 1.6;
/** Libraries larger than this start dimmed at the fitted zoom. */
export const DENSE_PAGES = 150;

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/** The whole world as a box. */
export function worldBox(world = WORLD) {
  return { x: 0, y: 0, width: world.width, height: world.height };
}

/** Scale that fits `box` in the viewport with `padding` px on every side. */
export function fitScale(box, viewport, padding = FIT_PADDING) {
  const w = Math.max(1, viewport.width - 2 * padding);
  const h = Math.max(1, viewport.height - 2 * padding);
  return Math.max(1e-6, Math.min(w / Math.max(box.width, 1e-6), h / Math.max(box.height, 1e-6)));
}

/** Fit `box` centred in the viewport (both axes) with padding. */
export function fitBounds(box, viewport, padding = FIT_PADDING) {
  const k = fitScale(box, viewport, padding);
  return {
    k,
    tx: viewport.width / 2 - (box.x + box.width / 2) * k,
    ty: viewport.height / 2 - (box.y + box.height / 2) * k,
  };
}

/** Fit the whole world (kept for callers without content bounds). */
export function fitView(viewport, world = WORLD, padding = FIT_PADDING) {
  return fitBounds(worldBox(world), viewport, padding);
}

/**
 * Keep zoom within limits (relative to fitting `box`) and keep `box` on screen:
 * fully, when it is smaller than the viewport; otherwise at least PAN_MARGIN of it.
 * @param {{ k: number, tx: number, ty: number }} view
 */
export function clampView(view, viewport, box = worldBox()) {
  const fitK = fitScale(box, viewport);
  const k = clamp(view.k, fitK * MIN_ZOOM, fitK * MAX_ZOOM);
  const axis = (t, size, start, length) => {
    const content = length * k;
    if (content <= size) return clamp(t, -start * k, size - content - start * k);
    return clamp(t, PAN_MARGIN - (start + length) * k, size - PAN_MARGIN - start * k);
  };
  return { k, tx: axis(view.tx, viewport.width, box.x, box.width), ty: axis(view.ty, viewport.height, box.y, box.height) };
}

/** Zoom by `factor` keeping the screen point `at` fixed, then clamp. */
export function zoomAt(view, factor, at, viewport, box = worldBox()) {
  const k = clampView({ ...view, k: view.k * factor }, viewport, box).k;
  const wx = (at.x - view.tx) / view.k;
  const wy = (at.y - view.ty) / view.k;
  return clampView({ k, tx: at.x - wx * k, ty: at.y - wy * k }, viewport, box);
}

/** Pan by a screen delta, then clamp. */
export function panBy(view, dx, dy, viewport, box = worldBox()) {
  return clampView({ ...view, tx: view.tx + dx, ty: view.ty + dy }, viewport, box);
}

/** World coordinates of a 0..1 layout point. */
export function toWorld(x, y, world = WORLD) {
  return { x: x * world.width, y: y * world.height };
}

/** Screen coordinates of a world point. */
export function toScreen(point, view) {
  return { x: point.x * view.k + view.tx, y: point.y * view.k + view.ty };
}

/** View that frames one topic's ellipse (with room for its label), zoomed in. */
export function viewForTopic(topic, viewport, box = worldBox(), world = WORLD, area = null) {
  const w = topic.rx * 2 * world.width * 1.5;
  const h = topic.ry * 2 * world.height * 1.9;
  const visible = area || { x0: 0, y0: 0, x1: viewport.width, y1: viewport.height };
  const vw = visible.x1 - visible.x0;
  const vh = visible.y1 - visible.y0;
  const fitK = fitScale(box, viewport);
  const k = clamp(Math.min(vw / w, vh / h), fitK, fitK * MAX_ZOOM);
  const c = toWorld(topic.x, topic.y, world);
  return clampView({
    k,
    tx: (visible.x0 + visible.x1) / 2 - c.x * k,
    ty: (visible.y0 + visible.y1) / 2 - c.y * k,
  }, viewport, box);
}

/**
 * Smallest pan that brings a screen rectangle inside the visible area (the
 * canvas minus whatever the panel covers), with a margin. The zoom is unchanged.
 * @param {{ x0: number, y0: number, x1: number, y1: number }} rect
 * @param {{ x0: number, y0: number, x1: number, y1: number }} area
 */
export function panIntoView(view, rect, area, margin = 24) {
  const shift = (lo, hi, aLo, aHi) => {
    let d = 0;
    if (hi > aHi - margin) d = aHi - margin - hi;
    if (lo + d < aLo + margin) d = aLo + margin - lo;
    return d;
  };
  const dx = shift(rect.x0, rect.x1, area.x0, area.x1);
  const dy = shift(rect.y0, rect.y1, area.y0, area.y1);
  return dx || dy ? { ...view, tx: view.tx + dx, ty: view.ty + dy } : view;
}

/** Linear interpolation between two views (t in 0..1, eased by the caller). */
export function lerpView(a, b, t) {
  return { k: a.k + (b.k - a.k) * t, tx: a.tx + (b.tx - a.tx) * t, ty: a.ty + (b.ty - a.ty) * t };
}

export const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

/**
 * World-space box around everything drawn (topic ellipses with room for their
 * labels, and every page), so "Fit" frames the content, not the 0..1 box.
 */
export function contentBounds(map, world = WORLD, labelRoom = 34) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const add = (x, y) => {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  };
  for (const t of map?.topics || []) {
    const labelHalf = (`${t.label || ''} · ${t.count} pages`.length * 7.4) / 2;
    const cx = t.x * world.width;
    add(Math.min(cx - t.rx * world.width, cx - labelHalf), (t.y - t.ry) * world.height - labelRoom);
    add(Math.max(cx + t.rx * world.width, cx + labelHalf), (t.y + t.ry) * world.height);
  }
  for (const p of map?.pages || []) add(p.x * world.width, p.y * world.height);
  if (!Number.isFinite(minX)) return worldBox(world);
  return { x: minX, y: minY, width: Math.max(1, maxX - minX), height: Math.max(1, maxY - minY) };
}

// ---- semantic zoom and links ------------------------------------------------------

/**
 * Strength (0..1) of dots and links. Small libraries are always at full
 * strength; larger ones start dim at the fitted zoom and reach full strength
 * at DETAIL_ZOOM x the fitted zoom.
 */
export function detailLevel(zoomRatio, pageCount) {
  if (pageCount <= DENSE_PAGES) return 1;
  const t = clamp((zoomRatio - 1) / (DETAIL_ZOOM - 1), 0, 1);
  return 0.45 + 0.55 * t;
}

/** Dot radius in screen px: smaller dots for big topics and unclustered pages. */
export function dotRadius(page, topicCount) {
  if (!page.topic) return 1.5;
  return topicCount >= 40 ? 1.75 : 2.5;
}

/**
 * Which page links to draw: only the links inside the hovered or selected
 * topic, plus the selected page's own links.
 */
export function visibleEdges(edges, topicOf, { hoverTopicId = null, selectedTopicId = null, selectedPageId = null } = {}) {
  const topics = new Set([hoverTopicId, selectedTopicId].filter(Boolean));
  if (!topics.size && !selectedPageId) return [];
  return (edges || []).filter((e) => {
    if (selectedPageId && (e.a === selectedPageId || e.b === selectedPageId)) return true;
    const t = topicOf.get(e.a);
    return t && t === topicOf.get(e.b) && topics.has(t);
  });
}

/** Point where the ray from an ellipse's centre towards `toward` leaves the ellipse. */
function rim(cx, cy, rx, ry, toward) {
  const dx = toward.x - cx;
  const dy = toward.y - cy;
  const s = 1 / Math.sqrt((dx / rx) ** 2 + (dy / ry) ** 2 || 1);
  return { x: cx + dx * s, y: cy + dy * s };
}

/** A dashed link between two topic ovals, drawn edge to edge (world coords). */
export function ovalLink(a, b, world = WORLD) {
  const ca = toWorld(a.x, a.y, world);
  const cb = toWorld(b.x, b.y, world);
  const p = rim(ca.x, ca.y, a.rx * world.width, a.ry * world.height, cb);
  const q = rim(cb.x, cb.y, b.rx * world.width, b.ry * world.height, ca);
  return { x1: p.x, y1: p.y, x2: q.x, y2: q.y };
}

// ---- find a topic -----------------------------------------------------------------

/**
 * What the map shows for a "Find a topic" query.
 * @param {string} query
 * @param {{ topics: Array<{ id: string, label: string, score: number }>, pages: string[] } | null} result
 * @returns {{ active: boolean, best: { id: string, label: string } | null, matchIds: Set<string>, message: string }}
 */
export function findState(query, result) {
  if (!query || !query.trim() || !result) {
    return { active: false, best: null, matchIds: new Set(), message: '' };
  }
  const best = result.topics?.[0] || null;
  return {
    active: true,
    best,
    matchIds: new Set(result.pages || []),
    message: best ? `Closest: ${best.label}` : 'No topic matches',
  };
}

/**
 * How bright a dot is drawn.
 * @returns {'selected' | 'neighbour' | 'match' | 'dim' | 'normal' | 'outlier'}
 */
export function dotState(page, { selectedId = null, neighbourIds = new Set(), find = null, topicId = null } = {}) {
  if (page.id === selectedId) return 'selected';
  if (neighbourIds.has(page.id)) return 'neighbour';
  if (find?.active) return find.matchIds.has(page.id) ? 'match' : 'dim';
  if (topicId && page.topic === topicId) return 'match';
  return page.topic ? 'normal' : 'outlier';
}

/** Ids of pages joined to `pageId` by an edge. */
export function neighboursOf(pageId, edges) {
  const ids = new Set();
  if (!pageId) return ids;
  for (const e of edges || []) {
    if (e.a === pageId) ids.add(e.b);
    else if (e.b === pageId) ids.add(e.a);
  }
  return ids;
}

// ---- side panel ------------------------------------------------------------------

export const EMPTY_PANEL = Object.freeze({ mode: 'none', pageId: null, topicId: null });

/**
 * Panel selection state.
 * Actions: { type: 'page', id } | { type: 'topic', id } | { type: 'clear' }
 *        | { type: 'map', pages, topics }  (a new map arrived: drop what no longer exists)
 */
export function panelReducer(state, action) {
  switch (action.type) {
    case 'page':
      if (!action.id) return EMPTY_PANEL;
      return { mode: 'page', pageId: action.id, topicId: action.topicId ?? null };
    case 'topic':
      if (!action.id) return EMPTY_PANEL;
      return { mode: 'topic', pageId: null, topicId: action.id };
    case 'clear':
      return EMPTY_PANEL;
    case 'map': {
      const pages = new Map((action.pages || []).map((p) => [p.id, p]));
      if (state.mode === 'page') {
        const page = pages.get(state.pageId);
        return page ? { mode: 'page', pageId: page.id, topicId: page.topic ?? null } : EMPTY_PANEL;
      }
      if (state.mode === 'topic') {
        const topics = new Set((action.topics || []).map((t) => t.id));
        return topics.has(state.topicId) ? state : EMPTY_PANEL;
      }
      return state;
    }
    default:
      return state;
  }
}

/** Topics in List view: largest first, unclustered pages last under "Other". */
export function listSections(map) {
  if (!map?.topics) return [];
  const byTopic = new Map(map.topics.map((t) => [t.id, []]));
  const other = [];
  for (const page of map.pages || []) {
    (byTopic.get(page.topic) || other).push(page);
  }
  const sections = map.topics.map((t) => ({ id: t.id, label: t.label, pages: byTopic.get(t.id) }));
  if (other.length) sections.push({ id: null, label: 'Other', pages: other });
  return sections;
}

