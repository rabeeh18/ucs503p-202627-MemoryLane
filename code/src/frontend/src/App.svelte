<script>
  import Landing from './routes/Landing.svelte';
  import Home from './routes/Home.svelte';
  import Results from './routes/Results.svelte';
  import Library from './routes/Library.svelte';
  import Callback from './routes/Callback.svelte';
  import Privacy from './routes/Privacy.svelte';
  import Extension from './routes/Extension.svelte';
  import MapPage from './routes/MapPage.svelte';
  import ScrollPill from './components/ScrollPill.svelte';
  import Toasts from './components/Toasts.svelte';
  import ReportDialog from './components/ReportDialog.svelte';
  import { session } from './auth.js';
  import { navigate, route } from './lib/router.js';
  import { openReport, reportDialog, reportFromQuery } from './report.js';

  $: path = $route.path.replace(/\/+$/, '') || '/';
  $: query = ($route.query.get('q') || '').trim();
  $: topic = ($route.query.get('topic') || '').trim();
  $: signedIn = Boolean($session);

  // The extension's "Report a problem" link: /?report=extension&v=…&err=…
  // Opens the dialog once signed in, then drops the parameters from the address.
  $: if (signedIn && $route.query.has('report')) {
    const setup = reportFromQuery($route.query);
    const rest = new URLSearchParams($route.query);
    ['report', 'v', 'err'].forEach((key) => rest.delete(key));
    const qs = rest.toString();
    navigate(`${$route.path}${qs ? `?${qs}` : ''}`, { replace: true });
    if (setup) openReport(setup);
  }
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
          : path === '/map'
            ? 'Map · MemoryLane'
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
{:else if path === '/map'}
  <MapPage />
{:else if path === '/search'}
  <Results {query} {topic} />
{:else if query}
  <Results {query} />
{:else}
  <Home />
{/if}

<Toasts />
{#if signedIn && $reportDialog}
  <ReportDialog setup={$reportDialog} />
{/if}
<ScrollPill />
