"""Load the generated payment-case documents into a local MongoDB.

This plays the part of the case-management SYSTEM writing its documents:
  --phase 1   the documents as they were on 2027-05-31 (drops the collection first)
  --phase 2   the documents as they are on 2027-06-30: new cases, plus some
              phase-1 cases that changed (reopened, QA reviewed, finally resolved)

    python python/etl/seed_mongo.py --phase 1
    python python/etl/seed_mongo.py --phase 2

Connection: WDA_MONGO_URI (default mongodb://localhost:27017), database wda_ops.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from bson import json_util
from pymongo import ASCENDING, MongoClient, ReplaceOne

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "synthetic_horizon" / "build03"


def collection():
    client = MongoClient(os.environ.get("WDA_MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=8000)
    return client["wda_ops"]["payment_cases"]


def seed(phase: int, data_dir: Path = DATA, batch: int = 2000) -> dict:
    coll = collection()
    if phase == 1:
        coll.drop()
    # the ETL reads in (updated_at, _id) order: this index keeps that fast
    coll.create_index([("updated_at", ASCENDING), ("_id", ASCENDING)], name="ix_updated_at_id")
    path = data_dir / f"payment_cases_phase{phase}.jsonl"
    ops, written = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            doc = json_util.loads(line)            # Extended JSON -> real BSON dates
            ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
            if len(ops) == batch:
                written += coll.bulk_write(ops, ordered=False).upserted_count; ops = []
    if ops:
        written += coll.bulk_write(ops, ordered=False).upserted_count
    return {"phase": phase, "documents_in_collection": coll.count_documents({}), "new_documents": written}


def main():
    ap = argparse.ArgumentParser(description="Seed MongoDB with generated payment-case documents.")
    ap.add_argument("--phase", type=int, choices=(1, 2), required=True)
    args = ap.parse_args()
    r = seed(args.phase)
    print(f"Phase {r['phase']}: {r['new_documents']} new documents; collection now holds {r['documents_in_collection']}")


if __name__ == "__main__":
    main()
