"""Reconcile MongoDB with SQL Server after an ETL run (the key ETL check).

  MongoDB documents  =  cases in core.payment_case  +  documents only ever rejected
  and, for every loaded case, its nested arrays match the rows in SQL
  (events, assignments, rework, QA checklist), so changed arrays left no stale rows.

    python python/etl/reconcile.py --server localhost
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from load_to_sql import DATABASE, connect  # noqa: E402


def reconcile(server: str) -> dict:
    coll = MongoClient(os.environ.get("WDA_MONGO_URI", "mongodb://localhost:27017"),
                       serverSelectionTimeoutMS=8000)["wda_ops"]["payment_cases"]
    cur = connect(server, DATABASE).cursor()
    loaded = {r[0] for r in cur.execute("SELECT case_id FROM core.payment_case").fetchall()}
    rejected = {r[0] for r in cur.execute("SELECT DISTINCT case_id FROM stg.rejected_record").fetchall()} - loaded
    sql_counts = {}
    for table, key in [("case_event", "events"), ("case_assignment", "assignments"), ("case_rework", "rework"),
                       ("qa_check", "qa")]:
        sql_counts[key] = Counter(dict(cur.execute(f"SELECT case_id, COUNT(*) FROM core.{table} GROUP BY case_id").fetchall()))
    mongo_ids, mismatched = set(), 0
    for doc in coll.find({}, {"events": 1, "assignments": 1, "rework": 1, "qa.checklist": 1}):
        mongo_ids.add(doc["_id"])
        if doc["_id"] in loaded:
            n = {"events": len(doc.get("events", [])), "assignments": len(doc.get("assignments", [])),
                 "rework": len(doc.get("rework", [])), "qa": len((doc.get("qa") or {}).get("checklist", []))}
            if any(sql_counts[k][doc["_id"]] != v for k, v in n.items()):
                mismatched += 1
    return {"mongo_documents": len(mongo_ids), "sql_cases": len(loaded), "rejected_only": len(rejected),
            "unaccounted": len(mongo_ids - loaded - rejected), "array_mismatches": mismatched}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--server", default=os.environ.get("WDA_SQL_SERVER"))
    args = ap.parse_args()
    r = reconcile(args.server)
    ok = r["unaccounted"] == 0 and r["array_mismatches"] == 0 and r["mongo_documents"] == r["sql_cases"] + r["rejected_only"]
    print(f"MongoDB {r['mongo_documents']} = SQL cases {r['sql_cases']} + rejected {r['rejected_only']}; "
          f"unaccounted {r['unaccounted']}; nested-array mismatches {r['array_mismatches']} -> {'OK' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
