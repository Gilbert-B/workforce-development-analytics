# Build 02 build log: coaching, certification and readiness

**Branch:** `build/02-coaching-certification-readiness`, from `main` at `aa96600` (verified before branching).

**Status:** implemented and **Claude-validated**. **Owner validation is pending.** Do not merge until the owner has run the Windows checks.

## What was built
| Area | Files |
|---|---|
| Config (fictional policy B02-R1) | `config/build02_synthetic.toml` |
| Generator | `python/generate_build02_data.py`: reads the committed Build 01 CSVs and writes `data/synthetic/build02/` (6 CSVs + manifest) |
| SQL tables | `sql/004_create_build02_tables.sql`: 6 `core` tables |
| SSMS load | `sql/005_load_build02_data.sql`: `BULK INSERT`, one transaction |
| Reporting views | `sql/006_create_build02_reporting_views.sql`: 6 `rpt` views |
| Python load | `python/load_build02_to_sql.py`: checks Build 01, loads in one transaction, validates Build 02 and re-validates Build 01 |
| Validation | `sql/build02_validation_queries.sql`: 26 error checks, 11 storyline checks, 4 info rows |
| Examples / trace | `sql/build02_analysis_examples.sql` (8 queries), `sql/build02_trace_one_enrolment.sql` |
| Tests | `tests/test_build02_generator.py` (39), `tests/test_build02_sql_integration.py` (22) |
| Docs | `docs/build02_walkthrough.md`, `docs/build02_data_dictionary.md`, this log, decisions D27–D33 |
| Changed Build 01 files | `sql/001_create_schema.sql` (+6 `DROP TABLE IF EXISTS` lines, D28); `.gitattributes` (LF rule for `data/synthetic/build02/`) |

**No changes** to the Build 01 CSVs or their checksums, the Build 01 tables, views or generator, or anything under `powerbi/` (`git diff -- powerbi` is empty).

## Reference numbers
Seed 20261118, as of 2026-11-02, from Build 01 seed 20261115.

**Rows per table:**

| Table | Rows |
|---|---|
| certification_type | 2 |
| watchlist_case | 64 |
| watchlist_case_event | 113 |
| coaching_action | 110 |
| certification_attempt | 304 |
| readiness_review | 168 |

**Watch-list:**
- 64 cases across 63 enrolments; one enrolment has 2 episodes.
- **By reason:** low competency 30, low attendance 22, manual referral 9, declining scores 3.
- **Closures:** Programme ended 29, Improved 12, Withdrawn 4, Administrative 4.
- **Open at the snapshot:** 15, all in Cohort 3, so the Cohort 3 watch-list rate is 15 / 63 active = 23.8%.

**Coaching:**
- 49 of 64 cases actioned, with 110 actions.
- **Coverage:** Cohort 1 73.9%, Cohort 2 75.0%, Cohort 3 81.0%.
- **Average days to first action:** 4.3, 3.9 and 4.6.

**Certification:**
- 238 first attempts; 160 passed (67.2%).
- 66 retakes; 38 passed.
- 198 of 238 enrolment × certification pairs passed (83.2%).
- 28 pairs failed both attempts; 12 failed once and haven't retaken.
- 4 completers have no attempt.

**Readiness:**
- 119 of 127 completers have been reviewed, across 168 reviews.
- 71 are Approved now, 9 of them after an earlier deferral.

| Cohort | Approved | Deferred | Not reviewed |
|---|---|---|---|
| Cohort 1 | 32 | 30 | 3 |
| Cohort 2 | 39 | 18 | 5 |

**Cohort 3:** 0 certification attempts and 0 readiness reviews; it is still in training.

**Build 01 baseline, re-checked with Build 02 loaded:**
- 208 enrolments; 206 employees; 199 started; 9 cancelled;
- 63 active; 127 completed; 9 withdrawn;
- 7,231 eligible attendance; 533 unrecorded; 6,655 assessment rows.

## Evidence (Claude Code cloud container: SQL Server 2025 on Linux, SQL login)
| Command | Result |
|---|---|
| `python python/generate_synthetic_data.py` + `python python/generate_build02_data.py`, then `git status` | Build 01 files unchanged; Build 02 files reproduced exactly |
| `python python/load_to_sql.py --server localhost` | 26 of 26 checks OK |
| `python python/load_build02_to_sql.py --server localhost` | 6 tables loaded; **41 of 41** Build 02 checks OK; Build 01 re-validated, 26 of 26 OK |
| SSMS route via `sqlcmd`: 004 → 005 (**run twice**) → 006 → validation | same row counts after the second load, no duplicates; 37 PASS + 4 INFO |
| `python -m pytest` (with SQL Server) | **121 passed** (Build 01: 60; Build 02: 39 generator + 22 SQL) |
| `sql/build02_analysis_examples.sql`, `sql/build02_trace_one_enrolment.sql` | all queries run; the numbers are above and in the walkthrough |

**Negative tests (all pass, so the bad data IS rejected):**
- **Constraints reject:** a duplicate attempt; approval without sign-off; a competency pass with no score; an unknown event type; a Closed event without a reason; a case for a missing enrolment; a manual referral with a trigger week.
- **Validation catches:** overlapping cases; an action before its case opened; an attempt on the completion day; a future-dated attempt; a result that disagrees with the pass mark; an approval claiming evidence that wasn't on record.
- **Python `validate()` catches** its own equivalents, plus too many attempts and an attempt by an active enrolment.
- **Loading:** a failed load (bad value in the last table) leaves every table unchanged; the loader refuses a Build 02 dataset whose snapshot date differs from Build 01's.

**Bug found by a negative test:** the Python overlap check crashed instead of reporting two cases with the same opening date. It is fixed.

**Not run here:** Windows authentication, SSMS itself and SQL Server 2022 (the owner's machine).

## Deviations and points for review
1. **D28:** a 6-line additive edit to Build 01's `001_create_schema.sql`. It's needed because Build 02 has real foreign keys to `core.enrolment`. **Please confirm.**
2. **Signals aren't stored**, only the case decisions. The spec separates signals from decisions; a signal table would be a seventh table. Unrecorded attendance is simply excluded from signals; there is no separate "data-quality review" record.
3. **Time awareness:** `is_latest_review` and `is_open_at_snapshot` are "as of the loaded snapshot". To see readiness *as of an earlier date*, regenerate with `--as-of-date`, or add date logic in the later BI increment.

## Owner validation (pending)
To fill in after the Windows run:
- generation and `git status`;
- both loads and their check results;
- `pytest` count;
- three verification queries;
- the ENR-00044 trace;
- the EMP-00025 repeat trace.
