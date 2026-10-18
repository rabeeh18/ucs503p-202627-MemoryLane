<script>
  import Header from '../components/Header.svelte';
  import { session } from '../auth.js';
  import { EXTENSION_ZIP_URL, extensionInstalled } from '../lib/extension.js';

  const steps = [
    { title: 'Unzip', text: 'Unzip memorylane-extension.zip. You get a folder named memorylane-extension.' },
    { title: 'Turn on Developer mode', text: 'Open chrome://extensions and switch on Developer mode at the top right.' },
    { title: 'Load unpacked', text: 'Click Load unpacked and choose the unzipped folder.' },
    {
      title: 'Pin it and sign in',
      text: 'Pin MemoryLane from the puzzle-piece menu, open it, and sign in with Google using the same account as this website.',
    },
  ];
</script>

<Header signedOut={!$session} />

<main class="extension">
  <h1>Save pages from Chrome</h1>
  <p class="lede">
    The MemoryLane extension saves the page you're reading with one click, or automatically if you turn on
    auto-capture.
  </p>

  {#if $extensionInstalled}
    <p class="installed" role="status">The extension is already installed in this browser.</p>
  {/if}

  <a class="btn btn-primary download" href={EXTENSION_ZIP_URL} download="memorylane-extension.zip">
    Download for Chrome
  </a>

  <ol class="steps">
    {#each steps as step, i}
      <li>
        <span class="n mono">{String(i + 1).padStart(2, '0')}</span>
        <div>
          <div class="step-title">{step.title}</div>
          <div class="step-text">{step.text}</div>
        </div>
      </li>
    {/each}
  </ol>
</main>

<style>
  .extension {
    flex: 1;
    width: 100%;
    max-width: 640px;
    margin: 0 auto;
    padding: 64px 32px 64px;
  }

  h1 {
    margin: 0;
    font-size: 28px;
    font-weight: 500;
    line-height: 1.25;
  }

  .lede {
    margin: 12px 0 0;
    font-size: 15px;
    line-height: 1.6;
    color: var(--text-2);
  }

  .installed {
    margin: 20px 0 0;
    font-size: 14px;
    color: var(--text-2);
  }

  .download {
    margin-top: 32px;
    width: 100%;
    max-width: 340px;
  }

  .steps {
    margin: 48px 0 0;
    padding: 0;
    list-style: none;
  }

  .steps li {
    display: flex;
    gap: 16px;
    padding: 16px 0;
    border-top: 1px solid var(--divider);
  }

  .n {
    flex: none;
    width: 24px;
    padding-top: 2px;
    font-size: 12px;
    color: var(--text-3);
  }

  .step-title {
    font-size: 15px;
    font-weight: 500;
  }

  .step-text {
    margin-top: 4px;
    font-size: 14px;
    line-height: 1.55;
    color: var(--text-2);
  }

  @media (max-width: 640px) {
    .extension {
      padding: 32px 16px 48px;
    }

    h1 {
      font-size: 24px;
    }
  }
</style>
