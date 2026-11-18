// Meaning-based docs search, added on top of the theme's keyword search.
//
// Nothing loads with the page. The first time the search box gets focus, the
// model files (~8 MB, built by hooks/semantic_search.py) are fetched; keyword
// results keep working meanwhile. Each query is then embedded in the browser in a
// few milliseconds and fused with the keyword results (Reciprocal Rank Fusion),
// and the best matches are shown above the theme's own list.
import { embed, fuse, loadModel, loadSections, rankByMeaning } from './semantic-core.js';

const SITE_ROOT = new URL('../../', import.meta.url);
const FILES = new URL('assets/semantic/', SITE_ROOT);
const MIN_QUERY_CHARS = 3;
const MIN_SIMILARITY = 0.35; // meaning-only matches weaker than this are left out
const SHOWN = 5;

let loading = null;
let model = null;
let sections = null;
let failed = false;

function loadFiles() {
  if (!loading) {
    loading = (async () => {
      const manifest = await (await fetch(new URL('manifest.json', FILES))).json();
      const get = (name) => fetch(new URL(name, FILES)).then((r) => {
        if (!r.ok) throw new Error(`${name}: ${r.status}`);
        return r;
      });
      const [vocab, table, scales, list] = await Promise.all([
        get(manifest.vocab).then((r) => r.text()),
        get(manifest.table).then((r) => r.arrayBuffer()),
        get(manifest.scales).then((r) => r.arrayBuffer()),
        get(manifest.sections).then((r) => r.json()),
      ]);
      model = loadModel(vocab, table, scales, manifest.dims, manifest.max_tokens);
      sections = loadSections(list);
    })().catch((err) => {
      failed = true;
      console.warn('Meaning-based search is unavailable:', err);
    }).finally(render);
  }
  return loading;
}

const input = () => document.querySelector('.md-search__input');

/** Our block, kept as the first child of the theme's results panel. */
function block() {
  const results = document.querySelector('.md-search-result');
  if (!results) return null;
  let el = results.querySelector(':scope > .ml-semantic');
  if (!el) {
    el = document.createElement('div');
    el.className = 'ml-semantic';
    el.setAttribute('aria-live', 'polite');
    results.prepend(el);
  }
  return el;
}

/** Locations of the theme's keyword results, in order ("page/#section"). */
function keywordLocations() {
  return [...document.querySelectorAll('.md-search-result__list a.md-search-result__link')]
    .map((a) => {
      const url = new URL(a.getAttribute('href'), location.href);
      return url.href.startsWith(SITE_ROOT.href) ? url.href.slice(SITE_ROOT.href.length) : null;
    })
    .filter(Boolean);
}

function render() {
  const el = block();
  if (!el) return;
  const query = (input()?.value || '').trim();
  el.replaceChildren();
  if (query.length < MIN_QUERY_CHARS || failed) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  const heading = document.createElement('div');
  heading.className = 'ml-semantic__heading';
  el.append(heading);
  if (!model) {
    heading.textContent = 'Loading meaning-based search…';
    return;
  }
  const vector = embed(query, model);
  const matches = vector
    ? fuse(rankByMeaning(vector, sections, 30), keywordLocations(), { limit: SHOWN, minSimilarity: MIN_SIMILARITY })
    : [];
  if (!matches.length) {
    el.hidden = true;
    return;
  }
  heading.textContent = 'Best matches, by meaning and keywords';
  const list = document.createElement('ol');
  list.className = 'ml-semantic__list';
  for (const match of matches) {
    const item = document.createElement('li');
    const link = document.createElement('a');
    link.className = 'ml-semantic__link';
    link.href = new URL(match.location, SITE_ROOT).href;
    const title = document.createElement('span');
    title.className = 'ml-semantic__title';
    title.textContent = match.title || match.page;
    link.append(title);
    if (match.page) {
      const page = document.createElement('span');
      page.className = 'ml-semantic__page';
      page.textContent = match.page;
      link.append(page);
    }
    if (match.snippet) {
      const snippet = document.createElement('span');
      snippet.className = 'ml-semantic__snippet';
      snippet.textContent = match.snippet;
      link.append(snippet);
    }
    item.append(link);
    list.append(item);
  }
  el.append(list);
}

let queued = false;
function scheduleRender() {
  if (queued) return;
  queued = true;
  requestAnimationFrame(() => {
    queued = false;
    render();
  });
}

function start() {
  const box = input();
  if (!box) return;
  box.addEventListener('focus', loadFiles);
  box.addEventListener('input', () => {
    loadFiles();
    scheduleRender();
  });
  // The theme renders keyword results asynchronously: re-fuse when they change.
  const list = document.querySelector('.md-search-result__list');
  if (list) new MutationObserver(scheduleRender).observe(list, { childList: true });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
else start();
