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
| Validation | `sql/build02_validation_queries.sql`: 30 error checks (incl. 4 population reconciliations), 11 storyline checks, 8 info rows |
| Audit | `data/synthetic/build02/audit/review_signals.csv` (1,108 rows), `audit/readiness_evidence.csv` (127 rows), and their SQL twin `sql/build02_audit_queries.sql` |
| Reset | `sql/007_reset_build02_objects.sql`, `python/full_reset.py --confirm`; the Build 01 drop guard is installed by `004` |
| Examples / trace | `sql/build02_analysis_examples.sql` (10 queries: 9 = KPI populations, 10 = as of any date), `sql/build02_trace_one_enrolment.sql` |
| Tests | `tests/test_build02_generator.py` (44), `tests/test_build02_sql_integration.py` (29) |
| Docs | `docs/build02_walkthrough.md`, `docs/build02_data_dictionary.md`, this log, decisions D27–D37 |
| Changed Build 01 files | **none.** `sql/001_create_schema.sql` is identical to `main` (D34 supersedes D28). Only `.gitattributes` gains LF rules for `data/synthetic/build02/` and its `audit/` folder |

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
Re-run after the conditional-approval changes (D34–D37).

| Command | Result |
|---|---|
| `python python/generate_synthetic_data.py` + `python python/generate_build02_data.py`, then `git status` | Build 01 files unchanged; the six Build 02 data CSVs are **byte-identical** to before the audit work (same checksums); audit files reproduced exactly |
| `python python/full_reset.py --server localhost` (no `--confirm`) | refused: `add --confirm to proceed` |
| `python python/full_reset.py --server localhost --confirm` | Build 01 **26 of 26**; Build 02 **49 of 49** (30 error + 11 story PASS, 8 INFO); `Full reset complete: all checks OK` |
| `sql/001_create_schema.sql` run with Build 02 loaded | `Msg 50001 … Nothing was dropped` (+ follow-on `Msg 2714`); still 15 core tables and 6,655 assessment rows |
| `python python/load_to_sql.py` with Build 02 loaded | refused with the same message; nothing dropped |
| SSMS route via `sqlcmd`: 004 → 005 (run twice) → 006 → validation | same counts after the second load |
| `sql/build02_audit_queries.sql` vs the audit CSVs | 1,108 / 127 rows; every key and value equal (averages within 0.01 rounding) |
| `sql/build02_analysis_examples.sql` | all 10 queries run; populations and the as-of-date figures are in the walkthrough |
| `python -m pytest` (with SQL Server) | **133 passed** (Build 01: 60; Build 02: 44 generator + 29 SQL) |

**Negative tests:**
- **Constraints reject:** a duplicate attempt; approval without sign-off; a competency pass with no score; an unknown event type; a Closed event without a reason; a case for a missing enrolment; a manual referral with a trigger week.
- **Validation catches:** overlapping cases; an action before its case opened; an attempt on the completion day; a future-dated attempt; a result that disagrees with the pass mark; an approval claiming evidence that wasn't on record.
- **Loading:** a failed load changes nothing; a snapshot mismatch is refused; the guard refuses 001 with nothing dropped.

**Bugs found and fixed during this work:**
1. The Python overlap check crashed on equal opening dates.
2. The audit first listed 4 case IDs whose records were entered after the snapshot.
3. An "ends with 'case opened'" text match also caught "no case opened".
4. SQL `ISNULL` truncated "Not reviewed" to `varchar(10)`.
5. **The guard trigger, created through `sqlcmd`, broke every `DROP TABLE` (error 1934).** sqlcmd defaults `QUOTED_IDENTIFIER OFF`, SQL Server stores that setting with the trigger, and the trigger's XML method needs it ON.
   - **Fix:** `004` now sets it ON explicitly, and `007` drops the trigger first.
   - **Regression test:** creates the guard from a QUOTED_IDENTIFIER OFF session and checks it still works.

**Not run here:** Windows authentication, SSMS itself and SQL Server 2022 (the owner's machine).

## Conditional-approval requirements (owner + ChatGPT, 2026-11-18)
| # | Requirement | Done |
|---|---|---|
| 1 | Restore Build 01's schema script; explicit full-reset for the foreign-key dependency | `001` identical to `main`; guard trigger; `007`; `full_reset.py --confirm` (D34) |
| 2 | Reproducible audit of risk signals, evidence completeness, missing-attendance data quality; no seventh core table | 2 audit CSVs in the manifest + SQL twin + row-by-row test (D35) |
| 3 | Document snapshot semantics of the case and latest-review flags | view header, data dictionary, walkthrough; time-aware query 10 (D36) |
| 4 | Preserve KPI grains; unactioned, unattempted and unreviewed reported separately | 4 population checks + 4 info rows; query 9; `readiness_evidence.csv` (D37) |
| 5 | Power BI model, DAX and pages unchanged | `git diff main -- powerbi` is empty |

## Owner validation (Windows, SQL Server 2022 Developer, 2026-11-18)
- **Earlier version** (`60419c7`, before the conditional-approval changes): `python -m pytest` gave **121 passed**.
- **Current version** (`f053362`, after D34–D37):
  - **Regeneration:** the generators reproduce the committed files.
  - **`full_reset.py --confirm`:** all checks passed (Build 01 26 of 26, Build 02 49 of 49).
  - **`python -m pytest`:** **133 passed**.

**Status:** owner-validated. Awaiting the owner and ChatGPT sign-off before PR #8 is merged.
