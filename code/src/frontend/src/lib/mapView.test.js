import { describe, expect, it } from 'vitest';
import {
  EMPTY_PANEL, MAX_ZOOM, MIN_ZOOM, WORLD, clampView, dotState, findState, fitView, listSections,
  neighboursOf, panBy, panelReducer, viewForTopic, zoomAt,
} from './mapView.js';

const viewport = { width: 1000, height: 600 };

describe('zoom and pan clamping', () => {
  it('fits the world centred in the viewport', () => {
    const v = fitView(viewport);
    expect(WORLD.width * v.k).toBeLessThanOrEqual(viewport.width);
    expect(WORLD.height * v.k).toBeLessThanOrEqual(viewport.height);
    expect(v.tx).toBeCloseTo((viewport.width - WORLD.width * v.k) / 2);
    expect(v.ty).toBeCloseTo((viewport.height - WORLD.height * v.k) / 2);
  });

  it('clamps zoom between the min and max relative to fit', () => {
    const fitK = fitView(viewport).k;
    expect(clampView({ k: fitK * 100, tx: 0, ty: 0 }, viewport).k).toBeCloseTo(fitK * MAX_ZOOM);
    expect(clampView({ k: fitK / 100, tx: 0, ty: 0 }, viewport).k).toBeCloseTo(fitK * MIN_ZOOM);
  });

  it('keeps a small world fully on screen', () => {
    const fit = fitView(viewport);
    const v = panBy(fit, 5000, -5000, viewport);
    expect(v.tx + WORLD.width * v.k).toBeLessThanOrEqual(viewport.width + 1e-6);
    expect(v.ty).toBeGreaterThanOrEqual(0);
  });

  it('keeps part of a zoomed-in world on screen when panning far', () => {
    const zoomed = { ...fitView(viewport), k: fitView(viewport).k * 4 };
    const right = panBy(zoomed, 1e6, 0, viewport);
    expect(right.tx).toBeLessThanOrEqual(viewport.width - 80);
    const left = panBy(zoomed, -1e6, 0, viewport);
    expect(left.tx + WORLD.width * left.k).toBeGreaterThanOrEqual(80);
  });

  it('zooms around the cursor', () => {
    const fit = fitView(viewport);
    const at = { x: 300, y: 200 };
    const worldBefore = { x: (at.x - fit.tx) / fit.k, y: (at.y - fit.ty) / fit.k };
    const v = zoomAt(fit, 2, at, viewport);
    expect((at.x - v.tx) / v.k).toBeCloseTo(worldBefore.x, 0);
    expect((at.y - v.ty) / v.k).toBeCloseTo(worldBefore.y, 0);
    expect(v.k).toBeCloseTo(fit.k * 2);
  });

  it('frames a topic, zooming in but within limits', () => {
    const topic = { x: 0.3, y: 0.4, rx: 0.08, ry: 0.06 };
    const v = viewForTopic(topic, viewport);
    const fitK = fitView(viewport).k;
    expect(v.k).toBeGreaterThan(fitK);
    expect(v.k).toBeLessThanOrEqual(fitK * MAX_ZOOM);
    const cx = topic.x * WORLD.width * v.k + v.tx;
    expect(cx).toBeCloseTo(viewport.width / 2, -1);
  });
});

describe('find a topic', () => {
  const result = {
    topics: [{ id: 't1', label: 'Machine learning', score: 0.7 }, { id: 't2', label: 'Search', score: 0.6 }],
    pages: ['a', 'b'],
  };

  it('is inactive for an empty query', () => {
    expect(findState('  ', result)).toEqual({ active: false, best: null, matchIds: new Set(), message: '' });
    expect(findState('x', null).active).toBe(false);
  });

  it('names the closest topic and collects matches', () => {
    const f = findState('neural nets', result);
    expect(f.best.id).toBe('t1');
    expect(f.message).toBe('Closest: Machine learning');
    expect([...f.matchIds]).toEqual(['a', 'b']);
  });

  it('says when nothing matches', () => {
    expect(findState('zebra', { topics: [], pages: [] }).message).toBe('No topic matches');
  });

  it('dims non-matching pages and brightens matches', () => {
    const find = findState('neural nets', result);
    expect(dotState({ id: 'a', topic: 't1' }, { find })).toBe('match');
    expect(dotState({ id: 'z', topic: 't1' }, { find })).toBe('dim');
  });

  it('restores everything when cleared', () => {
    const find = findState('', result);
    expect(dotState({ id: 'z', topic: 't1' }, { find })).toBe('normal');
    expect(dotState({ id: 'o', topic: null }, { find })).toBe('outlier');
  });

  it('selection beats find state', () => {
    const find = findState('neural nets', result);
    expect(dotState({ id: 'z', topic: 't1' }, { find, selectedId: 'z' })).toBe('selected');
    expect(dotState({ id: 'y', topic: 't1' }, { find, neighbourIds: new Set(['y']) })).toBe('neighbour');
  });

  it('a selected topic brightens its pages', () => {
    expect(dotState({ id: 'a', topic: 't1' }, { topicId: 't1' })).toBe('match');
    expect(dotState({ id: 'b', topic: 't2' }, { topicId: 't1' })).toBe('normal');
  });

  it('finds the neighbours of a page from its edges', () => {
    const edges = [{ a: 'x', b: 'y' }, { a: 'z', b: 'x' }, { a: 'y', b: 'z' }];
    expect([...neighboursOf('x', edges)].sort()).toEqual(['y', 'z']);
    expect(neighboursOf(null, edges).size).toBe(0);
  });
});

describe('panel state reducer', () => {
  it('selects a page, a topic, or nothing', () => {
    let s = panelReducer(EMPTY_PANEL, { type: 'page', id: 'p1', topicId: 't1' });
    expect(s).toEqual({ mode: 'page', pageId: 'p1', topicId: 't1' });
    s = panelReducer(s, { type: 'topic', id: 't2' });
    expect(s).toEqual({ mode: 'topic', pageId: null, topicId: 't2' });
    s = panelReducer(s, { type: 'clear' });
    expect(s).toBe(EMPTY_PANEL);
  });

  it('ignores empty ids and unknown actions', () => {
    expect(panelReducer(EMPTY_PANEL, { type: 'page', id: null })).toBe(EMPTY_PANEL);
    const s = { mode: 'topic', pageId: null, topicId: 't' };
    expect(panelReducer(s, { type: 'nope' })).toBe(s);
  });

  it('keeps or drops the selection when a new map arrives', () => {
    const map = { pages: [{ id: 'p1', topic: 't9' }], topics: [{ id: 't9' }] };
    expect(panelReducer({ mode: 'page', pageId: 'p1', topicId: 't1' }, { type: 'map', ...map }))
      .toEqual({ mode: 'page', pageId: 'p1', topicId: 't9' });
    expect(panelReducer({ mode: 'page', pageId: 'gone', topicId: null }, { type: 'map', ...map })).toBe(EMPTY_PANEL);
    expect(panelReducer({ mode: 'topic', pageId: null, topicId: 't1' }, { type: 'map', ...map })).toBe(EMPTY_PANEL);
    const keep = { mode: 'topic', pageId: null, topicId: 't9' };
    expect(panelReducer(keep, { type: 'map', ...map })).toBe(keep);
  });
});

describe('list view sections', () => {
  it('lists topics in order with unclustered pages last under Other', () => {
    const map = {
      topics: [{ id: 't1', label: 'A' }, { id: 't2', label: 'B' }],
      pages: [{ id: 'p1', topic: 't2' }, { id: 'p2', topic: null }, { id: 'p3', topic: 't1' }],
    };
    expect(listSections(map)).toEqual([
      { id: 't1', label: 'A', pages: [{ id: 'p3', topic: 't1' }] },
      { id: 't2', label: 'B', pages: [{ id: 'p1', topic: 't2' }] },
      { id: null, label: 'Other', pages: [{ id: 'p2', topic: null }] },
    ]);
  });
});

describe('fit, clamp and pan into view', () => {
  const map = {
    topics: [{ x: 0.2, y: 0.4, rx: 0.06, ry: 0.05, label: 'A', count: 10 }],
    pages: [{ x: 0.18, y: 0.4 }, { x: 0.3, y: 0.45 }],
  };

  it('fits the content bounding box centred on both axes with 48px padding', async () => {
    const { contentBounds, fitBounds, FIT_PADDING } = await import('./mapView.js');
    const b = contentBounds(map);
    const v = fitBounds(b, viewport);
    const left = b.x * v.k + v.tx;
    const right = (b.x + b.width) * v.k + v.tx;
    const top = b.y * v.k + v.ty;
    const bottom = (b.y + b.height) * v.k + v.ty;
    expect((left + right) / 2).toBeCloseTo(viewport.width / 2, 5);
    expect((top + bottom) / 2).toBeCloseTo(viewport.height / 2, 5);
    // The tighter axis touches the padding exactly.
    expect(Math.min(left, top, viewport.width - right, viewport.height - bottom)).toBeCloseTo(FIT_PADDING, 5);
  });

  it('clamping against the content box keeps off-centre content centred', async () => {
    const { contentBounds, fitBounds } = await import('./mapView.js');
    const b = contentBounds(map); // content sits in the left part of the world
    const v = fitBounds(b, viewport);
    expect(clampView(v, viewport, b)).toEqual(v);
  });

  it('pans the least needed to bring a dot out from under the panel', async () => {
    const { panIntoView } = await import('./mapView.js');
    const view = { k: 1, tx: 0, ty: 0 };
    const area = { x0: 0, y0: 0, x1: 1000 - 452, y1: 600 };
    const under = { x0: 800, y0: 300, x1: 810, y1: 310 };
    const moved = panIntoView(view, under, area);
    expect(810 + moved.tx).toBe(area.x1 - 24);
    expect(moved.ty).toBe(0);
    expect(moved.k).toBe(1);
    // Already visible: unchanged.
    expect(panIntoView(view, { x0: 100, y0: 100, x1: 110, y1: 110 }, area)).toBe(view);
  });

  it('prefers keeping the left/top edge visible when the rect is too big', async () => {
    const { panIntoView } = await import('./mapView.js');
    const moved = panIntoView({ k: 1, tx: 0, ty: 0 }, { x0: -50, y0: 10, x1: 2000, y1: 20 }, { x0: 0, y0: 0, x1: 500, y1: 600 });
    expect(-50 + moved.tx).toBe(24);
  });
});

describe('semantic zoom, dots and links', () => {
  it('dims large libraries at the fitted zoom and brightens past 1.6x', async () => {
    const { detailLevel } = await import('./mapView.js');
    expect(detailLevel(1, 100)).toBe(1);
    expect(detailLevel(1, 278)).toBeCloseTo(0.45);
    expect(detailLevel(1.3, 278)).toBeGreaterThan(0.45);
    expect(detailLevel(1.6, 278)).toBe(1);
    expect(detailLevel(4, 2000)).toBe(1);
  });

  it('uses smaller dots for big topics and unclustered pages', async () => {
    const { dotRadius } = await import('./mapView.js');
    expect(dotRadius({ topic: 't' }, 39)).toBe(2.5);   // 5px
    expect(dotRadius({ topic: 't' }, 40)).toBe(1.75);  // 3.5px
    expect(dotRadius({ topic: null }, 0)).toBeLessThan(1.75);
  });

  it("draws only the hovered or selected topic's links and the selected page's links", async () => {
    const { visibleEdges } = await import('./mapView.js');
    const topicOf = new Map([['a', 't1'], ['b', 't1'], ['c', 't2'], ['d', 't2']]);
    const edges = [{ a: 'a', b: 'b' }, { a: 'c', b: 'd' }];
    expect(visibleEdges(edges, topicOf, {})).toEqual([]);
    expect(visibleEdges(edges, topicOf, { hoverTopicId: 't2' })).toEqual([{ a: 'c', b: 'd' }]);
    expect(visibleEdges(edges, topicOf, { selectedTopicId: 't1' })).toEqual([{ a: 'a', b: 'b' }]);
    expect(visibleEdges(edges, topicOf, { selectedPageId: 'd' })).toEqual([{ a: 'c', b: 'd' }]);
  });

  it('links topic ovals edge to edge', async () => {
    const { ovalLink } = await import('./mapView.js');
    const a = { x: 0.25, y: 0.5, rx: 0.05, ry: 0.05 };
    const b = { x: 0.75, y: 0.5, rx: 0.05, ry: 0.05 };
    const l = ovalLink(a, b);
    expect(l.x1).toBeCloseTo(0.3 * WORLD.width);
    expect(l.x2).toBeCloseTo(0.7 * WORLD.width);
    expect(l.y1).toBeCloseTo(0.5 * WORLD.height);
  });
});
