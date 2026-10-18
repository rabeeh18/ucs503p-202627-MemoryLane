<script>
  import Header from '../components/Header.svelte';
  import { signIn } from '../auth.js';
  import { link } from '../lib/router.js';

  const steps = [
    { n: '01', title: 'Save', text: 'Keep a page with one click from the', linkText: 'extension', href: '/extension' },
    { n: '02', title: 'Search', text: 'Describe the idea, not the title.' },
    { n: '03', title: 'Rediscover', text: 'Open the page, or get a short summary first.' },
  ];
</script>

<div class="screen">
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
        <div class="step-text">
          {step.text}{#if step.href}{' '}<a href={step.href} use:link>{step.linkText}</a>.{/if}
        </div>
      </li>
    {/each}
  </ol>
</main>
</div>

<style>
  /* Exactly one viewport tall with the content centred; no scrolling at
     1366x768 and up. Narrow screens (below 640px) scroll normally. */
  .screen {
    height: 100vh;
    height: 100dvh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .landing {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 24px 32px 48px;
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

  .fine-print a,
  .step-text a {
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .steps {
    width: 100%;
    max-width: 640px;
    margin: 64px 0 0;
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

  @media (max-height: 800px) {
    .landing {
      padding-top: 8px;
      padding-bottom: 24px;
    }

    h1 {
      font-size: 34px;
    }

    .lede {
      margin-top: 14px;
    }

    .actions {
      margin-top: 28px;
    }

    .steps {
      margin-top: 40px;
    }
  }

  @media (max-width: 640px) {
    .screen {
      height: auto;
      min-height: 100dvh;
      overflow: visible;
    }

    .landing {
      justify-content: flex-start;
      padding: 48px 16px 32px;
    }

    h1 {
      font-size: 26px;
    }

    .steps {
      flex-direction: column;
      gap: 20px;
      margin-top: 40px;
    }
  }
</style>
