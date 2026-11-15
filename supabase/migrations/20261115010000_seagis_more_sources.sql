-- SeaGIS: document the datasets added on 2026-11-15 (no structural change; idempotent).
-- New dataset values in seagis_daily_metrics:
--   cmems_phy_cur  uo, vo (m s-1) and derived current_speed (m s-1), current_direction (degree,
--                  clockwise from north, direction the water flows TO), current_steadiness (0..1)
--   gpm_imerg      precipitation (mm/day), GPM IMERG Late Run daily V07
--   nasa_power     T2M, RH2M, WS10M, WD10M (degree, direction the wind blows FROM),
--                  ALLSKY_SFC_SW_DWN, ALLSKY_SFC_PAR_TOT, CLOUD_AMT; one point per zone,
--                  area_weighted = false, roi_pixel_count = 1
comment on column public.seagis_daily_metrics.dataset is
    'mur_sst | cmems_bgc_nut | cmems_bgc_car | cmems_phy_so | cmems_phy_cur | gpm_imerg | nasa_power';
comment on column public.seagis_daily_metrics.variable is
    'Source variable name, or derived: current_speed, current_direction (deg, toward), current_steadiness. '
    'nasa_power WD10M is meteorological (from).';
comment on column public.seagis_daily_metrics.area_weighted is
    'true: weighted over zone cells; false: single point (nasa_power).';
comment on column public.seagis_daily_metrics.units is
    'Display label set by export (°C, mmol/m³, PSU, pH, m/s, °, 0–1, mm/day, MJ/m²/day, %). Same unit as the '
    'source, relabelled only (e.g. 1e-3 -> PSU, kelvin difference -> °C); Parquet keeps the source strings.';
