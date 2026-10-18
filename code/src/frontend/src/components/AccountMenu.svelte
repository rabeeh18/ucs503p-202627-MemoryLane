<script>
  import { tick } from 'svelte';
  import ConfirmDialog from './ConfirmDialog.svelte';
  import { session, signOut } from '../auth.js';
  import { deleteAllData, exportData } from '../api.js';
  import { navigate } from '../lib/router.js';
  import { libraryVersion } from '../stores';

  let open = false;
  let button;
  let menu;
  let confirming = false;
  let deleting = false;
  let deleteError = '';
  let status = '';

  $: email = $session?.email || 'Account';

  function items() {
    return menu ? [...menu.querySelectorAll('[role="menuitem"]')] : [];
  }

  async function openMenu(focusIndex = 0) {
    open = true;
    await tick();
    items()[focusIndex]?.focus();
  }

  function closeMenu({ restoreFocus = true } = {}) {
    open = false;
    if (restoreFocus) button?.focus();
  }

  function onButtonKeydown(event) {
    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openMenu(0);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      openMenu(items().length - 1);
    }
  }

  function onMenuKeydown(event) {
    const list = items();
    const index = list.indexOf(document.activeElement);
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeMenu();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      list[(index + 1) % list.length]?.focus();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      list[(index - 1 + list.length) % list.length]?.focus();
    } else if (event.key === 'Home') {
      event.preventDefault();
      list[0]?.focus();
    } else if (event.key === 'End') {
      event.preventDefault();
      list[list.length - 1]?.focus();
    } else if (event.key === 'Tab') {
      closeMenu({ restoreFocus: false });
    }
  }

  function onWindowClick(event) {
    if (open && !menu?.contains(event.target) && !button?.contains(event.target)) {
      closeMenu({ restoreFocus: false });
    }
  }

  function goLibrary() {
    closeMenu({ restoreFocus: false });
    navigate('/library');
  }

  async function doExport() {
    closeMenu();
    status = 'Preparing your export…';
    try {
      await exportData();
      status = '';
    } catch {
      status = "Couldn't export your data. Try again.";
    }
  }

  function askDelete() {
    closeMenu({ restoreFocus: false });
    deleteError = '';
    confirming = true;
  }

  async function confirmDelete() {
    deleting = true;
    deleteError = '';
    try {
      await deleteAllData();
      confirming = false;
      libraryVersion.update((v) => v + 1);
      status = 'All saved pages were deleted.';
      button?.focus();
    } catch {
      deleteError = "Couldn't delete your data. Try again.";
    } finally {
      deleting = false;
    }
  }

  function cancelDelete() {
    confirming = false;
    button?.focus();
  }
</script>

<svelte:window on:click={onWindowClick} />

<div class="account">
  <button
    bind:this={button}
    type="button"
    class="account-button"
    aria-haspopup="menu"
    aria-expanded={open}
    aria-controls="account-menu"
    on:click={() => (open ? closeMenu() : openMenu())}
    on:keydown={onButtonKeydown}
  >
    {email}
  </button>

  {#if open}
    <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
    <div
      bind:this={menu}
      id="account-menu"
      class="menu"
      role="menu"
      tabindex="-1"
      aria-label="Account"
      on:keydown={onMenuKeydown}
    >
      <div class="menu-email" role="presentation">{email}</div>
      <button type="button" role="menuitem" tabindex="-1" on:click={goLibrary}>All saved pages</button>
      <button type="button" role="menuitem" tabindex="-1" on:click={doExport}>Export my data</button>
      <button type="button" role="menuitem" tabindex="-1" on:click={askDelete}>Delete all my data</button>
      <button type="button" role="menuitem" tabindex="-1" on:click={signOut}>Sign out</button>
    </div>
  {/if}

  <p class="visually-hidden" role="status">{status}</p>
  {#if status}
    <p class="toast" aria-hidden="true">{status}</p>
  {/if}
</div>

{#if confirming}
  <ConfirmDialog
    message="Delete all saved pages? This can't be undone."
    confirmLabel="Delete everything"
    busy={deleting}
    error={deleteError}
    on:confirm={confirmDelete}
    on:cancel={cancelDelete}
  />
{/if}

<style>
  .account {
    position: relative;
  }

  .account-button {
    max-width: 260px;
    min-height: 44px;
    padding: 0 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: transparent;
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .account-button:hover,
  .account-button[aria-expanded='true'] {
    background: var(--surface);
  }

  .menu {
    position: absolute;
    right: 0;
    top: calc(100% + 6px);
    z-index: 20;
    min-width: 220px;
    padding: 6px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
  }

  .menu-email {
    padding: 8px 10px 10px;
    margin-bottom: 4px;
    border-bottom: 1px solid var(--divider);
    font-size: 12px;
    color: var(--text-3);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .menu button {
    display: block;
    width: 100%;
    min-height: 40px;
    padding: 0 10px;
    border: 0;
    border-radius: var(--radius-xs);
    background: transparent;
    text-align: left;
    font-size: 14px;
  }

  .menu button:hover,
  .menu button:focus-visible {
    background: var(--surface-active);
  }

  .toast {
    position: absolute;
    right: 0;
    top: calc(100% + 8px);
    width: max-content;
    max-width: 260px;
    margin: 0;
    font-size: 12px;
    color: var(--text-3);
  }
</style>
