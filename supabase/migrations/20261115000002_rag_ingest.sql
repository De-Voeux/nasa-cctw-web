-- Ingestion entry points for the Ask SEAmon RAG (scripts/rag/ingest.mjs).
--
-- Tables stay private; the ingestion script reaches them through two service-role-only
-- functions. A source can be loaded before it is reviewed: it is stored but not searchable
-- until verified_by and verified_on are set (see rag_search in the first migration).
--
-- content_sha256 lets the script skip re-embedding a source whose text has not changed,
-- and update only its metadata (for example when a reviewer marks it verified).

begin;

alter table rag.sources add column if not exists content_sha256 text;

create function public.rag_source_hash(p_id text)
returns text
language sql stable security definer
set search_path = rag, pg_temp
as $$ select content_sha256 from rag.sources where id = p_id $$;

-- p_source: { id, title, citation, doi, url, publisher, year, species[], countries[],
--             evidence_grade, verified_by, verified_on, license, content_sha256 }
-- p_chunks: [ { ord, section, page, content, embedding[384] } ] to replace the source's
--           chunks, or NULL to update the metadata only. Returns the chunks written.
create function public.rag_ingest_source(p_source jsonb, p_chunks jsonb)
returns int
language plpgsql security definer
set search_path = rag, extensions, pg_temp
as $$
declare
  n int := 0;
begin
  insert into rag.sources as s (id, title, citation, doi, url, publisher, year, species, countries,
                                evidence_grade, verified_by, verified_on, license, content_sha256)
  values (
    p_source->>'id', p_source->>'title', p_source->>'citation',
    nullif(p_source->>'doi', ''), nullif(p_source->>'url', ''), nullif(p_source->>'publisher', ''),
    nullif(p_source->>'year', '')::int,
    array(select jsonb_array_elements_text(coalesce(p_source->'species', '[]'::jsonb))),
    array(select jsonb_array_elements_text(coalesce(p_source->'countries', '[]'::jsonb))),
    nullif(p_source->>'evidence_grade', ''),
    nullif(p_source->>'verified_by', ''), nullif(p_source->>'verified_on', '')::date,
    p_source->>'license', p_source->>'content_sha256'
  )
  on conflict (id) do update set
    title = excluded.title, citation = excluded.citation, doi = excluded.doi, url = excluded.url,
    publisher = excluded.publisher, year = excluded.year, species = excluded.species,
    countries = excluded.countries, evidence_grade = excluded.evidence_grade,
    verified_by = excluded.verified_by, verified_on = excluded.verified_on,
    license = excluded.license, content_sha256 = excluded.content_sha256;

  if p_chunks is not null then
    delete from rag.chunks where source_id = p_source->>'id';
    insert into rag.chunks (source_id, ord, section, page, content, embedding)
    select p_source->>'id', (c->>'ord')::int, nullif(c->>'section', ''), nullif(c->>'page', '')::int,
           c->>'content', (c->'embedding')::text::extensions.vector
    from jsonb_array_elements(p_chunks) c;
    get diagnostics n = row_count;
  end if;
  return n;
end
$$;

revoke all on function public.rag_source_hash(text)            from public, anon, authenticated;
revoke all on function public.rag_ingest_source(jsonb, jsonb)  from public, anon, authenticated;
grant execute on function public.rag_source_hash(text)           to service_role;
grant execute on function public.rag_ingest_source(jsonb, jsonb) to service_role;

commit;

-- rollback:
-- drop function if exists public.rag_ingest_source(jsonb, jsonb);
-- drop function if exists public.rag_source_hash(text);
-- alter table rag.sources drop column if exists content_sha256;
