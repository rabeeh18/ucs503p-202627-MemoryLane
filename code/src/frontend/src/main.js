import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-mono/400.css';
import './styles/tokens.css';
import App from './App.svelte';

const app = new App({
  target: document.getElementById('app'),
});

export default app;
