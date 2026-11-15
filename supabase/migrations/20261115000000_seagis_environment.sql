-- SeaGIS environmental time series (seagis-extract export).
-- Daily per-zone aggregates of NASA MUR SST and Copernicus Marine no3/po4/pH/salinity for the
-- candidate seaweed regions. Zones are 5 km seaward candidate buffers, NOT farm extents.
-- Idempotent: safe to run more than once. Written 2026-11-15.

-- ---------------------------------------------------------------- regions
create table if not exists public.seagis_regions (
    region_id     text primary key,
    country       text not null check (country ~ '^[A-Z]{2}$'),
    name          text not null,
    status        text not null check (status in ('candidate', 'literature_verified', 'field_verified')),
    review_notes  text,
    excluded      boolean not null default false,   -- dropped from the fetch (e.g. ID-CENT-SUL)
    updated_at    timestamptz not null default now()
);
comment on table public.seagis_regions is
    'Candidate seaweed regions (config/regions.yaml). status=candidate means an unverified literature lead.';

-- ---------------------------------------------------------------- zones (ROIs)
create table if not exists public.seagis_zones (
    region_id         text not null references public.seagis_regions (region_id) on update cascade,
    subregion_id      text not null,
    geometry_version  text not null,
    name              text not null,
    status            text not null,
    buffer_km         double precision,
    area_km2          double precision,
    bbox_w            double precision not null check (bbox_w between -180 and 180),
    bbox_s            double precision not null check (bbox_s between -90 and 90),
    bbox_e            double precision not null check (bbox_e between -180 and 180),
    bbox_n            double precision not null check (bbox_n between -90 and 90),
    source            text,
    source_sha256     text,
    method            text,
    review_notes      text,
    built_at          date,
    updated_at        timestamptz not null default now(),
    primary key (region_id, subregion_id, geometry_version),
    check (bbox_s <= bbox_n)
);
comment on table public.seagis_zones is
    'Candidate coastal zones: seaward buffer of admin units. Polygons stay in data/roi/*.geojson; only the bbox is stored here.';

-- ---------------------------------------------------------------- load runs
create table if not exists public.seagis_load_runs (
    run_id         uuid primary key default gen_random_uuid(),
    plan_sha256    text not null check (plan_sha256 ~ '^[0-9a-f]{64}$'),
    period_start   date not null,
    period_end     date not null,
    started_at     timestamptz not null default now(),
    finished_at    timestamptz,
    rows_upserted  integer,
    files          integer,
    tool_version   text,
    notes          text
);
comment on table public.seagis_load_runs is 'One row per export into this database (provenance).';

-- ---------------------------------------------------------------- daily metrics
create table if not exists public.seagis_daily_metrics (
    region_id          text not null,
    subregion_id       text not null,
    geometry_version   text not null,
    dataset            text not null,      -- mur_sst | cmems_bgc_nut | cmems_bgc_car | cmems_phy_so
    variable           text not null,      -- analysed_sst, analysis_error, no3, po4, ph, so
    date               date not null,
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
    primary key (region_id, subregion_id, geometry_version, dataset, variable, date),
    foreign key (region_id, subregion_id, geometry_version)
        references public.seagis_zones (region_id, subregion_id, geometry_version) on update cascade
);
comment on table public.seagis_daily_metrics is
    'Daily area-weighted per-zone statistics. MUR land/lake cells and Copernicus static-mask land cells are excluded.';

create index if not exists seagis_daily_metrics_var_date on public.seagis_daily_metrics (dataset, variable, date);
create index if not exists seagis_daily_metrics_date on public.seagis_daily_metrics (date);

-- ---------------------------------------------------------------- access
-- Public science data: anyone with the anon key may read; only the service role / DB owner writes.
alter table public.seagis_regions       enable row level security;
alter table public.seagis_zones         enable row level security;
alter table public.seagis_load_runs     enable row level security;
alter table public.seagis_daily_metrics enable row level security;

do $$
declare t text;
begin
    foreach t in array array['seagis_regions', 'seagis_zones', 'seagis_load_runs', 'seagis_daily_metrics'] loop
        if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = t and policyname = t || '_read') then
            execute format('create policy %I on public.%I for select to anon, authenticated using (true)', t || '_read', t);
        end if;
    end loop;
end $$;
