# Run it yourself: Build 02 walkthrough (coaching, certification, readiness)

These steps are for **Windows, SQL Server 2022 Developer (default instance `localhost`), Windows login, SSMS and Python 3.11+**. Compare each result with **"You should see"**. It takes about 30 minutes.

> The expected output comes from Claude Code's cloud test environment: SQL Server 2025 on Linux, SQL login. On your machine **row counts, checksums and check results should match exactly**; only paths and timings differ.

**What Build 02 adds**
- Six `core` tables, six `rpt` views and two audit files.
- **No Build 01 file is changed**, and `001_create_schema.sql` is identical to `main`.
- Nothing in Power BI changes.

## The one rule to remember: Build 02 depends on Build 01
The Build 02 tables have foreign keys to `core.enrolment`, so **Build 01 can't be rebuilt underneath Build 02**. Build 02 therefore installs a small guard (a database trigger). If you run `001_create_schema.sql` or `load_to_sql.py` while Build 02 is loaded, it refuses **before anything is dropped**:
```
Msg 50001 ... Build 02 tables depend on Build 01. Nothing was dropped.
To rebuild, run sql/007_reset_build02_objects.sql first (or python/full_reset.py --confirm).
```
In SSMS you'll also see one follow-on error (`Msg 2714 There is already an object named 'data_snapshot'`), because 001's next batch tries to create a table that still exists. **No data has changed.**

To rebuild everything, use the **explicit full reset**:

| | Route A: SSMS | Route B: one command |
|---|---|---|
| Full reset | `007` → `000` → `001` → `002` → `003` → `validation_queries.sql` → `004` → `005` → `006` → `build02_validation_queries.sql` | `python python\full_reset.py --server localhost --confirm` |
| Build 02 only (Build 01 untouched) | `004` → `005` → `006` → `build02_validation_queries.sql` | `python python\load_build02_to_sql.py --server localhost` |

`007_reset_build02_objects.sql` removes only what Build 02 added: 6 views, 6 tables and the guard.

---

## Route A: everything in SSMS

**A1. Copy the CSVs** to a folder the SQL Server service can read. In PowerShell, from the repo folder:
```powershell
New-Item -ItemType Directory -Force C:\WorkforceData\build02 | Out-Null
Copy-Item data\synthetic\*.csv C:\WorkforceData\
Copy-Item data\synthetic\build02\*.csv C:\WorkforceData\build02\
```

**A2. Run the full reset, in this order** (**File → Open → File**, then **F5**):

| # | File | You should see |
|---|---|---|
| 1 | `sql/007_reset_build02_objects.sql` | `Build 02 objects removed. Build 01 can now be rebuilt …` (safe even on a fresh database) |
| 2 | `sql/000_create_database.sql` | `Database WorkforceDevAnalytics already exists.` (or `Created …`) |
| 3 | `sql/001_create_schema.sql` | `Build 01 core schema created.` |
| 4 | `sql/002_reporting_views.sql` | `Build 01 reporting views created.` |
| 5 | `sql/003_load_synthetic_data.sql` (`@data_folder` = `C:\WorkforceData\`) | nine `loaded …` lines, ending `loaded 6655 rows into core.assessment` |
| 6 | `sql/validation_queries.sql` | 26 rows: **24 PASS**, 2 INFO |
| 7 | `sql/004_create_build02_tables.sql` | `Build 02 core tables created (Build 01 drop guard installed).` |
| 8 | `sql/005_load_build02_data.sql` (`@data_folder` = `C:\WorkforceData\build02\`) | six `loaded …` lines (table below) |
| 9 | `sql/006_create_build02_reporting_views.sql` | `Build 02 reporting views created.` |
| 10 | `sql/build02_validation_queries.sql` | **49 rows: 30 error checks PASS, 11 story checks PASS, 8 INFO, no FAIL** |

| Table | Rows |
|---|---|
| certification_type | 2 |
| watchlist_case | 64 |
| watchlist_case_event | 113 |
| coaching_action | 110 |
| certification_attempt | 304 |
| readiness_review | 168 |

**Info rows to check in step 10:**

| Info row | Value |
|---|---|
| `info_open_watchlist_enrolments_at_snapshot` | 15 |
| `info_cases_without_any_action` | 15 |
| `info_completed_without_any_attempt` | 4 |
| `info_completed_mandatory_pairs_not_attempted` | 16 |
| `info_completed_not_reviewed` | 8 |
| `info_cases_opened_after_unrecorded_withdrawal` | 1 |
| `info_build01_enrolments` | 208 |
| `info_build01_assessment_rows` | 6655 |

**A3. See the guard work (optional, and safe).** Run `sql/001_create_schema.sql` now:
- you get `Msg 50001 … Nothing was dropped`, plus the follow-on `Msg 2714`;
- then `SELECT COUNT(*) FROM core.assessment;` still returns **6655**.

**Safe re-runs:** `005` and `003` each reload in **one transaction**, so a failure changes nothing. Running `005` twice gives the same counts.

---

## Route B: Python command line (PowerShell)

### B0. Prerequisites
These are the same as Build 01: Python 3.11+, ODBC Driver 17 or 18, and `pip install -r requirements.txt`. No new packages.

### B1. Get the branch
```powershell
cd C:\path\to\workforce-development-analytics
git fetch origin
git checkout build/02-coaching-certification-readiness
git pull
```

### B2. Regenerate both datasets: nothing should change
```powershell
python python\generate_synthetic_data.py
python python\generate_build02_data.py
git status
```
**You should see:**
- the Build 02 output: `seed=20261118  as_of_date=2026-11-02  policy=B02-R1`, the six row counts, then `audit/review_signals.csv 1108 rows` and `audit/readiness_evidence.csv 127 rows`;
- `git status`: **`nothing to commit, working tree clean`**.

### B3. Full reset, load and validate
```powershell
python python\full_reset.py --server localhost --confirm
```
**You should see:**
1. `1. Removing Build 02 objects`;
2. `2. Rebuilding Build 01` … `26 of 26 checks OK`;
3. `3. Rebuilding Build 02` … `49 of 49 checks OK`;
4. `Full reset complete: all checks OK`.

Without `--confirm`, it stops with `add --confirm to proceed`.

### B4. Run all the tests
```powershell
$env:WDA_SQL_SERVER = "localhost"
python -m pytest
python python\full_reset.py --server localhost --confirm    # put Build 02 back afterwards
```
**You should see:** **`133 passed`**. Without `$env:WDA_SQL_SERVER`, the 46 SQL tests are **skipped**, not failed.

| File | Tests | What they prove |
|---|---|---|
| `tests/test_build02_generator.py` | 44 | determinism; Build 01 files untouched; no look-ahead; every business rule plus a negative test for each; policy from config; storylines; **audit consistency** |
| `tests/test_build02_sql_integration.py` | 29 | constraints and validation reject bad data; Build 01 totals unchanged; SQL KPIs = Python KPIs; safe re-runs; **guard refuses 001 with nothing dropped**; **SQL audit = generator audit, row by row** |
| Build 01 tests | 60 | unchanged, still passing |

**Why the second command:** the Build 02 SQL tests finish by removing the Build 02 objects with `007`, so that Build 01's own tests can rebuild Build 01 with the unchanged `001`. Run the full reset afterwards to have both builds loaded again.

---

## Audit: why each review decided what it did

Two audit files are written next to the data, and SQL reproduces them independently from the database.

| File (generator) | SQL twin | Grain | Shows |
|---|---|---|---|
| `data/synthetic/build02/audit/review_signals.csv` (1,108 rows) | `sql/build02_audit_queries.sql`, query 1 | one weekly watch-list review | the evidence known at that moment; **missing marks** and the data-quality flag; signals; decision |
| `data/synthetic/build02/audit/readiness_evidence.csv` (127 rows) | query 2 | one completed enrolment at the snapshot | competency evidence; certifications attempted, passed or exhausted; latest review; **KPI populations** |

**Reading `review_signals.csv`** (open it in Excel):
- **Attendance evidence:**
  - `eligible_sessions`: the sessions the trainee should have marks for, as far as staff knew;
  - `recorded_sessions` and `present_sessions`;
  - `unrecorded_sessions` = eligible − recorded. These marks are **missing**, never absent.
- **Attendance rate:** `recorded_attendance_rate` = present ÷ recorded.
- **Flags:** `attendance_dq_flag = VERIFY_UNRECORDED_MARKS` when 2 or more marks are missing (175 of 1,108 reviews). It asks staff to check the register; it never raises a risk signal.
- **Competency evidence:** `latest_full_week`, `latest_full_week_avg`, `cohort_same_week_avg`, `gap_vs_cohort` and `week_change`.
- **Signals:** `signal_low_attendance`, `signal_low_competency` and `signal_declining_scores` (0/1).
- **What was decided:** `review_outcome` and `watchlist_case_id`.

`review_outcome` counts:

| Outcome | Reviews |
|---|---|
| No signal | 876 |
| Signal: case already open | 108 |
| Signal: case opened | 55 |
| No signal: case already open | 27 |
| Case closed at this review | 16 |
| Signal: reviewed, no case opened | 11 |
| Manual referral: case opened | 9 |
| …(entered after snapshot) | 6 |

The six "entered after snapshot" rows are decisions taken at the 2 Nov review whose records were typed in later. The audit says so and hides their IDs, so it never reveals a record that isn't in the dataset yet.

**Check the SQL twin yourself:** run `sql/build02_audit_queries.sql` in SSMS. Query 1 returns **1,108 rows** and query 2 **127 rows**, matching the CSVs. The test `test_sql_audit_reproduces_the_generator_audit` compares them value by value.

---

## Snapshot flags: what they mean (and don't)

`fact_watchlist_case.is_open_at_snapshot` and `fact_readiness_review.is_latest_review` describe the state **on the snapshot date (2026-11-02)** only.
- Filtering a report to October does **not** make them October's state.
- For another date, use the time-aware pattern in **query 10** of `sql/build02_analysis_examples.sql`. It filters on the effective date **and** the recorded date, then takes the latest row.
- With `@as_of = '2026-10-20'` it shows:
  - **13** open watch-list enrolments in Cohort 3 (15 at the snapshot);
  - Cohort 2 at **18 Approved / 14 Deferred** (39 / 18 at the snapshot).

---

## Verify it yourself in SSMS: three queries

**1. Baseline unchanged.** Expected: 208, 206, 199, 9, 63, 127, 9, 7231, 533, 6655.
```sql
SELECT (SELECT COUNT(*) FROM core.enrolment) AS enrolments,
       (SELECT COUNT(DISTINCT employee_id) FROM core.enrolment) AS employees,
       (SELECT COUNT(*) FROM core.enrolment_status_event WHERE event_type = 'started') AS started,
       (SELECT COUNT(*) FROM core.enrolment_status_event WHERE event_type = 'cancelled') AS cancelled,
       (SELECT COUNT(*) FROM rpt.dim_enrolment WHERE status_as_of_snapshot = 'Active') AS active,
       (SELECT COUNT(*) FROM rpt.dim_enrolment WHERE status_as_of_snapshot = 'Completed') AS completed,
       (SELECT COUNT(*) FROM rpt.dim_enrolment WHERE status_as_of_snapshot = 'Withdrawn') AS withdrawn,
       (SELECT COUNT(*) FROM rpt.fact_attendance) AS eligible_attendance,
       (SELECT COUNT(*) FROM rpt.fact_attendance WHERE attendance_status = 'Unrecorded') AS unrecorded,
       (SELECT COUNT(*) FROM core.assessment) AS assessments;
```

**2. KPI populations, each kept separate** (query 9 in `sql/build02_analysis_examples.sql`):

| cohort | cases | actioned | **not actioned** | completed | fully cert. | partly | attempted, none passed | **not attempted** | pairs not attempted | approved | deferred | **not reviewed** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| COH-2026-01 | 23 | 17 | 6 | 65 | 34 | 24 | 4 | 3 | 8 | 32 | 30 | 3 |
| COH-2026-02 | 20 | 15 | 5 | 62 | 47 | 12 | 2 | 1 | 8 | 39 | 18 | 5 |
| COH-2026-03 | 21 | 17 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Each split adds back up to its whole: validation checks `population_…` must all PASS. Cohort 3 is still in training, so it has no completers.

**3. Headline KPIs, each on its own grain:**
```sql
SELECT (SELECT COUNT(DISTINCT enrolment_id) FROM rpt.fact_watchlist_case
        WHERE is_open_at_snapshot = 1) AS open_watchlist_enrolments,                    -- 15
       (SELECT SUM(has_action) FROM rpt.fact_watchlist_case) AS actioned_cases,         -- 49 of 64 cases
       (SELECT SUM(is_passed) FROM rpt.fact_certification_attempt WHERE is_first_attempt = 1) AS first_passed, -- 160
       (SELECT SUM(is_first_attempt) FROM rpt.fact_certification_attempt) AS first_attempts,              -- 238
       (SELECT COUNT(*) FROM rpt.fact_readiness_review
        WHERE is_latest_review = 1 AND is_approved = 1) AS approved_now;                -- 71
```

---

## Trace one enrolment end to end

Run `sql/build02_trace_one_enrolment.sql`; the default is **ENR-00044**, Cohort 1.

| Step | What you should see |
|---|---|
| Completion (Build 01) | completed 2026-06-26, recorded 2026-06-29 |
| Watch-list case `WLC-00044-1` | opened **2026-06-01** after the week 4 review; *Low recorded attendance*; Medium |
| Case events | Opened 06-01 → Closed **2026-06-22, Improved** |
| Coaching | Attendance follow-up 06-05, Supervisor check-in 06-15 |
| Scores vs cohort | stays 1–3 points below the cohort. "Improved" = signals cleared, **not** proof that coaching worked |
| Certification | PEH 70 Passed; **OCR 69 Failed**, retaken 08-20, **89 Passed** |
| Readiness | 08-06 **Deferred, CERTIFICATION_PENDING** → 08-26 **Approved** (all gates 1, score 70.2, sign-off 1) |

In `review_signals.csv`, the ENR-00044 row with `review_after_week = 4` shows what triggered it:
- `recorded_attendance_rate` below 0.75;
- `signal_low_attendance = 1`;
- outcome **Signal: case opened**, `WLC-00044-1`.

**Part 2** traces **EMP-00025**, a person with two enrolments. The case belongs to ENR-00025 (Cohort 1, withdrew); ENR-00143 (Cohort 3) has none.

---

## Troubleshooting
| Symptom | Cause and fix |
|---|---|
| `Msg 50001 … Nothing was dropped` | You ran 001 or `load_to_sql.py` while Build 02 is loaded. Use the full reset (007 first). |
| `Build 01 tables not found` / `Snapshot mismatch` | Run the full reset; regenerate Build 02 if you changed Build 01's as-of date. |
| `Invalid object name 'core.watchlist_case'` | Build 02 isn't loaded (for example after `pytest`). Run `full_reset.py --confirm`, or 004 → 005 → 006. |
| SSMS `005` error 4860, *cannot bulk load* | `@data_folder` is wrong or unreadable by the SQL Server service. Copy the CSVs to `C:\WorkforceData\build02\`. |
| `git status` shows changed Build 02 files after regenerating | You edited `config/build02_synthetic.toml`. Undo with `git checkout -- config data`. |
| A `story_…` check FAILS after editing the config | Your thresholds removed a required storyline. That's the check doing its job. |

---

## Exercises (optional)

### SQL: retake rate by cohort
**Question:** of the first attempts that **failed**, what share were retaken, and how many retakes passed, by cohort?

**Hint:** self-join `rpt.fact_certification_attempt` on enrolment + certification with `attempt_number = 2`. Use a LEFT JOIN so un-retaken failures stay in.

<details><summary>Answer (try first)</summary>

```sql
SELECT f.cohort_id,
       COUNT(*) AS failed_first_attempts,
       SUM(CASE WHEN r.certification_attempt_id IS NOT NULL THEN 1 ELSE 0 END) AS retaken,
       CAST(100.0 * SUM(CASE WHEN r.certification_attempt_id IS NOT NULL THEN 1 ELSE 0 END)
            / COUNT(*) AS DECIMAL(5,1)) AS retake_rate_pct,
       SUM(CASE WHEN r.result = 'Passed' THEN 1 ELSE 0 END) AS retake_passed
FROM rpt.fact_certification_attempt AS f
LEFT JOIN rpt.fact_certification_attempt AS r
  ON r.enrolment_id = f.enrolment_id AND r.certification_id = f.certification_id AND r.attempt_number = 2
WHERE f.attempt_number = 1 AND f.result = 'Failed'
GROUP BY f.cohort_id;
```
Expected:
- COH-2026-01: 56 failed, 46 retaken (82.1%), 26 passed;
- COH-2026-02: 22 failed, 20 retaken (90.9%), 12 passed.
</details>

### Python: change one coaching trigger and re-run a controlled test
**Question:** raise the low-attendance trigger from 0.75 to 0.80. More watch-list cases or fewer? Predict first, then test it without touching the committed files:
```powershell
Copy-Item config\build02_synthetic.toml $env:TEMP\b02_test.toml
# edit $env:TEMP\b02_test.toml: low_recorded_attendance_rate = 0.80
python python\generate_build02_data.py --config $env:TEMP\b02_test.toml --output-dir $env:TEMP\b02_out
```
<details><summary>Answer</summary>

There are **more cases**: 79 instead of 64, and low-attendance cases go from 22 to 41. Coaching actions rise from 110 to 130.

Manual referrals fall, from 9 to 7: a referral is only recorded when there is no signal, and more trainees now have one.

Open `$env:TEMP\b02_out\audit\review_signals.csv`. The extra cases are reviews whose `recorded_attendance_rate` is between 0.75 and 0.80.

`git status` stays clean.
</details>
