<script>
  // List view of the map: one section per topic (largest first), unclustered
  // pages last under "Other". Rows are the usual PageRow, delete included.
  import PageRow from '../PageRow.svelte';
  import { listSections } from '../../lib/mapView.js';
  import { link } from '../../lib/router.js';

  export let data;

  $: sections = listSections(data).filter((s) => s.pages.length);

  const toRow = (p) => ({ id: p.id, url: p.url, title: p.title, domain: p.domain, timestamp: p.saved_at });
</script>

<div class="list">
  {#each sections as section (section.id ?? 'other')}
    <section aria-labelledby="topic-{section.id ?? 'other'}">
      <div class="head">
        <h2 id="topic-{section.id ?? 'other'}">
          {section.label}<span class="count">{' · '}{section.pages.length} page{section.pages.length === 1 ? '' : 's'}</span>
        </h2>
        {#if section.id}
          <a href="/search?topic={encodeURIComponent(section.id)}&q=" use:link>Search within</a>
        {/if}
      </div>
      <ul>
        {#each section.pages as page (page.id)}
          <PageRow page={toRow(page)} />
        {/each}
      </ul>
    </section>
  {/each}
</div>

<style>
  .list {
    max-width: 800px;
    margin: 0 auto;
    padding: 8px 0 48px;
  }

  section + section {
    margin-top: 40px;
  }

  .head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--divider);
  }

  h2 {
    margin: 0;
    font-size: 15px;
    font-weight: 500;
  }

  .count {
    font-weight: 400;
    color: var(--text-3);
  }

  .head a {
    font-size: 13px;
  }

  ul {
    margin: 0;
    padding: 0;
  }
</style>
