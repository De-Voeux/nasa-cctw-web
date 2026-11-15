-- Monthly per-zone statistics, 2003-01 .. 2024-12 (data/seagis-nasa-extractor/scripts/monthly.py).
-- Kept apart from seagis_daily_metrics so daily and monthly values never mix. Decided 2026-11-15
-- (docs/Calzy/LONG_TERM_DATA.md). Missing months are rows with an empty mean and qc_flags
-- containing missing_at_source. Currents: mean flow vector only (current_vector_speed is the
-- magnitude of the monthly mean vector, not the mean speed).

create table if not exists public.seagis_monthly_metrics (
    region_id          text not null,
    subregion_id       text not null,
    geometry_version   text not null,
    dataset            text not null,      -- mur_sst_monthly | gpm_imerg_monthly | cmems_phy_my | cmems_bgc_my | nasa_power_monthly
    variable           text not null,
    month              date not null check (extract(day from month) = 1),
    units              text not null,
    mean               real,
    min                real,
    max                real,
    std                real,
    valid_pixel_count  integer not null check (valid_pixel_count >= 0),
    roi_pixel_count    integer not null check (roi_pixel_count >= 0),
    coverage_fraction  real check (coverage_fraction between 0 and 1),
    area_weighted      boolean not null,
    source_granule     text,
    product_version    text,
    qc_flags           text,
    plan_sha256        text not null,
    load_run_id        uuid references public.seagis_load_runs (run_id),
    loaded_at          timestamptz not null default now(),
    primary key (region_id, subregion_id, geometry_version, dataset, variable, month),
    foreign key (region_id, subregion_id, geometry_version)
        references public.seagis_zones (region_id, subregion_id, geometry_version) on update cascade
);
comment on table public.seagis_monthly_metrics is
    'Monthly area-weighted per-zone statistics, 2003-01..2024-12, long-term products only (MUR monthly via NOAA ERD, IMERG Final monthly, Copernicus multi-year, POWER monthly). month = first day of the month.';
comment on column public.seagis_monthly_metrics.plan_sha256 is 'SHA-256 of the approved outputs/monthly/requests.json';

create index if not exists seagis_monthly_metrics_var_month on public.seagis_monthly_metrics (dataset, variable, month);

alter table public.seagis_monthly_metrics enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'seagis_monthly_metrics'
                   and policyname = 'seagis_monthly_metrics_read') then
        create policy seagis_monthly_metrics_read on public.seagis_monthly_metrics for select to anon, authenticated using (true);
    end if;
end $$;
