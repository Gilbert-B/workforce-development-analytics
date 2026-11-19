"""ETL: MongoDB payment-case documents -> SQL Server (stg -> core).

  extract    documents changed since the checkpoint, in (updated_at, _id) order
  transform  flatten each document into a case row + one row per nested item
             (assignments, events, QA review, QA checklist, QA errors, rework)
  validate   required fields, known codes and agents, chronology, QA arithmetic;
             a failing document goes to stg.rejected_record with its reason
  load       per batch, in ONE transaction: stage the rows, delete the cases'
             existing core rows, insert the new ones, save the checkpoint

Why it is safe to re-run:
  * the checkpoint is (updated_at, _id), so documents with the SAME updated_at
    are never skipped or double-read, even across a batch boundary;
  * a changed document REPLACES its case (all child rows rewritten), so a
    changed or shorter nested array never leaves stale rows behind;
  * rows and checkpoint commit together: if a run dies, the next run resumes
    after the last committed batch.

    python python/etl/mongo_to_sql.py                 # incremental (default)
    python python/etl/mongo_to_sql.py --full          # reload everything
Connections: WDA_MONGO_URI (default mongodb://localhost:27017) and the usual
SQL Server settings (--server / WDA_SQL_SERVER, see .env.example).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from bson import json_util
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from load_to_sql import DATABASE, connect  # noqa: E402

CHILD_TABLES = ["qa_check", "qa_error", "qa_review", "case_rework", "case_event", "case_assignment"]
INSERT_ORDER = ["payment_case", "case_assignment", "case_event", "qa_review", "qa_check", "qa_error", "case_rework"]
COLUMNS = {
    "payment_case": ["case_id", "case_type_code", "priority", "channel", "amount_band", "queue_id", "received_at",
                     "sla_policy_version", "sla_target_hours", "status", "resolution_code", "first_resolved_at",
                     "final_resolved_at", "source_updated_at", "etl_run_id"],
    "case_assignment": ["case_id", "assignment_seq", "agent_id", "assigned_at"],
    "case_event": ["case_id", "event_seq", "event_type", "event_at", "agent_id"],
    "qa_review": ["case_id", "reviewed_at", "reviewer_role", "score", "passed"],
    "qa_check": ["case_id", "item_code", "weight", "passed"],
    "qa_error": ["case_id", "error_seq", "category", "severity"],
    "case_rework": ["case_id", "rework_seq", "rework_at", "reason"],
}
EVENT_TYPES = {"created", "assigned", "in_progress", "pending_info", "resolved", "reopened"}


class Rejected(Exception):
    pass


def reference_sets(cur) -> dict:
    get = lambda sql: {r[0] for r in cur.execute(sql).fetchall()}  # noqa: E731
    return {"case_types": get("SELECT case_type_code FROM core.case_type"),
            "queues": get("SELECT queue_id FROM core.ops_queue"),
            "agents": get("SELECT agent_id FROM core.ops_agent")}


def flatten(doc: dict, ref: dict, run_id: int) -> dict[str, list]:
    """One document -> rows per table. Raises Rejected(reason) if a rule is broken."""
    def need(key, src=doc):
        if src.get(key) in (None, ""):
            raise Rejected(f"missing {key}")
        return src[key]
    case_id, received = need("_id"), need("received_at")
    if not isinstance(received, datetime):
        raise Rejected("received_at is not a date")
    if need("case_type") not in ref["case_types"]:
        raise Rejected(f"unknown case_type '{doc['case_type']}'")
    if need("priority") not in {"P1", "P2", "P3"}:
        raise Rejected(f"invalid priority '{doc['priority']}'")
    if need("queue") not in ref["queues"]:
        raise Rejected(f"unknown queue '{doc['queue']}'")
    sla, res = need("sla"), doc.get("resolution") or {}
    first, final = res.get("first_resolved_at"), res.get("final_resolved_at")
    if first and first < received:
        raise Rejected("first resolution before receipt")
    if final and (final < received or (first and final < first)):
        raise Rejected("final resolution before receipt or before first resolution")
    if (doc.get("status") == "resolved") != bool(final):
        raise Rejected("status does not match final resolution")
    rows = {t: [] for t in COLUMNS}
    rows["payment_case"].append([case_id, doc["case_type"], doc["priority"], need("channel"), need("amount_band"),
                                 doc["queue"], received, need("policy_version", sla), need("target_hours", sla),
                                 doc["status"], res.get("code"), first, final, need("updated_at"), run_id])
    for i, a in enumerate(need("assignments"), start=1):
        if a.get("agent_id") not in ref["agents"]:
            raise Rejected(f"unknown agent '{a.get('agent_id')}'")
        rows["case_assignment"].append([case_id, i, a["agent_id"], a["assigned_at"]])
    for i, e in enumerate(need("events"), start=1):
        if e.get("type") not in EVENT_TYPES or e.get("at") is None or e["at"] < received:
            raise Rejected(f"invalid event #{i}")
        if e.get("by") and e["by"] not in ref["agents"]:
            raise Rejected(f"unknown agent '{e['by']}' on event #{i}")
        rows["case_event"].append([case_id, i, e["type"], e["at"], e.get("by")])
    qa = doc.get("qa")
    if qa:
        if first is None or qa["reviewed_at"] < first:
            raise Rejected("QA review before the case was first resolved")
        score = sum(c["weight"] for c in qa["checklist"] if c["passed"])
        if score != qa["score"]:
            raise Rejected("QA score does not equal the passed checklist weights")
        rows["qa_review"].append([case_id, qa["reviewed_at"], qa["reviewer_role"], qa["score"], int(qa["passed"])])
        rows["qa_check"] += [[case_id, c["item"], c["weight"], int(c["passed"])] for c in qa["checklist"]]
        rows["qa_error"] += [[case_id, i, e["category"], e["severity"]] for i, e in enumerate(qa.get("errors", []), start=1)]
    rows["case_rework"] += [[case_id, i, r["at"], r["reason"]] for i, r in enumerate(doc.get("rework", []), start=1)]
    return rows


def last_checkpoint(cur):
    row = cur.execute("SELECT TOP (1) checkpoint_updated_at, checkpoint_case_id FROM etl.load_run "
                      "WHERE checkpoint_updated_at IS NOT NULL ORDER BY run_id DESC").fetchone()
    return (row[0], row[1]) if row else (None, None)


def apply_batch(conn, run_id: int, rows: dict, rejected: list, checkpoint, counts) -> None:
    """Stage -> replace in core -> log rejections -> move checkpoint: all or nothing."""
    conn.autocommit = False
    cur = conn.cursor()
    cur.fast_executemany = True
    try:
        for t in COLUMNS:
            cur.execute(f"DELETE FROM stg.{t}")
        for t in INSERT_ORDER:
            if rows[t]:
                cols = COLUMNS[t]
                cur.executemany(f"INSERT INTO stg.{t} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows[t])
        for t in CHILD_TABLES + ["payment_case"]:          # replace the whole case: children first
            cur.execute(f"DELETE c FROM core.{t} AS c JOIN stg.payment_case AS s ON s.case_id = c.case_id")
        for t in INSERT_ORDER:
            cols = ", ".join(COLUMNS[t])
            cur.execute(f"INSERT INTO core.{t} ({cols}) SELECT {cols} FROM stg.{t}")
        if rejected:
            cur.executemany("INSERT INTO stg.rejected_record (run_id, case_id, reason, source_updated_at, raw_document) "
                            "VALUES (?, ?, ?, ?, ?)", rejected)
        cur.execute("UPDATE etl.load_run SET docs_read = docs_read + ?, docs_loaded = docs_loaded + ?, "
                    "docs_rejected = docs_rejected + ?, checkpoint_updated_at = ?, checkpoint_case_id = ? WHERE run_id = ?",
                    counts[0], counts[1], counts[2], checkpoint[0], checkpoint[1], run_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True


def run(server: str, full: bool = False, batch_size: int = 2000, stop_after_batches: int | None = None) -> dict:
    conn = connect(server, DATABASE)
    cur = conn.cursor()
    ref = reference_sets(cur)
    coll = MongoClient(os.environ.get("WDA_MONGO_URI", "mongodb://localhost:27017"),
                       serverSelectionTimeoutMS=8000)["wda_ops"]["payment_cases"]
    if full:                                              # start again from nothing
        for t in CHILD_TABLES + ["payment_case"]:
            cur.execute(f"DELETE FROM core.{t}")
        cur.execute("DELETE FROM stg.rejected_record")
        ts, cid = None, None
    else:
        ts, cid = last_checkpoint(cur)
    run_id = cur.execute("INSERT INTO etl.load_run (mode, status) OUTPUT INSERTED.run_id VALUES (?, 'running')",
                         "full" if full else "incremental").fetchone()[0]
    query = {} if ts is None else {"$or": [{"updated_at": {"$gt": ts}}, {"updated_at": ts, "_id": {"$gt": cid}}]}
    cursor = coll.find(query).sort([("updated_at", 1), ("_id", 1)]).batch_size(batch_size)
    totals, batches = [0, 0, 0], 0
    rows, rejected, counts, checkpoint = {t: [] for t in COLUMNS}, [], [0, 0, 0], None
    try:
        for doc in cursor:
            counts[0] += 1
            try:
                for t, r in flatten(doc, ref, run_id).items():
                    rows[t] += r
                counts[1] += 1
            except (Rejected, KeyError, TypeError) as e:
                reason = str(e) if isinstance(e, Rejected) else f"malformed structure ({type(e).__name__}: {e})"
                rejected.append([run_id, str(doc.get("_id")), reason[:200], doc.get("updated_at"),
                                 json_util.dumps(doc)])
                counts[2] += 1
            checkpoint = (doc.get("updated_at"), doc.get("_id"))
            if counts[0] == batch_size:
                apply_batch(conn, run_id, rows, rejected, checkpoint, counts)
                totals = [a + b for a, b in zip(totals, counts)]
                rows, rejected, counts = {t: [] for t in COLUMNS}, [], [0, 0, 0]
                batches += 1
                if stop_after_batches and batches >= stop_after_batches:
                    raise RuntimeError(f"stopped after {batches} batches (simulated interruption)")
        if counts[0]:
            apply_batch(conn, run_id, rows, rejected, checkpoint, counts)
            totals = [a + b for a, b in zip(totals, counts)]
        cur.execute("UPDATE etl.load_run SET status = 'succeeded', finished_at = SYSDATETIME() WHERE run_id = ?", run_id)
    except Exception:
        cur.execute("UPDATE etl.load_run SET status = 'failed', finished_at = SYSDATETIME() WHERE run_id = ?", run_id)
        raise
    return {"run_id": run_id, "read": totals[0], "loaded": totals[1], "rejected": totals[2]}


def main():
    ap = argparse.ArgumentParser(description="Load payment cases from MongoDB into SQL Server.")
    ap.add_argument("--server", default=os.environ.get("WDA_SQL_SERVER"))
    ap.add_argument("--full", action="store_true", help="ignore the checkpoint and reload every document")
    ap.add_argument("--batch-size", type=int, default=2000)
    ap.add_argument("--stop-after-batches", type=int, help="demo/test: simulate a crash after N batches")
    args = ap.parse_args()
    if not args.server:
        ap.error("give --server or set WDA_SQL_SERVER")
    r = run(args.server, args.full, args.batch_size, args.stop_after_batches)
    print(f"ETL run {r['run_id']}: read {r['read']}, loaded {r['loaded']}, rejected {r['rejected']}")


if __name__ == "__main__":
    main()
