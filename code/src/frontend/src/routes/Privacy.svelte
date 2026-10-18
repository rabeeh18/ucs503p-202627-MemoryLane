<script>
  import Header from '../components/Header.svelte';
  import { session } from '../auth.js';
</script>

<Header signedOut={!$session} />

<main class="privacy">
  <h1>Privacy</h1>

  <h2>What's stored</h2>
  <p>The URL, title and cleaned text of pages you save, and when you saved them.</p>

  <h2>Who can see it</h2>
  <p>Only your account. Every search, summary and listing is limited to the pages you saved.</p>

  <h2>What's sent to Google Gemini</h2>
  <p>A page's text, and only when you press Summarise on that page.</p>

  <h2>Export or delete</h2>
  <p>Use <strong>Export my data</strong> or <strong>Delete all my data</strong> in the account menu at the top right.</p>

  <h2>Automatic capture</h2>
  <p>
    The browser extension can save pages automatically as you browse. It is off by default and is
    turned on and off in the extension, where you can also exclude any site.
  </p>
</main>

<style>
  .privacy {
    flex: 1;
    width: 100%;
    max-width: 640px;
    margin: 0 auto;
    padding: 48px 32px 64px;
  }

  h1 {
    margin: 0 0 8px;
    font-size: 28px;
    font-weight: 500;
  }

  h2 {
    margin: 32px 0 6px;
    font-size: 15px;
    font-weight: 500;
  }

  p {
    margin: 0;
    font-size: 15px;
    line-height: 1.6;
    color: var(--text-2);
  }

  strong {
    font-weight: 500;
    color: var(--text);
  }

  @media (max-width: 640px) {
    .privacy {
      padding: 32px 16px 48px;
    }
  }
</style>
