"""Load Build 03's relational data (teams, queues, SLA policy, agents, deployments)
and create the Build 03 tables and reporting views.

Cases are NOT loaded here: they come from MongoDB through python/etl/mongo_to_sql.py.
Needs the horizon dataset in SQL Server first:
    python python/full_reset.py --server localhost --confirm --dataset horizon
    python python/load_build03_to_sql.py --server localhost
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

from load_build02_to_sql import run_checks
from load_to_sql import DATABASE, REPO_ROOT, SQL_DIR, connect, run_sql_file

DATA = REPO_ROOT / "data" / "synthetic_horizon" / "build03"
LOAD_ORDER = ["ops_team", "case_type", "ops_queue", "sla_policy", "ops_agent", "deployment"]


def check_horizon_loaded(conn) -> None:
    row = conn.cursor().execute("SELECT CONVERT(char(10), as_of_date, 23) FROM core.data_snapshot").fetchone()
    if not row or row[0] != "2027-06-30":
        sys.exit(f"SQL Server holds snapshot {row[0] if row else 'none'}; Build 03 needs the horizon dataset:\n"
                 "  python python/full_reset.py --server localhost --confirm --dataset horizon")


def load_reference(conn, data_dir: Path = DATA) -> None:
    conn.autocommit = False
    cur = conn.cursor()
    cur.fast_executemany = True
    try:
        for table in LOAD_ORDER:
            with open(data_dir / f"{table}.csv", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                cols = next(reader)
                rows = [[v if v != "" else None for v in r] for r in reader]
            cur.executemany(f"INSERT INTO core.{table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)
            print(f"  loaded {len(rows):>5} rows into core.{table}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True


def main() -> None:
    ap = argparse.ArgumentParser(description="Create Build 03 tables and load its relational data.")
    ap.add_argument("--server", default=os.environ.get("WDA_SQL_SERVER"))
    ap.add_argument("--validate-only", action="store_true", help="just run sql/build03_validation_queries.sql")
    args = ap.parse_args()
    if not args.server:
        ap.error("give --server or set WDA_SQL_SERVER")
    conn = connect(args.server, DATABASE)
    if args.validate_only:
        sys.exit(0 if run_checks(conn, SQL_DIR / "build03_validation_queries.sql") else 1)
    check_horizon_loaded(conn)
    print("1. Creating Build 03 tables")
    run_sql_file(conn, SQL_DIR / "008_create_build03_tables.sql")
    print("2. Loading teams, queues, SLA policy, agents and deployments")
    load_reference(conn)
    print("3. Creating Build 03 reporting views")
    run_sql_file(conn, SQL_DIR / "009_create_build03_reporting_views.sql")
    print("Next: load the cases from MongoDB with python/etl/mongo_to_sql.py")


if __name__ == "__main__":
    main()
