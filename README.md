# FootyDraft

A single-file, offline-capable football (soccer) **all-time XI drafting game**. A host
spins a wheel to a random club, and everyone drafts a legend from that club into a slot
on their squad — repeat until the XIs are full, then paste the squads into an AI to
simulate a season.

Everything lives in one self-contained file (`index.html`): vanilla HTML/CSS/JS, no
build step, no framework, no npm. Double-click it to play offline, or host it anywhere
that serves static files.

## Features

- 2–8 squads laid out in a single full-width row
- One-click **11-a-side / 6-a-side** (5 outfield + GK) mode switch, plus per-squad
  formations and an adjustable bench for everyone
- **Spin Club** wheel with no-repeat, league filters, and a coloured result pill
- ~2,080 players across 32 clubs; a player appears under **every** club they played for
- Add-player modal with a visual club picker, search, eligibility toggles, and custom
  players; **drag any player between slots** to move or swap
- Real club crests (loaded online) with a drawn-shield fallback when offline
- Pick timer with Web Audio beep, undo, auto-fill, copy-AI-prompt, and
  `localStorage` persistence
- Import/export the player database from the in-app **Settings → Player database** panel

## Deploy to Vercel

The site is 100% static — Vercel serves `index.html` at the root with **no build config**.

1. Push this repo to GitHub (already done if you're reading this there).
2. Go to <https://vercel.com/new> and **Import** the `footydraft` repository.
3. When prompted:
   - **Framework Preset:** Other
   - **Build Command:** _(leave empty)_
   - **Output Directory:** _(leave empty / default)_
   - **Install Command:** _(leave empty)_
4. Click **Deploy**. Vercel builds nothing and serves `index.html` at your
   `*.vercel.app` URL.

By default Vercel deploys the repository's **production branch** (usually `main`), and
creates preview URLs for every other branch. To go live on your main URL, merge this
branch into `main` (or, in the Vercel project: **Settings → Git → Production Branch**,
set it to whichever branch holds the game).

> Club logos load from a third-party image host, so they only appear when the page is
> online. If any don't load they fall back to a drawn crest, and you can turn logos off
> entirely in **Settings → Club logos**.

## Run locally

Just open `index.html` in a browser — no server needed.

## Editing the player database

- **In-app:** Settings (gear) → **Player database → Import / Export Players**. Paste a
  block of `# Club` headers with `Name: POS, POS` lines, or export the current data to
  edit and re-import.
- **Bulk from Wikidata:** run `build-db-wikidata.py` on any machine with internet:

  ```bash
  python build-db-wikidata.py --endpoint qlever      # fast mirror
  ```

  It writes `football-players.txt` (paste into the Import box) and `football-db.json`.
