<script>
  import Header from '../components/Header.svelte';
  import { signIn } from '../auth.js';
  import { link } from '../lib/router.js';

  const steps = [
    { n: '01', title: 'Save', text: 'Keep a page with one click from the extension.' },
    { n: '02', title: 'Search', text: 'Describe the idea, not the title.' },
    { n: '03', title: 'Rediscover', text: 'Open the page, or get a short summary first.' },
  ];
</script>

<Header signedOut />

<main class="landing">
  <h1>Find the page you saved, even when you forget its name.</h1>
  <p class="lede">Save pages as you browse. Search them later by meaning, not just exact words.</p>

  <div class="actions">
    <button type="button" class="btn btn-primary" on:click={() => signIn({ provider: 'Google' })}>
      Continue with Google
    </button>
    <button type="button" class="btn btn-outline" on:click={() => signIn({})}>Continue with email</button>
  </div>
  <p class="fine-print">
    Pages you save are stored on our servers and visible only to you. You can export or delete them any time.
    <a href="/privacy" use:link>Privacy</a>
  </p>

  <ol class="steps">
    {#each steps as step}
      <li>
        <div class="n mono">{step.n}</div>
        <div class="step-title">{step.title}</div>
        <div class="step-text">{step.text}</div>
      </li>
    {/each}
  </ol>
</main>

<style>
  .landing {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 120px 32px 40px;
    text-align: center;
  }

  h1 {
    margin: 0;
    max-width: 600px;
    font-size: 40px;
    font-weight: 500;
    line-height: 1.2;
    letter-spacing: -0.01em;
  }

  .lede {
    margin: 20px 0 0;
    max-width: 460px;
    font-size: 16px;
    line-height: 1.55;
    color: var(--text-2);
  }

  .actions {
    width: 100%;
    max-width: 340px;
    margin-top: 40px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .fine-print {
    margin: 16px 0 0;
    max-width: 340px;
    font-size: 12px;
    line-height: 1.5;
    color: var(--text-3);
  }

  .fine-print a {
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .steps {
    width: 100%;
    max-width: 640px;
    margin: 72px 0 0;
    padding: 0;
    display: flex;
    gap: 32px;
    text-align: left;
    list-style: none;
  }

  .steps li {
    flex: 1;
    border-top: 1px solid var(--divider);
    padding-top: 14px;
  }

  .n {
    font-size: 12px;
    color: var(--text-3);
  }

  .step-title {
    margin-top: 6px;
    font-size: 14px;
    font-weight: 500;
  }

  .step-text {
    margin-top: 4px;
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-2);
  }

  @media (max-width: 640px) {
    .landing {
      padding: 64px 16px 32px;
    }

    h1 {
      font-size: 26px;
    }

    .steps {
      flex-direction: column;
      gap: 20px;
      margin-top: 48px;
    }
  }
</style>
