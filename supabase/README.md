# Supabase for Ask SEAmon

Backend of the assistant described in [`docs/Radit/RAG_DESIGN.md`](../docs/Radit/RAG_DESIGN.md). Project: the staging project **`nasa-seagis`** (separate account, not the IoT project).

| Path | What |
|---|---|
| `migrations/20261115000001_rag_foundation.sql` | extensions, private schemas `rag` and `env`, tables, `rag_search`, `env_list_sites`, `env_get_series` |
| `migrations/20261115000004_rag_usage.sql` | `rag.usage` and `rag_usage_hit`: the daily cap on assistant questions (applied to staging 2026-11-15) |
| `migrations/20261115000002_rag_ingest.sql` | `rag_ingest_source`, `rag_source_hash` (used by `scripts/rag/ingest.mjs`) |
| `migrations/20261115000003_env_ingest.sql` | `env_ingest` (used by `scripts/env/load.mjs`); `env_list_sites` now reports what data each site has; `env_get_series` takes an optional product |
| `functions/embed/` | Edge Function that embeds text with the built-in gte-small model (384 dimensions) |
| `config.toml` | minimal CLI config |

## State on 2026-11-15

**Site data is loaded** (see below). The literature tables are still empty.

Both migrations and the `embed` function are applied/deployed on `nasa-seagis`. The tables are **empty**: no sources and no site data are loaded yet. Checked on the hosted project: RLS on, `anon` and `authenticated` cannot use the schemas or call any function, `service_role` can; search returns only verified sources; an unverified source is stored but not searchable; `embed` answers 403 to the anon key and 401 without a key.

## How it fits together

```
research/corpus/*.md ──ingest.mjs──▶ embed (Edge Function) ─▶ rag_ingest_source ─▶ rag.sources / rag.chunks
browser ─▶ /api/ask (Cloudflare Worker, worker/) ─▶ model + tools ─▶ rag_search / env_get_series / env_list_sites
```

## What you need to set

| Where | Name | Notes |
|---|---|---|
| Cloudflare Worker binding (in `wrangler.jsonc`, no key) | `AI` (Workers AI) | The assistant tries Workers AI first (`@cf/qwen/qwen3-30b-a3b-fp8`, then `glm-4.7-flash`, then `gemma-4-26b-a4b-it`; override with `ASK_CF_MODELS`). **Not free of charge in the strict sense**: every Workers AI model has a per-token price, and only the account's daily allocation (10,000 neurons a day on the Workers Free plan) costs nothing. On the Free plan requests are refused after that; on a Workers Paid plan the overage is billed. Check the plan under Billing. |
| Cloudflare Worker secrets (`wrangler secret put`) | `OPENROUTER_API_KEY` | the model provider. Until at least one key is set `/api/ask` answers 503 and the page uses its built-in answers |
| | `OPENROUTER_API_KEY_2` ... `_9`, or `OPENROUTER_API_KEYS` | optional extra OpenRouter keys (a comma list in the second form). **Only keys starting with `sk-or-` are used**; a key for another provider is skipped and never sent to OpenRouter. A refused key (401/402/403) or one that hit a daily or credit limit is skipped for the request |
| | `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| | `SUPABASE_SERVICE_ROLE_KEY` | the **legacy `service_role` JWT**. The `embed` function checks the role claim in the JWT, so the new `sb_secret_...` key does not work for it. This key is powerful: keep it as a secret only |
| Worker variable (optional) | `ASK_DAILY_LIMIT` | questions that reach a model per UTC day, counted in the database (`rag_usage_hit`). Unset = 100, a number = that, `0` or `off` = no cap. When it is reached the page shows its built-in answer. Greetings are not counted. The default is a rough guess (about half of what the Workers AI free allocation should cover), not a measured figure |
| Worker variables (optional) | `ASK_MODELS`, `MIN_SIMILARITY`, `LLM_BASE_URL` | `ASK_MODELS` is a comma list tried in order (default: four free OpenRouter models that advertise tool calling, listed in `worker/llm.js`; the free list changes often). `MIN_SIMILARITY` defaults to `0.8`. `LLM_BASE_URL` points at another OpenAI-compatible endpoint |
| Your shell, for ingestion | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | same values; never commit them |

## Loading sources

Put Markdown files in [`research/corpus/`](../research/corpus/README.md) (front matter format is there), then:

```bash
node scripts/rag/ingest.mjs --dry-run        # parse and chunk only, no network
node scripts/rag/ingest.mjs                  # embed and store; unchanged text is not embedded again
```

A source without `verified_by` and `verified_on` is stored but never retrieved. Add them after a reviewer has checked the source, and run the script again.

## Not done and not verified

- **No real model call has been made.** The Worker is tested against a fake model (29 tests across the Worker and the corpus tools). Nobody has yet asked it a real question with a real OpenRouter key.
- **Workers AI is first, OpenRouter second.** Checked live on 2026-11-15 through `wrangler dev` (the `AI` binding is always remote): the Maluku 2024 temperature question was answered with the real minimum, maximum and their dates (they match the database), a literature question abstained, and a greeting was answered instantly. Latency was 6 to 26 seconds per question. The usage per question was not measured; estimate it from the Workers AI usage page before relying on the daily allocation.
- **Free models are weaker and less predictable.** The Worker checks that every citation and number comes from what the tools returned in the same request, but it cannot check that a cited chunk actually supports the sentence next to it. A weak model can misread a real source; the evaluation set (RAG_DESIGN.md, section 8) is the control for that, and the model list should be chosen on it.
- **Free tiers have request limits and different data terms.** OpenRouter limits free-model requests per minute and per day, and some free providers may keep or train on prompts. Check the current limits and each model's data policy; users' questions are sent to them.
- **Retrieval quality is unknown** until real sources are loaded. gte-small is mostly an English model; the Worker makes the model write the search query in English, and Indonesian and English phrasings of one sentence scored 0.84 cosine similarity in a quick check. `MIN_SIMILARITY` (0.8) is a first guess to tune on the evaluation set.
- **Site data (`env.sites`, `env.daily`) is not loaded.** Needs a loader from Eca's CSVs; the measurement tools return "no data" until then.
- **Question logs** record the tools used and chunk ids only, no question text and no address. Retention is still to be decided.
- **Rate limit:** `wrangler.jsonc` adds a 10 questions per minute per address binding (`ASK_LIMITER`), validated with `wrangler deploy --dry-run` but not yet exercised on Cloudflare. With free models there is no spend, but each key has its own request limits; more keys spread them.
- The migrations use `begin/commit` and are applied by hand (`supabase-rag` / the Management API). The CLI's `db push` has not been used.

## Site data (`env.sites`, `env.daily`)

Loaded on 2026-11-15 from Eca's files in `research/data-access/`: 19 sites, 60,268 rows, 29 MB database in all. Nothing is filled, converted or interpolated; units are the sources' own.

| Product name | What it is | Rows |
|---|---|---|
| `POWER-monthly` | NASA POWER monthly means, 11 variables, dated the first of each month, 2003 to 2024 | 55,176 |
| `MUR-30d` | MUR sea-surface temperature, **one value every 30 days** (not daily), 2003-01-01 to 2024-12-08 | 5,092 |

**Read this before asking the assistant about "now".** The data is a historical file, not a live feed: it ends in December 2024. A question about last week cannot be answered from it, and the assistant is told to say so. The product names carry the time resolution because the assistant reads them.

```bash
node scripts/env/load.mjs --dry-run        # parse and validate, no network
node scripts/env/load.mjs                  # load, then compare the database with the files
node scripts/env/load.mjs --daily PRECTOTCORR,T2M   # opt in to daily POWER for chosen variables
```

The loader refuses unknown sites, moved coordinates, bad dates and non-numeric values, upserts (safe to run twice), and finishes by comparing the count and date range of every series with what it read (228 series matched). Values in the database were also spot-checked against the raw files independently of the loader (MUR for maluku, POWER monthly rainfall).

Daily POWER is **not loaded**: one variable is about 153,000 rows (19 sites x 8,036 days), all 11 about 1.7 million, which would not fit comfortably in a free database. Pick the variables that questions need.

Not loaded: `research/data-access/results/trends.csv` (Eca's Sen's slope and Mann-Kendall results), Copernicus products, and anything newer than the files. Whether trends should be answerable is a product decision, since they are derived results with their own caveats.
