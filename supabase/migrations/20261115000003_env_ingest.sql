-- Loading and describing the per-site environmental series (scripts/env/load.mjs).
--
--  * env_ingest      service-role-only upsert of sites and rows, used by the loader.
--  * env_list_sites  now also reports what each site HAS: variable, product, unit, first and
--                    last date and row count. The assistant needs this to say "the data ends
--                    in December 2024" instead of guessing, and to tell a monthly mean from a
--                    daily value.
--  * env_get_series  gets an optional product filter, because one variable can exist at more
--                    than one time resolution (for example POWER monthly and POWER daily).
--
-- Products are named so the resolution is visible: 'POWER-monthly' (monthly mean, dated the
-- first of the month), 'POWER-daily', 'MUR-30d' (one SST value every 30 days, not daily).

begin;

-- ---------------------------------------------------------------- env_ingest
create function public.env_ingest(p_sites jsonb, p_rows jsonb)
returns int
language plpgsql security definer
set search_path = env, pg_temp
as $$
declare
  n int := 0;
begin
  if p_sites is not null then
    insert into env.sites as s (id, name, country, lat, lon)
    select x->>'id', x->>'name', x->>'country', (x->>'lat')::float8, (x->>'lon')::float8
    from jsonb_array_elements(p_sites) x
    on conflict (id) do update
      set name = excluded.name, country = excluded.country, lat = excluded.lat, lon = excluded.lon;
  end if;

  if p_rows is not null then
    insert into env.daily as d (site_id, day, variable, value, unit, product, product_version)
    select x->>'site_id', (x->>'day')::date, x->>'variable', (x->>'value')::float8,
           x->>'unit', x->>'product', x->>'product_version'
    from jsonb_array_elements(p_rows) x
    on conflict (site_id, day, variable, product) do update
      set value = excluded.value, unit = excluded.unit, product_version = excluded.product_version;
    get diagnostics n = row_count;
  end if;
  return n;
end
$$;

-- ---------------------------------------------------------------- env_list_sites (with coverage)
drop function if exists public.env_list_sites(text);

create function public.env_list_sites(filter_country text default null)
returns table (id text, name text, country text, lat double precision, lon double precision, coverage jsonb)
language sql stable security definer
set search_path = env, pg_temp
as $$
  select s.id, s.name, s.country, s.lat, s.lon,
         coalesce((
           select jsonb_agg(jsonb_build_object(
                    'variable', c.variable, 'product', c.product, 'unit', c.unit,
                    'from', c.first_day, 'to', c.last_day, 'n', c.n)
                  order by c.product, c.variable)
           from (
             select d.variable, d.product, min(d.unit) as unit,
                    min(d.day) as first_day, max(d.day) as last_day, count(d.value) as n
             from env.daily d
             where d.site_id = s.id
             group by d.variable, d.product
           ) c
         ), '[]'::jsonb) as coverage
  from env.sites s
  where filter_country is null or s.country = filter_country
  order by s.country, s.name
$$;

-- ---------------------------------------------------------------- env_get_series (+ product)
drop function if exists public.env_get_series(text, text, date, date);

create function public.env_get_series(
  p_site_id  text,
  p_variable text,
  p_from     date,
  p_to       date,
  p_product  text default null
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
      and (p_product is null or d.product = p_product)
    order by d.day, d.product
    limit 2000;
end
$$;

-- ---------------------------------------------------------------- who may call what
revoke all on function public.env_ingest(jsonb, jsonb)                        from public, anon, authenticated;
revoke all on function public.env_list_sites(text)                            from public, anon, authenticated;
revoke all on function public.env_get_series(text, text, date, date, text)    from public, anon, authenticated;
grant execute on function public.env_ingest(jsonb, jsonb)                     to service_role;
grant execute on function public.env_list_sites(text)                         to service_role;
grant execute on function public.env_get_series(text, text, date, date, text) to service_role;

commit;

-- rollback (restores the previous signatures; loaded rows stay):
-- drop function if exists public.env_ingest(jsonb, jsonb);
-- drop function if exists public.env_list_sites(text);
-- drop function if exists public.env_get_series(text, text, date, date, text);
-- (then re-create env_list_sites(text) and env_get_series(text,text,date,date) from migration 1)
