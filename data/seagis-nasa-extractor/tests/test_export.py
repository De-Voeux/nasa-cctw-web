"""export: DSN handling always; the database round trip only when SEAGIS_TEST_DSN points at a scratch DB."""
import os
from pathlib import Path

import pytest

from seagis_extractor import export

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT.parents[1] / "supabase/migrations"


def test_dsn_must_be_postgres_and_is_never_echoed(monkeypatch):
    monkeypatch.delenv(export.DSN_ENV, raising=False)
    with pytest.raises(export.ExportError, match="not set"):
        export.dsn_from_env()
    monkeypatch.setenv(export.DSN_ENV, "https://abc.supabase.co")
    with pytest.raises(export.ExportError, match="postgresql://"):
        export.dsn_from_env()
    monkeypatch.setenv(export.DSN_ENV, "postgresql://u:s3cret@db.example.org:6543/postgres")
    dsn = export.dsn_from_env()
    assert export.dsn_host(dsn) == "db.example.org"
    assert "s3cret" not in export.describe(dsn) and "port=6543" in export.describe(dsn)


def test_migration_is_idempotent_sql():
    sql = (MIGRATIONS / "20261115000000_seagis_environment.sql").read_text().lower()
    assert sql.count("create table if not exists") == 4 and "enable row level security" in sql
    assert "primary key (region_id, subregion_id, geometry_version, dataset, variable, date)" in sql


def test_migration_selection_ignores_application_migrations(tmp_path):
    (tmp_path / "20261115000000_seagis_environment.sql").write_text("-- extractor")
    (tmp_path / "20261115000001_rag_foundation.sql").write_text("-- application")
    assert [p.name for p in export.migration_files(tmp_path)] == [export.EXTRACTOR_MIGRATION]
    (tmp_path / "20261115000005_seagis_forecast.sql").write_text("-- extractor forecast")
    (tmp_path / "20261115010000_seagis_more_sources.sql").write_text("-- extractor comments")
    assert [p.name for p in export.migration_files(tmp_path)] == list(export.EXTRACTOR_MIGRATIONS)


@pytest.mark.skipif(not os.environ.get("SEAGIS_TEST_DSN"), reason="set SEAGIS_TEST_DSN to a scratch Postgres")
def test_round_trip_upsert_is_idempotent():
    import datetime as dt

    import pandas as pd
    import psycopg
    plan = {"plan_sha256": "a" * 64}
    m = pd.DataFrame([{"region_id": "T-R", "subregion_id": "z", "geometry_version": "v1", "dataset": "mur_sst",
                       "variable": "analysed_sst", "date": dt.date(2026, 8, 15), "data_type": "observed",
                       "units": "degree_C", "mean": 29.1,
                       "min": 28.0, "max": 30.0, "std": 0.2, "valid_pixel_count": 5, "roi_pixel_count": 6,
                       "coverage_fraction": 0.83, "area_weighted": True, "source_granule": "g",
                       "product_version": "p", "qc_flags": ""}])
    inp = {"regions": [{"region_id": "T-R", "country": "ID", "name": "Test", "status": "candidate",
                        "review_notes": None, "excluded": False}],
           "zones": [{"region_id": "T-R", "subregion_id": "z", "geometry_version": "v1", "name": "Z",
                      "status": "candidate", "buffer_km": 5.0, "area_km2": 1.0, "bbox_w": 1.0, "bbox_s": 1.0,
                      "bbox_e": 2.0, "bbox_n": 2.0, "source": None, "source_sha256": None, "method": None,
                      "review_notes": None, "built_at": None}],
           "metrics": m[export.METRIC_COLUMNS], "files": 1, "excluded": [],
           "period": (dt.date(2026, 8, 15), dt.date(2026, 8, 15))}
    with psycopg.connect(os.environ["SEAGIS_TEST_DSN"]) as conn:
        export.export(conn, inp, plan, MIGRATIONS, log=lambda *a: None)
        m.loc[0, "mean"] = 29.5
        inp["metrics"] = m[export.METRIC_COLUMNS]
        export.export(conn, inp, plan, MIGRATIONS, log=lambda *a: None)
        rows = conn.execute("select mean from seagis_daily_metrics where region_id = 'T-R'").fetchall()
        assert len(rows) == 1 and abs(rows[0][0] - 29.5) < 1e-4
        with conn.transaction():
            conn.execute("delete from seagis_daily_metrics where region_id = 'T-R'")
            conn.execute("delete from seagis_zones where region_id = 'T-R'")
            conn.execute("delete from seagis_regions where region_id = 'T-R'")


def test_display_units_are_labels_only():
    from seagis_extractor import export
    assert export.display_unit("analysed_sst", "degree_C") == "°C"
    assert export.display_unit("T2M", "C") == "°C"
    assert export.display_unit("so", "1e-3") == "PSU"
    assert export.display_unit("no3", "mmol m-3") == "mmol/m³"
    assert export.display_unit("ph", "1") == "pH"
    assert export.display_unit("current_steadiness", "1") == "0–1"
    assert export.display_unit("current_direction", "degree") == "°"
    import pytest
    with pytest.raises(export.ExportError, match="no display label"):
        export.display_unit("x", "furlongs")
