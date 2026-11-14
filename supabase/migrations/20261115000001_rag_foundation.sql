-- Applied to the staging project `nasa-seagis` (see supabase/README.md).
--
-- Foundation for "Ask SEAmon" (docs/Radit/RAG_DESIGN.md):
--   rag.*  verified sources and their chunks (vector + full-text search)
--   env.*  per-site daily environmental series (loaded from Eca's pipeline)
--   public.rag_search / env_get_series / env_list_sites  the only entry points
--
-- Design choices to check:
--  1. Tables live in schemas `rag` and `env`, which are NOT exposed by the Data API.
--     Nothing here is reachable with the publishable (anon) key.
--  2. The three functions are in `public` so the Worker can call them over REST, but
--     EXECUTE is revoked from public, anon and authenticated and granted to service_role
--     only. The Worker keeps the service key as a secret. Trade-off: that key can do far
--     more than call these functions. A narrower role with its own JWT can replace it later.
--  3. Only chunks of VERIFIED sources are searchable (sources.verified_by is not null).
--  4. Embeddings are 384-dimensional: Supabase's built-in gte-small model. It is mostly an
--     English model, so the Worker has the LLM write the search query in English before it
--     is embedded. Changing the model later means re-embedding every chunk.
--  5. Nothing here stores assessments or stress levels; those follow
--     contracts/assessment.schema.json once a reviewed rule exists.

begin;

-- ------------------------------------------------------------ extensions
create extension if not exists vector   with schema extensions;
create extension if not exists pg_trgm  with schema extensions;
create extension if not exists unaccent with schema extensions;

-- ------------------------------------------------------------ schemas
create schema if not exists rag;
create schema if not exists env;
revoke all on schema rag from public, anon, authenticated;
revoke all on schema env from public, anon, authenticated;

-- ------------------------------------------------------------ rag.sources
create table rag.sources (
  id             text primary key,            -- DOI or a stable slug
  title          text not null,
  citation       text not null,               -- full reference as it should be shown
  doi            text,
  url            text,
  publisher      text,
  year           int check (year between 1900 and 2100),
  species        text[] not null default '{}',   -- taxa as stated by the source
  countries      text[] not null default '{}',
  evidence_grade text,                        -- per research/evidence/README.md
  verified_by    text,                        -- reviewer; NULL = not retrievable
  verified_on    date,
  license        text not null,               -- what we are allowed to store
  ingested_at    timestamptz not null default now(),
  check ((verified_by is null) = (verified_on is null))
);

-- ------------------------------------------------------------ rag.chunks
create table rag.chunks (
  id         bigint generated always as identity primary key,
  source_id  text not null references rag.sources(id) on delete cascade,
  ord        int  not null,
  section    text,                            -- e.g. "Methods", "Table 2"
  page       int,
  content    text not null,
  embedding  extensions.vector(384),         -- gte-small, see note 4
  tsv        tsvector generated always as (to_tsvector('simple', content)) stored,
  unique (source_id, ord)
);
create index chunks_embedding_idx on rag.chunks using hnsw (embedding extensions.vector_cosine_ops);
create index chunks_tsv_idx       on rag.chunks using gin (tsv);
create index chunks_source_idx    on rag.chunks (source_id);

-- ------------------------------------------------------------ env.sites / env.daily
create table env.sites (
  id       text primary key,                  -- same ids as research/data-access/sites.json
  name     text not null,
  country  text not null,
  lat      double precision not null check (lat between -90 and 90),
  lon      double precision not null check (lon between -180 and 180)
);

create table env.daily (
  site_id         text not null references env.sites(id),
  day             date not null,
  variable        text not null,              -- e.g. analysed_sst, PRECTOTCORR
  value           double precision,           -- NULL = missing, never a filled-in guess
  unit            text not null,
  product         text not null,              -- e.g. MUR, POWER, Copernicus
  product_version text not null,
  primary key (site_id, day, variable, product)
);
create index daily_lookup_idx on env.daily (site_id, variable, day);

-- ------------------------------------------------------------ lock the tables down
-- RLS on with no policies: anon and authenticated see nothing even if a grant slips in.
-- service_role bypasses RLS, and only the functions below read these tables for it.
alter table rag.sources enable row level security;
alter table rag.chunks  enable row level security;
alter table env.sites   enable row level security;
alter table env.daily   enable row level security;
revoke all on all tables in schema rag from public, anon, authenticated;
revoke all on all tables in schema env from public, anon, authenticated;

-- ------------------------------------------------------------ public.rag_search
-- Hybrid search: top 20 by meaning and top 20 by keywords, merged with reciprocal rank
-- fusion. Returns the cosine similarity as well, so the caller can decide that a result
-- is too weak and abstain. The threshold is tuned on the evaluation set, not hard-coded.
create function public.rag_search(
  query_text        text,
  query_embedding   extensions.vector(384),
  filter_species    text default null,
  filter_country    text default null,
  match_count       int  default 6
)
returns table (
  chunk_id    bigint,
  source_id   text,
  citation    text,
  doi         text,
  url         text,
  section     text,
  page        int,
  content     text,
  similarity  double precision,   -- 1 - cosine distance
  keyword_hit boolean,
  rrf_score   double precision
)
language sql
stable
security definer
set search_path = rag, extensions, pg_temp
as $$
  with scope as (
    select c.id, c.embedding, c.tsv
    from rag.chunks c
    join rag.sources s on s.id = c.source_id
    where s.verified_by is not null
      and (filter_species is null or filter_species = any (s.species))
      and (filter_country is null or filter_country = any (s.countries))
  ),
  sem as (
    select id, row_number() over (order by embedding <=> query_embedding) as rnk
    from scope
    where embedding is not null
    order by embedding <=> query_embedding
    limit 20
  ),
  kw as (
    select id,
           row_number() over (order by ts_rank_cd(tsv, websearch_to_tsquery('simple', query_text)) desc) as rnk
    from scope
    where tsv @@ websearch_to_tsquery('simple', query_text)
    order by ts_rank_cd(tsv, websearch_to_tsquery('simple', query_text)) desc
    limit 20
  ),
  fused as (
    select coalesce(sem.id, kw.id) as id,
           coalesce(1.0 / (60 + sem.rnk), 0) + coalesce(1.0 / (60 + kw.rnk), 0) as score,
           kw.id is not null as keyword_hit
    from sem full join kw on kw.id = sem.id
  )
  select c.id, s.id, s.citation, s.doi, s.url, c.section, c.page, c.content,
         1 - (c.embedding <=> query_embedding),
         f.keyword_hit,
         f.score
  from fused f
  join rag.chunks  c on c.id = f.id
  join rag.sources s on s.id = c.source_id
  order by f.score desc
  limit least(greatest(match_count, 1), 12)
$$;

-- ------------------------------------------------------------ public.env_list_sites
create function public.env_list_sites(filter_country text default null)
returns table (id text, name text, country text, lat double precision, lon double precision)
language sql stable security definer
set search_path = env, pg_temp
as $$
  select s.id, s.name, s.country, s.lat, s.lon
  from env.sites s
  where filter_country is null or s.country = filter_country
  order by s.country, s.name
$$;

-- ------------------------------------------------------------ public.env_get_series
-- Raw rows, capped. The caller (the model's tool) summarises; this never interpolates
-- or fills gaps, and it refuses a window longer than two years.
create function public.env_get_series(
  p_site_id  text,
  p_variable text,
  p_from     date,
  p_to       date
)
returns table (day date, value double precision, unit text, product text, product_version text)
language plpgsql stable security definer
set search_path = env, pg_temp
as $$
begin
  if p_to < p_from then
    raise exception 'p_to must not be before p_from';
  end if;
  if p_to - p_from > 731 then
    raise exception 'window too long (max 731 days)';
  end if;
  return query
    select d.day, d.value, d.unit, d.product, d.product_version
    from env.daily d
    where d.site_id = p_site_id and d.variable = p_variable
      and d.day between p_from and p_to
    order by d.day, d.product
    limit 2000;
end
$$;

-- ------------------------------------------------------------ who may call what
-- Supabase grants EXECUTE on new public functions to anon and authenticated by default.
revoke all on function public.rag_search(text, extensions.vector, text, text, int) from public, anon, authenticated;
revoke all on function public.env_list_sites(text)                                  from public, anon, authenticated;
revoke all on function public.env_get_series(text, text, date, date)                from public, anon, authenticated;
grant execute on function public.rag_search(text, extensions.vector, text, text, int) to service_role;
grant execute on function public.env_list_sites(text)                                  to service_role;
grant execute on function public.env_get_series(text, text, date, date)                to service_role;

commit;

-- ------------------------------------------------------------ rollback (kept as a comment on purpose)
-- begin;
--   drop function if exists public.rag_search(text, extensions.vector, text, text, int);
--   drop function if exists public.env_list_sites(text);
--   drop function if exists public.env_get_series(text, text, date, date);
--   drop schema if exists rag cascade;
--   drop schema if exists env cascade;
--   -- extensions are left installed; drop them by hand only if nothing else uses them.
-- commit;
