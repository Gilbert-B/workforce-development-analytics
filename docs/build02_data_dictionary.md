# Build 02 data dictionary: coaching, certification and readiness

Everything here is **synthetic**: a fictional payments-operations company. The certification names and thresholds are fictional internal policies, not regulations.

**The common chain:** every Build 02 record belongs to one **enrolment**, either directly or through its watch-list case. Through `core.enrolment` it therefore belongs to one cohort and one person.
- Build 02 never uses `employee_id` on its own as a key.
- The same person in two cohorts gets independent records, for example EMP-00025: ENR-00025 in Cohort 1, ENR-00143 in Cohort 3.

**Dates:** each event has two dates.
- **`effective_date`** (or `opened_effective_date`, `attempt_date`, `review_date`): when it happened in the business.
- **`recorded_at`**: when it was entered in the system, never earlier than the effective date.

Nothing is dated after the snapshot (`core.data_snapshot.as_of_date`, 2026-11-02).

**Missing is missing:**
- No table stores a "not attempted" or "not reviewed" row; those states are the *absence* of rows.
- Unrecorded attendance is never treated as absence.
- A missing score is never treated as zero.

---

## Source tables (`core`), created by `sql/004_create_build02_tables.sql`

### `core.certification_type`: one row per certification × policy version
| Column | Type | Null | Rule |
|---|---|---|---|
| certification_id | varchar(10) | no | **PK**, e.g. `CERT-01` |
| certification_code | varchar(10) | no | `PEH`, `OCR`; **unique with policy_version** |
| certification_name | nvarchar(80) | no | *Payments Exception Handling*; *Operational Controls & Reconciliation* |
| mandatory_for_readiness | bit | no | both 1 under policy B02-R1 |
| pass_mark | tinyint | no | 0–100 (70) |
| max_attempts | tinyint | no | ≥ 1 (2) |
| policy_version | varchar(10) | no | `B02-R1` |

### `core.watchlist_case`: one row per support episode for one enrolment
| Column | Type | Null | Rule |
|---|---|---|---|
| watchlist_case_id | varchar(20) | no | **PK**, `WLC-<enrolment no.>-<episode>`, stable whatever the as-of date |
| enrolment_id | varchar(20) | no | **FK** → `core.enrolment` |
| opened_effective_date | date | no | the review day the decision was made |
| opened_recorded_at | datetime2(0) | no | not before the effective date |
| primary_reason_code | varchar(30) | no | `LOW_ATTENDANCE`, `LOW_COMPETENCY`, `DECLINING_SCORES`, `MANUAL_REFERRAL` |
| severity | varchar(10) | no | `Low` (manual referral), `Medium` (one signal), `High` (two or more) |
| trigger_programme_week | tinyint | **yes** | the reviewed week; NULL **only** for a manual referral (CHECK) |
| source_type | varchar(20) | no | `Observed signal` or `Manual referral` (consistent with the reason: CHECK) |
| policy_version | varchar(10) | no | `B02-R1` |

**Never two open cases at once** for an enrolment. A later case opens only after the earlier one closed; this is checked by the validation queries. A case is **not** a dropout event and never changes enrolment status.

### `core.watchlist_case_event`: one row per Opened or Closed transition
| Column | Type | Null | Rule |
|---|---|---|---|
| watchlist_event_id | varchar(20) | no | **PK**, `WLE-<case>-O` / `-C` |
| watchlist_case_id | varchar(20) | no | **FK** → `core.watchlist_case`; **unique with event_type**, so exactly one Opened and at most one Closed |
| event_type | varchar(10) | no | `Opened`, `Closed` |
| effective_date | date | no | Closed ≥ Opened |
| recorded_at | datetime2(0) | no | ≥ effective date |
| closure_reason | varchar(20) | **yes** | Closed only: `Improved`, `Withdrawn`, `Programme ended`, `Administrative`. NULL on Opened (CHECK) |
| recorded_by_role | varchar(40) | no | role, not a person |

**Closure reasons:**
- **`Improved`**: two consecutive signal-free reviews. It does **not** mean the coaching caused the change.
- **`Withdrawn`** / **`Programme ended`**: administrative closure once the exit is recorded. These are not coaching outcomes.
- **`Administrative`**: a manual referral resolved with no signal.

### `core.coaching_action`: one row per completed, documented action
| Column | Type | Null | Rule |
|---|---|---|---|
| coaching_action_id | varchar(20) | no | **PK**, `CA-<case>-<n>` |
| watchlist_case_id | varchar(20) | no | **FK** → `core.watchlist_case` |
| action_date | date | no | within the case's open period, and while the trainee is still in training |
| recorded_at | datetime2(0) | no | ≥ action date |
| action_type | varchar(30) | no | `1:1 coaching`, `Attendance follow-up`, `Skills practice`, `Supervisor check-in` |
| staff_role | varchar(40) | no | role, not a person |
| followup_recommended | bit | no | |
| action_note_code | varchar(30) | no | controlled code (`NOTE-…`). There is **no free text** about people. |

A case can have **zero** actions; 15 of 64 have none.

### `core.certification_attempt`: one row per actual attempt
| Column | Type | Null | Rule |
|---|---|---|---|
| certification_attempt_id | varchar(25) | no | **PK**, `CAT-<enrolment no.>-<code>-<n>` |
| enrolment_id | varchar(20) | no | **FK** → `core.enrolment`; completed enrolments only |
| certification_id | varchar(10) | no | **FK** → `core.certification_type` |
| attempt_number | tinyint | no | 1, 2…; **unique (enrolment, certification, attempt_number)**; ≤ max_attempts |
| attempt_date | date | no | **strictly after** the completion effective date; each retake after the earlier attempt |
| recorded_at | datetime2(0) | no | ≥ attempt date |
| score | tinyint | no | 0–100 |
| result | varchar(10) | no | `Passed` if score ≥ pass mark, else `Failed` |
| policy_version | varchar(10) | no | matches the certification type |

### `core.readiness_review`: one row per explicit readiness decision
| Column | Type | Null | Rule |
|---|---|---|---|
| readiness_review_id | varchar(20) | no | **PK**, `RDR-<enrolment no.>-<n>` |
| enrolment_id | varchar(20) | no | **FK** → `core.enrolment`; completed enrolments only |
| review_number | tinyint | no | **unique with enrolment**, consecutive, in date order |
| review_date | date | no | after completion |
| recorded_at | datetime2(0) | no | ≥ review date |
| decision | varchar(10) | no | `Approved` or `Deferred` |
| decision_reason_code | varchar(40) | no | `ALL_GATES_MET_SIGNED_OFF` (Approved only), `CERTIFICATION_PENDING`, `CERTIFICATION_NOT_MET`, `COMPETENCY_BELOW_THRESHOLD`, `INSUFFICIENT_COMPETENCY_EVIDENCE`, `SIGNOFF_PENDING` |
| reviewer_role | varchar(40) | no | authorised role |
| policy_version | varchar(10) | no | `B02-R1` |
| completion_gate_passed | bit | no | completion was on record before the review day |
| certification_gate_passed | bit | no | every mandatory certification had a **pass on record** before the review day |
| competency_gate_passed | bit | no | `review_competency_score` ≥ the threshold (65) |
| review_competency_score | decimal(4,1) | **yes** | average of the latest week with **every** competency scored. NULL = no such evidence, and then the gate can't pass (CHECK) |
| signoff_recorded | bit | no | 1 only when the manager signs off an approval |

**Core rule (CHECK):** `Approved` requires all three gates plus sign-off. The validation queries also recompute the gates from the source records, so a row can't merely *claim* the evidence existed.

**History is kept:** a later review never edits an earlier one. The gate values are the evidence *as it stood at that review*.

---

## Reporting views (`rpt`), created by `sql/006_create_build02_reporting_views.sql`

Every fact has `enrolment_id`, the key for Power BI, plus `cohort_id` and `employee_id` as **labels only**.

| View | Grain | Added columns worth knowing |
|---|---|---|
| `dim_certification` | certification × policy version | (a copy of the type table) |
| `fact_watchlist_case` | one case | `episode_number`, `primary_reason` (label), `closed_effective_date`, `closure_reason`, `case_status_as_of_snapshot`, `is_open_at_snapshot`, `days_open`, `action_count`, `has_action`, `first_action_date`, `days_to_first_action` (NULL = no action) |
| `fact_watchlist_event` | one Opened/Closed transition | `open_count_change` (+1 / −1) for running open counts by date |
| `fact_coaching_action` | one action | `action_sequence`, `days_since_case_opened` |
| `fact_certification_attempt` | one attempt | `pass_mark`, `is_passed`, `is_first_attempt`, `is_retake`, `pair_attempt_count`, `pair_passed` (the enrolment × certification ever passed), `completion_date`, `days_after_completion` |
| `fact_readiness_review` | one review decision | `is_approved`, `is_latest_review` (the decision in force at the snapshot), `completion_date`, `days_from_completion` |

**Joins:**
- `fact_* .enrolment_id` → `rpt.dim_enrolment.enrolment_id` (many to one);
- `fact_certification_attempt.certification_id` → `dim_certification.certification_id`.

All keys are non-null and unique on the "one" side.

---

## KPI semantics (for the later Power BI increment; no DAX in Build 02)

| KPI | Numerator / denominator | Grain | Watch out |
|---|---|---|---|
| Open Watch-list Enrolments (snapshot) | distinct `enrolment_id` with `is_open_at_snapshot = 1` | enrolment | not cases, events or actions |
| Watch-list Rate (snapshot) | open watch-list **active** enrolments / Active trainees | enrolment | finished cohorts have none open; Cohort 3: 15 / 63 = 23.8% |
| New Watch-list Cases | cases with `opened_effective_date` in the period | case | cases ≠ people |
| Coaching Coverage | cases with `has_action = 1` / all cases | case | show unactioned cases; never count action rows |
| Time to First Coaching Action | avg `days_to_first_action` over actioned cases | case | NULL rows are excluded from the average, **not** from coverage |
| Change After Coaching | change in (trainee − cohort same-week average) from the trigger week to two weeks later | case | **association only**; raw scores rise for nearly everyone, so compare against the cohort |
| Certification Attempts | rows | attempt | attempts ≠ candidates |
| First-Attempt Pass Rate | first attempts passed / first attempts | attempt | not ÷ all trainees |
| Candidate Pass Rate | enrolment × certification pairs with `pair_passed = 1` / pairs attempted | pair | not-attempted excluded; report them separately |
| Mandatory Certifications Met | completed enrolments that passed **every** mandatory certification | enrolment | passing one of two is not certified |
| Reviewed for Readiness | completed enrolments with ≥ 1 review | enrolment | unreviewed ≠ failed |
| Ready / Approved (snapshot) | completed enrolments whose `is_latest_review = 1` row is Approved | enrolment | never count all Approved rows |
| Readiness Approval Rate | latest Approved / latest reviewed | enrolment | show **Readiness Coverage** (approved / all completed) separately |
| Days to Readiness | approved `review_date` − completion date | enrolment | approved only |

---

## Proposed Power BI model extension (for BI review, **not implemented**)

1. **Import** the six views.
2. **Relate** each fact's `enrolment_id` → `rpt dim_enrolment[enrolment_id]`, many-to-one, single direction. This keeps the approved cohort → enrolment → fact path.
3. **Relate** `fact_certification_attempt[certification_id]` → `dim_certification`.
4. **Do not** relate the facts to `dim_cohort` directly; that would create a second filter path.
5. **No fact-to-fact relationships.** Coaching is reached through the enrolment; for case-level counts use `fact_watchlist_case[action_count]`.
6. **Dates:** optionally add *inactive* relationships to `rpt dim_date` (`opened_effective_date`, `attempt_date`, `review_date`) and activate them with `USERELATIONSHIP` in measures. `dim_date` already covers these dates, because it runs to the snapshot.
7. **Measures:** the KPIs above, with their exact denominators.
