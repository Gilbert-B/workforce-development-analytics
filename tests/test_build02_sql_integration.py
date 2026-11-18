"""Build 02 end-to-end tests against a real SQL Server.

Skipped unless WDA_SQL_SERVER is set (plus WDA_SQL_USER / WDA_SQL_PASSWORD
for a SQL login). They REBUILD the WorkforceDevAnalytics database from the
committed CSVs (Build 01, then Build 02), so never point them at anything else.

    $env:WDA_SQL_SERVER = "localhost"      # PowerShell
    python -m pytest tests/test_build02_sql_integration.py -v

Negative tests change data inside a transaction and always roll it back.
"""

import csv
import json
import os
import shutil
from collections import defaultdict

import pytest

from conftest import REPO_ROOT, read_tables

pytestmark = pytest.mark.skipif(not os.environ.get("WDA_SQL_SERVER"),
                                reason="set WDA_SQL_SERVER to run SQL Server tests")

B01_DIR = REPO_ROOT / "data" / "synthetic"
B02_DIR = B01_DIR / "build02"
SQL = REPO_ROOT / "sql"


@pytest.fixture(scope="module")
def conn():
    import full_reset              # imported here so pyodbc is only needed for these tests
    import load_to_sql as b01
    server = os.environ["WDA_SQL_SERVER"]
    assert full_reset.full_reset(server)          # 007 -> Build 01 -> Build 02, all checks OK
    c = b01.connect(server, b01.DATABASE)
    yield c
    # Leave the database as Build 01 alone, so Build 01's own SQL tests (which
    # rebuild it with 001) can run next. Reload Build 02 afterwards with
    # python/full_reset.py --confirm.
    b01.run_sql_file(c, SQL / "007_reset_build02_objects.sql")
    c.close()


@pytest.fixture(scope="module")
def committed():
    return read_tables(B02_DIR)


def scalar(conn, sql, *params):
    return conn.cursor().execute(sql, *params).fetchone()[0]


def run_validation(conn, filename):
    cur = conn.cursor().execute((SQL / filename).read_text(encoding="utf-8"))
    while cur.description is None:      # skip the 'USE ...' message
        cur.nextset()
    return {r.check_name: r for r in cur.fetchall()}


def failing_checks(conn, filename="build02_validation_queries.sql"):
    return {name for name, r in run_validation(conn, filename).items() if r.result == "FAIL"}


def counts(conn):
    import load_build02_to_sql as b02
    return {t: scalar(conn, f"SELECT COUNT(*) FROM core.{t}") for t in b02.LOAD_ORDER}


# ---------------------------------------------------------------- loads and validates

def test_row_counts_match_csv_files(conn, committed):
    for table, rows in committed.items():
        assert scalar(conn, f"SELECT COUNT(*) FROM core.{table}") == len(rows), table


def test_every_build02_validation_check_passes(conn):
    results = run_validation(conn, "build02_validation_queries.sql")
    assert not [n for n, r in results.items() if r.result == "FAIL"]
    assert len([r for r in results.values() if r.severity == "error"]) >= 25
    assert len([r for r in results.values() if r.severity == "story"]) >= 10


def test_build01_still_validates_with_build02_loaded(conn):
    assert failing_checks(conn, "validation_queries.sql") == set()


def test_build01_reference_totals_unchanged(conn):
    q = {
        "enrolments": "SELECT COUNT(*) FROM core.enrolment",
        "employees": "SELECT COUNT(DISTINCT employee_id) FROM core.enrolment",
        "started": "SELECT COUNT(*) FROM core.enrolment_status_event WHERE event_type = 'started'",
        "cancelled": "SELECT COUNT(*) FROM core.enrolment_status_event WHERE event_type = 'cancelled'",
        "active": "SELECT COUNT(*) FROM rpt.dim_enrolment WHERE status_as_of_snapshot = 'Active'",
        "completed": "SELECT COUNT(*) FROM rpt.dim_enrolment WHERE status_as_of_snapshot = 'Completed'",
        "withdrawn": "SELECT COUNT(*) FROM rpt.dim_enrolment WHERE status_as_of_snapshot = 'Withdrawn'",
        "eligible_attendance": "SELECT COUNT(*) FROM rpt.fact_attendance",
        "unrecorded": "SELECT COUNT(*) FROM rpt.fact_attendance WHERE attendance_status = 'Unrecorded'",
        "assessments": "SELECT COUNT(*) FROM core.assessment",
    }
    expected = {"enrolments": 208, "employees": 206, "started": 199, "cancelled": 9, "active": 63,
                "completed": 127, "withdrawn": 9, "eligible_attendance": 7231, "unrecorded": 533,
                "assessments": 6655}
    assert {k: scalar(conn, sql) for k, sql in q.items()} == expected


def test_reporting_views_have_one_row_per_source_row(conn):
    pairs = [("rpt.fact_watchlist_case", "core.watchlist_case"),
             ("rpt.fact_watchlist_event", "core.watchlist_case_event"),
             ("rpt.fact_coaching_action", "core.coaching_action"),
             ("rpt.dim_certification", "core.certification_type"),
             ("rpt.fact_certification_attempt", "core.certification_attempt"),
             ("rpt.fact_readiness_review", "core.readiness_review")]
    for view, table in pairs:
        assert scalar(conn, f"SELECT COUNT(*) FROM {view}") == scalar(conn, f"SELECT COUNT(*) FROM {table}"), view


# ---------------------------------------------------------------- independent metric cross-check

def test_sql_metrics_match_an_independent_python_calculation(conn, committed):
    """Same KPIs computed two ways: Python over the CSV files, SQL over the views."""
    attempts = committed["certification_attempt"]
    first = [a for a in attempts if a["attempt_number"] == "1"]
    pairs = defaultdict(list)
    for a in attempts:
        pairs[(a["enrolment_id"], a["certification_id"])].append(a["result"])
    latest = {}
    for r in sorted(committed["readiness_review"], key=lambda r: int(r["review_number"])):
        latest[r["enrolment_id"]] = r["decision"]
    closed = {e["watchlist_case_id"] for e in committed["watchlist_case_event"] if e["event_type"] == "Closed"}
    open_enrolments = {c["enrolment_id"] for c in committed["watchlist_case"] if c["watchlist_case_id"] not in closed}
    actioned = {a["watchlist_case_id"] for a in committed["coaching_action"]}

    python = {
        "first_attempts_passed": sum(a["result"] == "Passed" for a in first),
        "first_attempts": len(first),
        "pairs_passed": sum("Passed" in v for v in pairs.values()),
        "pairs_attempted": len(pairs),
        "latest_approved": sum(v == "Approved" for v in latest.values()),
        "open_watchlist_enrolments": len(open_enrolments),
        "actioned_cases": len(actioned),
    }
    sql = {
        "first_attempts_passed": scalar(conn, "SELECT SUM(is_passed) FROM rpt.fact_certification_attempt WHERE is_first_attempt = 1"),
        "first_attempts": scalar(conn, "SELECT SUM(is_first_attempt) FROM rpt.fact_certification_attempt"),
        "pairs_passed": scalar(conn, "SELECT COUNT(*) FROM (SELECT DISTINCT enrolment_id, certification_id FROM rpt.fact_certification_attempt WHERE pair_passed = 1) p"),
        "pairs_attempted": scalar(conn, "SELECT COUNT(*) FROM (SELECT DISTINCT enrolment_id, certification_id FROM rpt.fact_certification_attempt) p"),
        "latest_approved": scalar(conn, "SELECT COUNT(*) FROM rpt.fact_readiness_review WHERE is_latest_review = 1 AND decision = 'Approved'"),
        "open_watchlist_enrolments": scalar(conn, "SELECT COUNT(DISTINCT enrolment_id) FROM rpt.fact_watchlist_case WHERE is_open_at_snapshot = 1"),
        "actioned_cases": scalar(conn, "SELECT SUM(has_action) FROM rpt.fact_watchlist_case"),
    }
    assert sql == python
    # approved headcount is never inflated by older reviews
    assert python["latest_approved"] == scalar(conn, "SELECT COUNT(DISTINCT enrolment_id) FROM rpt.fact_readiness_review WHERE is_latest_review = 1 AND is_approved = 1")


def test_repeat_employee_records_stay_on_separate_enrolments(conn):
    rows = conn.cursor().execute(
        "SELECT enrolment_id, cohort_id FROM rpt.fact_watchlist_case WHERE employee_id = 'EMP-00025'").fetchall()
    assert [tuple(r) for r in rows] == [("ENR-00025", "COH-2026-01")]
    assert scalar(conn, "SELECT COUNT(*) FROM core.enrolment WHERE employee_id = 'EMP-00025'") == 2


# ---------------------------------------------------------------- negative tests: constraints reject bad rows

def rejected(conn, sql) -> bool:
    import pyodbc
    try:
        conn.cursor().execute(sql)
    except pyodbc.Error:
        return True
    conn.cursor().execute("DELETE FROM core.readiness_review WHERE readiness_review_id LIKE 'TEST-%'; "
                          "DELETE FROM core.certification_attempt WHERE certification_attempt_id LIKE 'TEST-%'; "
                          "DELETE FROM core.watchlist_case_event WHERE watchlist_event_id LIKE 'TEST-%'; "
                          "DELETE FROM core.watchlist_case WHERE watchlist_case_id LIKE 'TEST-%';")
    return False


def test_constraint_rejects_duplicate_attempt(conn):
    assert rejected(conn, """INSERT INTO core.certification_attempt
        SELECT 'TEST-1', enrolment_id, certification_id, attempt_number, attempt_date, recorded_at, score, result, policy_version
        FROM core.certification_attempt WHERE certification_attempt_id = (SELECT MIN(certification_attempt_id) FROM core.certification_attempt)""")


def test_constraint_rejects_approval_without_signoff(conn):
    assert rejected(conn, """INSERT INTO core.readiness_review VALUES
        ('TEST-1', 'ENR-00001', 9, '2026-09-01', '2026-09-01 16:00', 'Approved', 'ALL_GATES_MET_SIGNED_OFF',
         'Operations manager', 'B02-R1', 1, 1, 1, 70.0, 0)""")


def test_constraint_rejects_competency_pass_without_score(conn):
    assert rejected(conn, """INSERT INTO core.readiness_review VALUES
        ('TEST-1', 'ENR-00001', 9, '2026-09-01', '2026-09-01 16:00', 'Deferred', 'SIGNOFF_PENDING',
         'Operations manager', 'B02-R1', 1, 1, 1, NULL, 0)""")


def test_constraint_rejects_unknown_event_type_and_missing_closure_reason(conn):
    case = scalar(conn, "SELECT MIN(watchlist_case_id) FROM core.watchlist_case")
    assert rejected(conn, f"""INSERT INTO core.watchlist_case_event VALUES
        ('TEST-1', '{case}', 'Paused', '2026-09-01', '2026-09-01 16:00', NULL, 'Training lead')""")
    assert rejected(conn, f"""INSERT INTO core.watchlist_case_event VALUES
        ('TEST-2', '{case}', 'Closed', '2026-09-01', '2026-09-01 16:00', NULL, 'Training lead')""")


def test_constraint_rejects_case_for_missing_enrolment(conn):
    assert rejected(conn, """INSERT INTO core.watchlist_case VALUES
        ('TEST-1', 'ENR-99999', '2026-09-01', '2026-09-01 11:00', 'LOW_ATTENDANCE', 'Medium', 3,
         'Observed signal', 'B02-R1')""")


def test_constraint_rejects_manual_referral_with_trigger_week(conn):
    assert rejected(conn, """INSERT INTO core.watchlist_case VALUES
        ('TEST-1', 'ENR-00001', '2026-06-01', '2026-06-01 11:00', 'MANUAL_REFERRAL', 'Low', 3,
         'Manual referral', 'B02-R1')""")


# ---------------------------------------------------------------- negative tests: validation catches cross-table errors

def failing_after(conn, statements: str) -> set:
    """Apply `statements` in a transaction, run validation, then roll back."""
    conn.autocommit = False
    try:
        conn.cursor().execute(statements)
        return failing_checks(conn)
    finally:
        conn.rollback()
        conn.autocommit = True


def test_validation_catches_overlapping_cases(conn):
    failing = failing_after(conn, """
        DECLARE @c VARCHAR(20) = (SELECT MIN(watchlist_case_id) FROM core.watchlist_case);
        INSERT INTO core.watchlist_case
            SELECT 'TEST-OVL', enrolment_id, opened_effective_date, opened_recorded_at, primary_reason_code,
                   severity, trigger_programme_week, source_type, policy_version
            FROM core.watchlist_case WHERE watchlist_case_id = @c;
        INSERT INTO core.watchlist_case_event
            SELECT 'TEST-OVL-O', 'TEST-OVL', 'Opened', effective_date, recorded_at, NULL, recorded_by_role
            FROM core.watchlist_case_event WHERE watchlist_case_id = @c AND event_type = 'Opened';""")
    assert "overlapping_watchlist_cases" in failing


def test_validation_catches_action_before_case_opened(conn):
    failing = failing_after(conn, """
        UPDATE a SET action_date = DATEADD(DAY, -5, c.opened_effective_date)
        FROM core.coaching_action AS a JOIN core.watchlist_case AS c ON c.watchlist_case_id = a.watchlist_case_id
        WHERE a.coaching_action_id = (SELECT MIN(coaching_action_id) FROM core.coaching_action);""")
    assert "coaching_action_outside_its_case" in failing


def test_validation_catches_attempt_on_completion_day(conn):
    failing = failing_after(conn, """
        UPDATE a SET attempt_date = ev.effective_date, recorded_at = ev.effective_date
        FROM core.certification_attempt AS a
        JOIN core.enrolment_status_event AS ev ON ev.enrolment_id = a.enrolment_id AND ev.event_type = 'completed'
        WHERE a.certification_attempt_id = (SELECT MIN(certification_attempt_id) FROM core.certification_attempt);""")
    assert "attempt_without_completion_or_not_after_it" in failing


def test_validation_catches_future_dated_attempt(conn):
    failing = failing_after(conn, """
        UPDATE core.certification_attempt SET attempt_date = '2026-12-01', recorded_at = '2026-12-01 15:00'
        WHERE certification_attempt_id = (SELECT MAX(certification_attempt_id) FROM core.certification_attempt);""")
    assert "records_after_snapshot_date" in failing


def test_validation_catches_result_that_disagrees_with_pass_mark(conn):
    failing = failing_after(conn, """
        UPDATE core.certification_attempt SET result = 'Passed'
        WHERE certification_attempt_id = (SELECT MIN(certification_attempt_id) FROM core.certification_attempt
                                          WHERE result = 'Failed');""")
    assert "attempt_result_disagrees_with_pass_mark" in failing


def test_validation_catches_approval_claimed_without_real_evidence(conn):
    """Flags say 'certification passed' but no pass was on record: the
    constraint can't see that, the independent evidence check can."""
    failing = failing_after(conn, """
        UPDATE core.readiness_review
        SET decision = 'Approved', decision_reason_code = 'ALL_GATES_MET_SIGNED_OFF',
            certification_gate_passed = 1, competency_gate_passed = 1, signoff_recorded = 1
        WHERE readiness_review_id = (SELECT MIN(readiness_review_id) FROM core.readiness_review
                                     WHERE decision_reason_code = 'CERTIFICATION_NOT_MET');""")
    assert "review_gates_disagree_with_recorded_evidence" in failing


# ---------------------------------------------------------------- safe, idempotent loading

def test_reloading_does_not_double_rows(conn):
    import load_build02_to_sql as b02
    before = counts(conn)
    b02.load_csvs(conn, B02_DIR)
    b02.load_csvs(conn, B02_DIR)
    assert counts(conn) == before


def test_failed_load_leaves_previous_data_untouched(conn, tmp_path):
    import load_build02_to_sql as b02
    bad = tmp_path / "build02"
    shutil.copytree(B02_DIR, bad)
    path = bad / "readiness_review.csv"
    rows = list(csv.reader(open(path, newline="", encoding="utf-8")))
    rows[-1][rows[0].index("decision")] = "Maybe"          # breaks a CHECK constraint on the LAST table
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    before = counts(conn)
    with pytest.raises(Exception):
        b02.load_csvs(conn, bad)
    assert counts(conn) == before                          # earlier tables were rolled back too
    assert failing_checks(conn) == set()


def test_loader_refuses_a_different_build01_snapshot(conn, tmp_path):
    import load_build02_to_sql as b02
    other = tmp_path / "build02"
    shutil.copytree(B02_DIR, other)
    manifest = json.loads((other / "generation_manifest.json").read_text(encoding="utf-8"))
    manifest["as_of_date"] = "2026-10-01"
    (other / "generation_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SystemExit):
        b02.check_build01_loaded(conn, other)


# ---------------------------------------------------------------- explicit reset and the Build 01 guard

def test_build01_schema_script_is_refused_while_build02_is_loaded(conn):
    """001 (unchanged from Build 01) would otherwise drop SOME tables and then
    fail on core.enrolment. The guard refuses before anything is dropped."""
    import pyodbc
    import load_to_sql as b01
    tables_before = scalar(conn, "SELECT COUNT(*) FROM sys.tables WHERE schema_id = SCHEMA_ID('core')")
    rows_before = scalar(conn, "SELECT COUNT(*) FROM core.assessment")
    with pytest.raises(pyodbc.Error, match="Nothing was dropped"):
        b01.run_sql_file(conn, SQL / "001_create_schema.sql")
    assert scalar(conn, "SELECT COUNT(*) FROM sys.tables WHERE schema_id = SCHEMA_ID('core')") == tables_before == 15
    assert scalar(conn, "SELECT COUNT(*) FROM core.assessment") == rows_before == 6655


def test_build01_schema_script_is_unchanged_from_build01():
    """D28 resolved: 001 has no Build 02 knowledge at all."""
    text = (SQL / "001_create_schema.sql").read_text(encoding="utf-8")
    assert "watchlist" not in text and "readiness" not in text and "certification" not in text


def test_full_reset_requires_confirm(monkeypatch):
    import full_reset
    monkeypatch.setattr("sys.argv", ["full_reset.py", "--server", os.environ["WDA_SQL_SERVER"]])
    with pytest.raises(SystemExit):
        full_reset.main()


# ---------------------------------------------------------------- audit: SQL reproduces the generator's audit files

def run_audit_queries(conn):
    cur = conn.cursor().execute((SQL / "build02_audit_queries.sql").read_text(encoding="utf-8"))
    results = []
    while True:
        if cur.description:
            cols = [d[0] for d in cur.description]
            results.append([dict(zip(cols, r)) for r in cur.fetchall()])
        if not cur.nextset():
            break
    return results


def _norm(value):
    if value is None or value == "":
        return None
    text = str(value)
    try:
        return round(float(text), 2)
    except ValueError:
        return text[:19]          # datetimes: 'YYYY-MM-DD HH:MM:SS'


@pytest.mark.parametrize("index, filename, key", [
    (0, "review_signals.csv", ("enrolment_id", "review_after_week")),
    (1, "readiness_evidence.csv", ("enrolment_id",)),
])
def test_sql_audit_reproduces_the_generator_audit(conn, index, filename, key):
    sql_rows = run_audit_queries(conn)[index]
    with open(B02_DIR / "audit" / filename, newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    as_key = lambda r: tuple(str(r[k]) for k in key)   # noqa: E731
    by_sql = {as_key(r): r for r in sql_rows}
    by_csv = {as_key(r): r for r in csv_rows}
    assert by_sql.keys() == by_csv.keys()
    for k, row in by_sql.items():
        for col, value in row.items():
            a, b = _norm(value), _norm(by_csv[k][col])
            if isinstance(a, float) and isinstance(b, float):
                assert abs(a - b) <= 0.011, (k, col, a, b)      # rounding of averages only
            else:
                assert a == b, (k, col, a, b)


def test_audit_sql_settings_match_the_config():
    import tomllib
    cfg = tomllib.loads((REPO_ROOT / "config" / "build02_synthetic.toml").read_text(encoding="utf-8"))["watchlist"]
    text = (SQL / "build02_audit_queries.sql").read_text(encoding="utf-8")
    for var, key in [("first_review_week", "first_review_after_week"), ("last_review_week", "last_review_after_week"),
                     ("review_hour", "review_hour"), ("window_weeks", "attendance_window_weeks"),
                     ("min_recorded", "attendance_min_recorded_sessions"),
                     ("unrecorded_flag", "unrecorded_review_min_sessions")]:
        assert f"DECLARE @{var}" in text
        line = next(line for line in text.splitlines() if line.startswith(f"DECLARE @{var} "))
        assert int(line.split("=")[1].split(";")[0]) == cfg[key], var


def test_guard_works_even_when_created_from_a_quoted_identifier_off_session(conn):
    """sqlcmd defaults QUOTED_IDENTIFIER OFF, and SQL Server stores that setting
    with the trigger. 004 sets it ON itself, so the guard must still refuse
    with its own message (not error 1934). Runs last: it recreates Build 02."""
    import pyodbc
    import load_to_sql as b01
    import load_build02_to_sql as b02
    conn.cursor().execute("SET QUOTED_IDENTIFIER OFF")
    b01.run_sql_file(conn, SQL / "004_create_build02_tables.sql")
    with pytest.raises(pyodbc.Error, match="Nothing was dropped"):
        conn.cursor().execute("DROP TABLE core.assessment")
    conn.cursor().execute("SET QUOTED_IDENTIFIER ON")
    b02.load_csvs(conn, B02_DIR)                       # put the rows back for anything after
    b01.run_sql_file(conn, SQL / "006_create_build02_reporting_views.sql")
    assert scalar(conn, "SELECT COUNT(*) FROM core.assessment") == 6655
