# Build log

## Build 01 — Multi-cohort training foundation (2026-11-15)

**Scope:** the synthetic data generator, the SQL Server schema and reporting views, validation, tests and documentation, which together are enough for a first Power BI cohort and competency report.
**Not in scope** (held for later builds): MongoDB, payment cases, certification and readiness, operational QA, 90-day proficiency, the website, and a Power BI embed.

### What was built
| Area | Files |
|---|---|
| Synthetic assumptions | `config/build01_synthetic.toml` |
| Generator | `python/generate_synthetic_data.py` → `data/synthetic/*.csv` + `generation_manifest.json` |
| Database | `sql/000_create_database.sql`, `sql/001_create_schema.sql`, `sql/002_reporting_views.sql` |
| Loader | `python/load_to_sql.py` (database, tables, load, views and validation in one command) |
| SSMS loader | `sql/003_load_synthetic_data.sql` (`BULK INSERT`; the whole build runs in SSMS without Python) |
| Validation | `sql/validation_queries.sql` (24 error checks + 2 informational) |
| Reference answers | `sql/analysis_examples.sql` (numbers to check DAX against) |
| Trace one person | `sql/trace_one_enrolment.sql` (one employee through every layer) |
| Owner walkthrough | `docs/walkthrough.md` (commands, expected output, troubleshooting, exercise) |
| Tests | `tests/test_generator.py` (43, no database needed), `tests/test_sql_integration.py` (16, needs SQL Server) |

### Test evidence (Claude Code cloud container)
- Python 3.13, with SQL Server 2025 Developer Edition on Linux. The owner's target is SQL Server Express or Developer on Windows; everything used here works on SQL Server 2017 and later.
- `python -m pytest`: **43 passed**, 16 skipped (SQL tests skipped when no server is configured).
- With a server configured: **59 passed**.
- `python python/load_to_sql.py`: all 9 tables loaded, **26 of 26 checks OK** (24 PASS + 2 INFO).
- Fresh clone with a new virtual environment: regenerating produced byte-identical files, and all tests passed.
- **SSMS route** (`000` → `001` → `002` → `003` → validation, run with `sqlcmd` against an empty server): same row counts, 24 PASS + 2 INFO. Re-running `003` works. A wrong folder path fails with error 4860 and leaves the data unchanged.

### Test evidence (owner's machine, 2026-11-16)
Run by the owner on Windows in SSMS, using the SSMS route (walkthrough Route A).
- SQL Server: Microsoft SQL Server 2022 (RTM-GDR) (KB5132747) - 16.0.1220.3 (X64), Developer Edition (64-bit), on Windows
- `000` → `001` → `002` → `003_load_synthetic_data.sql`: all 9 tables loaded with the expected row counts (1 / 3 / 206 / 5 / 208 / 552 / 120 / 6,698 / 6,655).
- `validation_queries.sql`: **24 PASS + 2 INFO, no FAIL** (2 repeat employees; 533 unrecorded eligible attendance records).
- `analysis_examples.sql` and `trace_one_enrolment.sql`: every result matched the reference numbers below.
- **Route B (Python), Python 3.13.1 with ODBC Driver 18:**
  - the generator reproduced all 9 CSVs with identical checksums;
  - this run found a Windows line-ending bug in the manifest checksum, now fixed (`decisions.md` D18);
  - `load_to_sql.py --server localhost` (Windows authentication): 26 of 26 checks OK, exit code 0;
  - `python -m pytest` with `WDA_SQL_SERVER=localhost`: **59 passed**.

Compare your own run with [`docs/walkthrough.md`](walkthrough.md), which has the expected output for every step.

### Reference numbers for checking DAX (seed 20261115, as of 2026-11-02)
All counts are synthetic.

**Headcount and status at the snapshot date**
| Cohort | Enrolled | Cancelled before start | Starting headcount | Withdrawn | Completed | Active |
|---|---|---|---|---|---|---|
| COH-2026-01 (finished) | 72 | 4 | 68 | 3 | 65 | 0 |
| COH-2026-02 (finished) | 70 | 3 | 67 | 5 | 62 | 0 |
| COH-2026-03 (in progress, Week 7) | 66 | 2 | 64 | 1 | 0 | 63 |
| **Total** | 208 | 9 | 199 | 9 | 127 | 63 |

There are 206 distinct employees across 208 enrolments, because 2 employees (`EMP-00025`, `EMP-00034`) re-enrolled from Cohort 1 into Cohort 3.

**Active trainees as of a date** (all cohorts combined)
| Date | Active | Why |
|---|---|---|
| 2026-05-15 | 67 | Cohort 1, Week 2 |
| 2026-06-26 | **0** | Cohort 1's final day: completion takes effect that day (see `decisions.md` D7) |
| 2026-07-20 | 67 | Cohort 2, Week 3 |
| 2026-10-15 | 64 | Cohort 3, Week 4 |
| 2026-11-02 | 63 | Snapshot date |

**Attendance** (eligible sessions up to the snapshot)
| Cohort | Eligible | Present | Absent | Unrecorded | Present ÷ recorded | Present ÷ eligible |
|---|---|---|---|---|---|---|
| COH-2026-01 | 2,649 | 2,198 | 217 | 234 | 91.0% | 83.0% |
| COH-2026-02 | 2,604 | 2,159 | 162 | 283 | 93.0% | 82.9% |
| COH-2026-03 | 1,978 | 1,809 | 153 | 16 | 92.2% | 91.5% |

**Average core competency score** (all 5 competencies, equal weight)
| Week | Cohort 1 | Cohort 2 | Cohort 3 |
|---|---|---|---|
| 1 | 52.4 | 52.9 | 52.1 |
| 2 | 58.7 | 61.6 | 58.3 |
| 3 | 63.1 | 66.3 | 63.2 |
| 4 | 65.8 | 71.4 | 66.5 |
| 5 | 68.8 | 74.6 | 70.0 |
| 6 | 70.3 | 77.8 | 72.0 |
| 7 | 71.9 | 79.5 | (not yet assessed) |
| 8 | 73.1 | 80.4 | (not yet assessed) |

The overall average across all 6,655 scores is 66.6. Cohort 2 is the designed fast improver.

### Challenges and how they were solved
1. **People enrolled before they were hired (found by tracing one enrolment).**
   - **Cause:** hire date and enrolment date were drawn independently, so 119 of the 208 enrolments came before the person's hire date. All 23 checks passed anyway, because none compared those two dates.
   - **Fix:** a new hire is now hired 0–9 days before enrolling.
   - **Prevention:** validation check `enrolled_before_hire_date` and test `test_nobody_enrols_before_they_are_hired`.
   - **Side effect:** the fix changed the random sequence, so every reference number above changed from the first draft.
   - **Lesson:** automated checks only catch what someone thought to check, so look at individual records too.
2. **IDs changed with the as-of date.** Sequential numbering gave the same record a different ID under a different as-of date. Fixed with stable IDs derived from the enrolment number (D4), proven by the subset test.
3. **Negative score changes and `TINYINT`.** SQL Server's `TINYINT` holds 0–255 only, so subtracting a higher previous score would overflow. The view converts to `INT` before subtracting.
4. **More unrecorded attendance than the config rate suggests.** It's random variation (7 of 111 registers missing, against about 3–4 expected), not a bug. Left visible and flagged for ChatGPT (D10).
5. **Getting a test SQL Server into the cloud container.** This affected only the build environment, not the project. SQL Server 2022 needs an older system library, so the build used Microsoft's SQL Server 2025 package for Ubuntu 24.04 instead.

### Open items for ChatGPT review
See the decisions marked `Review: ChatGPT` in `decisions.md`: D1, D5, D6, D7, D10, D12 and D13.

---

## UX-01 — Workforce Intelligence Overview page (2026-11-17, branch `ux/overview-page`)

**Commits:**
1. The untouched PBIP baseline, which is the restore point.
2. The `rpt.dim_snapshot` view.
3. Model changes: the snapshot table and label, Auto date/time off, and the date table marked.
4. The theme and the page.
5. The docs.

**Evidence (Claude Code cloud container):**
- SQL: `load_to_sql.py` gives 26 of 26 checks OK; `pytest` gives **60 passed**, including the new `test_dim_snapshot_is_one_row_with_the_data_as_of_date`; `rpt.dim_snapshot` returns `2026-11-02`.
- Model: Microsoft's TMDL parser (`Microsoft.AnalysisServices` 19.84.1) loads the model. It has 8 tables, 13 measures and the 8 approved M:1 single-direction relationships. Auto date/time is off, and `rpt dim_date` is the date table, keyed on `date`. No existing measure lines changed.
- Report: all 17 PBIR JSON files validate against Microsoft's schemas (report 3.3.0, page 2.1.0, visualContainer 2.13.0). Three deliberately broken copies were all rejected, which proves the check works. All 17 field references used by visuals exist in the model.

**Owner's Power BI Desktop validation (2026-11-17, Windows, SQL Server 2022 Developer):**
- Opened the PBIP and refreshed it. The page renders as designed, and the snapshot label reads `Data as of 2 Nov 2026 | Synthetic data`.
- KPI cards match the reference numbers: 199 · 63 · 127 · 66.6 · 92.1% · 92.6%.
- Status bars: Cohort 1 65 completed / 3 withdrawn; Cohort 2 62 / 5; Cohort 3 63 active / 1 withdrawn.
- Competency lines: Cohort 2 is highest (80.4 at Week 8); Cohort 3 stops at Week 6.
- **Practice tasks done by the owner:** percentage format on both rate measures (`formatString: 0.0%`), and the card label renamed to "Avg competency score".
- **What Power BI changed on save (reviewed, all harmless):**
  - it upgraded visuals to schema 2.14.0;
  - it re-wrote the theme and the Snapshot Label formula in its own style, with no value changes;
  - it saved the Filters pane as collapsed;
  - it added auto-generated Q&A language data in `cultures/en-GB.tmdl`.
- **Final checks (Claude):**
  - the model loads in Microsoft's TMDL parser, with the 8 approved relationships and Auto date/time off;
  - no cache or `.pbix` files are tracked, and the privacy scan is clean;
  - PBIR schema check not possible after the save: Desktop now writes visualContainer 2.14.0, which Microsoft hasn't yet published.

