<script>
  import Landing from './routes/Landing.svelte';
  import Home from './routes/Home.svelte';
  import Results from './routes/Results.svelte';
  import Library from './routes/Library.svelte';
  import Callback from './routes/Callback.svelte';
  import Privacy from './routes/Privacy.svelte';
  import Extension from './routes/Extension.svelte';
  import ScrollPill from './components/ScrollPill.svelte';
  import Toasts from './components/Toasts.svelte';
  import { session } from './auth.js';
  import { route } from './lib/router.js';

  $: path = $route.path.replace(/\/+$/, '') || '/';
  $: query = ($route.query.get('q') || '').trim();
  $: signedIn = Boolean($session);
  /** Pages anyone can open, signed in or not. */
  $: isPublic = path === '/privacy' || path === '/extension';

  $: title = !signedIn && !isPublic
    ? 'MemoryLane'
    : path === '/library'
      ? 'All saved pages · MemoryLane'
      : path === '/privacy'
        ? 'Privacy · MemoryLane'
        : path === '/extension'
          ? 'Get the extension · MemoryLane'
          : query
            ? `${query} · MemoryLane`
            : 'MemoryLane';
</script>

<svelte:head>
  <title>{title}</title>
</svelte:head>

{#if path === '/auth/callback'}
  <Callback />
{:else if path === '/privacy'}
  <Privacy />
{:else if path === '/extension'}
  <Extension />
{:else if !signedIn}
  <Landing />
{:else if path === '/library'}
  <Library />
{:else if query}
  <Results {query} />
{:else}
  <Home />
{/if}

<Toasts />
<ScrollPill />
