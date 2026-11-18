/* ---------------------------------------------------------------------------
   006_create_build02_reporting_views.sql
   Build 02 reporting views (schema rpt). ADDITIVE: no Build 01 view changes.
   Run after 004 + 005 (or python/load_build02_to_sql.py). Always re-runnable.

   Every fact carries enrolment_id (the key Power BI will relate on) plus
   cohort_id / employee_id as plain labels. The intended filter path stays
   dim_cohort -> dim_enrolment -> fact, so do NOT relate these facts to
   dim_cohort directly in Power BI (that would create a second path).

   SNAPSHOT-SPECIFIC FLAGS (read before using them in a KPI):
     fact_watchlist_case.is_open_at_snapshot / case_status_as_of_snapshot / days_open
     fact_readiness_review.is_latest_review
   describe the state at core.data_snapshot.as_of_date (2026-11-02 by default),
   using only records entered by then. They are NOT "as of any date": filtering
   a report to September does not turn them into September's state. For an
   earlier date, either regenerate the data with --as-of-date, or use the
   "as of any date" pattern in build02_analysis_examples.sql (query 10).
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
GO

/* ===== dim_certification ================================================= */
-- Grain: one certification x policy version.
CREATE OR ALTER VIEW rpt.dim_certification AS
SELECT
    certification_id,
    certification_code,
    certification_name,
    mandatory_for_readiness,
    pass_mark,
    max_attempts,
    policy_version
FROM core.certification_type;
GO

/* ===== fact_watchlist_case =============================================== */
-- Grain: one watch-list case. Status is "as of snapshot": a case is Open
-- unless a Closed event effective on or before the snapshot exists.
CREATE OR ALTER VIEW rpt.fact_watchlist_case AS
WITH closes AS (
    SELECT watchlist_case_id, effective_date, recorded_at, closure_reason
    FROM core.watchlist_case_event
    WHERE event_type = 'Closed'
),
actions AS (
    SELECT watchlist_case_id, COUNT(*) AS action_count, MIN(action_date) AS first_action_date
    FROM core.coaching_action
    GROUP BY watchlist_case_id
)
SELECT
    c.watchlist_case_id,
    c.enrolment_id,
    e.cohort_id,
    e.employee_id,
    -- 1st, 2nd ... episode for this enrolment (episodes never overlap)
    ROW_NUMBER() OVER (PARTITION BY c.enrolment_id ORDER BY c.opened_effective_date) AS episode_number,
    c.opened_effective_date,
    c.opened_recorded_at,
    c.primary_reason_code,
    CASE c.primary_reason_code
        WHEN 'LOW_ATTENDANCE'   THEN 'Low recorded attendance'
        WHEN 'LOW_COMPETENCY'   THEN 'Low score vs cohort, same week'
        WHEN 'DECLINING_SCORES' THEN 'Declining scores'
        WHEN 'MANUAL_REFERRAL'  THEN 'Manual referral'
    END AS primary_reason,
    c.severity,
    c.trigger_programme_week,
    c.source_type,
    c.policy_version,
    cl.effective_date AS closed_effective_date,
    cl.closure_reason,
    CASE WHEN cl.effective_date <= s.as_of_date THEN 'Closed' ELSE 'Open' END AS case_status_as_of_snapshot,
    CASE WHEN cl.effective_date <= s.as_of_date THEN 0 ELSE 1 END AS is_open_at_snapshot,
    DATEDIFF(DAY, c.opened_effective_date,
             CASE WHEN cl.effective_date <= s.as_of_date THEN cl.effective_date ELSE s.as_of_date END) AS days_open,
    ISNULL(a.action_count, 0) AS action_count,
    CASE WHEN a.action_count > 0 THEN 1 ELSE 0 END AS has_action,
    a.first_action_date,
    DATEDIFF(DAY, c.opened_effective_date, a.first_action_date) AS days_to_first_action   -- NULL = no action yet
FROM core.watchlist_case AS c
JOIN core.enrolment AS e ON e.enrolment_id = c.enrolment_id
CROSS JOIN core.data_snapshot AS s
LEFT JOIN closes  AS cl ON cl.watchlist_case_id = c.watchlist_case_id
LEFT JOIN actions AS a  ON a.watchlist_case_id  = c.watchlist_case_id;
GO

/* ===== fact_watchlist_event ============================================== */
-- Grain: one Opened / Closed transition. open_count_change (+1 / -1) lets a
-- running total by effective date show how many cases were open on any day.
CREATE OR ALTER VIEW rpt.fact_watchlist_event AS
SELECT
    ev.watchlist_event_id,
    ev.watchlist_case_id,
    c.enrolment_id,
    e.cohort_id,
    e.employee_id,
    ev.event_type,
    ev.effective_date,
    ev.recorded_at,
    ev.closure_reason,
    ev.recorded_by_role,
    CASE ev.event_type WHEN 'Opened' THEN 1 ELSE -1 END AS open_count_change
FROM core.watchlist_case_event AS ev
JOIN core.watchlist_case AS c ON c.watchlist_case_id = ev.watchlist_case_id
JOIN core.enrolment AS e ON e.enrolment_id = c.enrolment_id;
GO

/* ===== fact_coaching_action ============================================== */
-- Grain: one completed coaching action. Count CASES (not these rows) when
-- measuring coverage: a case with three actions is still one case.
CREATE OR ALTER VIEW rpt.fact_coaching_action AS
SELECT
    a.coaching_action_id,
    a.watchlist_case_id,
    c.enrolment_id,
    e.cohort_id,
    e.employee_id,
    a.action_date,
    a.recorded_at,
    a.action_type,
    a.staff_role,
    a.followup_recommended,
    a.action_note_code,
    ROW_NUMBER() OVER (PARTITION BY a.watchlist_case_id ORDER BY a.action_date, a.coaching_action_id) AS action_sequence,
    DATEDIFF(DAY, c.opened_effective_date, a.action_date) AS days_since_case_opened
FROM core.coaching_action AS a
JOIN core.watchlist_case AS c ON c.watchlist_case_id = a.watchlist_case_id
JOIN core.enrolment AS e ON e.enrolment_id = c.enrolment_id;
GO

/* ===== fact_certification_attempt ======================================== */
-- Grain: one attempt. "Pair" = one enrolment x one certification.
-- Candidate pass rate divides PAIRS with a pass by PAIRS attempted;
-- first-attempt pass rate divides first attempts passed by first attempts.
CREATE OR ALTER VIEW rpt.fact_certification_attempt AS
WITH completion AS (
    SELECT enrolment_id, effective_date AS completion_date
    FROM core.enrolment_status_event
    WHERE event_type = 'completed'
),
pairs AS (
    SELECT enrolment_id, certification_id,
           COUNT(*) AS pair_attempt_count,
           MAX(CASE WHEN result = 'Passed' THEN 1 ELSE 0 END) AS pair_passed
    FROM core.certification_attempt
    GROUP BY enrolment_id, certification_id
)
SELECT
    ca.certification_attempt_id,
    ca.enrolment_id,
    e.cohort_id,
    e.employee_id,
    ca.certification_id,
    ca.attempt_number,
    ca.attempt_date,
    ca.recorded_at,
    ca.score,
    ct.pass_mark,
    ca.result,
    CASE WHEN ca.result = 'Passed' THEN 1 ELSE 0 END AS is_passed,
    CASE WHEN ca.attempt_number = 1 THEN 1 ELSE 0 END AS is_first_attempt,
    CASE WHEN ca.attempt_number > 1 THEN 1 ELSE 0 END AS is_retake,
    p.pair_attempt_count,
    p.pair_passed,                               -- same value on every row of the pair
    ca.policy_version,
    comp.completion_date,
    DATEDIFF(DAY, comp.completion_date, ca.attempt_date) AS days_after_completion
FROM core.certification_attempt AS ca
JOIN core.enrolment AS e ON e.enrolment_id = ca.enrolment_id
JOIN core.certification_type AS ct ON ct.certification_id = ca.certification_id
JOIN pairs AS p ON p.enrolment_id = ca.enrolment_id AND p.certification_id = ca.certification_id
LEFT JOIN completion AS comp ON comp.enrolment_id = ca.enrolment_id;
GO

/* ===== fact_readiness_review ============================================= */
-- Grain: one review decision. is_latest_review marks the decision in force
-- at the snapshot: use it for "Ready / Approved (snapshot)" so an enrolment
-- with several reviews is counted once. Completed enrolments with NO row
-- here are "Not reviewed", which is not the same as Deferred.
CREATE OR ALTER VIEW rpt.fact_readiness_review AS
WITH completion AS (
    SELECT enrolment_id, effective_date AS completion_date
    FROM core.enrolment_status_event
    WHERE event_type = 'completed'
)
SELECT
    r.readiness_review_id,
    r.enrolment_id,
    e.cohort_id,
    e.employee_id,
    r.review_number,
    r.review_date,
    r.recorded_at,
    r.decision,
    r.decision_reason_code,
    r.reviewer_role,
    r.policy_version,
    r.completion_gate_passed,
    r.certification_gate_passed,
    r.competency_gate_passed,
    r.review_competency_score,
    r.signoff_recorded,
    CASE WHEN r.decision = 'Approved' THEN 1 ELSE 0 END AS is_approved,
    CASE WHEN r.review_number = MAX(r.review_number) OVER (PARTITION BY r.enrolment_id)
         THEN 1 ELSE 0 END AS is_latest_review,
    comp.completion_date,
    DATEDIFF(DAY, comp.completion_date, r.review_date) AS days_from_completion
FROM core.readiness_review AS r
JOIN core.enrolment AS e ON e.enrolment_id = r.enrolment_id
LEFT JOIN completion AS comp ON comp.enrolment_id = r.enrolment_id;
GO

PRINT 'Build 02 reporting views created.';
GO
