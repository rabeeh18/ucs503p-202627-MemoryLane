// Pure helpers for the library map: view transform (zoom / pan / fit),
// find-a-topic dimming, and the side panel's selection state. No DOM here,
// so every rule is unit-tested (mapView.test.js).

/** World size the 0..1 layout is drawn into (wider than tall, like the canvas). */
export const WORLD = { width: 1400, height: 900 };

/** Zoom limits, relative to the "fit" scale. */
export const MIN_ZOOM = 0.6;
export const MAX_ZOOM = 8;

/** How much of the world must stay on screen when panning (px). */
const PAN_MARGIN = 80;

/**
 * Scale and offset that fit the whole world in the viewport with padding.
 * @param {{ width: number, height: number }} viewport
 * @returns {{ k: number, tx: number, ty: number }}
 */
export function fitView(viewport, world = WORLD, padding = 0.92) {
  const k = Math.max(1e-6, Math.min(viewport.width / world.width, viewport.height / world.height) * padding);
  return {
    k,
    tx: (viewport.width - world.width * k) / 2,
    ty: (viewport.height - world.height * k) / 2,
  };
}

/**
 * Keep zoom within limits and keep part of the world on screen.
 * @param {{ k: number, tx: number, ty: number }} view
 */
export function clampView(view, viewport, world = WORLD) {
  const fitK = fitView(viewport, world).k;
  const k = Math.min(fitK * MAX_ZOOM, Math.max(fitK * MIN_ZOOM, view.k));
  const clampAxis = (t, size, worldSize) => {
    const content = worldSize * k;
    if (content <= size) {
      // Smaller than the viewport: keep it fully visible.
      return Math.min(size - content, Math.max(0, t));
    }
    // Larger: never pan so far that less than PAN_MARGIN of it remains.
    return Math.min(size - PAN_MARGIN, Math.max(PAN_MARGIN - content, t));
  };
  return {
    k,
    tx: clampAxis(view.tx, viewport.width, world.width),
    ty: clampAxis(view.ty, viewport.height, world.height),
  };
}

/** Zoom by `factor` keeping the screen point `at` fixed, then clamp. */
export function zoomAt(view, factor, at, viewport, world = WORLD) {
  const target = clampView({ ...view, k: view.k * factor }, viewport, world);
  const k = target.k;
  const wx = (at.x - view.tx) / view.k;
  const wy = (at.y - view.ty) / view.k;
  return clampView({ k, tx: at.x - wx * k, ty: at.y - wy * k }, viewport, world);
}

/** Pan by a screen delta, then clamp. */
export function panBy(view, dx, dy, viewport, world = WORLD) {
  return clampView({ ...view, tx: view.tx + dx, ty: view.ty + dy }, viewport, world);
}

/** World coordinates of a 0..1 layout point. */
export function toWorld(x, y, world = WORLD) {
  return { x: x * world.width, y: y * world.height };
}

/** Screen coordinates of a world point. */
export function toScreen(point, view) {
  return { x: point.x * view.k + view.tx, y: point.y * view.k + view.ty };
}

/** View that frames one topic's ellipse (with room for its label). */
export function viewForTopic(topic, viewport, world = WORLD) {
  const w = topic.rx * 2 * world.width * 1.6;
  const h = topic.ry * 2 * world.height * 1.8;
  const fitK = fitView(viewport, world).k;
  const k = Math.min(fitK * MAX_ZOOM, Math.max(fitK, Math.min(viewport.width / w, viewport.height / h)));
  const c = toWorld(topic.x, topic.y, world);
  return clampView({ k, tx: viewport.width / 2 - c.x * k, ty: viewport.height / 2 - c.y * k }, viewport, world);
}

/** Linear interpolation between two views (t in 0..1, eased by the caller). */
export function lerpView(a, b, t) {
  return { k: a.k + (b.k - a.k) * t, tx: a.tx + (b.tx - a.tx) * t, ty: a.ty + (b.ty - a.ty) * t };
}

export const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

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

/**
 * World-space box around everything drawn (topic ellipses with room for their
 * labels, and every page), so "fit" frames the content rather than the whole
 * 0..1 layout box.
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
    add((t.x - t.rx) * world.width, (t.y - t.ry) * world.height - labelRoom);
    add((t.x + t.rx) * world.width, (t.y + t.ry) * world.height);
  }
  for (const p of map?.pages || []) add(p.x * world.width, p.y * world.height);
  if (!Number.isFinite(minX)) return { x: 0, y: 0, width: world.width, height: world.height };
  const pad = 40;
  return { x: minX - pad, y: minY - pad, width: maxX - minX + pad * 2, height: maxY - minY + pad * 2 };
}

/** Fit a world-space box (e.g. contentBounds) into the viewport, then clamp. */
export function fitBounds(bounds, viewport, world = WORLD, padding = 0.95) {
  const fitK = fitView(viewport, world).k;
  const k = Math.min(fitK * MAX_ZOOM, Math.max(fitK,
    Math.min(viewport.width / bounds.width, viewport.height / bounds.height) * padding));
  const cx = bounds.x + bounds.width / 2;
  const cy = bounds.y + bounds.height / 2;
  return clampView({ k, tx: viewport.width / 2 - cx * k, ty: viewport.height / 2 - cy * k }, viewport, world);
}
