# Deploy to Render (free) — step by step

This `render_app/` folder is a self-contained web app that runs on Render's
**free** tier. It uses a lightweight embedding engine (fastembed / ONNX, no
PyTorch) so it fits inside the free 512 MB memory limit.

## What's in this folder

```
render_app/
├── app.py              # Flask app + REST API (entry point)
├── search_engine.py    # fastembed + FAISS + hybrid search (lightweight)
├── data_loader.py      # loads the CSV
├── suggestions.py      # typo-tolerant suggestions
├── data/documents.csv  # Keeper support articles
├── templates/index.html# the search web page
├── requirements.txt    # dependencies (no torch)
├── render.yaml         # Render build/run config
├── .gitignore          # files to not upload
└── DEPLOY.md           # this guide (don't need to deploy it)
```

Render deploys from a **GitHub repository**, so the flow is:
**put these files on GitHub → connect Render to that repo → it builds and runs.**

---

## STEP 1 — Create a GitHub account and repository

1. Sign up (free): https://github.com/join
2. Create a new repo: https://github.com/new
   - **Repository name:** `keeper-help-search`
   - **Visibility:** Public (simplest) or Private
   - Do NOT add a README/gitignore (we have our own)
   - Click **Create repository**
3. Leave that page open — it shows commands you'll use next.

## STEP 2 — Push these files to GitHub

Open a terminal **inside this `render_app` folder** and run (replace
YOUR-USERNAME):

```bash
git init
git add .
git commit -m "Keeper semantic search"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/keeper-help-search.git
git push -u origin main
```

If git asks you to log in, follow the prompt (GitHub may ask for a Personal
Access Token instead of a password — create one at
https://github.com/settings/tokens if needed).

Refresh your GitHub repo page — you should see all the files.

## STEP 3 — Create a Render account

1. Go to https://render.com and click **Get Started** / **Sign up**.
2. **Sign up with GitHub** (easiest — it links your repos automatically).
3. Authorize Render to access your GitHub.

## STEP 4 — Create the web service

1. In the Render dashboard click **New +** → **Web Service**.
2. Connect / pick your `keeper-help-search` GitHub repo.
3. Render reads `render.yaml` and fills most settings in. Confirm:
   - **Runtime:** Python
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app --workers 1 --timeout 120 --preload`
   - **Instance type / plan:** **Free**
4. Click **Create Web Service**.

## STEP 5 — Wait for the build, then open your link

1. Render installs the dependencies and starts the app (first build takes a
   few minutes; it also downloads the small embedding model once).
2. When the status is **Live**, click the URL at the top of the page. It looks
   like:
   ```
   https://keeper-help-search.onrender.com
   ```
3. Share that link. It works from anywhere.

---

## Important notes about the free tier

- **It sleeps when idle.** After ~15 minutes with no visitors, the free
  service spins down. The next visit wakes it up, which takes ~30–60 seconds
  (one slow load), then it's fast again. This is normal for free hosting.
- **Memory:** the app is built to stay under 512 MB by using fastembed
  instead of PyTorch. If you add many more documents it stays fine; the model
  itself is the main cost and it's small.
- **Updating articles:** edit `data/documents.csv`, then
  `git add . && git commit -m "update" && git push`. Render auto-redeploys.

---

## Why this version differs from the Flask app in the parent folder

The parent `semantic_search/` app uses `sentence-transformers` (PyTorch),
which is ~1 GB in memory — too big for a free host. This `render_app/`
version swaps in **fastembed** (ONNX, a few hundred MB) with the
`BAAI/bge-small-en-v1.5` model. Same 384-dim embeddings, same search quality,
much smaller footprint. Everything else (API, web page, suggestions, hybrid
ranking) is identical.
```
