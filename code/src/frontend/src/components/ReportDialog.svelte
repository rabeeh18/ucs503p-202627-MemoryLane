<script>
  import { onMount } from 'svelte';
  import { sendReport } from '../api.js';
  import { session } from '../auth.js';
  import { closeReport, currentPage } from '../report.js';

  /** @type {{ source: 'web' | 'extension', appVersion: string, lastError: string }} */
  export let setup;

  const MAX_CHARS = 4000;

  let dialog;
  let textarea;
  let message = '';
  let sending = false;
  let sent = false;
  let error = '';

  const page = currentPage();
  const userAgent = navigator.userAgent.slice(0, 400);

  $: email = $session?.email || '';
  $: appLabel = setup.source === 'extension' ? 'Extension' : 'Website';
  $: canSend = message.trim().length > 0 && !sending;

  onMount(() => {
    dialog.showModal();
    textarea.focus();
  });

  function close() {
    if (!sending) closeReport();
  }

  async function send() {
    if (!canSend) return;
    sending = true;
    error = '';
    try {
      await sendReport({
        message: message.trim(),
        source: setup.source,
        context: {
          app_version: setup.appVersion,
          page: setup.source === 'web' ? page : '',
          user_agent: userAgent,
          last_error: setup.lastError,
        },
      });
      sent = true;
    } catch (err) {
      error = err?.status === 429
        ? "You've sent several reports recently. Try again in an hour."
        : "Couldn't send your report. Try again.";
    } finally {
      sending = false;
    }
  }

  function onKeydown(event) {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      send();
    }
  }
</script>

<!-- Native <dialog>: focus is trapped and Esc fires `cancel`. -->
<dialog bind:this={dialog} aria-labelledby="report-title" on:cancel|preventDefault={close}>
  {#if sent}
    <h2 id="report-title">Thanks, your report was sent</h2>
    <p class="lede">
      {email ? `If we need more detail, we'll reply to ${email}.` : 'It will be looked at soon.'}
    </p>
    <div class="actions">
      <button type="button" class="btn btn-primary" on:click={closeReport}>Done</button>
    </div>
  {:else}
    <h2 id="report-title">Report a problem</h2>
    <form on:submit|preventDefault={send}>
      <label for="report-message">What went wrong?</label>
      <textarea
        bind:this={textarea}
        id="report-message"
        bind:value={message}
        maxlength={MAX_CHARS}
        rows="5"
        placeholder="What did you do, what did you expect, and what happened instead?"
        disabled={sending}
        on:keydown={onKeydown}
      ></textarea>

      <details>
        <summary>Sent with your report</summary>
        <dl>
          {#if email}<dt>Your email</dt><dd>{email}, so we can reply</dd>{/if}
          <dt>App</dt><dd>{appLabel}{setup.appVersion ? ` ${setup.appVersion}` : ''}</dd>
          {#if setup.source === 'web'}<dt>Page</dt><dd class="mono">{page}</dd>{/if}
          <dt>Browser</dt><dd class="ua">{userAgent}</dd>
          {#if setup.lastError}<dt>Last error</dt><dd>{setup.lastError}</dd>{/if}
        </dl>
        <p class="note">Your saved pages and searches are not included.</p>
      </details>

      {#if error}
        <p class="error" role="alert">{error}</p>
      {/if}

      <div class="actions">
        <button type="button" class="btn btn-outline" on:click={close} disabled={sending}>Cancel</button>
        <button type="submit" class="btn btn-primary" disabled={!canSend}>
          {sending ? 'Sending…' : 'Send report'}
        </button>
      </div>
    </form>
  {/if}
</dialog>

<style>
  dialog {
    width: min(480px, calc(100vw - 32px));
    padding: 24px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--text);
  }

  dialog::backdrop {
    background: rgba(0, 0, 0, 0.6);
  }

  h2 {
    margin: 0;
    font-size: 17px;
    font-weight: 500;
  }

  .lede {
    margin: 10px 0 0;
    font-size: 14px;
    line-height: 1.5;
    color: var(--text-2);
  }

  form {
    margin-top: 16px;
  }

  label {
    display: block;
    margin-bottom: 6px;
    font-size: 13px;
    color: var(--text-2);
  }

  textarea {
    display: block;
    width: 100%;
    min-height: 110px;
    padding: 10px 12px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--bg);
    color: var(--text);
    font: inherit;
    font-size: 14px;
    line-height: 1.5;
    resize: vertical;
  }

  textarea::placeholder {
    color: var(--text-3);
  }

  details {
    margin-top: 14px;
    font-size: 13px;
    color: var(--text-2);
  }

  summary {
    cursor: pointer;
    color: var(--text-2);
  }

  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 6px 12px;
    margin: 10px 0 0;
  }

  dt {
    color: var(--text-3);
  }

  dd {
    margin: 0;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .ua {
    font-size: 12px;
    color: var(--text-3);
  }

  .mono {
    font-family: var(--font-mono);
    font-size: 12px;
  }

  .note {
    margin: 10px 0 0;
    font-size: 12px;
    color: var(--text-3);
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
    margin-top: 20px;
  }

  .actions .btn {
    height: 40px;
    padding: 0 16px;
  }
</style>
