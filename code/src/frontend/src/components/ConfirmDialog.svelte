<script>
  import { createEventDispatcher, onMount } from 'svelte';

  export let message = '';
  export let confirmLabel = 'Confirm';
  export let busy = false;
  export let error = '';

  const dispatch = createEventDispatcher();
  let dialog;
  let cancelButton;

  onMount(() => {
    dialog.showModal();
    cancelButton.focus();
  });

  function cancel() {
    if (!busy) dispatch('cancel');
  }
</script>

<!-- Native <dialog>: focus is trapped and Esc fires `cancel`. -->
<dialog bind:this={dialog} aria-labelledby="confirm-message" on:cancel|preventDefault={cancel}>
  <p id="confirm-message" class="message">{message}</p>
  {#if error}
    <p class="error" role="alert">{error}</p>
  {/if}
  <div class="actions">
    <button bind:this={cancelButton} type="button" class="btn btn-outline" on:click={cancel} disabled={busy}>
      Cancel
    </button>
    <button type="button" class="btn btn-primary" on:click={() => dispatch('confirm')} disabled={busy}>
      {busy ? 'Deleting…' : confirmLabel}
    </button>
  </div>
</dialog>

<style>
  dialog {
    width: min(420px, calc(100vw - 32px));
    padding: 24px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--text);
  }

  dialog::backdrop {
    background: rgba(0, 0, 0, 0.6);
  }

  .message {
    margin: 0;
    font-size: 15px;
    line-height: 1.5;
  }

  .error {
    margin: 12px 0 0;
    font-size: 13px;
    color: var(--text-2);
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 24px;
  }

  .actions .btn {
    height: 40px;
    padding: 0 16px;
  }
</style>
