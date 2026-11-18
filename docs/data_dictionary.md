# Data dictionary — Build 01

All data is **synthetic**. The CSV files in `data/synthetic/` load 1:1 into the `core` tables. Power BI reads the `rpt` views.

**Two kinds of key:**
- **PK** is the technical primary key.
- **Grain** is the business meaning of "one row".

---

## Source tables (`core` schema = CSV files)

### `cohort` — one scheduled training cohort
| Column | Type | Notes |
|---|---|---|
| cohort_id | varchar(20) | **PK**, e.g. `COH-2026-01` |
| cohort_name | nvarchar(50) | Unique display name |
| start_date | date | Always a Monday |
| planned_end_date | date | The Friday of the final programme week |
| planned_weeks | tinyint | 8 in Build 01 (configurable) |
| delivery_mode | varchar(20) | `In person` or `Virtual` |

### `employee` — one synthetic person
| Column | Type | Notes |
|---|---|---|
| employee_id | varchar(20) | **PK**, e.g. `EMP-00001` |
| first_name, last_name | nvarchar(50) | Randomly combined from fictional name lists |
| hire_date | date | 0–9 days before their first enrolment. Never after it (validation check `enrolled_before_hire_date`) |

There's deliberately **no cohort column**: one person can enrol more than once.

### `competency` — one core competency on the rubric
| Column | Type | Notes |
|---|---|---|
| competency_id | varchar(20) | **PK**, `COMP-01` … `COMP-05` |
| competency_name | nvarchar(60) | Communication; Problem Solving; Transaction Investigation; Operational Controls; Accuracy & Attention to Detail |
| display_order | tinyint | Sort order for visuals |

### `enrolment` — one employee in one cohort
| Column | Type | Notes |
|---|---|---|
| enrolment_id | varchar(20) | **PK**, e.g. `ENR-00001` |
| employee_id | varchar(20) | FK → employee |
| cohort_id | varchar(20) | FK → cohort |
| enrolled_date | date | When the place was offered and accepted |

**Grain:** unique (employee_id, cohort_id). A repeat enrolment in a *different* cohort gets a new enrolment_id.

### `enrolment_status_event` — one dated lifecycle event
| Column | Type | Notes |
|---|---|---|
| status_event_id | varchar(20) | **PK**, `EVT-<enrolment number>-<event code>` |
| enrolment_id | varchar(20) | FK → enrolment |
| event_type | varchar(20) | `enrolled`, `cancelled`, `started`, `withdrawn`, `completed` |
| effective_date | date | When the status applies in the business (see `decisions.md` D7) |
| recorded_at | datetime2 | When it was entered. Never before `effective_date`, never after the as-of date |

**Grain:** unique (enrolment_id, event_type); each event happens at most once per enrolment.

**Valid lifecycles:**
- `enrolled → cancelled`
- `enrolled → started`, then either `withdrawn` or `completed`, or neither while the trainee is still active

### `scheduled_session` — one planned training session
| Column | Type | Notes |
|---|---|---|
| session_id | varchar(30) | **PK**, e.g. `SES-2026-01-W03-D2` |
| cohort_id | varchar(20) | FK → cohort |
| programme_week | tinyint | 1 … planned_weeks |
| session_day | tinyint | 1 = Monday … 5 = Friday |
| session_date | date | |

**Grain:** unique (cohort_id, session_date). Schedules exist in advance, so future sessions are present too.

### `attendance` — one *recorded* attendance mark
| Column | Type | Notes |
|---|---|---|
| enrolment_id | varchar(20) | **PK** part 1; FK → enrolment |
| session_id | varchar(30) | **PK** part 2; FK → scheduled_session (must be the same cohort; checked by validation) |
| attendance_status | varchar(10) | `Present` or `Absent` only |
| recorded_at | datetime2 | |

A **missing row means "not recorded"**, not absent. See `rpt.fact_attendance`.

### `assessment` — one competency score
| Column | Type | Notes |
|---|---|---|
| assessment_id | varchar(20) | **PK**, `ASM-<enrolment number>-W<week>-C<competency>` |
| enrolment_id | varchar(20) | FK → enrolment |
| competency_id | varchar(20) | FK → competency |
| programme_week | tinyint | Week the assessment belongs to |
| attempt_number | tinyint | Always 1 in Build 01 |
| assessment_date | date | The Friday of that programme week |
| score | tinyint | 0–100 |
| rubric_version | varchar(10) | `R1` for all of Build 01 |
| recorded_at | datetime2 | |

**Grain:** unique (enrolment_id, competency_id, programme_week, attempt_number).

### `data_snapshot` — the as-of date of the whole dataset (one row)
| Column | Type | Notes |
|---|---|---|
| as_of_date | date | "Today" for the data; nothing after it exists |
| seed | int | Random seed used |
| generator_version | varchar(20) | |

`generation_manifest.json` (not loaded into SQL) lists every file's row count and SHA-256 checksum.

---

## Reporting views (`rpt` schema — what Power BI imports)

| View | Grain | Purpose / key columns |
|---|---|---|
| `dim_cohort` | cohort | cohort attributes plus `schedule_status` (Scheduled / In progress / Finished as of the snapshot) and `weeks_started` |
| `dim_enrolment` | enrolment | employee_id, **employee_name**, cohort_id, start_date, `status_as_of_snapshot`, `has_started` |
| `dim_employee` | person | employee_name, hire_date, `enrolment_count` (for distinct-person counts) |
| `dim_competency` | competency | name and display order |
| `dim_programme_week` | programme week | 1 … max planned weeks; `week_label` |
| `dim_date` | calendar day | from the first enrolment date to the later of the last cohort end and the snapshot date; month, Monday week start, weekday flag |
| `dim_snapshot` | the whole dataset (exactly 1 row) | `as_of_date`, the generator's as-of date. Imported into Power BI as a **disconnected** table (no relationships) for the dynamic snapshot label |
| `fact_attendance` | **eligible** enrolment × session (up to the snapshot) | `attendance_status` = Present / Absent / **Unrecorded**; 0/1 flags `is_present`, `is_absent`, `is_unrecorded` |
| `fact_assessment` | enrolment × competency × week × attempt | score, rubric_version, `previous_week_score` and `week_over_week_change` (only filled when the previous week is consecutive) |
| `fact_enrolment_status_event` | status event | event plus cohort_id and employee_id; `is_end_event` |
| `enrolment_status_history` | status period | `status`, `valid_from`, `valid_to` (exclusive; NULL = current), via `LEAD()` |
| `fn_enrolment_status_as_of(@date)` | enrolment | Table function: each enrolment's status on any date, using only events effective on or before it |

### Status labels
| Label | Meaning |
|---|---|
| Enrolled (not started) | has an `enrolled` event only |
| Cancelled before start | cancelled; **never** counted in starting headcount |
| Active | started, with no withdrawal or completion effective on or before the date |
| Withdrawn | withdrawal effective on or before the date |
| Completed | completion effective on or before the date |


### Approved first Power BI model (ChatGPT review, 2026-11-16)
Import 7 views from `localhost` / `WorkforceDevAnalytics` in **Import** mode: `rpt.dim_cohort`, `rpt.dim_enrolment`, `rpt.dim_programme_week`, `rpt.dim_competency`, `rpt.dim_date`, `rpt.fact_attendance` and `rpt.fact_assessment`.

**Turn off relationship autodetect first** (File → Options → Current File → Data Load). Both facts carry `cohort_id`, and autodetect would add direct cohort → fact links.

All 8 relationships are one-to-many, **single direction**, and active:
```
dim_cohort[cohort_id] ──> dim_enrolment[cohort_id]
dim_enrolment[enrolment_id] ──> fact_attendance[enrolment_id]
dim_enrolment[enrolment_id] ──> fact_assessment[enrolment_id]
dim_programme_week[programme_week] ──> fact_attendance[programme_week]
dim_programme_week[programme_week] ──> fact_assessment[programme_week]
dim_competency[competency_id] ──> fact_assessment[competency_id]
dim_date[date] ──> fact_attendance[session_date]
dim_date[date] ──> fact_assessment[assessment_date]
```
- Cohort reaches the facts **only through `dim_enrolment`**, a deliberate small snowflake. Don't relate `dim_cohort` to the facts directly. Don't relate `dim_enrolment` to `dim_date` or `dim_programme_week`.
- The facts' `cohort_id` and `employee_id` columns are there for SQL checks and drill-through labels. They're not relationship keys in this model.

**Column types relevant to DAX** (checked against the views):
- `dim_enrolment[has_started]` is an integer (1/0), so filter with `= 1`, not `TRUE()`.
- `fact_attendance[is_present]`, `[is_absent]` and `[is_unrecorded]` are integer flags (1/0).
- `fact_assessment[score]` is a whole number from 0 to 100.
- `fact_assessment[week_over_week_change]` is blank when the previous week is missing.
- `dim_enrolment[status_as_of_snapshot]` is text. It reflects the **snapshot date (2026-11-02) only**. A date slicer doesn't change it; as-of headcount by date needs status-history logic in a later build.

---

## Report measures added for the Overview page (UX-02)
| Measure | Table | Returns | Note |
|---|---|---|---|
| Completion Share of Starters | rpt dim_enrolment | % | Completed (snapshot) ÷ Starting Headcount; as-of snapshot, not final |
| Total Enrolments | rpt dim_enrolment | count | All enrolments, including cancelled before start |
| Cancelled Before Start | rpt dim_enrolment | count | Enrolments whose snapshot status is "Cancelled before start" |
| Starting Headcount Context | rpt dim_enrolment | text | "208 enrolments · 9 cancelled before start" |
| Completion Context | rpt dim_enrolment | text | "63.8% of starters completed to date" |
| Recorded Attendance Bar SVG | rpt fact_attendance | image URL (SVG) | Progress bar from Recorded Attendance Rate, clamped 0–100% |
| Attendance Recording Bar SVG | rpt fact_attendance | image URL (SVG) | Progress bar from Attendance Recording Rate, clamped 0–100% |
| Current Training Week Label | rpt dim_cohort | text | "Currently in Week N" for exactly one in-progress cohort; otherwise empty |

All of these respond to the cohort selection.

