-- Distinguish observed analysis rows from short-range forecast rows.
-- Forecast rows use the same valid date and are replaced on each refresh.
alter table public.seagis_daily_metrics
  add column if not exists data_type text not null default 'observed';

alter table public.seagis_daily_metrics
  drop constraint if exists seagis_daily_metrics_data_type_check;
alter table public.seagis_daily_metrics
  add constraint seagis_daily_metrics_data_type_check
  check (data_type in ('observed', 'forecast'));

alter table public.seagis_daily_metrics
  drop constraint if exists seagis_daily_metrics_pkey;
alter table public.seagis_daily_metrics
  add constraint seagis_daily_metrics_pkey
  primary key (region_id, subregion_id, geometry_version, dataset, variable, date, data_type);

create index if not exists seagis_daily_metrics_type_date
  on public.seagis_daily_metrics (data_type, date);

comment on column public.seagis_daily_metrics.data_type is
  'observed for satellite/model analysis; forecast for Copernicus valid-time outlook.';
