-- One-off: the zone labelled PH-NE-BOHOL is the whole Bohol province coast, so it becomes PH-BOHOL
-- (Faisan et al. 2021, "Bohol"). PH-NE-BOHOL stays as a region with no zone until the northeastern
-- study coast (Largo et al. 1995) is identified. Run once in the Supabase SQL editor (or psql).
-- Safe to re-run: every step is conditional. Matches config/regions.yaml as of 2026-11-15.

begin;

-- 1. the new region
insert into public.seagis_regions (region_id, country, name, status, review_notes, excluded)
values ('PH-BOHOL', 'PH', 'Bohol', 'candidate',
        'Whole-province coast (Faisan et al. 2021: five farms in Bohol, municipalities not named in the abstract)', false)
on conflict (region_id) do update
    set name = excluded.name, review_notes = excluded.review_notes, updated_at = now();

-- 2. move the zone; its daily metrics follow through the ON UPDATE CASCADE foreign key
update public.seagis_zones
   set region_id = 'PH-BOHOL',
       review_notes = 'PROVISIONAL whole-province coast (Bohol, Faisan et al. 2021).',
       updated_at = now()
 where region_id = 'PH-NE-BOHOL';

-- 3. the old region stays, without zones, as a pending lead
update public.seagis_regions
   set review_notes = 'Pending: no zone until the northeastern Bohol study coast (Largo et al. 1995) is identified',
       updated_at = now()
 where region_id = 'PH-NE-BOHOL';

commit;

-- check: expect PH-BOHOL with 1 zone, PH-NE-BOHOL with 0 zones and 0 metric rows
select r.region_id, r.name,
       (select count(*) from public.seagis_zones z where z.region_id = r.region_id)          as zones,
       (select count(*) from public.seagis_daily_metrics m where m.region_id = r.region_id) as metric_rows
  from public.seagis_regions r
 where r.region_id in ('PH-BOHOL', 'PH-NE-BOHOL')
 order by 1;
