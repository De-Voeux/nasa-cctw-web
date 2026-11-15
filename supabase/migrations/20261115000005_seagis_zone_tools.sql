-- Read-only access for the assistant to the team's regional zone metrics
-- (public.seagis_regions / seagis_zones / seagis_daily_metrics, loaded by data/seagis-nasa-extractor).
--
--  * seagis_coverage     one row per zone and variable: what we hold and from/to which date.
--  * seagis_zone_series  daily zone averages of one variable for one region (all its zones) or one zone.
--
-- Nothing is written and no team table is changed. Only service_role may call these, like the env_* functions.

begin;

create function public.seagis_coverage()
returns table (
  region_id text, region_name text, country text, subregion_id text, zone_name text,
  dataset text, variable text, units text, first_day date, last_day date, n_days bigint
)
language sql stable security definer
set search_path = public, pg_temp
as $$
  select r.region_id, r.name, r.country, z.subregion_id, z.name,
         m.dataset, m.variable, m.units, min(m.date), max(m.date), count(distinct m.date)
  from public.seagis_daily_metrics m
  join public.seagis_zones z on z.region_id = m.region_id and z.subregion_id = m.subregion_id
  join public.seagis_regions r on r.region_id = m.region_id
  group by r.region_id, r.name, r.country, z.subregion_id, z.name, m.dataset, m.variable, m.units
  order by r.region_id, z.subregion_id, m.variable;
$$;

create function public.seagis_zone_series(
  p_region_id    text,
  p_variable     text,
  p_from         date,
  p_to           date,
  p_subregion_id text default null
)
returns table (
  subregion_id text, zone_name text, day date, mean double precision, min double precision,
  max double precision, coverage_fraction double precision, units text, dataset text, product_version text
)
language plpgsql stable security definer
set search_path = public, pg_temp
as $$
begin
  if p_to < p_from then
    raise exception 'p_to must not be before p_from';
  end if;
  if p_to - p_from > 731 then
    raise exception 'window too long (max 731 days)';
  end if;
  return query
    select m.subregion_id, z.name, m.date, m.mean::float8, m.min::float8, m.max::float8,
           m.coverage_fraction::float8, m.units, m.dataset, m.product_version
    from public.seagis_daily_metrics m
    join public.seagis_zones z on z.region_id = m.region_id and z.subregion_id = m.subregion_id
    where m.region_id = p_region_id and m.variable = p_variable
      and m.date between p_from and p_to
      and (p_subregion_id is null or m.subregion_id = p_subregion_id)
    order by m.subregion_id, m.date
    limit 3000;
end
$$;

revoke all on function public.seagis_coverage()                                      from public, anon, authenticated;
revoke all on function public.seagis_zone_series(text, text, date, date, text)       from public, anon, authenticated;
grant execute on function public.seagis_coverage()                                   to service_role;
grant execute on function public.seagis_zone_series(text, text, date, date, text)    to service_role;

commit;

-- rollback:
-- drop function if exists public.seagis_coverage();
-- drop function if exists public.seagis_zone_series(text, text, date, date, text);
