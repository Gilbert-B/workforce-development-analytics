"""Build the whole Workforce Intelligence Suite database in one command.

Runs every step in the only safe order and stops at the first failure:

  1. Builds 01-02  full reset from the horizon dataset (2027-06-30)    full_reset.py
  2. Build 03      ops tables, agents, deployments, views             load_build03_to_sql.py
  3. MongoDB       phase 1 documents (as on 2027-05-31)               etl/seed_mongo.py
  4. ETL           initial load MongoDB -> SQL Server                 etl/mongo_to_sql.py
  5. MongoDB       phase 2 documents (as on 2027-06-30: new + changed)
  6. ETL           incremental load (only the changed documents)
  7. Build 04      outcome views (30/60/90 days, training effectiveness)  sql/011
  8. Checks        Build 03 + Build 04 validation, MongoDB/SQL reconciliation

Each step is also a script you can run on its own (see docs/validation_checkpoints.md).
Prerequisites: SQL Server, MongoDB on localhost:27017 (or WDA_MONGO_URI), and
`python python/generate_build03_data.py` run once after cloning (the case
documents are generated, not committed).

    python python/build_all.py --server localhost
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import full_reset
import load_build02_to_sql as b02
import load_build03_to_sql as b03
import load_to_sql as b01

sys.path.insert(0, str(Path(__file__).resolve().parent))
from etl import mongo_to_sql, reconcile, seed_mongo  # noqa: E402

PHASE1 = b01.REPO_ROOT / "data" / "synthetic_horizon" / "build03" / "payment_cases_phase1.jsonl"


def step(n: int, text: str) -> float:
    print(f"\n=== {n}. {text}")
    return time.perf_counter()


def build_all(server: str) -> bool:
    if not PHASE1.exists():
        raise SystemExit("Case documents not found: run  python python/generate_build03_data.py  first")
    t = step(1, "Builds 01-02 from the horizon dataset")
    if not full_reset.full_reset(server, "horizon"):
        print("Build 01/02 checks failed: stopping"); return False
    conn = b01.connect(server, b01.DATABASE)
    t = step(2, "Build 03 tables, agents, deployments and views")
    b03.check_horizon_loaded(conn)
    b01.run_sql_file(conn, b01.SQL_DIR / "008_create_build03_tables.sql")
    b03.load_reference(conn)
    b01.run_sql_file(conn, b01.SQL_DIR / "009_create_build03_reporting_views.sql")
    step(3, "MongoDB phase 1"); print(seed_mongo.seed(1))
    step(4, "ETL initial load"); r1 = mongo_to_sql.run(server)
    step(5, "MongoDB phase 2"); print(seed_mongo.seed(2))
    step(6, "ETL incremental load"); r2 = mongo_to_sql.run(server)
    step(7, "Build 04 outcome views")
    b01.run_sql_file(conn, b01.SQL_DIR / "011_create_build04_outcome_views.sql")
    step(8, "Checks")
    ok3 = b02.run_checks(conn, b01.SQL_DIR / "build03_validation_queries.sql")
    ok4 = b02.run_checks(conn, b01.SQL_DIR / "build04_validation_queries.sql")
    rec = reconcile.reconcile(server)
    ok = ok3 and ok4 and rec["unaccounted"] == 0 and rec["array_mismatches"] == 0
    print(f"\nETL: initial read {r1['read']} (loaded {r1['loaded']}, rejected {r1['rejected']}); "
          f"incremental read {r2['read']}")
    conn.close()
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the whole suite database (Builds 01-04).")
    ap.add_argument("--server", default=os.environ.get("WDA_SQL_SERVER"), help='e.g. "localhost"')
    args = ap.parse_args()
    if not args.server:
        ap.error("give --server or set WDA_SQL_SERVER")
    start = time.perf_counter()
    ok = build_all(args.server)
    print(f"\nSuite build {'complete: all checks OK' if ok else 'FAILED: see above'} "
          f"({time.perf_counter() - start:.0f} s). Next: open the .pbip files in Power BI Desktop and Refresh.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
