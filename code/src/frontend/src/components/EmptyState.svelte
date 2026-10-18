<div class="empty">
  <slot />
</div>

<style>
  .empty {
    padding: 28px 0;
    color: var(--text-2);
    font-size: 14px;
    line-height: 1.6;
    border-bottom: 1px solid var(--divider-soft);
  }
  .empty :global(a) {
    color: var(--text);
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .empty :global(strong) {
    font-weight: 500;
    color: var(--text);
  }
</style>
