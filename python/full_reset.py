"""Full reset: rebuild Build 01 AND Build 02 from the committed CSVs.

Why this exists: Build 02 tables have foreign keys to Build 01's
core.enrolment, so Build 01 can't be rebuilt while Build 02 is loaded.
This script does the steps in the only safe order:

  1. sql/007_reset_build02_objects.sql   remove Build 02 views, tables, guard
  2. Build 01: 000 -> 001 -> load CSVs -> 002 -> validation_queries.sql
  3. Build 02: 004 -> load CSVs -> 006 -> build02_validation_queries.sql

It deletes and reloads ALL rows in WorkforceDevAnalytics (synthetic data
only), so it refuses to run without --confirm.

    python python/full_reset.py --server localhost --confirm
"""

from __future__ import annotations

import argparse
import os
import sys

import load_build02_to_sql as b02
import load_to_sql as b01


def full_reset(server: str) -> bool:
    master = b01.connect(server, "master")
    b01.run_sql_file(master, b01.SQL_DIR / "000_create_database.sql")
    conn = b01.connect(server, b01.DATABASE)

    print("1. Removing Build 02 objects")
    b01.run_sql_file(conn, b01.SQL_DIR / "007_reset_build02_objects.sql")

    print("2. Rebuilding Build 01")
    b01.run_sql_file(conn, b01.SQL_DIR / "001_create_schema.sql")
    b01.load_csvs(conn, b01.DEFAULT_DATA)
    b01.run_sql_file(conn, b01.SQL_DIR / "002_reporting_views.sql")
    ok01 = b01.run_validation(conn)

    print("3. Rebuilding Build 02")
    b02.check_build01_loaded(conn, b02.DEFAULT_DATA)
    b01.run_sql_file(conn, b01.SQL_DIR / "004_create_build02_tables.sql")
    b02.load_csvs(conn, b02.DEFAULT_DATA)
    b01.run_sql_file(conn, b01.SQL_DIR / "006_create_build02_reporting_views.sql")
    ok02 = b02.run_checks(conn, b01.SQL_DIR / "build02_validation_queries.sql")
    conn.close()
    return ok01 and ok02


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Build 01 and Build 02 from the committed CSVs.")
    parser.add_argument("--server", default=os.environ.get("WDA_SQL_SERVER"),
                        help=r'e.g. "localhost" (or set WDA_SQL_SERVER)')
    parser.add_argument("--confirm", action="store_true",
                        help="required: deletes and reloads every row in WorkforceDevAnalytics")
    args = parser.parse_args()
    if not args.server:
        parser.error("give --server or set WDA_SQL_SERVER")
    if not args.confirm:
        parser.error("this deletes and reloads ALL rows in WorkforceDevAnalytics; add --confirm to proceed")
    ok = full_reset(args.server)
    print("\nFull reset complete: " + ("all checks OK" if ok else "SOME CHECKS FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
