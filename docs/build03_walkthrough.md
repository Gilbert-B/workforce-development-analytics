# Build 03 walkthrough: MongoDB → Python ETL → SQL Server (Windows)

**What it builds:** payment-operations data for Report 02. Payment-exception cases live as **documents in MongoDB**, and a Python ETL flattens, validates and loads them into SQL Server `stg` → `core` → `rpt`. Agents and deployments are relational CSVs.

It runs on the **horizon dataset** (Builds 01–02 simulated forward to 2027-06-30). The frozen 2026-11-02 baseline is untouched; to go back to it, see step 8.

## Prerequisites (once)
- **Python packages:** `pip install -r requirements.txt`, which now includes `pymongo`.
- **MongoDB on `localhost:27017`**, either way:
  - **Docker Desktop:** `docker run -d --name wda-mongo -p 27017:27017 mongo:7.0`
  - **or MongoDB Community Server** (free MSI from mongodb.com). Install it "as a service"; it listens on 27017.
- **Optional:** MongoDB Compass, the free GUI, to browse the `wda_ops.payment_cases` documents.

## Run it (PowerShell, repository root)
```powershell
git fetch origin
git checkout build/03-payment-operations
git pull
python python\generate_build03_data.py                                   # 1. documents + agents (~10 s)
python python\full_reset.py --server localhost --confirm --dataset horizon   # 2. Builds 01-02 at the horizon
python python\load_build03_to_sql.py --server localhost                  # 3. tables, agents, deployments, views
python python\etl\seed_mongo.py --phase 1                                # 4. MongoDB as on 2027-05-31
python python\etl\mongo_to_sql.py --server localhost                     # 5. initial load
python python\etl\mongo_to_sql.py --server localhost                     #    repeat: nothing to do
python python\etl\seed_mongo.py --phase 2                                # 6. MongoDB as on 2027-06-30
python python\etl\mongo_to_sql.py --server localhost                     #    incremental load
python python\load_build03_to_sql.py --server localhost --validate-only  # 7. checks
python python\etl\reconcile.py --server localhost
```

## What you should see
| Step | Output |
|---|---|
| 1 | `ops_agent.csv 149 rows`, `deployment.csv 109`, `payment_cases_phase1.jsonl 44166`, `payment_cases_phase2.jsonl 50035`, `phase 2 new or changed documents: 6211` |
| 2 | Build 01 `26 of 26`, Build 02 `49 of 49`, then `all checks OK` |
| 3 | 3 teams, 5 case types, 5 queues, 15 SLA rows, **149 agents** (109 graduates + 40 tenured), **109 deployments** |
| 4 | `Phase 1: 44166 new documents` |
| 5 | `read 44166, loaded 44066, rejected 100`, then the repeat run: `read 0, loaded 0, rejected 0` |
| 6 | `Phase 2: 5969 new documents; collection now holds 50135`, then `read 6211, loaded 6211, rejected 0` |
| 7 | `26 of 26 checks OK` (50,035 cases, 249 open at the horizon, 19 of them overdue, 11 agents exited); then `MongoDB 50135 = SQL cases 50035 + rejected 100 … OK` |

**Tests:** `python -m pytest`, with `$env:WDA_SQL_SERVER = "localhost"` set and MongoDB running, gives **170 passed**. The 7 pipeline tests are skipped if MongoDB isn't running.

**Timings (Claude's environment):** generate 6 s; initial ETL 11 s; incremental 2 s. Benchmark these before raising `target_cases` in `config/build03_synthetic.toml`.

## Look at the results (SSMS)
```sql
-- Learning curve: graduates improve with experience; tenured agents are the benchmark
SELECT tenure_band, COUNT(*) AS cases,
       CAST(100.0 * AVG(CAST(sla_met AS FLOAT)) AS DECIMAL(5,1))          AS sla_met_pct,
       CAST(100.0 * AVG(CAST(first_time_right AS FLOAT)) AS DECIMAL(5,1)) AS first_time_right_pct,
       CAST(100.0 * AVG(CAST(qa_passed AS FLOAT)) AS DECIMAL(5,1))        AS qa_pass_pct_of_sampled
FROM rpt.fact_payment_case GROUP BY tenure_band;
```

| tenure_band | cases | SLA met | first-time right | QA pass (sampled) |
|---|---|---|---|---|
| 0-30 days | 3,370 | 74.5% | 95.6% | 92.7% |
| 31-60 days | 3,824 | 79.6% | 96.8% | 96.7% |
| 61-90 days | 3,974 | 80.7% | 97.6% | 97.3% |
| 90+ days | 19,843 | 83.3% | 97.1% | 96.9% |
| Tenured | 19,024 | 84.2% | 98.0% | 97.6% |

(This quick query averages first-time-right over *all* cases, open ones included. Report 02's measure uses resolved cases only: see `docs/bi03_measure_proposal.md`.)

```sql
SELECT reason, COUNT(*) FROM stg.rejected_record GROUP BY reason;   -- 5 fault types x 20
SELECT * FROM etl.load_run ORDER BY run_id;                         -- every run, its counts and checkpoint
```

## 8. Back to the baseline (for Report 01)
```powershell
python python\full_reset.py --server localhost --confirm
```
This removes Build 03 and loads the frozen 2026-11-02 data, with Report 01's validated numbers. Report 01 on the *horizon* dataset shows later, simulated numbers; it isn't the validated baseline until the horizon is promoted.

## One concept: the checkpoint
- **The order:** the ETL reads documents sorted by `(updated_at, _id)` and saves the *last pair it committed*. The next run asks MongoDB for anything after that pair.
- **Why `_id` as well as `updated_at`:** QA reviews are batched at 14:00, so up to 54 documents share one `updated_at`. With the timestamp alone, a crash in the middle of such a group would skip or repeat documents.
- **Safe re-runs:** each case is *replaced as a whole*, children and all, so running the same batch twice changes nothing.
- **Try it:**
  ```powershell
  python python\etl\mongo_to_sql.py --server localhost --full --batch-size 37 --stop-after-batches 3
  python python\etl\mongo_to_sql.py --server localhost --batch-size 37
  ```
  The first command simulates a crash; the second resumes. `reconcile.py` still says OK.
