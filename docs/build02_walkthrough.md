# Run it yourself: Build 02 walkthrough (coaching, certification, readiness)

Build 02 sits **on top of** Build 01, so load Build 01 first ([walkthrough.md](walkthrough.md)). Then follow these steps on Windows and compare each result with **"You should see"**. It takes about 20 minutes.

> The expected output comes from Claude Code's cloud test environment: SQL Server 2025 on Linux, SQL login. On your machine (SQL Server 2022 Developer, Windows login) **row counts, checksums and check results should match exactly**; only paths and timings differ.

**What Build 02 adds**
- Six `core` tables and six `rpt` views, all additive.
- One small change to Build 01's `sql/001_create_schema.sql`, which now drops the Build 02 tables first. See decision D28.
- No Power BI changes.

| | Route A: SSMS only | Route B: Python command line |
|---|---|---|
| Loads with | `sql/005_load_build02_data.sql` (`BULK INSERT`) | `python/load_build02_to_sql.py` |
| Regenerates the CSVs | no (uses the committed ones) | yes (identical files) |
| Runs the automated tests | no | yes |

---

## Route A: everything in SSMS

**A1. Load Build 01** as usual (`000` → `001` → `002` → `003` → `validation_queries.sql`: 24 PASS, 2 INFO).

**A2. Copy the Build 02 CSVs** where the SQL Server service can read them. In PowerShell, from the repo folder:
```powershell
New-Item -ItemType Directory -Force C:\WorkforceData\build02 | Out-Null
Copy-Item data\synthetic\build02\*.csv C:\WorkforceData\build02\
```

**A3. Run these files in order** in SSMS (**File → Open → File**, then **F5**):

| # | File | You should see |
|---|---|---|
| 1 | `sql/004_create_build02_tables.sql` | `Build 02 core tables created.` |
| 2 | `sql/005_load_build02_data.sql` (check that `@data_folder` = `C:\WorkforceData\build02\`) | six `loaded … rows` lines (table below) |
| 3 | `sql/006_create_build02_reporting_views.sql` | `Build 02 reporting views created.` |
| 4 | `sql/build02_validation_queries.sql` | Results: 41 rows, **26 error checks PASS + 11 story checks PASS + 4 INFO**, no `FAIL` |
| 5 | `sql/validation_queries.sql` (Build 01, again) | still 24 PASS + 2 INFO: Build 01 unaffected |

**Expected rows after step 2:**

| Table | Rows |
|---|---|
| certification_type | 2 |
| watchlist_case | 64 |
| watchlist_case_event | 113 |
| coaching_action | 110 |
| certification_attempt | 304 |
| readiness_review | 168 |

**Safe re-run:** `005` deletes and reloads only the six Build 02 tables, in **one transaction**. If anything fails, nothing changes. Run it twice and the counts stay the same; that was tested.

---

## Route B: Python command line (PowerShell)

### B0. Prerequisites
These are the same as Build 01: Python 3.11+, ODBC Driver 17/18 and `pip install -r requirements.txt`. No new packages.

### B1. Get the branch
```powershell
cd C:\path\to\workforce-development-analytics
git fetch origin
git checkout build/02-coaching-certification-readiness
```

### B2. Regenerate both datasets: nothing should change
```powershell
python python\generate_synthetic_data.py
python python\generate_build02_data.py
git status
```
**You should see:**
- **Build 02 output:** `seed=20261118  as_of_date=2026-11-02  policy=B02-R1`, with the six row counts above.
- **`git status`:** `nothing to commit, working tree clean`. Both generators reproduce the committed files byte for byte.

### B3. Load and validate
```powershell
python python\load_to_sql.py --server localhost          # Build 01 first (26 of 26 checks OK)
python python\load_build02_to_sql.py --server localhost  # then Build 02
```
**You should see:**
- `1. Checking Build 01 is loaded`, then `Build 01 snapshot 2026-11-02 found; matches the Build 02 CSVs`;
- the six `loaded` lines;
- `41 of 41 checks OK` for Build 02;
- then `26 of 26 checks OK` for Build 01, because the loader re-validates Build 01 to prove nothing broke.

**Order matters.** `load_to_sql.py` (or `001_create_schema.sql`) rebuilds the Build 01 tables, and because of the foreign keys it **drops the Build 02 tables first**. After reloading Build 01, always run `load_build02_to_sql.py` again.

### B4. Run all the tests
```powershell
$env:WDA_SQL_SERVER = "localhost"
python -m pytest
```
**You should see:** `121 passed`.

| File | Tests | What they prove |
|---|---|---|
| `tests/test_build02_generator.py` | 39 | determinism, Build 01 files never modified, no look-ahead, every business rule, a negative test per rule, policy from config, storylines |
| `tests/test_build02_sql_integration.py` | 22 | constraints reject bad rows; validation catches cross-table errors; Build 01 totals unchanged; SQL KPIs = Python KPIs; re-run safe; a failed load changes nothing |
| Build 01 tests | 60 | unchanged and still passing |

Without `$env:WDA_SQL_SERVER` the 39 SQL tests are **skipped**, not failed.

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

**2. Build 02 headline numbers.**
```sql
SELECT (SELECT COUNT(*) FROM rpt.fact_watchlist_case) AS cases,                         -- 64
       (SELECT COUNT(DISTINCT enrolment_id) FROM rpt.fact_watchlist_case
        WHERE is_open_at_snapshot = 1) AS open_watchlist_enrolments,                    -- 15 (all Cohort 3)
       (SELECT SUM(has_action) FROM rpt.fact_watchlist_case) AS actioned_cases,         -- 49
       (SELECT SUM(is_first_attempt) FROM rpt.fact_certification_attempt) AS first_attempts,              -- 238
       (SELECT SUM(is_passed) FROM rpt.fact_certification_attempt WHERE is_first_attempt = 1) AS first_passed, -- 160
       (SELECT SUM(is_retake) FROM rpt.fact_certification_attempt) AS retakes,          -- 66
       (SELECT COUNT(*) FROM rpt.fact_readiness_review
        WHERE is_latest_review = 1 AND is_approved = 1) AS approved_now;                -- 71
```

**3. Readiness by cohort.** Run query 7 in `sql/build02_analysis_examples.sql`. It keeps "Not reviewed" separate from "Deferred":

| cohort | completed | approved | deferred | not reviewed | approval rate | coverage |
|---|---|---|---|---|---|---|
| COH-2026-01 | 65 | 32 | 30 | 3 | 51.6% | 49.2% |
| COH-2026-02 | 62 | 39 | 18 | 5 | 68.4% | 62.9% |

Cohort 3 is still in training, so it has no certification attempts or readiness reviews.

`sql/build02_analysis_examples.sql` has eight queries in all, each with its numerator and denominator spelled out:
- watch-list rate;
- new cases by month;
- coaching coverage;
- change after coaching;
- certification pass rates;
- mandatory certifications met;
- readiness;
- deferral reasons.

---

## Trace one enrolment end to end

Open `sql/build02_trace_one_enrolment.sql` and run it. The default is **ENR-00044** (Cohort 1). Match each result set to its CSV in `data\synthetic\build02\`:

| Step | What you should see |
|---|---|
| Completion (Build 01) | completed 2026-06-26, recorded 2026-06-29 |
| Watch-list case `WLC-00044-1` | opened **2026-06-01** after the week 4 review, reason *Low recorded attendance*, Medium |
| Case events | Opened 06-01 → Closed **2026-06-22, Improved** (two clear reviews in a row) |
| Coaching | `CA-00044-1-1` Attendance follow-up on 06-05 (4 days after opening), `CA-00044-1-2` Supervisor check-in on 06-15 |
| Scores vs cohort | the trainee stays 1–3 points below the cohort average. "Improved" means the *signals* cleared, **not** that coaching caused a jump. |
| Certification | PEH passed first time (70); **OCR failed with 69**, retaken 2026-08-20 and **passed with 89** |
| Readiness | review 1 on 2026-08-06: **Deferred, CERTIFICATION_PENDING** (OCR not yet passed). Review 2 on 2026-08-26: **Approved**, all gates = 1, score 70.2, sign-off = 1 |

Part 2 of the script traces **EMP-00025**, a person with two enrolments. The watch-list case belongs to ENR-00025 (Cohort 1, withdrew), not to the person, and their Cohort 3 enrolment ENR-00143 has no Build 02 records.

---

## Troubleshooting
| Symptom | Cause and fix |
|---|---|
| `Build 01 tables not found` / `Snapshot mismatch` | Load Build 01 first with `load_to_sql.py`. Regenerate Build 02 if you changed Build 01's as-of date. |
| `Invalid object name 'core.watchlist_case'` after reloading Build 01 | Expected: reloading Build 01 drops the Build 02 tables. Re-run `load_build02_to_sql.py` (or 004 → 005 → 006). |
| SSMS `005`: error 4860, *cannot bulk load* | `@data_folder` is wrong or unreadable by the SQL Server service. Copy the CSVs to `C:\WorkforceData\build02\`. |
| `load_to_sql.py --skip-schema` fails with a FOREIGN KEY error | Build 02 rows still reference enrolments. Run it without `--skip-schema` (rebuilds both levels), then reload Build 02. Nothing is half-changed: the load is one transaction. |
| `git status` shows changed Build 02 CSVs after regenerating | You edited `config/build02_synthetic.toml`. Undo with `git checkout -- config data`. |
| A `story_…` check FAILS after editing the config | Your new thresholds removed a required storyline. That's the check doing its job. |

---

## Exercises (optional)

### SQL: retake rate by cohort
**Question:** of the first attempts that **failed**, what share were retaken, and how many retakes passed, by cohort?

**Hint:** join `rpt.fact_certification_attempt` to itself on enrolment + certification, with `attempt_number = 2` on the right side; use a LEFT JOIN so un-retaken failures stay in. Remember the grain: one row per failed first attempt.

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
**Question:** raise the low-attendance trigger from 0.75 to 0.80. Will there be more watch-list cases or fewer? Predict first, then test it **without touching the committed files**:
```powershell
Copy-Item config\build02_synthetic.toml $env:TEMP\b02_test.toml
# edit $env:TEMP\b02_test.toml: low_recorded_attendance_rate = 0.80
python python\generate_build02_data.py --config $env:TEMP\b02_test.toml --output-dir $env:TEMP\b02_out
```
<details><summary>Answer</summary>

There are **more cases**: 79 instead of 64, and low-attendance cases go from 22 to 41. Coaching actions rise from 110 to 130.

Manual referrals *fall*, from 9 to 7. A referral is only recorded when there is no signal, and more trainees now have one.

`git status` stays clean, because you wrote to a temp folder. The generator validated the new data against every business rule before writing it.
</details>
