"""Build 03 pipeline tests: real MongoDB -> Python ETL -> SQL Server.

Skipped unless WDA_SQL_SERVER is set AND MongoDB answers (WDA_MONGO_URI,
default mongodb://localhost:27017). They rebuild WorkforceDevAnalytics with
the horizon dataset and reseed the wda_ops.payment_cases collection.
"""

import os

import pytest

from conftest import REPO_ROOT

pytestmark = pytest.mark.skipif(not os.environ.get("WDA_SQL_SERVER"), reason="set WDA_SQL_SERVER")
SQL = REPO_ROOT / "sql"
import json as _json  # noqa: E402
MANIFEST = _json.loads((REPO_ROOT / "data/synthetic_horizon/build03/generation_manifest.json").read_text())
P1_DOCS = MANIFEST["files"]["payment_cases_phase1.jsonl"]["rows"]      # includes the malformed documents
BAD = 100


def mongo_up() -> bool:
    try:
        from pymongo import MongoClient
        MongoClient(os.environ.get("WDA_MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=3000).server_info()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def env():
    if not mongo_up():
        pytest.skip("MongoDB not reachable")
    import full_reset
    import load_build03_to_sql as b03
    import load_to_sql as b01
    import etl.seed_mongo as seed
    import etl.mongo_to_sql as etl
    import etl.reconcile as rec
    server = os.environ["WDA_SQL_SERVER"]
    assert full_reset.full_reset(server, "horizon")
    conn = b01.connect(server, b01.DATABASE)
    b01.run_sql_file(conn, SQL / "008_create_build03_tables.sql")
    b03.load_reference(conn)
    b01.run_sql_file(conn, SQL / "009_create_build03_reporting_views.sql")
    seed.seed(1)
    yield {"server": server, "conn": conn, "seed": seed, "etl": etl, "rec": rec, "b03": b03}
    # leave Build 01 rebuildable for the Build 01 SQL tests that run later
    b01.run_sql_file(conn, SQL / "010_reset_build03_objects.sql")
    b01.run_sql_file(conn, SQL / "007_reset_build02_objects.sql")
    conn.close()


def scalar(conn, sql):
    return conn.cursor().execute(sql).fetchone()[0]


def checks_fail(conn):
    cur = conn.cursor().execute((SQL / "build03_validation_queries.sql").read_text(encoding="utf-8"))
    while cur.description is None:
        cur.nextset()
    return [r.check_name for r in cur.fetchall() if r.result == "FAIL"]


def test_1_interrupted_initial_load_resumes_without_loss(env):
    """Tiny batches put batch boundaries INSIDE groups of tied updated_at values;
    a simulated crash after 3 batches must resume exactly where it stopped."""
    with pytest.raises(RuntimeError, match="simulated interruption"):
        env["etl"].run(env["server"], full=True, batch_size=37, stop_after_batches=3)
    partial = scalar(env["conn"], "SELECT COUNT(*) FROM core.payment_case")
    assert 0 < partial <= 3 * 37
    r = env["etl"].run(env["server"], batch_size=37)               # incremental: resumes from the checkpoint
    assert scalar(env["conn"], "SELECT COUNT(*) FROM core.payment_case") == P1_DOCS - BAD
    assert scalar(env["conn"], "SELECT COUNT(DISTINCT case_id) FROM stg.rejected_record") == 100
    assert partial + r["read"] == P1_DOCS                              # nothing skipped, nothing read twice
    assert env["rec"].reconcile(env["server"])["unaccounted"] == 0


def test_2_repeat_run_reads_nothing(env):
    r = env["etl"].run(env["server"])
    assert (r["read"], r["loaded"], r["rejected"]) == (0, 0, 0)


def test_3_full_reload_is_idempotent(env):
    before = scalar(env["conn"], "SELECT CHECKSUM_AGG(CHECKSUM(case_id, status, final_resolved_at)) FROM core.payment_case")
    r = env["etl"].run(env["server"], full=True)
    assert (r["read"], r["loaded"], r["rejected"]) == (P1_DOCS, P1_DOCS - BAD, BAD)
    after = scalar(env["conn"], "SELECT CHECKSUM_AGG(CHECKSUM(case_id, status, final_resolved_at)) FROM core.payment_case")
    assert before == after


def test_4_every_malformed_document_rejected_with_its_reason(env):
    reasons = {r[0] for r in env["conn"].cursor().execute(
        "SELECT DISTINCT reason FROM stg.rejected_record WHERE case_id LIKE 'PC-DQ-%'").fetchall()}
    for expected in ["missing received_at", "final resolution before receipt", "unknown case_type",
                     "unknown agent", "invalid priority"]:
        assert any(r.startswith(expected) for r in reasons), (expected, reasons)
    assert scalar(env["conn"], "SELECT COUNT(*) FROM core.payment_case WHERE case_id LIKE 'PC-DQ-%'") == 0


def test_5_incremental_update_processes_only_changed_documents(env):
    import json
    manifest = json.loads((REPO_ROOT / "data/synthetic_horizon/build03/generation_manifest.json").read_text())
    env["seed"].seed(2)
    r = env["etl"].run(env["server"], batch_size=500)
    assert r["read"] == manifest["phase2_changed_or_new"]
    assert scalar(env["conn"], "SELECT COUNT(*) FROM core.payment_case") == manifest["files"]["payment_cases_phase2.jsonl"]["rows"]
    rec = env["rec"].reconcile(env["server"])
    assert rec["unaccounted"] == 0 and rec["array_mismatches"] == 0     # changed arrays left no stale rows


def test_6_all_validation_checks_pass(env):
    assert checks_fail(env["conn"]) == []


def test_7_reporting_views_and_sla_rules(env):
    c = env["conn"]
    assert scalar(c, "SELECT COUNT(*) FROM rpt.fact_payment_case") == scalar(c, "SELECT COUNT(*) FROM core.payment_case")
    # unresolved cases are never counted as SLA met or missed; they are judged as overdue instead
    assert scalar(c, "SELECT COUNT(*) FROM rpt.fact_payment_case WHERE is_open = 1 AND sla_met IS NOT NULL") == 0
    # QA results only exist for sampled cases
    assert scalar(c, "SELECT COUNT(*) FROM rpt.fact_payment_case WHERE qa_sampled = 0 AND qa_passed IS NOT NULL") == 0
    # no agent-day rows after an exit (no manufactured zero performance)
    assert scalar(c, """SELECT COUNT(*) FROM rpt.fact_agent_day AS d JOIN core.ops_agent AS a ON a.agent_id = d.agent_id
                        WHERE a.exit_date IS NOT NULL AND d.work_date >= a.exit_date""") == 0
    # graduate improvement is visible in the reporting layer
    early = scalar(c, "SELECT AVG(CAST(qa_passed AS FLOAT)) FROM rpt.fact_payment_case WHERE tenure_band = '0-30 days' AND qa_sampled = 1")
    mature = scalar(c, "SELECT AVG(CAST(qa_passed AS FLOAT)) FROM rpt.fact_payment_case WHERE tenure_band = '90+ days' AND qa_sampled = 1")
    assert early < mature


def test_8_build04_outcome_windows(env):
    """Build 04: 30/60/90-day windows are honest (NULL when not measurable) and its checks pass."""
    import load_to_sql as b01
    c = env["conn"]
    b01.run_sql_file(c, SQL / "011_create_build04_outcome_views.sql")
    cur = c.cursor().execute((SQL / "build04_validation_queries.sql").read_text(encoding="utf-8"))
    while cur.description is None:
        cur.nextset()
    assert [r.check_name for r in cur.fetchall() if r.result == "FAIL"] == []
    assert scalar(c, "SELECT COUNT(*) FROM rpt.dim_graduate") == scalar(
        c, "SELECT COUNT(*) FROM core.ops_agent WHERE agent_type = 'Graduate'")
    # an exit never becomes a zero-performance window
    assert scalar(c, "SELECT COUNT(*) FROM rpt.fact_outcome_window WHERE is_complete = 0 AND cases_received = 0") == 0
