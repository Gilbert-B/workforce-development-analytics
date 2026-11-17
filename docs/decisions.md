# Decisions log

Each entry records **what** was decided, **why**, and **who** needs to confirm it.
`Review: ChatGPT` means it was an implementation decision made during Build 01 that touches modelling or KPI semantics and should be confirmed or changed.

---

## Approved before Build 01 (by the project owner with ChatGPT)

| # | Decision |
|---|---|
| A1 | Portfolio Edition is a **fictional, fully synthetic** banking/fintech workforce scenario. Nothing comes from the original professional project. |
| A2 | **Multiple cohorts from day one**; compare cohorts by **programme week**, not calendar date. |
| A3 | Training completion, certification, readiness and deployment are **separate** concepts. Build 01 covers training only. |
| A4 | Missing attendance is **unknown**, never silently counted as absent. |
| A5 | Active trainees are calculated **as of a date** from effective-dated events, never by hard-coding cohorts or subtracting all-time dropouts. |
| A6 | Business-policy numbers live in **configuration**, not inside code or measures. |
| A7 | No live Power BI embed (personal Power BI account). The website will use a video walkthrough plus screenshots. |

---

## Build 01 implementation decisions

### D1 — SQL Server as the database engine  · Review: ChatGPT
**Decision:** target SQL Server 2017 or later (Express or Developer edition, both free). The owner has both SQL Server and PostgreSQL installed.
**Why:**
- It's the same T-SQL family as the original project's Azure SQL, so the story of continuity is honest.
- Power BI connects to it natively, with no extra driver.
- T-SQL is the most common dialect in BI job descriptions.

**Trade-off:** reviewers on macOS or Linux can't run it as easily. The generator and its tests run without any database, and the CSVs are committed, so the data can still be inspected anywhere.

### D2 — Python standard library for generation; two dependencies in total
**Decision:** the generator uses only Python's standard library (`random`, `csv`, `tomllib`, `hashlib`). The only packages installed are `pyodbc` (for the SQL Server load) and `pytest`.
**Why:** a ~400-row-per-cohort dataset doesn't need pandas or NumPy. Plain Python keeps each step visible and easy to explain.
**Determinism:** the generator calls only `rng.random()` and `rng.gauss()`, whose output is stable across Python versions. It requires Python 3.11+ for `tomllib`.

### D3 — "Simulate everything, then observe as of a date"
**Decision:** the generator simulates the full 8 weeks of every cohort, then keeps only what had happened **and** been recorded by the as-of date.
**Why:** this guarantees there's no future leakage. It also gives a property we can test: data generated for an earlier as-of date is an exact subset of later data (`test_earlier_as_of_date_is_a_subset_of_later`).

### D4 — Stable record IDs built from the enrolment number
**Decision:**
- Status events are named `EVT-<enrolment number>-<event code>`.
- Assessments are named `ASM-<enrolment number>-W<week>-C<competency>`.

**Why:** the first version numbered records sequentially, so the same record got a different ID under a different as-of date. A real system never renumbers records.

### D5 — Status events use `effective_date` (a date) plus `recorded_at` (a timestamp)  · Review: ChatGPT
**Decision:** the brief says "effective timestamp"; I used a **date** for the effective time and a datetime for when the event was recorded.
**Why:** the as-of rules work at day level ("on or before that date"). Comparing a timestamp with a date slicer in Power BI causes off-by-a-few-hours errors.

**Recording delays are simulated:**
- Withdrawals are entered 1–4 working days late, completions 1–3 days late, and assessments 0–1 day late.
- An event that happened but wasn't recorded by the as-of date doesn't exist yet in the data.

### D6 — The as-of rule uses effective dates only (not "what was known then")  · Review: ChatGPT
**Decision:** `rpt.fn_enrolment_status_as_of(@date)` decides status from `effective_date <= @date` and ignores `recorded_at`.
**Consequence:** looking back at 15 October with today's data, a withdrawal effective on 14 October but recorded on 17 October counts as withdrawn. That's "the truth as we now know it", not "what the system showed on 15 October".
**Note:** the second view, often called *bitemporal*, can be added later with `recorded_at <= @date` if a business question needs it.

### D7 — Event date meanings  · Review: ChatGPT (important edge case)
| Event | `effective_date` means |
|---|---|
| started | the cohort's first day |
| withdrawn | the first day the trainee is **no longer** in training. No attendance or assessment on or after it. |
| completed | the programme's **last day** (the Friday of Week 8) |
| cancelled | the date the place was cancelled, before the start date |

**Edge case:** under the approved Rule 2 ("no withdrawn/completed event *on or before* the date"), every completer stops being Active on the final programme day itself. In the data, Cohort 1's Active Trainees count on 2026-06-26 is **0**, even though everyone attended that day.

**Options for ChatGPT:**
- (a) Keep it, and document that the last day counts as completion.
- (b) Make completion effective the day after the programme ends.
- (c) Change the rule to "strictly before" for completion only.

Build 01 implements (a), exactly as written in the rules.

### D8 — Completion is explicit, but has no criteria yet
**Decision:** every trainee who doesn't withdraw gets a `completed` event at programme end. The generator doesn't apply any completion criteria, such as a minimum attendance.
**Why:** the rules say completion criteria come later. Inventing a threshold now would be an unapproved business rule.
**Guard:** completion is never inferred from Week 8 records. A test and a validation check both confirm that completions exist only as explicit events.

### D9 — Attendance is stored as recorded marks only; the reporting view creates the "Unrecorded" rows
**Decision:**
- `core.attendance` holds only marks that were actually recorded ("Present" or "Absent").
- `rpt.fact_attendance` builds every **eligible** enrolment × session (started, not yet withdrawn, session on or before the as-of date) and labels the gaps "Unrecorded".

**Why:** this mirrors a real register, where missing marks are missing rows. It keeps "Unrecorded" as a reporting concept rather than a fake value in the source data.

**Note:** if a withdrawal happened but hasn't been recorded yet, the trainee's sessions after leaving appear as eligible but Unrecorded. That's realistic, because the business doesn't yet know they left.

### D10 — Attendance-rate denominator  · Review: ChatGPT
The rule says "attended / eligible scheduled sessions", while the measure list says "Recorded Attendance Rate + Unrecorded Attendance Count". The view supports both readings:

| Definition | Cohort 1 | Cohort 2 | Cohort 3 |
|---|---|---|---|
| Present ÷ recorded (Present + Absent) | 91.0% | 93.0% | 92.2% |
| Present ÷ all eligible (Unrecorded included in the denominator) | 83.0% | 82.9% | 91.5% |

The gap is large because whole registers are missing for some sessions. Seven of the 111 sessions held so far are fully unrecorded, against roughly three to four expected from the 3% setting: ordinary random variation.

**Recommendation for ChatGPT:** decide which definition the headline KPI uses, and whether to lower `whole_session_unrecorded_probability` in the config.

### D11 — No assessment when the trainee was absent on assessment day
**Decision:** assessments happen on the Friday of each week, and only for trainees marked Present that day. That's why a cohort's assessed count (for example 61 in Cohort 1, Week 1) is below its starters (68).
**Why:** it produces realistic "not available" scores that are never zero, which tests the rule "don't treat unobserved as zero". Retakes and make-up assessments are out of scope (`attempt_number` is always 1).

### D12 — Week-over-week change: SQL gives a per-person helper; the cohort KPI is for DAX  · Review: ChatGPT
**Decision:** `rpt.fact_assessment.week_over_week_change` is a person's change from their *immediately preceding* week. If that week is missing, the value is NULL, so a gap is never counted as a one-week change.

**Note:** a cohort-level DAX measure (average this week minus average last week) gives a different number from the average of individual changes, because different people are assessed each week. `sql/analysis_examples.sql` query 5 shows both. Which one the report shows is a KPI decision.

### D13 — Employee name is copied into `dim_enrolment`  · Review: ChatGPT
**Decision:** the reporting layer offers `dim_enrolment`, with employee ID and name copied in, as the main dimension for individual trainees. `dim_employee` is still available for counting distinct people.
**Why:** a person can have more than one enrolment (2 synthetic employees, `EMP-00025` and `EMP-00034`, re-enrolled), so cohort belongs on the enrolment, not on the person. Copying the name in avoids a chained, two-hop dimension in the first model.

The fact views carry `cohort_id`, `enrolment_id` and `employee_id`. ChatGPT should confirm which relationships to use, so Power BI doesn't end up with ambiguous filter paths.

### D14 — No synthetic data-quality corruption in Build 01
**Decision:** Build 01 data is clean apart from the intended business realities: missing attendance marks, recording delays, cancellations, withdrawals and repeat enrolments. Duplicates, malformed dates and similar issues are **not** injected yet.
**Why:** the brief asks for a clean, explicit contract first. The planned approach for the data-quality build is a separate "inject issues" step that writes a manifest of what it broke, so validation can be tested against it.

### D15 — Committed CSVs, reproduced and checked by a test
**Decision:** the small generated CSVs (under 1 MB in total) are committed in `data/synthetic/`, so Power BI can be used without running Python. `test_committed_csvs_match_the_generator` fails if they drift from the generator. `.gitattributes` forces LF line endings so the checksums match on Windows.

### D16 — No extra indexes yet
**Decision:** only the indexes created by primary keys and unique constraints. The largest table has about 7k rows, so more indexes wouldn't be justified. Revisit when the payment-case data arrives.

### D17 — Two load routes: SSMS (`BULK INSERT`) and Python
**Decision:** the database can be built entirely in SSMS with `sql/003_load_synthetic_data.sql`, or from the command line with `python/load_to_sql.py`. Both load the same committed CSVs into the same tables and pass the same validation.
**Why:** the owner works in SSMS. `BULK INSERT` is the standard T-SQL way to load files and needs no extra tools. The Python route is still the one that regenerates data and runs the tests.

**Trade-offs:**
- `BULK INSERT` is executed by the SQL Server service account, so the files must sit in a folder that account can read (`C:\WorkforceData`).
- The file name can't be a variable, so the script builds each statement as text (dynamic SQL).
- There's no `CODEPAGE` option, because it isn't supported on SQL Server for Linux, where the script was tested. The files are plain ASCII, which a test enforces.

**At scale:** you'd load from a staging area with a scheduled job, or with an ETL tool rather than a hand-run script.



### D18 — Line endings must not change checksums
**Found by:** the owner's first Python run on Windows. Regenerating the data left `generation_manifest.json` modified, although every CSV was identical.
**Cause:** Git for Windows (`core.autocrlf = true`) checks text files out with CRLF line endings, so the config file's checksum differed. Separately, Python's `write_text()` writes CRLF on Windows unless told otherwise.
**Fix:** the config checksum ignores line endings (`sha256_ignoring_line_endings`), and the manifest is always written with LF. The CSVs already were. `test_manifest_is_the_same_with_windows_line_endings` guards it.
**Lesson:** code tested on only one operating system can hide platform bugs, so the owner's local run is the real test.



---

## ChatGPT review outcomes (2026-11-16)
Reviewed after the owner's local run (Routes A and B). Entries above marked `Review: ChatGPT` are resolved as follows.

| # | Outcome |
|---|---|
| D1 | **Approved.** SQL Server: a natural bridge from the original Azure SQL, with native Power BI connectivity. |
| D5 | **Approved.** Date-level `effective_date`, with a separate `recorded_at` timestamp. |
| D6 | **Approved.** Historical status is *corrected history as known at the snapshot*. Never describe it as "what was known on that past date"; reconstructing that is a possible future enhancement. |
| D7 | **Approved, option (a).** Completion takes effect on the last programme day, and Active Trainees is defined as **end-of-day** headcount. A final-day attendance mark doesn't contradict an end-of-day status of Completed. Reports must label the measure this way. |
| D10 | **Approved.** Headline = **Recorded Attendance Rate** = Present ÷ (Present + Absent). Also shown: **Attendance Data Completeness** = (Present + Absent) ÷ eligible, and **Confirmed Attendance Coverage** = Present ÷ eligible. Unrecorded ≠ Absent. The missing-register rate is **not** to be tuned just to make results look better. |
| D12 | **Approved.** Paired consecutive-week change (`week_over_week_change`) is the individual development measure. It's separate from the difference in cohort averages, whose assessed populations vary. For "average person's improvement", average per enrolment first, so trainees aren't weighted by how many competency rows they have. |
| D13 | **Approved.** Employee name copied into `dim_enrolment` for Build 01. Keep employee IDs to tell 206 people from 208 enrolments. Avoid duplicate filter routes from cohort to the facts. |
