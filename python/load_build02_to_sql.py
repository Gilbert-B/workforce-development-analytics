"""Load the Build 02 synthetic CSVs into SQL Server and validate them.

Build 01 must already be loaded (python/load_to_sql.py): Build 02 rows point
at core.enrolment. This script never changes Build 01 tables or rows.

Steps (each prints what it did):
  1. check Build 01 is loaded and has the same snapshot date as Build 02
  2. run sql/004_create_build02_tables.sql   (unless --skip-schema)
  3. load the six CSVs in ONE transaction (all or nothing)
  4. run sql/006_create_build02_reporting_views.sql
  5. run sql/build02_validation_queries.sql, then Build 01's
     sql/validation_queries.sql again (proves Build 01 still validates)

    python python/load_build02_to_sql.py --server localhost
Connection settings work exactly as for load_to_sql.py (see .env.example).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from load_to_sql import DATABASE, REPO_ROOT, SQL_DIR, connect, run_sql_file

DEFAULT_DATA = REPO_ROOT / "data" / "synthetic" / "build02"

# Parents before children (foreign keys).
LOAD_ORDER = ["certification_type", "watchlist_case", "watchlist_case_event",
              "coaching_action", "certification_attempt", "readiness_review"]


def check_build01_loaded(conn, data_dir: Path) -> None:
    """Refuse to load onto a missing or different Build 01 snapshot."""
    manifest = json.loads((data_dir / "generation_manifest.json").read_text(encoding="utf-8"))
    cur = conn.cursor()
    if not cur.execute("SELECT OBJECT_ID('core.data_snapshot')").fetchone()[0]:
        sys.exit("Build 01 tables not found. Run python/load_to_sql.py first.")
    row = cur.execute("SELECT CONVERT(char(10), as_of_date, 23) FROM core.data_snapshot").fetchone()
    if not row:
        sys.exit("core.data_snapshot is empty. Run python/load_to_sql.py first.")
    if row[0] != manifest["as_of_date"]:
        sys.exit(f"Snapshot mismatch: Build 01 in SQL is {row[0]}, Build 02 CSVs are {manifest['as_of_date']}. "
                 "Regenerate Build 02 from the same Build 01 data.")
    print(f"  Build 01 snapshot {row[0]} found; matches the Build 02 CSVs")


def load_csvs(conn, data_dir: Path) -> dict[str, int]:
    """Replace all Build 02 rows with the CSV contents, all-or-nothing."""
    conn.autocommit = False
    cur = conn.cursor()
    cur.fast_executemany = True
    counts = {}
    try:
        for table in reversed(LOAD_ORDER):          # children first when deleting
            cur.execute(f"DELETE FROM core.{table}")
        for table in LOAD_ORDER:
            with open(data_dir / f"{table}.csv", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                columns = next(reader)
                # an empty CSV field means "no value": send NULL, never ''
                rows = [[v if v != "" else None for v in row] for row in reader]
            if rows:
                placeholders = ", ".join("?" for _ in columns)
                cur.executemany(
                    f"INSERT INTO core.{table} ({', '.join(columns)}) VALUES ({placeholders})", rows)
            counts[table] = len(rows)
            print(f"  loaded {len(rows):>6} rows into core.{table}")
        conn.commit()
    except Exception:
        conn.rollback()
        print("  load failed: nothing was changed (transaction rolled back)")
        raise
    finally:
        conn.autocommit = True
    return counts


def run_checks(conn, path: Path) -> bool:
    """Run a one-row-per-check validation file and print the results."""
    cur = conn.cursor().execute(path.read_text(encoding="utf-8"))
    while cur.description is None:   # skip the 'USE ...' message to reach the results
        cur.nextset()
    rows = cur.fetchall()
    print(f"\n  {'check':<54} {'rows':>6}  result")
    for r in rows:
        print(f"  {r.check_name:<54} {r.failing_rows:>6}  {r.result}")
    failed = [r.check_name for r in rows if r.result == "FAIL"]
    print(f"\n  {len(rows) - len(failed)} of {len(rows)} checks OK" + (f"; FAILED: {failed}" if failed else ""))
    return not failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Build 02 synthetic data into SQL Server.")
    parser.add_argument("--server", default=os.environ.get("WDA_SQL_SERVER"),
                        help=r'e.g. "localhost" or "localhost\SQLEXPRESS" (or set WDA_SQL_SERVER)')
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--skip-schema", action="store_true",
                        help="keep existing Build 02 tables; only reload rows, views and validation")
    args = parser.parse_args()
    if not args.server:
        parser.error("give --server or set WDA_SQL_SERVER")

    conn = connect(args.server, DATABASE)
    print("1. Checking Build 01 is loaded")
    check_build01_loaded(conn, args.data_dir)
    if not args.skip_schema:
        print("2. Creating Build 02 tables")
        run_sql_file(conn, SQL_DIR / "004_create_build02_tables.sql")
    print(f"3. Loading CSVs from {args.data_dir}")
    load_csvs(conn, args.data_dir)
    print("4. Creating Build 02 reporting views")
    run_sql_file(conn, SQL_DIR / "006_create_build02_reporting_views.sql")
    print("5a. Validating Build 02")
    ok02 = run_checks(conn, SQL_DIR / "build02_validation_queries.sql")
    print("5b. Re-validating Build 01 (non-regression)")
    ok01 = run_checks(conn, SQL_DIR / "validation_queries.sql")
    sys.exit(0 if ok02 and ok01 else 1)


if __name__ == "__main__":
    main()
