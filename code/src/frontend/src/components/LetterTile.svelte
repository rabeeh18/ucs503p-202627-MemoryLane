<script>
  /** Domain the letter comes from ("www." is ignored). */
  export let domain = '';
  export let size = 28;

  $: letter = (domain || '?').replace(/^www\./, '').charAt(0).toUpperCase() || '?';
</script>

<span class="tile" style="--size: {size}px" aria-hidden="true">{letter}</span>

<style>
  .tile {
    flex: none;
    width: var(--size);
    height: var(--size);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: calc(var(--size) / 4);
    color: var(--text-2);
    font-size: calc(var(--size) * 0.43);
  }
</style>
