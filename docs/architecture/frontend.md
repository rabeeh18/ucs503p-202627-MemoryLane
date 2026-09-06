# Frontend Architecture

The MemoryLane frontend is built with Svelte, Vite, and JavaScript.

## Responsibilities

The frontend provides:

- Natural-language search
- Search result display
- Page title, URL, and domain information
- Voice search input
- On-demand result summarization

## Main structure

Important frontend files include:

```text
frontend/
├── src/
│   ├── App.svelte
│   ├── api.js
│   ├── main.js
│   ├── stores.ts
│   ├── utils.js
│   ├── components/
│   │   ├── SearchBar.svelte
│   │   ├── ResultCard.svelte
│   │   └── ResultList.svelte
│   └── styles/
│       └── global.css
├── package.json
└── vite.config.js
```

The frontend communicates with the FastAPI backend through the configured Vite development proxy.

The frontend is intentionally separate from the backend's processing and retrieval logic.
