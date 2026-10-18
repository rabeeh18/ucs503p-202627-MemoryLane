<script>
  import { deleteToasts, pageDeletes } from '../pageDeletes.js';
</script>

<div class="toasts" role="status" aria-live="polite">
  {#each $deleteToasts as toast (toast.id)}
    <div class="toast" class:error={toast.kind === 'error'}>
      {#if toast.kind === 'undo'}
        <span>{toast.message}</span>
        <span aria-hidden="true">·</span>
        <button type="button" class="undo" on:click={() => pageDeletes.undo(toast.pageId)}>Undo</button>
      {:else}
        <span>{toast.message}</span>
        <button
          type="button"
          class="close"
          aria-label="Dismiss"
          on:click={() => pageDeletes.dismissToast(toast.id)}
        >×</button>
      {/if}
    </div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    left: 50%;
    bottom: 24px;
    transform: translateX(-50%);
    z-index: 50;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    pointer-events: none;
  }

  .toast {
    pointer-events: auto;
    display: flex;
    align-items: center;
    gap: 8px;
    max-width: calc(100vw - 32px);
    min-height: 44px;
    padding: 0 8px 0 16px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
    font-size: 14px;
  }

  .toast.error {
    padding-right: 4px;
  }

  .undo,
  .close {
    min-height: 36px;
    padding: 0 8px;
    border: 0;
    border-radius: var(--radius-xs);
    background: none;
    color: var(--text);
    font-weight: 500;
  }

  .undo:hover,
  .close:hover {
    background: var(--surface-active);
  }

  .close {
    color: var(--text-2);
    font-size: 18px;
    line-height: 1;
  }
</style>
