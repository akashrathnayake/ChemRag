# ChemRAG — Document-based RAG Assistant

<img src=".\assets\interface.png" width="1000" alt="Interface">

A small, fully working Retrieval-Augmented Generation system over a PDF
knowledge base (e.g. chemistry textbook chapters and lecture notes), with
grounded answers, visible
citations, follow-up conversation support, and evaluation with an
LLM judge.

## What it does

1. Upload 1–10 PDF, TXT, or Markdown documents through the web UI's
   **Knowledge Base** view. Re-uploading a file with identical content is
   detected via a SHA-256 content hash and skipped rather than duplicated
   (BR-04).
2. Each document is split into pages (PDF) or treated as one page (TXT/MD),
   then into overlapping text chunks (LlamaIndex `SentenceSplitter`).
3. Each chunk is embedded with Gemini and stored in Postgres/pgvector,
   tagged with document title, page, and chunk index. Progress and
   metadata are visible in the **Ingestion Status** view.
4. A user asks a question in the **Chat** view. A LangGraph pipeline:
   `validate → retrieve → generate → calculate → verify → respond`
   - **retrieve**: hybrid search — pgvector cosine similarity ("meaning")
     fused with keyword overlap ("keywords") — also rewrites short
     follow-ups ("explain more") into a standalone query using the last
     Q/A turn. Retrieved chunks are then screened for prompt-injection
     patterns (`agents/rules.contains_injection_attempt`) and any flagged
     chunk is excluded from the context before generation ever sees it
     (BR-06).
   - **generate**: Gemini answers using *only* the retrieved chunks, cites
     every factual sentence with `[n]` markers, and — instead of doing
     arithmetic itself — writes any calculation as `CALC[ expression ]`
     (e.g. `CALC[ -2.179e-18 / 3^2 ]`).
   - **calculate**: a deterministic tool node (`agents/calculator.py`,
     backed by `sympy`) finds every `CALC[...]` block and replaces it
     with a verified, correctly-computed result — so numeric answers are
     never just the LLM's mental math. Verified calculations are shown
     to the user as a checkmark chip under the answer.
   - **verify**: `agents/rules.py` — deterministic, regex-based checks
     (no LLM call) confirm every citation number actually refers to a
     retrieved source, and that low-confidence retrieval results in an
     explicit "I cannot confirm this" instead of a guess.
5. The UI shows the answer next to citation cards (document title, page
   or chunk number, text preview, match score), any verified
   calculations, and an overall confidence label (High/Medium/Low)
   derived from the top retrieval score. The same sources are also
   viewable, larger, in the dedicated **Retrieved Sources** view. Chat
   history persists across page reloads (loaded from Postgres on
   startup, not just saved). Uploads report per-file status — one
   corrupt file doesn't fail the whole batch. Safe (non-secret)
   configuration is visible under **Settings**.

## Architecture

```
Project/
├── app/        # Static web UI (HTML/CSS/JS) — purple/orange/white theme
├── api/        # FastAPI app: typed request/response models, routers
├── rag/        # Ingestion, embeddings, hybrid retrieval, prompts, generation
├── agents/     # LangGraph pipeline (graph.py) + deterministic rules.py
├── db/         # SQLAlchemy models, pgvector setup, init.sql
├── evals/      # benchmark.json, LLM judge, evaluation runner
├── data/sample_docs/  # 3 generated sample chemistry PDFs for demoing
└── tests/      # rule/schema/retrieval unit tests
```

### Data model

| Object | Fields |
|---|---|
| `Document` | id, title, source_type, file_path, created_at |
| `Chunk` | id, document_id, text, page, chunk_index, doc_metadata, **embedding** (pgvector column used for search) |
| `Embedding` | chunk_id, vector, model_name, created_at — audit record of the embedding event |
| `ChatMessage` | id, session_id, question, answer, citations, supported, created_at |
| `EvaluationCase` | question, expected_source, result, notes |

### Why a separate `Chunk.embedding` and `Embedding` table?

The vector actually queried by pgvector lives on `Chunk.embedding` (fast,
indexable). The `Embedding` table is a lightweight audit trail — which
model/version produced each vector and when — useful if you later
re-embed the corpus with a newer Gemini embedding model.

## Guardrails: rules.py vs the LLM judge

- **`agents/rules.py`** runs on **every live request**. It's deterministic
  regex/logic — no extra LLM call, no extra latency risk: checks for the
  "I cannot confirm..." phrase, validates that every `[n]` citation marker
  in the answer maps to an actually-retrieved source, and rejects
  ungrounded or citation-less factual answers by downgrading them to
  "cannot confirm."
- **`evals/judge.py`** (Gemini) runs **only offline**, during
  `evals/run_eval.py`, scoring correctness / relevance / groundedness
  0–2 for each benchmark question. This keeps the live answer path fast
  and cheap while still giving you an LLM-quality signal for regression
  tracking.

## Follow-up questions ("explain more")

`agents/rules.is_followup_question()` flags short or pattern-matched
follow-ups (e.g. "explain more", "why", "what about...") when there's
prior chat history for the session. The pipeline then asks Gemini to
rewrite the follow-up into a standalone search query using the previous
Q/A turn, before running retrieval — so "explain more" after "what does
Bohr's model say about electron energy levels?" correctly re-retrieves
the relevant atomic-structure chunks.

## Running with Docker

```bash
cp .env.example .env
# edit .env and set GEMINI_API_KEY=...

docker compose up --build
```

- UI: http://localhost:8000
- API docs: http://localhost:8000/docs
- Postgres (pgvector): localhost:5432

Sample chemistry PDFs are already generated in `data/sample_docs/` — upload
them through the UI (or via `POST /api/documents/upload`) to try the
system immediately.

**`RetryError[... state=finished raised NotFound>]` on ingest/ask** — this
means the Gemini model name in `.env` no longer exists (Google
periodically retires model versions). As of this writing the project
defaults to `models/gemini-embedding-001` (embeddings) and
`models/gemini-3.6-flash` (generation/judge). If those also 404 by the
time you're reading this, check https://ai.google.dev/gemini-api/docs/models
for current model IDs and update `GEMINI_EMBED_MODEL` /
`GEMINI_GEN_MODEL` / `GEMINI_JUDGE_MODEL` in `.env` accordingly, then
`docker compose up --build` again. Note `gemini-embedding-001` defaults
to 3072 output dimensions — this project requests 768 via
`GEMINI_EMBED_DIM`/`output_dimensionality` to match the pgvector column
in `db/models.py`; if you change embedding models, keep those two in
sync (or update `EMBED_DIM` in `db/models.py` and re-ingest).

## Editing the project after it's running

`docker-compose.yml` bind-mounts `app/` (the web UI) directly into the
container, so **HTML/CSS/JS changes in `app/` only need a browser
refresh** — no rebuild.

Everything else (`api/`, `rag/`, `agents/`, `db/`, `requirements.txt`) is
baked into the image at build time, so changes there need:
```bash
docker compose up --build -d
```

## Troubleshooting

**Upgrading an existing install?** This version adds a `content_hash`
column to `documents` (for duplicate detection, BR-04). Since this
project uses SQLAlchemy `create_all` rather than migrations, an existing
database won't pick up new columns automatically — reset it once:
```bash
docker compose down -v
docker compose up --build -d
```
(`-v` removes the Postgres volume — re-upload your documents afterward.)

**`FATAL: database "rag_db" does not exist`** — Postgres only creates
`POSTGRES_DB` the first time its data volume is initialized. If you
changed `.env` after an earlier `docker compose up`, or the first run
was interrupted, the volume may be stale. Reset it:

```bash
docker compose down -v
docker compose up --build
```

Also make sure you don't have a `DATABASE_URL` in `.env` that names a
different database than `POSTGRES_DB` — `db/database.py` builds the
connection string from `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`/
`POSTGRES_HOST`/`POSTGRES_PORT` automatically, so there's no need to set
`DATABASE_URL` at all in normal use.

## Running the evaluation suite

Either click **"Run evaluation"** in the sidebar (after uploading the
sample docs), or from a shell:

```bash
docker compose exec api python -m evals.run_eval
```

This runs every question in `evals/benchmark.json` through the real
pipeline, scores it with `agents/rules.py` + the Gemini judge, writes
`evals/results.json`, and stores each case as an `EvaluationCase` row.

## Running unit tests

```bash
docker compose exec api pytest tests/ -v
```

`tests/test_rules.py` and `tests/test_retrieval.py` need no DB or API
key. Full upload→ask integration tests are meant to run inside the
compose stack where Postgres and `GEMINI_API_KEY` are available.

## Notes on the UI theme

The interface uses a purple/orange/white palette with the sidebar, chat
bubbles, and citation cards styled accordingly. Instead of hot-linking
external "Google images" (which would create a broken/unlicensed
dependency once this project runs offline in Docker), the UI uses simple
emoji/CSS-based iconography so it renders correctly out of the box with
no external asset dependency. Swap in your own logo/imagery in
`app/index.html` / `app/style.css` if desired.

## Environment variables (`.env`)

See `.env.example` — set `GEMINI_API_KEY` at minimum. Chunk size,
overlap, top-K, and the minimum similarity threshold for "cannot confirm"
are all tunable there.

## Known Limitations

Documented honestly, as required by the project brief's Quality Baseline
and Week 6 evaluation evidence — none of these are hidden or silently
worked around:

- **PDF text extraction can garble symbol-heavy content.** PDFs using
  custom/symbol fonts for math or chemistry notation (common in
  textbook-exported PDFs) can extract with corrupted characters, since
  the underlying `pypdf`/LlamaIndex reader relies on the PDF's embedded
  character map. This affects retrieval and citation text quality for
  those specific documents, not the pipeline logic itself.
- **Prompt-injection detection is heuristic, not exhaustive.**
  `agents/rules.contains_injection_attempt()` is a regex pattern list —
  it catches obvious cases ("ignore previous instructions", "reveal your
  system prompt", etc.) but a sufficiently reworded or obfuscated
  injection attempt embedded in a document could evade it. The system
  prompt's untrusted-content framing is a second layer of defense, but
  neither layer is a formal guarantee.
- **The calculator agent verifies single well-formed expressions only.**
  `agents/calculator.py` correctly evaluates arithmetic the model
  proposes via `CALC[...]` blocks, but it cannot verify multi-step
  symbolic derivations, proofs, or open-ended mathematical reasoning —
  only concrete numeric expressions.
- **Duplicate detection is exact-content-hash based.** Re-uploading the
  identical file (or byte-identical re-export) is correctly caught. A
  document re-saved through different software with different bytes but
  visually identical content — or a slightly edited version — will not
  be recognized as a duplicate.
- **Confidence score reflects retrieval similarity only.** The
  High/Medium/Low confidence label shown with each answer is derived
  from how closely the top retrieved chunk matched the question
  (embedding cosine similarity + keyword overlap) — it is not an
  independent fact-check of whether the generated answer is correct.
- **No database migrations.** Schema changes (e.g. this project's
  `content_hash`, `confidence` columns) require a full volume reset in
  development (`docker compose down -v`) rather than an in-place
  migration, since the project uses SQLAlchemy `create_all` rather than
  Alembic. Acceptable for this scope; a production system would use
  proper migrations.
- **Gemini free-tier rate limits can interrupt the evaluation run.**
  Running all benchmark questions fires many API calls in quick
  succession; `evals/run_eval.py` throttles and retries, but a very low
  free-tier quota can still cause some cases to be skipped with a
  rate-limit note rather than a score.
- **Retrieval is limited to what pgvector cosine similarity + keyword
  overlap can surface.** There's no re-ranking model or cross-encoder
  step — for very large or highly overlapping knowledge bases, retrieval
  quality would benefit from one.

  ## Question Answering

  <img src=".\assets\question answering.png" width="1000" alt="Chat">
  <img src=".\assets\calculations.png" width="1000" alt="Chat">

  ## Knowledge Base

  <img src=".\assets\knowledge base.png" width="1000" alt="Knowledge Base">

  ## Ingestion Status

  <img src=".\assets\ingestion status.png" width="1000" alt="Ingestion Status">

  ## Retrieved Sources

  <img src=".\assets\retrieved sources.png" width="1000" alt="Retrieved Sources">

  ## Evaluation

  <img src=".\assets\evaluation.png" width="1000" alt="Evaluation">
  <img src=".\assets\evaluation 2.jpeg" width="1000" alt="Evaluation">

  ## Settings

  <img src=".\assets\settings.png" width="1000" alt="Settings">
