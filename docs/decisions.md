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

---

## Power BI Overview page (UX-01, 2026-11-17, approved by owner + ChatGPT)

### D19 — Dynamic snapshot label from a disconnected table
**Decision:** a one-row view, `rpt.dim_snapshot` (`as_of_date` from `core.data_snapshot`), is imported as an eighth Power BI table **with no relationships**. `[Snapshot Label]` formats it as "Data as of 2 Nov 2026 | Synthetic data".
**Why:** the date comes from the data, so it updates after regeneration and a refresh, instead of being typed into a text box. Because the table is disconnected, no slicer or click can filter it.
**Trade-off:** one extra table for a single value.

### D20 — Auto date/time off; `rpt dim_date` marked as the date table
**Decision:** removed the 8 hidden auto-generated date tables, their 7 relationships and the 7 column "variations", and marked `rpt dim_date` (key `date`) as the date table.
**Why:** the model already has a proper date dimension. The hidden tables added size and offered confusing date hierarchies on every date column. The page had no visuals at the time, so nothing depended on them.
**Effect:** date columns no longer expand into Year / Quarter / Month / Day automatically. Use `rpt dim_date` columns instead.

### D21 — The Power BI report is version-controlled as PBIP
**Decision:** the synthetic report is committed in `powerbi/` as PBIP: PBIR report JSON plus TMDL model text. `.gitignore` still blocks `.pbi/` (the `cache.abf` data copy and per-machine settings) and any `.pbix`. `.gitattributes` stores these files with LF line endings.
**Why:** text files can be reviewed, diffed and generated, and binary `.pbix` files can't. The data cache and local settings stay off GitHub.

### D22 — Overview page built by generating PBIR, styled by a theme
**Decision:** a readable generator (`powerbi/tools/build_overview_page.py`) scaffolded the page's 13 visuals from a layout grid. Colours, fonts and visual defaults live in a custom theme. Chart clicks don't filter the KPI cards; only the cohort slicer does.
**Why:** a theme plus a grid is faster and more consistent than formatting each visual by hand, and every position and style can be traced to one place. After the owner saves the report in Desktop, **Desktop is the source of truth**. Re-running the generator resets the page.
**Checked:** all 17 report JSON files against Microsoft's PBIR schemas, and the model with Microsoft's TMDL parser.
**Not checked here:** rendering. Power BI Desktop is Windows-only, so the owner validates the page visually.

### D23 — Showcase redesign: designed canvas, bookmarks, navigation (UX-02, owner-approved)
**Decision:** the report moves to a dark design matching the portfolio website (navy, gold and teal), and deliberately demonstrates advanced Power BI UX:
- an SVG/PNG background canvas;
- an icon navigation rail with page-navigation buttons;
- bookmark-driven view toggles;
- a definitions drawer and a Reset bookmark;
- a conditional-format heatmap;
- an About page.

**Why:** the owner wants the portfolio report to show that these techniques can be built and explained. The design stays credible for a banking/fintech audience: restrained colours, and definitions always one click away.
**Constraint kept:** no new measures, model or SQL changes. Ideas that need new DAX (data-driven context lines, SVG progress bars, a current-week marker, the further pages) are proposed to ChatGPT separately.
**Trade-off:** static labels drawn in the background image are edited in SVG rather than in Desktop. Each toggle needs 4 visuals and 2 bookmarks.

### D24 — UX-02 completion: approved display measures, split reset, planned pages (ChatGPT review 2026-11-18)
**Added measures** (additions only, no existing DAX changed):
- `Completion Share of Starters`, `Total Enrolments` and `Cancelled Before Start`, exactly as approved.
- Two text measures for the cards:
  - `Starting Headcount Context` reads "208 enrolments · 9 cancelled before start". It says "enrolments", not "employees", because repeat enrolments exist.
  - `Completion Context` reads "63.8% of starters completed to date". It's an **as-of-snapshot share**, not a final completion rate.
- Two **SVG progress-bar measures**, drawn from the existing rate measures. They're clamped to 0–100%, blank-safe, use the accent colour on a neutral track, and have no thresholds. Each is shown in an image visual, with the numeric rate shown separately.
- `Current Training Week Label`.

**One deviation for ChatGPT to confirm:** `Current Training Week Label` returns `""` instead of `BLANK()` when the marker shouldn't show. A card displays the literal text "(Blank)" for BLANK, and the empty text keeps the panel clean. Behaviour is otherwise as specified: it only shows when exactly one in-progress cohort is selected. It reads "Currently in Week 7" and doesn't claim Week 7 assessments exist.

**Reset split:**
- **Reset view** is a display-only bookmark that keeps the cohort selection.
- **Clear filters** is a data-only bookmark that clears the cohort slicer and keeps the current panels.
- All toggle bookmarks are display-only, so they never change the selection.

**Navigation:** unbuilt pages appear as "planned" rail items with **no click action**. Next iteration: Cohort Intelligence, Competency & Skills Development, Attendance & Engagement, and a Trainee 360 drill-through (by `enrolment_id`).
**Attendance quality:** shows % data labels and adds the session **count** to the tooltip.

**Owner refinement (2026-11-18):** `Starting Headcount Context` now omits the cancellation part when there are none ("72 enrolments"), and says "1 enrolment" in the singular. The owner implemented it in Power BI Desktop (commit `fcd4c89`) and tested the zero branch with a temporary threshold. It's display wording only; the counts come from the approved measures unchanged.

### D25 — UX-03 report expansion: four pages on Build 01 data (2026-11-18)
**Built:**
- **Cohort Intelligence**: scorecard, lifecycle status mix, attendance rate vs completeness, same-week competency trend, and an enrolment roster that is the drill-through source.
- **Competency & Skills Development**: trend per competency, competency × week heatmap, cross-cohort comparison driven by the week selector, and sample size per week.
- **Attendance & Participation**: 4 KPI tiles, composition by cohort, rates by week, a cohort × week heatmap, and counts per week by mark.
- **Trainee 360 — Training**: a drill-through page keyed on `enrolment_id`, hidden in view mode, with a Back button.

**Key choices:**
- **Sync group:** the cohort slicer on every page belongs to sync group `CohortSelection`, so a selection persists across pages. The week selector is synced separately (`WeekSelection`).
- **Unrecorded count without a new measure:** the existing `[Eligible Attendance Sessions]` on a card with a **visual-level filter** `attendance_status = "Unrecorded"`.
- **Week selector scope (Skills page):** it filters only the cross-cohort comparison, via `NoFilter` interactions, so the trend and heatmap always show every week.
- **Drill-through key:** `enrolment_id`, **not** `employee_id`, so the two re-enrolled synthetic employees stay distinct per cohort.
- **Navigation:** the rail links only to working pages. Trainee 360 is labelled "drill-through" and has no link.
- **Only approved new DAX:** `Withdrawal Rate (Snapshot)`.

**Drafts sent for ChatGPT review (superseded by D26; kept for the record, not deployed):**

1. *Paired person-level week-over-week change*: same enrolment, same competency, consecutive weeks.
```dax
Paired WoW Competency Change =
-- Only for ONE selected programme week; blank otherwise (no mixing of weeks)
IF (
    HASONEVALUE ( 'rpt dim_programme_week'[programme_week] ),
    AVERAGEX (
        FILTER (
            ADDCOLUMNS (
                VALUES ( 'rpt fact_assessment'[enrolment_id] ),
                "@change", CALCULATE ( AVERAGE ( 'rpt fact_assessment'[week_over_week_change] ) )
            ),
            NOT ISBLANK ( [@change] )       -- enrolments without a consecutive prior week are excluded, never zero
        ),
        [@change]                           -- average per enrolment first, then across enrolments
    )
)
```
2. *Trainee 360: cohort average at the same week*, for comparing one enrolment against its own cohort.
```dax
Cohort Avg Competency (Same Week) =
VAR TraineeCohorts = VALUES ( 'rpt dim_enrolment'[cohort_id] )      -- the drilled enrolment's cohort
RETURN
    CALCULATE (
        [Average Competency Score],
        REMOVEFILTERS ( 'rpt dim_enrolment' ),                        -- drop the enrolment filter...
        TREATAS ( TraineeCohorts, 'rpt dim_enrolment'[cohort_id] )    -- ...but keep its cohort
    )
```
Both need review of semantics, filter context and naming before they're added to the model.

**Owner addition (UX-03):** display-only measure `Selected Weeks Label` (in `rpt dim_programme_week`, folder *UX display*). It labels the Skills comparison panel "Showing Week 6", "Showing Week 4, Week 5 (combined)", or "Showing all weeks · mixed programme stages". It's text only and changes no calculation.

### D26 — D25 review: paired change and cohort benchmark measures (2026-11-18, branch `ux/d25-measures`)
**Why:**
- A cohort mean that moves between weeks partly reflects *which* trainees were assessed. The paired change compares each trainee only with their own previous week, so that effect disappears.
- A trainee's score means little on its own; the same-week cohort average gives it context.
- **Trade-off:** both measures are averages of averages *by design*: one value per trainee first, so a trainee with more rows doesn't count more.
- **At scale:** the per-enrolment loop in `AVERAGEX` is cheap at 208 enrolments. With 100k+ enrolments, pre-compute the per-enrolment change in SQL.

**Final DAX** (ChatGPT's reference, plus the owner-approved changes; the measures live in `rpt dim_competency`, folder *Competency · D25*):
```dax
Paired WoW Competency Change =                      -- format +0.0;-0.0;0.0
AVERAGEX (
    VALUES ( 'rpt dim_enrolment'[enrolment_id] ),
    CALCULATE ( AVERAGE ( 'rpt fact_assessment'[week_over_week_change] ) )
)

Cohort Same-Week Average =                          -- format 0.0
VAR CurrentCohort = SELECTEDVALUE ( 'rpt dim_enrolment'[cohort_id] )
RETURN
    IF (
        NOT ISBLANK ( CurrentCohort )
            && HASONEVALUE ( 'rpt dim_enrolment'[enrolment_id] ),
        CALCULATE (
            [Average Competency Score],
            REMOVEFILTERS ( 'rpt dim_enrolment' ),
            REMOVEFILTERS ( 'rpt fact_assessment'[enrolment_id] ),
            TREATAS ( { CurrentCohort }, 'rpt dim_cohort'[cohort_id] )
        )
    )
```

**Differences from the D25 drafts, and why:**

| Measure | Change from the draft | Reason |
|---|---|---|
| Paired WoW Competency Change | The single-week `HASONEVALUE` gate is dropped, so several weeks are allowed | Per ChatGPT's rules: the result is the average of each trainee's own changes across the selected weeks. |
| Paired WoW Competency Change | Iterates `dim_enrolment[enrolment_id]` instead of `FILTER`/`ADDCOLUMNS` | Same result, simpler code: `AVERAGEX` already skips blanks. |
| Paired WoW Competency Change | Signed format | Owner-approved, so a fall reads as −1.2. |
| Cohort Same-Week Average | `SELECTEDVALUE` replaces `VALUES` | The draft could average several cohorts together into one misleading benchmark. |
| Cohort Same-Week Average | `TREATAS` filters `dim_cohort` | The dimension is the right place to apply the cohort filter. |
| Cohort Same-Week Average | `HASONEVALUE(enrolment_id)` gate added | Owner-approved, so it meets ChatGPT's test "several enrolments selected → blank". |
| Cohort Same-Week Average | Renamed from "Cohort Avg Competency (Same Week)" | ChatGPT's name. |

**Where they're shown:**
- **Skills page:** a header strip next to the week selector. It follows the cohort tiles and the week selector.
- **Trainee 360:** the competency panel is split. The top half is unchanged: one line per competency. The new bottom half plots *This trainee* against *Cohort, same week*.

**Unchanged:** SQL, source data, relationships and every existing measure.



---

## Build 02: coaching, certification and readiness (2026-11-18, branch `build/02-coaching-certification-readiness`)

Implements the approved specification (`BUILD02_COACHING_CERTIFICATION_READINESS_SPEC`, policy `B02-R1`). All thresholds are fictional and live in `config/build02_synthetic.toml`.

### D27: Build 02 is generated from the committed Build 01 CSVs, and decisions only see what was recorded by then
**Why:**
- Build 01 is frozen and validated, so Build 02 *reads* its CSVs and never regenerates or edits them. A test proves the files' checksums are untouched.
- Every simulated decision has a moment: a weekly review at 10:00, an exam, a readiness review. It only sees Build 01 records whose `recorded_at` is on or before that moment, which is a stronger guarantee than "nothing after the snapshot".
- **Proof:** Build 02 generated from Build 01 *as it stood* on 10 June, 20 August and 12 October matches the full run observed on those dates. Same cases, attempts and reviews.

**How it stays reproducible:**
- **Own seed:** Build 02 uses seed 20261118, separate from Build 01's.
- **One random stream per record**, seeded with text such as `seed|certification|ENR-00044|OCR`. One trainee's results therefore never depend on how many records were generated before them.
- **Stable IDs:** IDs come from the enrolment number (`WLC-00044-1`), so they are the same at every as-of date.

**Trade-off:** the "what was known when" lookups are simple linear scans. That's fine at 208 enrolments; with 100k+ enrolments, pre-index by date.

### D28 (SUPERSEDED by D34): `sql/001_create_schema.sql` drops the Build 02 tables first
**Why:**
- The Build 02 tables have real foreign keys to `core.enrolment`, and SQL Server refuses to drop a table that other tables reference. Without this change, re-running Build 01's schema script would fail as soon as Build 02 exists.
- The six added lines are `DROP TABLE IF EXISTS`. No Build 01 table, column, constraint, view, CSV or result changes.

**Consequence:** reloading Build 01 removes the Build 02 tables; reload Build 02 afterwards. This is documented in the walkthrough.

**Alternative rejected:** dropping the foreign keys, so 001 needed no edit. That would have weakened integrity, which the spec asks us to enforce.

### D29: Rules within a row are CHECK constraints; rules across tables are validated twice, independently
**Why:**
- **Same-row rules → CHECK constraints.** Examples: Approved needs all gates plus sign-off; a closure reason only on Closed events; a manual referral has no trigger week. The database itself then refuses bad rows.
- **Cross-table rules → validation in two places.** Examples: an attempt strictly after completion, no overlapping cases, gates matching the evidence actually on record. These are checked by the Python `validate()` **and**, independently, by `sql/build02_validation_queries.sql`, so a bug in one is caught by the other.
- **The competency threshold (65) is not repeated in SQL,** because policy values live in config. The SQL instead checks that the gate was applied *consistently*: every passing score is above every failing one.

### D30: Watch-list signals compare like with like; cases close on evidence, not on coaching
**Signals.** Signals are reasons to *look*, not predictions, and they aren't stored; only the staff decision is. There are three:
- **Low recorded attendance:** the last two weeks, Present ÷ (Present + Absent). Unrecorded marks are ignored, and at least 4 known marks are needed.
- **Low competency:** at least 9 points below the cohort's **same-week** average.
- **Declining scores:** a drop of at least 2.5 points from the previous week.

**Opening a case.** Not every signal becomes a case (85%), and occasional manual referrals happen without any signal.

**Closing a case:**
- **Improved:** two consecutive signal-free reviews.
- **Withdrawn / Programme ended:** an administrative closure once the exit is *recorded*.
- **Administrative:** a resolved manual referral.

Coaching actions are generated *after* each case's lifecycle and never influence closure, so the data can't "prove" that coaching works.

**Change after coaching** is measured as the change in the trainee's gap to the cohort, because raw scores rise for almost everyone during training. With that measure, coached trainees go both ways: one gap narrowed by 3.2 points, another widened by 4.8.

**One honest edge case (info check):** one case was opened a few days after a withdrawal that had happened but wasn't yet recorded. It closes as Withdrawn once the withdrawal is entered.

### D31: Readiness gates use evidence on record before the review day; re-review only when something can change
**Gates.** Gates are computed at review time from records entered before the review:
- **completion** must be on record;
- **certification:** each mandatory certification has a recorded pass;
- **competency:** the latest week with **all five** competencies scored, average at least 65.

**Approval.** Approval also needs manager sign-off (85% when every gate passes). Otherwise the review is Deferred with `SIGNOFF_PENDING`.

**Deferral reason priority:** certification, then evidence, then competency, then sign-off.

**Re-review.** A Deferred enrolment is reviewed again (up to 3 times) only when the cause can still change: a certification pending, or sign-off pending. A certification failed at the maximum number of attempts, or a competency score below threshold after training has ended, is final within Build 02.

**History.** Every review keeps its own evidence, so a later approval never rewrites an earlier deferral.

### D32: Reporting views carry the "pick one row" flags, so KPIs can't double-count
**Flags added to the views:**
- `fact_readiness_review.is_latest_review`, for "Approved now";
- `fact_certification_attempt.pair_passed` and `is_first_attempt`, for the candidate and first-attempt pass rates;
- `fact_watchlist_case.is_open_at_snapshot`, `action_count` and `days_to_first_action`, for coverage and timeliness at case grain.

**Validation** reconciles the views with the core tables: open = total − closed; every action counted exactly once; one latest review per reviewed enrolment.

**Keys and labels.** Facts carry `cohort_id` and `employee_id` only as labels. Power BI should relate on `enrolment_id` only (proposal in `docs/build02_data_dictionary.md`).

**No seventh view.** There is no extra "readiness status per enrolment" view: "Not reviewed" is derived from `dim_enrolment` plus the latest review, as in `build02_analysis_examples.sql` query 7.

### D33: Tuned synthetic parameters (fictional)
The first run produced only 59% first-attempt passes, and most readiness reviews fell before trainees had sat their exams. The exam score was tuned to "latest training average − 1 ± 7", and the first review moved to 28–45 working days after completion.

**Result:**
- **First attempts:** 67% pass.
- **Readiness outcomes:** a realistic mix of approvals, deferrals pending a retake, final deferrals and unreviewed completers.

The policy values (70 pass mark, 2 attempts, 65 competency, sign-off required) were **not** changed.

---

## Build 02 conditional-approval changes (2026-11-18, same branch, PR #8)

The owner and ChatGPT conditionally approved Build 02, with five requirements. D34–D37 implement them.

### D34: Build 01's `001` is restored unchanged; Build 02 adds a guard and an explicit full reset (supersedes D28)
**Why:**
- Build 01 scripts must not know about later builds, so `001_create_schema.sql` is byte-identical to `main` again.
- But with Build 02's foreign keys in place, the unchanged 001 would drop *some* Build 01 tables and then fail on `core.enrolment`. That was tested: it left Build 01 half-deleted.

**What was built:**
- **The guard.** `004` installs a database-level DDL trigger, `trg_protect_build01_from_partial_drop`. While Build 02 tables exist, it cancels any `DROP` of a Build 01 core table before anything is removed, with a message naming the reset procedure.
- **The reset.** `sql/007_reset_build02_objects.sql` removes everything Build 02 added (6 views, 6 tables, the guard).
- **One command.** `python/full_reset.py --confirm` runs 007 → Build 01 → Build 02 and both validations. It refuses to run without `--confirm`.

**Lesson recorded.** A trigger keeps the `QUOTED_IDENTIFIER` setting it was created with. Created from `sqlcmd` (default OFF), its `EVENTDATA()` XML call failed and blocked every `DROP TABLE`. `004` now sets it ON explicitly, and `007` drops the trigger first, so the reset can always clean up. A test covers it.

**Trade-off:** the trigger is a database object you can't see in the table list (find it under *Programmability → Database Triggers* in SSMS). In exchange, a wrong-order rebuild can no longer damage Build 01. At scale this is normally handled by migration tooling instead.

### D35: Audit outputs for signals, evidence completeness and missing-attendance data quality (no new table)
**Why:** the signals behind each watch-list decision, and the evidence behind each readiness status, must be inspectable and reproducible without adding a seventh core table.

**What was built:**
- **Two audit files from the generator** (in its manifest):
  - `data/synthetic/build02/audit/review_signals.csv`: one row per weekly review, with eligible / recorded / present / **unrecorded** sessions, the rate, the `VERIFY_UNRECORDED_MARKS` data-quality flag, competency evidence, the gap to the cohort, signals, outcome and case ID.
  - `audit/readiness_evidence.csv`: one row per completed enrolment, with competency evidence, certification status and populations.
- **An independent SQL twin.** `sql/build02_audit_queries.sql` recomputes both from the database, and a test compares them value by value.

**Thresholds stay in config.** The SQL reproduces the evidence *inputs*; its few schedule settings are declared at the top, and a test checks they equal the config.

**No look-ahead.** A decision taken on the snapshot day but entered later is shown as "(entered after snapshot)" with its ID hidden, so the audit never reveals a record the dataset doesn't hold. Building this exposed exactly that issue: a first version listed 4 case IDs that weren't in the dataset yet.

### D36: Snapshot flags are documented as snapshot-only; a time-aware pattern is provided
`is_open_at_snapshot`, `case_status_as_of_snapshot`, `days_open` and `is_latest_review` describe the state at `core.data_snapshot.as_of_date`, using records entered by then. They are **not** "as of any date". This is documented in the view header, the data dictionary and the walkthrough.

`build02_analysis_examples.sql` query 10 shows the correct pattern for any earlier date: filter on the effective **and** recorded dates, then take the latest row. Example on 2026-10-20: Cohort 3 had 13 open watch-list enrolments, and Cohort 2 stood at 18 Approved / 14 Deferred.

### D37: Unactioned, unattempted and unreviewed populations are reported separately and reconciled
**Grains are unchanged:**

| KPI | Grain |
|---|---|
| Coverage | cases |
| Candidate pass rate | enrolment × certification pairs |
| First-attempt pass rate | attempts |
| Readiness | completed enrolments, latest review |

The people outside each denominator are reported, not dropped:
- **Validation:** four `population_…` error checks prove each split adds back up to its whole, and four new info rows give the counts: 15 unactioned cases, 4 completers with no attempt, 16 mandatory pairs not attempted, 8 not reviewed.
- **Analysis:** `build02_analysis_examples.sql` query 9 lists all populations per cohort; `readiness_evidence.csv` gives them per enrolment.

---

## BI-02: Coaching, Certification & Readiness analytics (2026-11-19, branch `bi/02-coaching-certification-readiness`)

The measures and relationships were approved by the owner and ChatGPT (`docs/bi02_measure_proposal.md`, including the two final corrections). D38–D40 record the implementation choices.

### D38: An additive model extension, and the approved measures only
**What:**
- six tables (the Build 02 `rpt` views);
- six relationships, all **many-to-one, single direction, active**: five facts → `dim_enrolment[enrolment_id]`, plus `fact_certification_attempt` → `dim_certification[certification_id]`;
- 17 approved measures in three display folders.

**Not added:** no `dim_date` relationships (D2), no direct `dim_cohort` links. No existing table, relationship or measure was edited.

**Why:**
- The cohort reaches every new fact through exactly one path (cohort → enrolment → fact), so selections can't be ambiguous.
- With no date path, a date filter can't turn a snapshot card into a fake historical number.

**Status-safe denominators:** four measures count their own denominators with `KEEPFILTERS` instead of reusing `Active/Completed Trainees (Snapshot)`, whose plain filter would override a status selection.

**Trade-off:** a few lines of DAX are repeated (the "completed in context" count) rather than adding unapproved helper measures.

### D39: Two pages, an extended Trainee 360, and three built-in counts
**Pages:** *Coaching & Watch List* and *Certification & Readiness* use the existing design system (generator, dark theme, synced cohort tiles, their own Clear filters bookmark, and rail navigation).

**KPI cards:** chart clicks never change the KPI cards (`NoFilter`), as on the Overview.

**Built-in counts.** Three charts use Power BI's built-in *Count of* a column instead of a new DAX measure, each labelled on the chart:
- events by effective date;
- actions by type;
- latest decisions by cohort and reason.

These are plain row counts on clearly stated grains, so they need no new semantics review.

**Trainee 360:** the page grows from 1080 to **1824 px tall** (Fit to width, scroll down) instead of squeezing the new history into the existing panels, which stay unchanged. It gains:
- a readiness status banner, using `Readiness Status Label`, which never says "Failed";
- watch-list episodes, coaching actions, certification attempts and the review timeline, all filtered by the drill-through `enrolment_id`.

### D40: Validation evidence is split honestly
**Claude's environment can prove:**
- the model parses (Microsoft TMDL parser: 14 relationships, all many-to-one, single direction, active);
- every column and measure referenced in the new DAX exists;
- all 451 report files pass Microsoft's schemas;
- the cross-file report checks pass;
- the generator is deterministic;
- the SQL reference values.

**It cannot execute DAX**, because there is no Analysis Services engine here. Whether each measure returns the reference value is proven by the owner's Desktop run against `sql/bi02_measure_reference.sql` (validation plan in section 6 of the proposal). This is the same split used for D26.


---

## D41 (PENDING APPROVAL): Workforce Intelligence Suite, three reports on one shared semantic model (2026-11-19)
**Status:** proposed; awaiting owner and ChatGPT approval. **Nothing has been restructured yet.**

**Full proposal:** `docs/architecture_multi_report_proposal.md`.

**Proposal:**
- Evolve the single report into three: **Report 01** Workforce Development & Readiness (the existing report, unchanged), **Report 02** Payment Operations Performance (BI-03) and **Report 03** Workforce Outcomes & Training Effectiveness (BI-04).
- All three share **one** semantic model folder through PBIP `byPath` references, as Report 01 already does. That gives one set of tables, relationships and DAX.

**Why:**
- It demonstrates reusable semantic modelling and consistent definitions, fully offline in Power BI Desktop.
- Separate models would duplicate DAX and drift apart.
- A published model with live-connected thin reports (`byConnection`) is the enterprise pattern, but it needs the Power BI Service and licences. It stays a one-setting future option.

**Trade-off:** locally, every report opens the full model, so the safety rules are:
- one Desktop window at a time;
- an automated additive-only model check against a validated tag;
- Report 01 regenerated byte-identically;
- a developer-only Model QA report for repeatable measure regression checks.

**At scale:** publish the model once and connect the reports live, add incremental refresh in the Service, and use aggregate tables for very large facts.

**Material finding needing a decision (E1):** at the frozen snapshot (2026-11-02), no approved associate can have 90 days of operational history:
- the earliest approval was 89 days before the snapshot;
- Cohort 2's approvals are 3–26 days before it;
- Cohort 3 is still in training.

The proposal is to move the suite snapshot to 2027-06-30 once, at the start of Build 03, as a controlled re-baseline of the reference numbers.
