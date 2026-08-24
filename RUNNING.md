# Running DocuMind — Step-by-Step Guide

This covers everything needed to get the project running from scratch,
plus the fixes for problems that commonly come up along the way.

---

## 1. Prerequisites

Install these before anything else:

1. **Docker Desktop** — https://www.docker.com/products/docker-desktop/
   Open it and make sure it says it's running (whale icon in your system
   tray/menu bar) before doing anything else.
2. **A Gemini API key** — get one free at https://aistudio.google.com/apikey

That's it — you do **not** need to separately install Python, PostgreSQL,
or any dependencies. Docker handles all of that inside containers.

---

## 2. Get the project onto your machine

1. Extract the project zip to a folder of your choice, e.g.:
   ```
   C:\Users\<you>\Desktop\Project
   ```
   (Any folder name works — `Project`, `ChemRAG`, `DocuMind`, doesn't
   matter. Avoid putting it inside a OneDrive-synced folder if possible,
   since OneDrive can lock files mid-build.)

2. Open a terminal (PowerShell on Windows, Terminal on Mac/Linux) and
   navigate into the folder:
   ```bash
   cd C:\Users\<you>\Desktop\Project
   ```

---

## 3. Configure your environment variables

1. Copy the example env file:
   ```bash
   copy .env.example .env
   ```
   (Mac/Linux: `cp .env.example .env`)

2. Open `.env` in a text editor and set your API key:
   ```
   GEMINI_API_KEY=your_actual_key_here
   ```

3. Leave everything else as-is unless you have a specific reason to
   change it (model names, chunk size, etc. all have sensible defaults).

---

## 4. First run

```bash
docker compose up --build -d
```

- `--build` compiles the application image (only needed the first time,
  or after code changes) — this can take 1–3 minutes.
- `-d` runs it in the background so your terminal is free.

### Verify it's actually running

```bash
docker compose ps
```

You should see **two** containers, both `Up`:
```
NAME            STATUS
project-api-1   Up
project-db-1    Up (healthy)
```

If `project-db-1` isn't `healthy` yet, wait a few seconds and check
again — Postgres takes a moment to initialize on first boot.

### Check the logs if anything looks wrong

```bash
docker compose logs api --tail 30
```

Look for `INFO: Application startup complete.` with no errors/tracebacks
after it.

---

## 5. Open the app

Go to **http://localhost:8000** in your browser.

You should see the DocuMind interface: a purple sidebar with navigation
(Chat / Knowledge Base / Ingestion Status / Retrieved Sources /
Evaluation / Settings) and a chat panel.

---

## 6. Try it out

1. Go to the **Knowledge Base** tab.
2. Upload the sample PDFs from `data/sample_docs/` (5 chemistry PDFs are
   included), or drag your own PDF/TXT/Markdown files.
3. Click **Ingest documents** and wait — this embeds every chunk via the
   Gemini API, so it can take 30–90 seconds per file.
4. Go to the **Chat** tab and ask something like:
   *"What does Bohr's model say about electron energy levels?"*
5. Check the **Retrieved Sources** tab to see exactly which document
   chunks were used.
6. Try the **Evaluation** tab and click **Run evaluation** to see the
   benchmark scorecard.

---

## 7. Stopping and restarting later

**To stop for now (keeps all your data):**
```bash
docker compose stop
```
Safe to close your terminal and shut down your computer after this.

**To start it again later (same data, no rebuild):**
```bash
docker compose up -d
```

**Quick reference:**

| Command | Containers | Your data (documents, chat history) |
|---|---|---|
| `docker compose stop` | Stopped | Kept |
| `docker compose up -d` | Started | Kept |
| `docker compose down` | Removed | Kept |
| `docker compose down -v` | Removed | **Wiped** |

Use `docker compose stop` / `docker compose up -d` for everyday
pausing and resuming. Only use `down -v` when you deliberately want a
clean slate (see troubleshooting below).

---

## 8. When do you need to rebuild (`--build`)?

| You changed... | Command needed |
|---|---|
| `app/` (HTML/CSS/JS) | **Nothing** — just refresh your browser (`Ctrl+Shift+R`). The `app/` folder is bind-mounted, not baked into the image. |
| `api/`, `rag/`, `agents/`, `db/`, `requirements.txt` | `docker compose up --build -d` |
| `.env` values | `docker compose down` then `docker compose up -d` (restart is enough, no rebuild needed) |

---

## 9. Troubleshooting

### `FATAL: database "rag_db" does not exist`
Postgres only creates the database on the **first** volume initialization.
If `.env` changed after an earlier run, or the first run was interrupted,
reset the volume:
```bash
docker compose down -v
docker compose up --build -d
```

### `RetryError[...NotFound]` when uploading or chatting
This means a Gemini model name in `.env` no longer exists (Google retires
model versions periodically). Check current model IDs at
https://ai.google.dev/gemini-api/docs/models and update
`GEMINI_EMBED_MODEL` / `GEMINI_GEN_MODEL` / `GEMINI_JUDGE_MODEL` in
`.env`, then restart.

### `RetryError[...ResourceExhausted]` (especially during evaluation)
This is a Gemini **rate limit or quota** error, not a bug — evaluation
fires many API calls quickly. Wait 60 seconds and retry, or check your
quota at https://aistudio.google.com/apikey. Free-tier keys have low
per-minute limits.

### `ports are not available: ... bind: ... forbidden by its access permissions`
Windows has reserved that port. Change the host port in
`docker-compose.yml` under the `api` service:
```yaml
    ports:
      - "8080:8000"   # was "8000:8000"
```
Then use `http://localhost:8080` instead.

### `ports are not available: ... Only one usage of each socket address...`
Something else is actively using that port. Either stop the other
process, or pick a different port the same way as above (try `8501`,
`9000`, etc.).

### Image pull fails with `httpReadSeeker... EOF` during `docker compose up --build`
A network issue while downloading the base images, not a project bug.
1. Just retry — Docker resumes from where it left off.
2. If it keeps failing, try disabling IPv6 on your network adapter:
   ```bash
   Disable-NetAdapterBinding -Name "Wi-Fi" -ComponentID ms_tcpip6
   ```
   then restart Docker Desktop and retry.
3. Temporarily disable antivirus HTTPS/web scanning if you have it —
   this is a very common cause of exactly this error.

### CSS/HTML changes not showing up
1. Confirm `docker-compose.yml` has this line under the `api` service's
   `volumes:` section:
   ```yaml
         - ./app:/app/app:ro
   ```
2. Hard refresh: `Ctrl+Shift+R` (or open in an incognito window).
3. If still stale, confirm the container sees your file:
   ```bash
   docker compose exec api cat /app/app/style.css
   ```

### Upgrading from an older copy of this project
Recent versions added new database columns (`content_hash`,
`confidence`, `confidence_label`, `calculations`). Since this project
uses `create_all` rather than migrations, an existing database won't
pick up new columns automatically:
```bash
docker compose down -v
docker compose up --build -d
```
You'll need to re-upload your documents afterward.

---

## 10. Running without Docker (optional, for development)

If you want fast iteration (auto-reload on every code save) instead of
rebuilding images:

```bash
# 1. Keep only the database in Docker
docker compose up -d db

# 2. Create a Python 3.11 virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1        # Windows
source venv/bin/activate           # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. In .env, change:
#    POSTGRES_HOST=localhost
#    (was "db" — that hostname only resolves inside Docker's network)

# 5. Run the app directly
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 — same UI, same database, but any Python
file you edit now restarts the server automatically.

---

## 11. Running tests

Inside the running container:
```bash
docker compose exec api pytest tests/ -v
```

Note: `tests/test_rules.py`, `tests/test_retrieval.py`, and
`tests/test_calculator.py` need no database or API key. Full
upload→ask integration tests need the running Postgres + a valid
`GEMINI_API_KEY`.

---

## 12. Running the evaluation benchmark from the command line

```bash
docker compose exec api python -m evals.run_eval
```

This runs all benchmark questions in `evals/benchmark.json` through the
live pipeline, scores them, and writes `evals/results.json`. The same
thing happens when you click **Run evaluation** in the UI.
