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

describe('fit to content', () => {
  it('frames the drawn content, never zooming out past the whole-world fit', async () => {
    const { contentBounds, fitBounds } = await import('./mapView.js');
    const map = { topics: [{ x: 0.4, y: 0.5, rx: 0.1, ry: 0.07 }], pages: [{ x: 0.42, y: 0.5 }, { x: 0.6, y: 0.55 }] };
    const b = contentBounds(map);
    expect(b.x).toBeLessThan(0.3 * WORLD.width);
    expect(b.x + b.width).toBeGreaterThan(0.6 * WORLD.width);
    const v = fitBounds(b, viewport);
    expect(v.k).toBeGreaterThan(fitView(viewport).k);
    // The content centre lands in the viewport centre.
    expect((b.x + b.width / 2) * v.k + v.tx).toBeCloseTo(viewport.width / 2, 0);
  });

  it('falls back to the whole world when empty', async () => {
    const { contentBounds } = await import('./mapView.js');
    expect(contentBounds({ topics: [], pages: [] })).toEqual({ x: 0, y: 0, width: WORLD.width, height: WORLD.height });
  });
});
