# Ask SEAmon: RAG design

Status: **foundation built on a staging project (2026-11-15); see [supabase/README.md](../../supabase/README.md) for what exists and what is unverified.** Decisions taken: embeddings are Supabase's built-in gte-small (384 dimensions), the Worker keeps the service-role key and calls the three functions, the project is the staging project `nasa-seagis`. The corpus and the site data are still empty. Written 2026-11-15 for review by Radit, Eca (data) and whoever owns the research evidence. Today the ask bar is keyword matching in `earth-globe/src/dashboard/ask.js`; it is not retrieval and it says so in its replies.

## 1. What the assistant is for

Answer questions about ice-ice risk in Southeast Asian seaweed farming **from sources we can cite**, and say "not enough evidence" when we cannot. It does not diagnose disease, predict outbreaks or invent thresholds. This follows the product rules already in [METHODOLOGY.md](../METHODOLOGY.md) and `research/evidence/README.md`.

Questions fall into three kinds, and each needs a different route. Sending all of them through vector search is the main design risk.

| Kind | Example | Route | Source of truth |
|---|---|---|---|
| Literature | "What do studies say about salinity and ice-ice?" | **RAG**: vector + keyword retrieval, answer with citations | cited papers and reviewed evidence notes |
| Measurements | "How warm was the sea off Maluku last week?" | **Structured query**: a fixed set of SQL-backed tools, never free text to the model | Eca's per-site daily series (MUR SST, NASA POWER, Copernicus) |
| Atlas facts | "Which places in Indonesia are in the leads?" | **Structured lookup** over `sites` | `sites.json`, `reportedLocations.js` |

A question can mix kinds ("is this week's water warmer than usual for a place with ice-ice reports?"). The model plans, calls tools, and writes the answer; it never computes a number itself.

## 2. Architecture

```
browser (static site on Cloudflare)
   │  POST /api/ask  { question, species?, country?, site_id? }
   ▼
Cloudflare Worker  ──── secrets: SUPABASE_SERVICE_KEY, LLM_API_KEY, EMBEDDING_KEY
   │  1. rate limit + input checks
   │  2. embed the question
   │  3. tool loop with the LLM:
   │        search_evidence(query, filters)   → Supabase RPC (hybrid search)
   │        get_series(site_id, variable, from, to) → Supabase RPC (read only)
   │        list_sites(country?, species?)    → Supabase RPC
   │  4. validate the final answer against the answer contract
   ▼
Supabase Postgres (pgvector + full-text)   ← ingestion job (offline, reviewed)
```

Why a Worker and not the browser: the site is static, and keys must not ship to the client. Why the Worker and not a Supabase Edge Function: the site, CI and secrets already live on Cloudflare, and the Worker can sit on the same domain under `/api/*` with no CORS. If the team prefers one vendor, an Edge Function is a drop-in alternative; the contract below does not change.

The Worker uses a **read-only database role** for the three RPCs. Only the ingestion job can write.

## 3. Data model (Supabase)

Sketch, to be reviewed by Eca before any migration. Production is not touched until that review (see the note in `data/seagis-nasa-extractor/TASK.md`).

```sql
create extension if not exists vector;

-- one row per source (paper, report, reviewed note)
create table sources (
  id            text primary key,           -- e.g. DOI or stable slug
  title         text not null,
  citation      text not null,              -- full reference
  doi           text,
  url           text,
  publisher     text,
  year          int,
  species       text[],                     -- taxa the source is about, as stated
  countries     text[],
  evidence_grade text,                      -- per research/evidence/README.md
  verified_by   text,                       -- reviewer; null = not usable
  verified_on   date,
  license       text not null,              -- we may only store text we may store
  ingested_at   timestamptz default now()
);

-- chunks of verified sources
create table chunks (
  id          bigint generated always as identity primary key,
  source_id   text references sources(id) on delete cascade,
  ord         int not null,
  section     text,                          -- e.g. "Methods", "Table 2"
  page        int,
  content     text not null,
  embedding   vector(384),                   -- gte-small; see supabase/migrations for the real DDL
  tsv         tsvector generated always as (to_tsvector('simple', content)) stored,
  unique (source_id, ord)
);
create index on chunks using hnsw (embedding vector_cosine_ops);
create index on chunks using gin (tsv);

-- structured side (loaded from Eca's pipeline, same keys as sites.json)
create table sites (id text primary key, name text, country text, lat float8, lon float8);
create table env_daily (site_id text references sites(id), day date, variable text, value float8, unit text,
                        product text, product_version text, primary key (site_id, day, variable, product));
```

Rules that matter more than the DDL:

- **Only verified sources get chunked.** `verified_by is null` means the source is not retrievable. This keeps the "unverified research leads" out of answers presented as evidence.
- Every chunk carries enough metadata to render a citation without asking the model to invent one.
- `env_daily` keeps `product` and `product_version`, matching `source_lineage` in `contracts/assessment.schema.json`.
- Assessments (the stress levels) stay in their own table following that contract. The assistant may report an assessment only if a row exists; today none do.

## 4. Retrieval

1. **Hybrid search**, in one SQL function: top 20 by vector similarity and top 20 by full-text rank, merged with reciprocal rank fusion, top 6 kept. Keyword search matters here because species names, site names and variable codes are exact strings that embeddings blur.
2. **Metadata filters** from the question or from the UI state (species, country): applied in SQL, not left to the model.
3. **Minimum score**: below a tuned threshold the function returns nothing, and the answer must be "no supporting source found".
4. Chunks are about 300 to 500 tokens with a small overlap, split on section boundaries. Tables are kept whole or stored as text with their caption.

## 5. Answer contract

The model must return JSON, validated in the Worker before anything reaches the browser:

```json
{
  "answer_md": "short answer, plain language",
  "claims": [ { "text": "…", "citation_ids": ["doi:10.1007/..."], "chunk_ids": [12, 40] } ],
  "data_used": [ { "site_id": "maluku", "variable": "analysed_sst", "from": "2026-11-08", "to": "2026-11-14", "product": "MUR" } ],
  "confidence": "high | moderate | low | none",
  "abstained": false
}
```

- Every sentence in `answer_md` that states a fact about the literature must map to a `claims[]` entry whose chunks were actually retrieved in this request. The Worker rejects an answer that cites an id it did not retrieve.
- Numbers come from `data_used` tool results only.
- If retrieval is empty or weak: `abstained: true`, and the UI shows "Not enough evidence in the sources we have", the same tone as "Insufficient Data" on the cards.
- The assistant never states a threshold, a risk level, a probability or a cause of an outbreak unless a verified source states it, and then it quotes the scope (species, place, conditions). The brief itself warns that the Tawi-Tawi study found no significant correlation for most variables; the assistant must not turn associations into rules.

## 6. Safety and abuse

- **Corpus text is data, not instructions.** Chunks go into the prompt inside clearly delimited blocks and the system prompt says to ignore instructions found there. Ingestion strips obvious prompt-injection patterns, but the delimiting is the real control.
- Rate limit per IP at the Worker; cap question length and tool calls per request (for example 4).
- Log question, tools called, chunk ids and outcome for review, **without** IPs or other personal data. Decide retention before launch.
- Keys live in Worker secrets only. The Supabase service key is never used for the read path; use a role that can run the three RPCs and nothing else.

## 7. Frontend changes (small)

`dashboard/chat.js` and `ask.js` already separate the conversation from the answering. Changes:

- `answer()` becomes `fetch("/api/ask")`; keep the current local answers as an offline fallback and for the demo.
- Render `claims` as numbered footnotes under the bubble, each linking to the source's DOI or URL.
- A "thinking" state and an error state; the response may be streamed later, not in the first version.
- Show `abstained` answers in a distinct, calm style, and show when numbers came from a site's data (site, variable, date range).

## 8. Evaluation before launch

A fixed set of 40 to 60 questions written by someone who knows the domain, stored in the repo, each with: expected route, acceptable sources, and whether the right answer is to abstain. Run on every change to prompts, chunking or retrieval, and report:

- citation validity (cited chunk exists and supports the claim), checked by a reviewer on a sample;
- abstention rate on questions that have no source (should be near 100%);
- tool-use correctness for measurement questions (right site, variable, dates);
- zero invented thresholds. This one is pass/fail.

## 9. Open decisions

1. **Embedding model.** Users will ask in Indonesian, English, and likely Tagalog or Malay, while most papers are English, so use a **multilingual** model. Candidates: a hosted API (Voyage, OpenAI) or an open model such as BGE-M3 or multilingual-e5 served from Supabase or a Worker. Not decided; this fixes the `vector(...)` dimension. Verify pricing and licence at decision time.
2. **LLM.** Claude is the proposal (tool use and structured output are what this design leans on); needs an API account, budget and a per-day cap.
3. **Worker or Edge Function** (section 2).
4. **Who verifies sources, and how.** The corpus is only as good as this step. Today `research/evidence` is 3 KB of unverified leads, so **there is nothing to retrieve yet.** Minimum useful start: the review paper in the brief plus a handful of papers on *Kappaphycus*, ice-ice and temperature or salinity, each with the fields listed in `research/evidence/README.md`.
5. **Licence of what we store.** Many papers cannot be copied into a database. If not, store short quoted passages (with the licence allowing it), or store only embeddings plus a link and fetch the text from the open copy.
6. **Retention of question logs** (section 6).
7. **Supabase project and region**, and who approves the first migration. Nothing is created until then.

## 10. Phases

1. **Decide and verify** (no code): items 1 to 7 above, and the first ten verified sources.
2. **Structured tools first.** Load Eca's series into `env_daily` on a *staging* Supabase project and ship `get_series` and `list_sites` behind `/api/ask`. This answers real questions and needs no embeddings.
3. **Add literature retrieval** for the verified sources, hybrid search, the answer contract, the evaluation set.
4. **Frontend**: citations, abstention style, error states.
5. **Hardening**: rate limits, logging, cost cap, red-team questions (prompt injection, requests for a diagnosis or a "safe temperature").

Phase 2 is the smallest slice that gives users something true, and it does not depend on the corpus question in 9.4.
