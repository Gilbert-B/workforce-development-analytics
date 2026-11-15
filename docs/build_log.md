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
| Validation | `sql/validation_queries.sql` (23 error checks + 2 informational) |
| Reference answers | `sql/analysis_examples.sql` (numbers to check DAX against) |
| Tests | `tests/test_generator.py` (40, no database needed), `tests/test_sql_integration.py` (16, needs SQL Server) |

### Test evidence (run in the Claude Code cloud container)
- Python 3.13, with SQL Server 2025 Developer Edition on Linux. The owner's target is SQL Server Express or Developer on Windows; everything used here works on SQL Server 2017 and later.
- `python -m pytest`: **40 passed**, 16 skipped (SQL tests skipped when no server is configured).
- `python -m pytest tests/test_sql_integration.py` with a server configured: **16 passed**.
- `python python/load_to_sql.py`: all 9 tables loaded, **25 of 25 checks OK** (23 PASS + 2 INFO).
- Reproducibility: two runs with the same seed and as-of date produce byte-identical files (the SHA-256 checksums match).

### Reference numbers for checking DAX (seed 20261115, as of 2026-11-02)
All counts are synthetic.

**Headcount and status at the snapshot date**
| Cohort | Enrolled | Cancelled before start | Starting headcount | Withdrawn | Completed | Active |
|---|---|---|---|---|---|---|
| COH-2026-01 (finished) | 72 | 2 | 70 | 7 | 63 | 0 |
| COH-2026-02 (finished) | 70 | 1 | 69 | 6 | 63 | 0 |
| COH-2026-03 (in progress, Week 7) | 66 | 4 | 62 | 1 | 0 | 61 |
| **Total** | 208 | 7 | 201 | 14 | 126 | 61 |

There are 206 distinct employees across 208 enrolments, because 2 employees re-enrolled from Cohort 1 into Cohort 3.

**Active trainees as of a date** (all cohorts combined)
| Date | Active | Why |
|---|---|---|
| 2026-05-15 | 70 | Cohort 1, Week 2 |
| 2026-06-26 | **0** | Cohort 1's final day: completion takes effect that day (see `decisions.md` D7) |
| 2026-07-20 | 69 | Cohort 2, Week 3 |
| 2026-10-15 | 61 | Cohort 3, Week 4 |
| 2026-11-02 | 61 | Snapshot date |

**Attendance** (eligible sessions up to the snapshot)
| Cohort | Eligible | Present | Absent | Unrecorded | Present ÷ recorded | Present ÷ eligible |
|---|---|---|---|---|---|---|
| COH-2026-01 | 2,679 | 2,267 | 171 | 241 | 93.0% | 84.6% |
| COH-2026-02 | 2,669 | 2,226 | 154 | 289 | 93.5% | 83.4% |
| COH-2026-03 | 1,906 | 1,744 | 144 | 18 | 92.4% | 91.5% |

**Average core competency score** (all 5 competencies, equal weight)
| Week | Cohort 1 | Cohort 2 | Cohort 3 |
|---|---|---|---|
| 1 | 53.7 | 52.8 | 53.3 |
| 2 | 59.6 | 61.5 | 60.4 |
| 3 | 64.1 | 66.9 | 65.7 |
| 4 | 67.7 | 72.1 | 68.5 |
| 5 | 69.8 | 75.4 | 71.3 |
| 6 | 72.4 | 78.6 | 74.1 |
| 7 | 73.5 | 79.2 | (not yet assessed) |
| 8 | 74.9 | 81.2 | (not yet assessed) |

The overall average across all 6,680 scores is 67.8. Cohort 2 is the designed fast improver.

### Challenges and how they were solved
1. **IDs changed with the as-of date.** Sequential numbering gave the same record a different ID under a different as-of date. Fixed with stable IDs derived from the enrolment number (D4), proven by the subset test.
2. **Negative score changes and `TINYINT`.** SQL Server's `TINYINT` holds 0–255 only, so subtracting a higher previous score would overflow. The view converts to `INT` before subtracting.
3. **More unrecorded attendance than the config rate suggests.** It's random variation (7 of 111 registers missing, against about 3–4 expected), not a bug. Left visible and flagged for ChatGPT (D10).
4. **Getting a test SQL Server into the cloud container.** This affected only the build environment, not the project. SQL Server 2022 needs an older system library, so the build used Microsoft's SQL Server 2025 package for Ubuntu 24.04 instead.

### Open items for ChatGPT review
See the decisions marked `Review: ChatGPT` in `decisions.md`: D1, D5, D6, D7, D10, D12 and D13.
