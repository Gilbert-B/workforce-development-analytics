# Run it yourself — Build 01 walkthrough

Follow these steps on your own Windows machine and compare each result with **"You should see"**. If something differs, check [Troubleshooting](#troubleshooting) at the end.
Allow about 20 minutes.

> The expected output below comes from Claude Code's cloud test environment: SQL Server 2025 on Linux. Your SQL Server version and file paths will differ; **row counts, checksums and check results should match exactly**.

**Two ways to run it. Both build the same database:**

| | Route A: SSMS only | Route B: Python command line |
|---|---|---|
| Needs | SQL Server + SSMS | SQL Server + Python 3.11+ + ODBC driver |
| Data | the committed CSVs | regenerates the CSVs (identical files) |
| Loads with | `sql/003_load_synthetic_data.sql` (`BULK INSERT`) | `python/load_to_sql.py` |
| Runs the automated tests | no | yes |

Start with **Route A**. Use Route B when you want to change the generator, or run the tests.

---

## Route A — everything in SSMS

**A1. Get the files.** Clone the repo with `git clone https://github.com/Gilbert-B/workforce-development-analytics.git`, or on GitHub use **Code → Download ZIP** and unzip it.

**A2. Put the CSVs where SQL Server can read them.** In PowerShell, from the repo folder:
```powershell
New-Item -ItemType Directory -Force C:\WorkforceData | Out-Null
Copy-Item data\synthetic\*.csv C:\WorkforceData\
```
**Why a separate folder:** with `BULK INSERT`, the **SQL Server service** reads the file, not you. That service runs under its own Windows account, which normally can't see inside `C:\Users\<you>\`. (`C:\WorkforceData` is outside the repo, so nothing in it is ever committed.)

**A3. In SSMS, connect to your instance.** Then open and run each file below in order, with **File → Open → File** and then **F5**.

| # | File | You should see in the Messages tab |
|---|---|---|
| 1 | `sql/000_create_database.sql` | `Created database WorkforceDevAnalytics.` |
| 2 | `sql/001_create_schema.sql` | `Build 01 core schema created.` |
| 3 | `sql/002_reporting_views.sql` | `Build 01 reporting views created.` |
| 4 | `sql/003_load_synthetic_data.sql`: first check `@data_folder` near the top says `C:\WorkforceData\` | nine `loaded … rows` lines, ending with `loaded 6655 rows into core.assessment` |
| 5 | `sql/validation_queries.sql` | Results tab: 26 rows, **24 `PASS`** and 2 `INFO`, no `FAIL` |

Then go straight to [step 5](#5-look-at-the-data-yourself-ssms) and [step 6](#6-trace-one-person-through-the-whole-pipeline) below. Both are SSMS steps.

**Expected row counts after step 4:**

| Table | Rows | Table | Rows |
|---|---|---|---|
| data_snapshot | 1 | enrolment_status_event | 552 |
| cohort | 3 | scheduled_session | 120 |
| employee | 206 | attendance | 6,698 |
| competency | 5 | assessment | 6,655 |
| enrolment | 208 | | |

**How `003_load_synthetic_data.sql` works:**
- It loops over the nine tables in foreign-key order: it deletes children first, then loads parents first.
- For each table it builds a `BULK INSERT` statement as text and runs it. This is **dynamic SQL**, needed because `BULK INSERT` won't accept a variable as the file name. Add `PRINT @sql;` inside the loop to see each generated statement.
- Everything runs in one **transaction**, so a wrong folder or a bad row changes nothing. That's tested: a wrong path fails with error 4860 and leaves the existing data intact.
- It's safe to re-run whenever you like.

---

## Route B — Python command line

## 0. Check your prerequisites (PowerShell)

```powershell
py --version                                  # need 3.11 or newer
Get-Service *SQL* | Format-Table Name, Status # your SQL Server instance(s)
Get-OdbcDriver -Name "*SQL Server*" | Select-Object Name -Unique
```
**You should see:**
- Python 3.11 or newer.
- A service named `MSSQL$SQLEXPRESS` (the instance is then `localhost\SQLEXPRESS`) or `MSSQLSERVER` (the instance is just `localhost`), with Status `Running`.
- `ODBC Driver 17 for SQL Server` or `ODBC Driver 18 for SQL Server` in the driver list.

## 1. Set up the project

```powershell
git clone https://github.com/Gilbert-B/workforce-development-analytics.git
cd workforce-development-analytics
py -m venv .venv
.venv\Scripts\activate          # your prompt now starts with (.venv)
pip install -r requirements.txt
```
**Why a virtual environment (`.venv`)?** It keeps this project's packages separate from everything else on your computer, so other projects can't break it, and vice versa.

## 2. Generate the synthetic data

```powershell
python python/generate_synthetic_data.py
git status --short data/
```
**You should see** (your folder path will differ):
```
Synthetic data written to ...\data\synthetic
  seed=20261115  as_of_date=2026-11-02
  cohort.csv                          3 rows  sha256=e0cb3ede0399
  employee.csv                      206 rows  sha256=e88e2e930e2f
  competency.csv                      5 rows  sha256=ee4c0920ab7e
  enrolment.csv                     208 rows  sha256=17120a30aba4
  enrolment_status_event.csv        552 rows  sha256=a810e7ade15d
  scheduled_session.csv             120 rows  sha256=cb9278e1e1c4
  attendance.csv                   6698 rows  sha256=518c31e4ad01
  assessment.csv                   6655 rows  sha256=08a6d68bda9d
  data_snapshot.csv                   1 rows  sha256=33b58d233a16
```
`git status` then prints **nothing**. You regenerated byte-identical copies of the committed files, which is the proof that generation is reproducible.

**Try it:** run it again with `--as-of-date 2026-09-01 --output-dir tmp/early`. Fewer rows come out: it's the same simulated history, observed at an earlier date. (`tmp/` is git-ignored.)

## 3. Build, load and validate the database

```powershell
python python/load_to_sql.py --server "localhost\SQLEXPRESS"     # or --server localhost
```
**You should see** five numbered steps, ending in:
```
  loaded    208 rows into core.enrolment
  loaded    552 rows into core.enrolment_status_event
  ...
  enrolled_before_hire_date                           0  PASS
  ...
  info_employees_with_more_than_one_enrolment         2  INFO
  info_unrecorded_eligible_attendance               533  INFO

  26 of 26 checks OK
```
- A **FAIL** row names the broken rule; look up that check in `sql/validation_queries.sql`.
- The script exits with an error code on any failure, so it can't fail silently.

**Why one script does five steps:**
- A fresh checkout needs only one command.
- The load runs in a **transaction**: if any row is rejected, nothing is changed.
- You can still run each SQL file yourself in SSMS: `000` → `001` → load → `002`.

## 4. Run the tests

```powershell
python -m pytest                                   # no database needed
$env:WDA_SQL_SERVER = "localhost\SQLEXPRESS"
python -m pytest -v tests/test_sql_integration.py  # rebuilds the database, then tests it
```
**You should see:** `43 passed, 16 skipped` for the first command, then `16 passed` for the second.
The test names describe the rules, for example `test_status_as_of_has_no_future_leakage`. Reading the failing test's name is the fastest way to find a problem.

## 5. Look at the data yourself (SSMS)

Connect SSMS to your instance and open the **WorkforceDevAnalytics** database. Then run `sql/analysis_examples.sql`.
**You should see** these numbers, among others:

| Check | Cohort 1 | Cohort 2 | Cohort 3 |
|---|---|---|---|
| Starting headcount | 68 | 67 | 64 |
| Present ÷ recorded attendance | 91.0% | 93.0% | 92.2% |
| Average score, Week 1 → latest week | 52.4 → 73.1 | 52.9 → 80.4 | 52.1 → 72.0 (Week 6) |

There's a full set of reference numbers in [`build_log.md`](build_log.md). When you build a DAX measure, it should reproduce them.

## 6. Trace one person through the whole pipeline

```powershell
sqlcmd -S "localhost\SQLEXPRESS" -E -C -d WorkforceDevAnalytics -i sql\trace_one_enrolment.sql
```
(Or open the file in SSMS and press F5.) It follows `EMP-00025`, who **withdrew from Cohort 1 and re-enrolled in Cohort 3**.

**You should see, and why it matters:**

| Section | What you'll see | The rule it shows |
|---|---|---|
| 2 | Two enrolments, `ENR-00025` and `ENR-00143`, for one person | A person ≠ an enrolment; cohort belongs on the enrolment |
| 3 | Withdrawal **effective 2026-06-17**, but **recorded 2026-06-23** | The business date and the data-entry date are different things |
| 4 | `Active` from 2026-05-04 to 2026-06-17, then `Withdrawn` with `valid_to = NULL` | `LEAD()` turns events into periods |
| 5 | `Active` on 06-16, `Withdrawn` on 06-17 | As-of status uses only events on or before the date |
| 6 | Week 7 has 2 eligible sessions, not 5 | Attendance stops at the withdrawal date |
| 6 | Weeks 2 and 6 each have 2 `unrecorded` | Missing marks are not absences |
| 7 | Cohort 1 scores flatten and then drop (60.4 → 56.8); Cohort 3 scores climb (46.4 → 74.0) | A designed "disengaging trainee" pattern |

**Where this person comes from in the Python code** (`python/generate_synthetic_data.py`):
1. `simulate()` creates the full 8-week "truth" for each enrolment: an `EnrolmentTruth` object with attendance, withdrawal date and scores.
2. `observe()` keeps only what had happened **and** been recorded by the as-of date. That's why a withdrawal that isn't recorded yet doesn't appear.
3. `write_csv()` writes the tables, and `load_to_sql.py` → `load_csvs()` inserts them.
4. The `rpt` views in `sql/002_reporting_views.sql` apply the reporting rules.

Change `@employee_id` at the top of the script to trace anyone else.
**Tracing one record found a real bug in this build:** people were enrolling before they were hired. All 23 automated checks passed anyway, because none of them compared those two dates. See `build_log.md`, challenge 1.

---

## One concept to understand: effective-dated events

The database never stores "current status" in a column. It stores **events with dates**: started on X, withdrawn on Y. The status on any date is then *calculated*: find the latest event on or before that date.

- **Why:** a status column only tells you about today. With events, Power BI can answer "how many were active in Week 3?" for any cohort, and the answer never changes when new events arrive later.
- **The cost:** every status question needs a date-aware query, like `rpt.fn_enrolment_status_as_of` here, or a DAX measure with a date filter. That's the main thing to get right in the first Power BI measures.
- **At larger scale:** you'd often pre-compute a daily snapshot table (one row per enrolment per day) to make reports faster. At about 200 enrolments that isn't needed.

---

## Optional exercise (about 15 minutes)

**Task:** write a SQL query that counts **withdrawals per cohort per programme week**. This will be the basis of a later dropout chart.

**Hints:**
- Withdrawals are rows in `core.enrolment_status_event` with `event_type = 'withdrawn'`.
- You need the cohort (via `core.enrolment`) and the programme week. Which table knows the programme week of a date? Join on the withdrawal's `effective_date`.

**Check yourself:**
- The counts should add up to **9**.
- **Cohort 2** should have the most withdrawals.
- No withdrawal should be in Week 1. Why can't one be? The answer is in `simulate()`.

Send me your query and I'll review it: what's right, what would break on other data, and how it could be simpler.

---

## Troubleshooting

| Symptom | Likely cause → fix |
|---|---|
| SSMS: `Msg 4860 … does not exist or you don't have file access rights` | Wrong `@data_folder`, or the SQL Server service account can't read the folder. Check the path ends in `\` and the CSVs are in it, and use a folder outside `C:\Users` (step A2). Nothing was changed, because the load rolled back. |
| SSMS: `Msg 4861 … Operating system error code 5 (Access is denied)` | Same cause: the service account can't read the file. Copy the CSVs to `C:\WorkforceData`, or give `NT Service\MSSQL$SQLEXPRESS` read access to the folder. |
| SSMS: `You do not have permission to use the bulk load statement` | Your login needs the `bulkadmin` server role. Ask whoever installed SQL Server to add you, or run as an administrator login. The installer usually makes the installing user an administrator. |
| SSMS: `Invalid object name 'core.…'` or `'rpt.…'` | The scripts ran out of order, or `000` and `001` weren't run. Run them in the order in step A3. |
| `py` or `python` isn't recognised | Python isn't on PATH. Reinstall from python.org with "Add to PATH" ticked, or use the full path. |
| `.venv\Scripts\activate` "cannot be loaded because running scripts is disabled" | PowerShell policy. Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again. |
| `ModuleNotFoundError: No module named 'tomllib'` | Python older than 3.11. Install 3.11 or newer. |
| `ModuleNotFoundError: No module named 'pyodbc'` | The virtual environment isn't active, or the dependencies aren't installed. Activate it, then `pip install -r requirements.txt`. |
| `No 'ODBC Driver 17/18 for SQL Server' found` | Install "Microsoft ODBC Driver 18 for SQL Server" from Microsoft. |
| `Login timeout expired` or `server was not found` | Wrong instance name, or the service is stopped. Check step 0, and try `--server localhost` vs `--server "localhost\SQLEXPRESS"`. |
| `SSPI Provider: No credentials were supplied` | Windows authentication isn't available (for example on Linux or macOS). Set `WDA_SQL_USER` and `WDA_SQL_PASSWORD` to use a SQL login. |
| `Login failed for user` | Your Windows account has no access to that instance. In SSMS, connect as an admin and add your login, or use a SQL login. |
| A validation check says **FAIL** | Find the check name in `sql/validation_queries.sql`. Each check is a small `SELECT` you can run on its own to see the offending rows. |
| `test_committed_csvs_match_the_generator` fails | The config or generator changed, but the CSVs weren't regenerated. Run step 2, then commit `data/synthetic/`. |
| `sqlcmd: unknown option -C` | You have an old `sqlcmd`. Remove `-C`, or run the file in SSMS instead. |
