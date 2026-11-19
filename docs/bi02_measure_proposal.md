# BI-02 measure and relationship proposal (FOR REVIEW: not implemented)

**Branch:** `bi/02-coaching-certification-readiness`, from `main` at `216f056` (the Build 02 merge).

**Status:** a draft for owner and ChatGPT review. **No model, DAX or report file has been changed.**

**Built from:** the merged `sql/006_create_build02_reporting_views.sql` and `docs/build02_data_dictionary.md`, checked against a fresh load of the merged code (Claude's environment).

**Independent reference values:** `sql/bi02_measure_reference.sql`. It computes every measure from the **core tables**, never from the `rpt` view flags the DAX uses.

---

## 1. Physical relationship map (verified)

| One side (1) | Many side (*) | Key (physical column) | Rows (many) | NULL keys | Orphans | One side unique? |
|---|---|---|---|---|---|---|
| `rpt dim_enrolment` | `rpt fact_watchlist_case` | `enrolment_id` | 64 | 0 | 0 | 208 rows / 208 distinct |
| `rpt dim_enrolment` | `rpt fact_watchlist_event` | `enrolment_id` | 113 | 0 | 0 | ✓ |
| `rpt dim_enrolment` | `rpt fact_coaching_action` | `enrolment_id` | 110 | 0 | 0 | ✓ |
| `rpt dim_enrolment` | `rpt fact_certification_attempt` | `enrolment_id` | 304 | 0 | 0 | ✓ |
| `rpt dim_certification` | `rpt fact_certification_attempt` | `certification_id` (one per certification × policy version, so version-aware) | 304 | 0 | 0 | 2 rows / 2 distinct |
| `rpt dim_enrolment` | `rpt fact_readiness_review` | `enrolment_id` | 168 | 0 | 0 | ✓ |

**How the relationships are set up:**
- All are **one-to-many, single direction, active**.
- The existing 8 relationships are unchanged.
- There are **no** direct `dim_cohort → fact` links: the cohort reaches every new fact only through `dim_cohort → dim_enrolment → fact`.
- `cohort_id` and `employee_id` in the facts stay plain label columns, with no relationship.

**Date roles. Recommendation: no `dim_date` relationship in BI-02 (decision D2 below).**
- The new trend visual (cases opened/closed over time) can put `fact_watchlist_event[effective_date]` straight on its axis, without a relationship.
- With no path from `dim_date` to the new facts, no date selection can ever reach the snapshot flags (acceptance criterion 14), so the snapshot measures need no `REMOVEFILTERS('rpt dim_date')` guard.
- If a later question needs date-sliced event counts, the relationships and guards can be added then, as the spec allows.

**Data types to expect on import:**
- dates → Date;
- `*_recorded_at` / `recorded_at` → Date/Time;
- **Flags the views calculate** (`is_open_at_snapshot`, `has_action`, `is_passed`, `is_first_attempt`, `is_retake`, `pair_passed`, `is_latest_review`, `is_approved`) are SQL `int` → **Whole number 0/1**, compared with `= 1`.
- **Columns passed through from the core tables** (`mandatory_for_readiness`, the readiness gates, `signoff_recorded`, `followup_recommended`) are SQL `bit` → **True/False**. The DAX compares `mandatory_for_readiness` with `TRUE ()`; no batch 1 measure filters on the gates.

These types were checked with `sys.columns` on the loaded views.

---

## 2. Proposed measures, batch 1 (DAX drafts)

**Rules applied throughout:**
- **Grain:** each measure counts its own grain. Enrolments always use `DISTINCTCOUNT(enrolment_id)`, never `employee_id`.
- **Ratios** use `DIVIDE()` with no alternative result, so a zero denominator shows **blank**, not 0%.
- **Snapshot measures** are named "(Snapshot)" and use the snapshot flags only.
- **Status filters** use `KEEPFILTERS`, so a user's own status selection is respected rather than overridden.
- **Home tables and display folders:** `Watch-list & Coaching` on `rpt fact_watchlist_case`; `Certification` on `rpt fact_certification_attempt`; `Readiness` on `rpt fact_readiness_review`.

### Watch-list & coaching
```dax
Open Watch-list Enrolments (Snapshot) =            -- format 0
COALESCE (
    CALCULATE (
        DISTINCTCOUNT ( 'rpt fact_watchlist_case'[enrolment_id] ),   -- 2 episodes of one enrolment = 1
        'rpt fact_watchlist_case'[is_open_at_snapshot] = 1
    ),
    0
)

Watch-list Rate (Snapshot) =                        -- format 0.0%
DIVIDE (
    CALCULATE (
        [Open Watch-list Enrolments (Snapshot)],
        KEEPFILTERS ( 'rpt dim_enrolment'[status_as_of_snapshot] = "Active" )   -- active only
    ),
    [Active Trainees (Snapshot)]                    -- existing measure, reused
)

Watch-list Cases =                                  -- format 0; cases, not people
COALESCE ( COUNTROWS ( 'rpt fact_watchlist_case' ), 0 )

Unactioned Watch-list Cases =                       -- format 0
COALESCE (
    CALCULATE ( COUNTROWS ( 'rpt fact_watchlist_case' ), 'rpt fact_watchlist_case'[has_action] = 0 ),
    0
)

Coaching Coverage =                                 -- format 0.0%; option A (decision D1)
DIVIDE (
    CALCULATE ( COUNTROWS ( 'rpt fact_watchlist_case' ), 'rpt fact_watchlist_case'[has_action] = 1 ),
    COUNTROWS ( 'rpt fact_watchlist_case' )
)
```

### Certification
```dax
Certification Attempts =                            -- format 0; attempts, not people
COALESCE ( COUNTROWS ( 'rpt fact_certification_attempt' ), 0 )

Certification Candidate Pass Rate =                 -- format 0.0%
VAR Pairs =                                         -- one row per enrolment x certification ATTEMPTED
    SUMMARIZE (
        'rpt fact_certification_attempt',
        'rpt fact_certification_attempt'[enrolment_id],
        'rpt fact_certification_attempt'[certification_id]
    )
VAR PassedPairs =                                   -- the pair passed on ANY attempt (retakes count once)
    FILTER ( Pairs, CALCULATE ( MAX ( 'rpt fact_certification_attempt'[is_passed] ) ) = 1 )
RETURN
    DIVIDE ( COUNTROWS ( PassedPairs ), COUNTROWS ( Pairs ) )

First-Attempt Pass Rate =                           -- format 0.0%
DIVIDE (
    CALCULATE ( COUNTROWS ( 'rpt fact_certification_attempt' ),
                'rpt fact_certification_attempt'[attempt_number] = 1,
                'rpt fact_certification_attempt'[result] = "Passed" ),
    CALCULATE ( COUNTROWS ( 'rpt fact_certification_attempt' ),
                'rpt fact_certification_attempt'[attempt_number] = 1 )
)

Mandatory Certifications Met =                      -- format 0; completed enrolments that passed ALL mandatory
VAR MandatoryCount =
    CALCULATE ( COUNTROWS ( 'rpt dim_certification' ),
                REMOVEFILTERS ( 'rpt dim_certification' ),
                'rpt dim_certification'[mandatory_for_readiness] = TRUE () )
VAR CompletedEnrolments =
    CALCULATETABLE ( VALUES ( 'rpt dim_enrolment'[enrolment_id] ),
                     KEEPFILTERS ( 'rpt dim_enrolment'[status_as_of_snapshot] = "Completed" ) )
RETURN
COALESCE (
    COUNTROWS (
        FILTER ( CompletedEnrolments,
            CALCULATE ( DISTINCTCOUNT ( 'rpt fact_certification_attempt'[certification_id] ),
                        'rpt fact_certification_attempt'[is_passed] = 1,
                        REMOVEFILTERS ( 'rpt dim_certification' ),
                        'rpt dim_certification'[mandatory_for_readiness] = TRUE () )
                = MandatoryCount ) ),
    0
)

Unattempted Certification Opportunities =           -- format 0; completed x mandatory pairs with NO attempt
VAR MandatoryCount =
    CALCULATE ( COUNTROWS ( 'rpt dim_certification' ),
                REMOVEFILTERS ( 'rpt dim_certification' ),
                'rpt dim_certification'[mandatory_for_readiness] = TRUE () )
VAR AttemptedPairs =
    CALCULATE (
        COUNTROWS ( SUMMARIZE ( 'rpt fact_certification_attempt',
                                'rpt fact_certification_attempt'[enrolment_id],
                                'rpt fact_certification_attempt'[certification_id] ) ),
        KEEPFILTERS ( 'rpt dim_enrolment'[status_as_of_snapshot] = "Completed" ),
        REMOVEFILTERS ( 'rpt dim_certification' ),
        'rpt dim_certification'[mandatory_for_readiness] = TRUE ()
    )
RETURN
    COALESCE ( [Completed Trainees (Snapshot)], 0 ) * MandatoryCount - COALESCE ( AttemptedPairs, 0 )

Completers With No Certification Attempt =          -- format 0; extra QA count for the "4" population
VAR CompletedEnrolments =
    CALCULATETABLE ( VALUES ( 'rpt dim_enrolment'[enrolment_id] ),
                     KEEPFILTERS ( 'rpt dim_enrolment'[status_as_of_snapshot] = "Completed" ) )
RETURN
COALESCE (
    COUNTROWS ( FILTER ( CompletedEnrolments,
                         ISBLANK ( CALCULATE ( COUNTROWS ( 'rpt fact_certification_attempt' ) ) ) ) ),
    0
)
```

### Readiness
```dax
Reviewed for Readiness =                            -- format 0; completed enrolments with >= 1 review
COALESCE (
    CALCULATE ( DISTINCTCOUNT ( 'rpt fact_readiness_review'[enrolment_id] ),
                KEEPFILTERS ( 'rpt dim_enrolment'[status_as_of_snapshot] = "Completed" ) ),
    0
)

Unreviewed Completers =                             -- format 0; NOT deferred, NOT failed
COALESCE ( [Completed Trainees (Snapshot)], 0 ) - [Reviewed for Readiness]

Ready / Approved (Snapshot) =                       -- format 0; LATEST review only
COALESCE (
    CALCULATE ( DISTINCTCOUNT ( 'rpt fact_readiness_review'[enrolment_id] ),
                'rpt fact_readiness_review'[is_latest_review] = 1,   -- a superseded approval never counts
                'rpt fact_readiness_review'[decision] = "Approved",
                KEEPFILTERS ( 'rpt dim_enrolment'[status_as_of_snapshot] = "Completed" ) ),
    0
)

Readiness Approval Rate =                           -- format 0.0%; approved / latest-reviewed completers
DIVIDE ( [Ready / Approved (Snapshot)], [Reviewed for Readiness] )

Readiness Coverage =                                -- format 0.0%; approved / ALL completers
DIVIDE ( [Ready / Approved (Snapshot)], [Completed Trainees (Snapshot)] )
```

### Trainee 360 display measure (text, one enrolment)
```dax
Readiness Status Label =                            -- never shows "Failed"
IF (
    HASONEVALUE ( 'rpt dim_enrolment'[enrolment_id] ),
    VAR Status = SELECTEDVALUE ( 'rpt dim_enrolment'[status_as_of_snapshot] )
    VAR Latest =
        CALCULATE ( SELECTEDVALUE ( 'rpt fact_readiness_review'[decision] ),
                    'rpt fact_readiness_review'[is_latest_review] = 1 )
    VAR Reason =
        CALCULATE ( SELECTEDVALUE ( 'rpt fact_readiness_review'[decision_reason_code] ),
                    'rpt fact_readiness_review'[is_latest_review] = 1 )
    RETURN
        SWITCH ( TRUE (),
            Status = "Active", "Not yet eligible: training in progress",
            Status <> "Completed", "Not eligible: enrolment ended (" & Status & ")",
            ISBLANK ( Latest ), "Completed: not yet reviewed",
            Latest = "Approved", "Approved for readiness (not deployment)",
            "Deferred: " & Reason ),
    ""                                              -- cards show "" rather than (Blank)
)
```

---

## 3. Expected values (from `sql/bi02_measure_reference.sql`; core tables, Claude's environment)

| Measure | Cohort 1 | Cohort 2 | Cohort 3 | All |
|---|---|---|---|---|
| Open Watch-list Enrolments (Snapshot) | 0 | 0 | 15 | **15** |
| Watch-list Rate (Snapshot) | blank (0 active) | blank (0 active) | 23.8% (15/63) | **23.8%** (15/63) |
| Watch-list Cases | 23 | 20 | 21 | **64** |
| Unactioned Watch-list Cases | 6 | 5 | 4 | **15** |
| Coaching Coverage (option A) | 73.9% (17/23) | 75.0% (15/20) | 81.0% (17/21) | **76.6%** (49/64) |
| *Coaching Coverage (option B: open ≥ 7 days)* | *85.0% (17/20)* | *86.7% (13/15)* | *85.0% (17/20)* | *85.5% (47/55)* |
| Certification Attempts | 168 | 136 | 0 | **304** |
| Certification Candidate Pass Rate | 75.4% (92/122) | 91.4% (106/116) | blank | **83.2%** (198/238) |
| First-Attempt Pass Rate | 54.1% (66/122) | 81.0% (94/116) | blank | **67.2%** (160/238) |
| Mandatory Certifications Met | 34 | 47 | 0 | **81** |
| Unattempted Certification Opportunities | 8 | 8 | 0 | **16** |
| Completers With No Certification Attempt | 3 | 1 | 0 | **4** |
| Reviewed for Readiness | 62 | 57 | 0 | **119** |
| Unreviewed Completers | 3 | 5 | 0 | **8** |
| Ready / Approved (Snapshot) | 32 | 39 | 0 | **71** |
| Readiness Approval Rate | 51.6% (32/62) | 68.4% (39/57) | blank | **59.7%** (71/119) |
| Readiness Coverage | 49.2% (32/65) | 62.9% (39/62) | blank | **55.9%** (71/127) |

All four D37 reference populations are reproduced independently: 15 / 4 / 16 / 8. They are different populations and are never summed.

**Repeat employees:** EMP-00025's case belongs to ENR-00025 only (Cohort 1). Their Cohort 3 enrolment ENR-00143 has none, so it is never counted in the Cohort 3 figures.

---

## 4. Decisions for owner and ChatGPT

**D1. Coaching Coverage denominator: which cases are "eligible, requiring action"?**

Of the 15 unactioned cases, 7 had almost no opportunity for action:
- 5 were closed by "Programme ended" within 4 days;
- 2 were closed as "Withdrawn" within 2 days;
- 1 more (WLC-00176-1) was opened on the snapshot day itself.

The slowest first action in the data took 8 days.

| Option | Definition | Value |
|---|---|---|
| **A (recommended for BI-02)** | all cases (matches the Build 02 SQL and the approved D37 "15 unactioned") | 76.6% |
| B | cases open at least 7 days (to closure or snapshot) | 85.5% (47/55) |

Option A is simple and already reconciled. Pair it with a tooltip that splits the 15 unactioned into "open < 7 days" and "open ≥ 7 days".

Option B is fairer to staff, but it adds a policy constant (7 days) that would need to live in `config/` and in DAX.

**D2. Date relationships:** none in BI-02 (recommended, see section 1).

**D3. Zero handling:**
- counts return 0 (via `COALESCE`), so cards never show "(Blank)";
- percentages with a zero denominator return blank, as the spec requires.

Note: `COALESCE(…, 0)` measures make *every* row appear in a table visual. Those measures will therefore only be used on cards, never as table values.

**D4. Extra measures beyond the spec's batch 1:**
- `Watch-list Cases`, needed as the coverage context count;
- `Completers With No Certification Attempt`, for the "4" QA population;
- `Readiness Status Label`, needed for the Trainee 360 rule "never a red Failed badge".

---

## 5. How to verify these numbers yourself (owner exercise)

1. **SQL:** run `sql/bi02_measure_reference.sql` in SSMS (after `python python\full_reset.py --server localhost --confirm`). You should get 64 rows, matching the table above.
2. **The distinct-pair denominator, by hand:** this is the core of the Candidate Pass Rate.
   ```sql
   SELECT COUNT(*) AS attempt_rows,
          COUNT(DISTINCT CONCAT(enrolment_id, '|', certification_id)) AS attempted_pairs
   FROM rpt.fact_certification_attempt;      -- 304 rows, but only 238 pairs
   ```
   **Why 304 ≠ 238:** the 66 retakes add rows but no new candidate × certification pairs. Dividing by 304 would penalise people for retaking.
3. **After implementation (Power BI):** put the measures in a matrix with `cohort_name` on rows and compare each cell with section 3.
