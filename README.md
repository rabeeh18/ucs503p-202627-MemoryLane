[Check out `demonstration.md` for a walkthrough of the working model.](demonstration.md)

# MemoryLane

MemoryLane automatically remembers the webpages you visit and lets you find
them again later using vague, natural-language descriptions — no bookmarks,
no folders, no exact keywords.

```
You browse                         You later type
     ↓                                   ↓
Tampermonkey saves the page      "that article about PPO clipping"
     ↓                                   ↓
Embedding + ChromaDB        ←———  Semantic search finds the right page
                                         ↓
                              Gemini summarizes THAT page, focused
                              on what you asked about
                                         ↓
                                  URL + Summary
```

- Pages are saved **automatically** as you browse — no button to click.
- Login/account pages are **skipped automatically** — nothing behind a
  password ever gets stored.
- Search is **semantic** — you don't need the exact title or words from
  the page, just what you remember about it.
- Summaries are generated **at query time**, focused on what you asked —
  the same saved page can produce a different summary depending on what
  part of it you're trying to recall.

---

## How it fits together

| File | What it does |
|---|---|
| `memorylane_user.js` | Tampermonkey userscript. Runs in your browser, detects login pages, extracts article content, sends it to the backend. |
| `main.py` | FastAPI backend. Receives pages from the userscript, embeds them, stores them in ChromaDB. |
| `query.py` | CLI you run to search your saved pages and get Gemini-generated summaries. |
| `test_backend_manual.py` | Optional. Exercises the backend without a browser, for debugging. |

---

## 1. Prerequisites

- Python 3.10+
- Google Chrome (or any browser Tampermonkey supports)
- A [Gemini API key](https://aistudio.google.com/apikey) — free tier is fine

## 2. Install dependencies

```bash
pip install fastapi uvicorn sentence-transformers chromadb pydantic
pip install google-genai python-dotenv
```

## 3. Configure your Gemini API key

Copy the example env file and fill in your key:

```bash
cp .env.example .env
```

Edit `.env`:

```
GEMINI_API_KEY=your_key_here
```

`.env` is already listed in `.gitignore` — don't commit it.

## 4. Start the backend

```bash
uvicorn main:app --reload
```

(If your `main.py` lives inside a `backend/` folder, run
`uvicorn backend.main:app --reload` instead.)

You should see it load the embedding model, initialize ChromaDB, and start
listening on `http://localhost:8000`. Leave this running — the userscript
and `query.py` both talk to it over HTTP.

Check it's alive:

```bash
curl http://localhost:8000/health
```

## 5. Install the Tampermonkey userscript

1. Install the [Tampermonkey](https://www.tampermonkey.net/) extension in
   your browser.
2. Open the Tampermonkey dashboard → **Create a new script**.
3. Delete the placeholder content and paste in the contents of
   `memorylane_user.js`.
4. Save (Ctrl+S / Cmd+S).

That's it — no configuration needed. From now on, every public page you
visit will be saved automatically about 7 seconds after it loads (enough
time for most pages to finish rendering). You can watch it happen in your
browser's developer console (`F12` → Console), where it logs each save,
skip, or error with a `[MemoryLane]` prefix.

Pages it will **not** save:
- Anything with a login form or password field
- Pages under paths like `/login`, `/account`, `/dashboard`
- Pages it already saved in the last 30 minutes (avoids duplicate saves on refresh)

If you want a visible on-page status panel and a manual "save now" button
for debugging, open `memorylane_user.js` and set:

```js
const DEBUG_MODE = true;
```

## 6. Search your memories

With the backend running, ask it what you remember:

```bash
python query.py "that article about PPO clipping"
python query.py "quickly remind me about the OS memory article"
python query.py "give me a detailed summary of that internship posting"
```

A few things worth knowing:
- The **wording of your query** controls how long the summary is —
  "quickly"/"briefly" → short, "detailed"/"in depth" → long, anything
  else → medium.
- Results always show **title, URL, and summary** — never a raw
  similarity score. Pass `--debug` if you want to see that anyway:

```bash
python query.py "that PPO article" --debug
```

- Control how many results come back with `-n`:

```bash
python query.py "machine learning articles" -n 10
```

---

## Optional: test the backend without a browser

Useful for confirming saving/embedding/search all work before bothering
with Tampermonkey:

```bash
python test_backend_manual.py
```

This saves four sample pages (PPO, reinforcement learning, deep learning,
a pasta recipe) and runs a few test queries against them, so you can see
at a glance whether semantic search is actually discriminating between
topics correctly.

---

## Troubleshooting

**`✗ Cannot connect to backend`**
The FastAPI server isn't running, or it's on a different port. Start it
with `uvicorn main:app --reload` and confirm `curl http://localhost:8000/health`
returns `{"status": "ok", ...}`.

**Pages aren't being saved automatically**
Open the browser console (F12) on the page you visited and look for
`[MemoryLane]` log lines — it'll tell you whether it skipped the page
(auth-protected, recently saved, no content) or hit an error.

**`✗ Gemini not configured` / summaries say "Summary unavailable."**
`GEMINI_API_KEY` isn't set. Check `.env` exists in the same directory
you're running `query.py` from, and that `python-dotenv` is installed.

**A page you expected to be blocked wasn't, or vice versa**
The auth-page detector is a heuristic, not a guarantee — it's tuned to
avoid false positives (blocking normal articles) more than false
negatives. If you find a case it gets consistently wrong, the scoring
logic is in `detectAuthProtectedPage()` in `memorylane_user.js`.

**Where is the data actually stored?**
`./chroma_db` in the directory the backend was started from — that's the
only database. There's no separate SQLite file; each ChromaDB record
holds the embedding, the metadata (url/title/timestamp), and the full
extracted page text together.
