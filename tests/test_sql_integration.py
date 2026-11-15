"""End-to-end tests against a real SQL Server.

Skipped automatically unless WDA_SQL_SERVER is set (plus WDA_SQL_USER /
WDA_SQL_PASSWORD for a SQL login). They rebuild the WorkforceDevAnalytics
database from the committed CSVs, so never point them at anything else.

    $env:WDA_SQL_SERVER = "localhost\\SQLEXPRESS"   # PowerShell
    python -m pytest tests/test_sql_integration.py -v
"""

import os
from datetime import date, timedelta

import pytest

from conftest import REPO_ROOT, read_tables
from test_generator import events_by_enrolment, status_as_of

pytestmark = pytest.mark.skipif(not os.environ.get("WDA_SQL_SERVER"),
                                reason="set WDA_SQL_SERVER to run SQL Server tests")

DATA_DIR = REPO_ROOT / "data" / "synthetic"


@pytest.fixture(scope="module")
def conn():
    import load_to_sql as loader   # imported here so pyodbc is only needed for these tests
    server = os.environ["WDA_SQL_SERVER"]
    loader.run_sql_file(loader.connect(server, "master"), loader.SQL_DIR / "000_create_database.sql")
    c = loader.connect(server, loader.DATABASE)
    loader.run_sql_file(c, loader.SQL_DIR / "001_create_schema.sql")
    loader.load_csvs(c, DATA_DIR)
    loader.run_sql_file(c, loader.SQL_DIR / "002_reporting_views.sql")
    yield c
    c.close()


@pytest.fixture(scope="module")
def committed():
    return read_tables(DATA_DIR)


def scalar(conn, sql, *params):
    return conn.cursor().execute(sql, *params).fetchone()[0]


def test_row_counts_match_csv_files(conn, committed):
    for table, rows in committed.items():
        assert scalar(conn, f"SELECT COUNT(*) FROM core.{table}") == len(rows), table


def test_every_validation_check_passes(conn):
    sql = (REPO_ROOT / "sql" / "validation_queries.sql").read_text(encoding="utf-8")
    rows = conn.cursor().execute(sql).fetchall()
    failures = [(r.check_name, r.failing_rows) for r in rows if r.result == "FAIL"]
    assert not failures
    assert len(rows) >= 20


def test_constraints_reject_a_duplicate_enrolment(conn, committed):
    import pyodbc
    e = committed["enrolment"][0]
    with pytest.raises(pyodbc.IntegrityError):
        conn.cursor().execute(
            "INSERT INTO core.enrolment VALUES ('ENR-TEST', ?, ?, '2026-01-01')",
            e["employee_id"], e["cohort_id"])


def test_constraints_reject_a_score_over_100(conn, committed):
    import pyodbc
    a = committed["assessment"][0]
    with pytest.raises(pyodbc.IntegrityError):
        conn.cursor().execute(
            "INSERT INTO core.assessment VALUES ('ASM-TEST', ?, ?, 9, 1, '2026-01-01', 101, 'R1', '2026-01-01')",
            a["enrolment_id"], a["competency_id"])


@pytest.mark.parametrize("day", ["2026-04-20", "2026-05-04", "2026-06-15", "2026-06-26",
                                 "2026-07-20", "2026-09-30", "2026-11-02"])
def test_sql_status_as_of_matches_python_rule(conn, committed, day):
    """rpt.fn_enrolment_status_as_of must agree with the Python version of
    the rule on every enrolment, for dates across all cohort stages."""
    d = date.fromisoformat(day)
    events = events_by_enrolment(committed)
    expected = {eid: status_as_of(ev, d) for eid, ev in events.items() if status_as_of(ev, d)}
    rows = conn.cursor().execute(
        "SELECT enrolment_id, status FROM rpt.fn_enrolment_status_as_of(?)", d).fetchall()
    assert {r.enrolment_id: r.status for r in rows} == expected


def test_status_as_of_has_no_future_leakage(conn):
    """A withdrawn enrolment is Active the day before its withdrawal."""
    rows = conn.cursor().execute(
        "SELECT enrolment_id, effective_date FROM core.enrolment_status_event WHERE event_type = 'withdrawn'"
    ).fetchall()
    assert rows
    for r in rows:
        status = scalar(conn, "SELECT status FROM rpt.fn_enrolment_status_as_of(?) WHERE enrolment_id = ?",
                        r.effective_date - timedelta(days=1), r.enrolment_id)
        assert status == "Active"


def test_fact_attendance_makes_missing_marks_explicit(conn):
    cur = conn.cursor()
    recorded = scalar(conn, "SELECT COUNT(*) FROM core.attendance")
    eligible = scalar(conn, "SELECT COUNT(*) FROM rpt.fact_attendance")
    unrecorded = scalar(conn, "SELECT COUNT(*) FROM rpt.fact_attendance WHERE attendance_status = 'Unrecorded'")
    assert eligible == recorded + unrecorded
    assert unrecorded > 0
    # Unrecorded rows are never counted as absences
    assert scalar(conn, "SELECT COUNT(*) FROM rpt.fact_attendance WHERE is_unrecorded = 1 AND is_absent = 1") == 0
    # Grain check: one row per enrolment x session
    dupes = cur.execute("""SELECT COUNT(*) FROM (SELECT enrolment_id, session_id FROM rpt.fact_attendance
                           GROUP BY enrolment_id, session_id HAVING COUNT(*) > 1) AS d""").fetchone()[0]
    assert dupes == 0


def test_week_over_week_change_only_for_consecutive_weeks(conn):
    bad = scalar(conn, """
        SELECT COUNT(*) FROM rpt.fact_assessment AS f
        WHERE f.week_over_week_change IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM rpt.fact_assessment AS p
                          WHERE p.enrolment_id = f.enrolment_id AND p.competency_id = f.competency_id
                            AND p.programme_week = f.programme_week - 1)""")
    assert bad == 0


def test_dimensions_cover_the_facts(conn):
    """Every fact key exists in its dimension (what Power BI relationships need)."""
    checks = {
        "cohort": "SELECT COUNT(*) FROM rpt.fact_assessment f WHERE NOT EXISTS (SELECT 1 FROM rpt.dim_cohort d WHERE d.cohort_id = f.cohort_id)",
        "competency": "SELECT COUNT(*) FROM rpt.fact_assessment f WHERE NOT EXISTS (SELECT 1 FROM rpt.dim_competency d WHERE d.competency_id = f.competency_id)",
        "week": "SELECT COUNT(*) FROM rpt.fact_assessment f WHERE NOT EXISTS (SELECT 1 FROM rpt.dim_programme_week d WHERE d.programme_week = f.programme_week)",
        "date": "SELECT COUNT(*) FROM rpt.fact_attendance f WHERE NOT EXISTS (SELECT 1 FROM rpt.dim_date d WHERE d.[date] = f.session_date)",
        "enrolment": "SELECT COUNT(*) FROM rpt.fact_attendance f WHERE NOT EXISTS (SELECT 1 FROM rpt.dim_enrolment d WHERE d.enrolment_id = f.enrolment_id)",
    }
    for name, sql in checks.items():
        assert scalar(conn, sql) == 0, name
    # dim_date has one row per date
    assert scalar(conn, "SELECT COUNT(*) - COUNT(DISTINCT [date]) FROM rpt.dim_date") == 0


def test_in_progress_cohort_reported_as_in_progress(conn):
    status = scalar(conn, "SELECT schedule_status FROM rpt.dim_cohort WHERE cohort_id = 'COH-2026-03'")
    assert status == "In progress"
    assert scalar(conn, "SELECT MAX(programme_week) FROM rpt.fact_assessment WHERE cohort_id = 'COH-2026-03'") == 6
