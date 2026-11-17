"""Load the synthetic CSV files into SQL Server and validate the result.

Steps (each one prints what it did):
  1. run sql/000_create_database.sql   (unless --skip-schema)
  2. run sql/001_create_schema.sql     (drops + recreates core tables)
  3. load every CSV in data/synthetic/ in one transaction
  4. run sql/002_reporting_views.sql
  5. run sql/validation_queries.sql and fail if any 'error' check fails

Connection settings come from command-line options or environment
variables (see .env.example). No passwords are stored in the repository.

  Windows, local SQL Server Express, Windows login (most common):
      python python/load_to_sql.py --server "localhost\\SQLEXPRESS"
  SQL login (e.g. Linux/macOS):
      set WDA_SQL_USER and WDA_SQL_PASSWORD, then
      python python/load_to_sql.py --server localhost
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

import pyodbc

REPO_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = REPO_ROOT / "sql"
DEFAULT_DATA = REPO_ROOT / "data" / "synthetic"
DATABASE = "WorkforceDevAnalytics"

# Parents before children, so every foreign key target exists first.
LOAD_ORDER = [
    "data_snapshot", "cohort", "employee", "competency",
    "enrolment", "enrolment_status_event", "scheduled_session",
    "attendance", "assessment",
]


def pick_driver() -> str:
    """Use the newest installed Microsoft ODBC driver for SQL Server."""
    for name in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
        if name in pyodbc.drivers():
            return name
    sys.exit("No 'ODBC Driver 17/18 for SQL Server' found. Install it from Microsoft, then retry.")


def connect(server: str, database: str) -> pyodbc.Connection:
    parts = [
        f"DRIVER={{{os.environ.get('WDA_SQL_DRIVER') or pick_driver()}}}",
        f"SERVER={server}",
        f"DATABASE={database}",
        # Local development server with a self-signed certificate.
        "Encrypt=yes", "TrustServerCertificate=yes",
    ]
    user = os.environ.get("WDA_SQL_USER")
    if user:
        parts += [f"UID={user}", f"PWD={os.environ.get('WDA_SQL_PASSWORD', '')}"]
    else:
        parts.append("Trusted_Connection=yes")   # Windows authentication
    return pyodbc.connect(";".join(parts), autocommit=True)


def run_sql_file(conn: pyodbc.Connection, path: Path) -> None:
    """Run a .sql file, splitting it into batches on lines that say GO
    (the same thing sqlcmd and SSMS do)."""
    text = path.read_text(encoding="utf-8")
    batches = re.split(r"^\s*GO\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
    cur = conn.cursor()
    for batch in batches:
        if batch.strip():
            cur.execute(batch)
            while cur.nextset():   # drain PRINT/rowcount messages
                pass
    print(f"  ran {path.relative_to(REPO_ROOT)}")


def load_csvs(conn: pyodbc.Connection, data_dir: Path) -> None:
    """Replace all core-table rows with the CSV contents, all-or-nothing."""
    conn.autocommit = False
    cur = conn.cursor()
    cur.fast_executemany = True
    try:
        for table in reversed(LOAD_ORDER):          # children first when deleting
            cur.execute(f"DELETE FROM core.{table}")
        for table in LOAD_ORDER:
            with open(data_dir / f"{table}.csv", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                columns = next(reader)
                rows = list(reader)
            placeholders = ", ".join("?" for _ in columns)
            cur.executemany(
                f"INSERT INTO core.{table} ({', '.join(columns)}) VALUES ({placeholders})", rows)
            print(f"  loaded {len(rows):>6} rows into core.{table}")
        conn.commit()
    except Exception:
        conn.rollback()
        print("  load failed: nothing was changed (transaction rolled back)")
        raise
    finally:
        conn.autocommit = True


def run_validation(conn: pyodbc.Connection) -> bool:
    sql = (SQL_DIR / "validation_queries.sql").read_text(encoding="utf-8")
    cur = conn.cursor().execute(sql)
    while cur.description is None:   # skip the 'USE ...' message to reach the results
        cur.nextset()
    rows = cur.fetchall()
    print(f"\n  {'check':<46} {'rows':>6}  result")
    for r in rows:
        print(f"  {r.check_name:<46} {r.failing_rows:>6}  {r.result}")
    failed = [r.check_name for r in rows if r.result == "FAIL"]
    print(f"\n  {len(rows) - len(failed)} of {len(rows)} checks OK" + (f"; FAILED: {failed}" if failed else ""))
    return not failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Build 01 synthetic data into SQL Server.")
    parser.add_argument("--server", default=os.environ.get("WDA_SQL_SERVER"),
                        help=r'e.g. "localhost\SQLEXPRESS" (or set WDA_SQL_SERVER)')
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--skip-schema", action="store_true",
                        help="keep existing tables; only reload rows, views and validation")
    args = parser.parse_args()
    if not args.server:
        parser.error("give --server or set WDA_SQL_SERVER")

    if not args.skip_schema:
        print("1-2. Creating database and tables")
        run_sql_file(connect(args.server, "master"), SQL_DIR / "000_create_database.sql")
    conn = connect(args.server, DATABASE)
    if not args.skip_schema:
        run_sql_file(conn, SQL_DIR / "001_create_schema.sql")

    print(f"3. Loading CSVs from {args.data_dir}")
    load_csvs(conn, args.data_dir)

    print("4. Creating reporting views")
    run_sql_file(conn, SQL_DIR / "002_reporting_views.sql")

    print("5. Validating")
    ok = run_validation(conn)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
