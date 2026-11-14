# Supabase drafts (not applied)

SQL here is a **proposal for review**. It sits in `drafts/`, not `migrations/`, so the Supabase CLI will not pick it up by accident. Nothing in this folder has been run against a real project.

| File | What it sets up |
|---|---|
| `0001_rag_foundation.sql` | extensions, private schemas `rag` and `env`, tables for verified sources, chunks and per-site daily series, and three service-role-only functions for the Worker |

Design background: [`docs/Radit/RAG_DESIGN.md`](../../docs/Radit/RAG_DESIGN.md).

## What was checked, and what was not

Checked on a throwaway local Postgres 16 (since deleted), with the `vector` type replaced by a stand-in because pgvector is not installed locally:

- the whole file applies cleanly;
- `rag_search` returns only chunks of verified sources, honours the country filter, and reports similarity and keyword hits;
- `env_get_series` keeps missing values as null, caps the window, and rejects a longer one;
- `anon` and `authenticated` cannot execute the functions, cannot use the `rag` or `env` schemas, and RLS is on for all four tables.

**Not checked:** the real `vector` type, the HNSW index and the `<=>` operator (needs pgvector, which the target project has available at 0.8.2 but not installed), and Supabase's own default grants on the hosted project. Run it first on an empty staging project and repeat the permission checks there.

## Open before it runs

1. The embedding size `1024` is a placeholder until the model is chosen (RAG_DESIGN.md, section 9.1).
2. The Worker would use the service-role key. A narrower role with its own JWT would be tighter; decide before launch.
3. Eca should confirm the `env.daily` shape against the extractor's output, and whether it is loaded from CSV or Parquet.
4. Who approves running it, and against which project. Do not run it against the IoT production project.

## How to apply, once approved

Put the project's database connection string in an untracked environment variable and run it yourself:

```bash
psql "$RAG_DB_URL" -v ON_ERROR_STOP=1 -f supabase/drafts/0001_rag_foundation.sql
```
