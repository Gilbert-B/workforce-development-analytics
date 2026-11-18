/* ---------------------------------------------------------------------------
   build02_trace_one_enrolment.sql
   Follow ONE enrolment through Build 02: source CSV row -> core table ->
   rpt view. Change @enrolment_id to trace another one.

   Default: ENR-00044 (2026 Cohort 1), which has all three storylines:
     * a watch-list case with coaching actions, later closed;
     * a certification failed on the first attempt and passed on the retake;
     * a readiness review Deferred, then Approved.
   Each result set says which CSV file the same rows come from, so you can
   open data\synthetic\build02\<file>.csv and find them by ID.

   Part 2 traces a PERSON (EMP-00025) who has two enrolments, to show that
   Build 02 records attach to an enrolment, never to the person alone.
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
SET NOCOUNT ON;

DECLARE @enrolment_id VARCHAR(20) = 'ENR-00044';   -- <== change me

-- 0. Who and which cohort (Build 01)
SELECT 'Build 01: rpt.dim_enrolment' AS step, enrolment_id, employee_id, cohort_id,
       status_as_of_snapshot, start_date
FROM rpt.dim_enrolment WHERE enrolment_id = @enrolment_id;

SELECT 'Build 01: completion event' AS step, event_type, effective_date, recorded_at
FROM core.enrolment_status_event
WHERE enrolment_id = @enrolment_id AND event_type IN ('started', 'completed', 'withdrawn');

-- 1. Watch-list case (source: watchlist_case.csv) and its history (watchlist_case_event.csv)
SELECT 'core.watchlist_case' AS step, * FROM core.watchlist_case WHERE enrolment_id = @enrolment_id;

SELECT 'core.watchlist_case_event' AS step, ev.*
FROM core.watchlist_case_event AS ev
JOIN core.watchlist_case AS c ON c.watchlist_case_id = ev.watchlist_case_id
WHERE c.enrolment_id = @enrolment_id
ORDER BY ev.effective_date, ev.event_type DESC;

-- The same case as Power BI will see it: status, action count, days to first action
SELECT 'rpt.fact_watchlist_case' AS step, watchlist_case_id, episode_number, primary_reason,
       trigger_programme_week, case_status_as_of_snapshot, closure_reason, action_count,
       days_to_first_action
FROM rpt.fact_watchlist_case WHERE enrolment_id = @enrolment_id;

-- 2. Coaching actions (coaching_action.csv)
SELECT 'rpt.fact_coaching_action' AS step, coaching_action_id, action_sequence, action_date,
       action_type, staff_role, days_since_case_opened
FROM rpt.fact_coaching_action WHERE enrolment_id = @enrolment_id
ORDER BY action_sequence;

-- Scores around the case: this trainee vs the same cohort, same week (descriptive only)
SELECT 'scores vs cohort' AS step, t.programme_week,
       CAST(AVG(CAST(t.score AS DECIMAL(6,2))) AS DECIMAL(5,1)) AS trainee_avg,
       (SELECT CAST(AVG(CAST(c.score AS DECIMAL(6,2))) AS DECIMAL(5,1))
        FROM rpt.fact_assessment AS c
        WHERE c.cohort_id = MAX(t.cohort_id) AND c.programme_week = t.programme_week) AS cohort_avg
FROM rpt.fact_assessment AS t
WHERE t.enrolment_id = @enrolment_id
GROUP BY t.programme_week ORDER BY t.programme_week;

-- 3. Certification attempts (certification_attempt.csv)
SELECT 'rpt.fact_certification_attempt' AS step, certification_attempt_id, certification_id,
       attempt_number, attempt_date, score, pass_mark, result, pair_passed, days_after_completion
FROM rpt.fact_certification_attempt WHERE enrolment_id = @enrolment_id
ORDER BY certification_id, attempt_number;

-- 4. Readiness reviews (readiness_review.csv): the evidence AS IT STOOD at each review
SELECT 'rpt.fact_readiness_review' AS step, readiness_review_id, review_number, review_date,
       decision, decision_reason_code, completion_gate_passed, certification_gate_passed,
       competency_gate_passed, review_competency_score, signoff_recorded, is_latest_review
FROM rpt.fact_readiness_review WHERE enrolment_id = @enrolment_id
ORDER BY review_number;

/* ---- Part 2: one person, two enrolments -------------------------------- */
DECLARE @employee_id VARCHAR(20) = 'EMP-00025';

SELECT 'person: enrolments' AS step, e.enrolment_id, e.cohort_id, d.status_as_of_snapshot,
       (SELECT COUNT(*) FROM core.watchlist_case AS c WHERE c.enrolment_id = e.enrolment_id) AS watchlist_cases,
       (SELECT COUNT(*) FROM core.certification_attempt AS a WHERE a.enrolment_id = e.enrolment_id) AS attempts,
       (SELECT COUNT(*) FROM core.readiness_review AS r WHERE r.enrolment_id = e.enrolment_id) AS reviews
FROM core.enrolment AS e
JOIN rpt.dim_enrolment AS d ON d.enrolment_id = e.enrolment_id
WHERE e.employee_id = @employee_id
ORDER BY e.enrolment_id;

SELECT 'person: watch-list cases by enrolment' AS step, c.watchlist_case_id, c.enrolment_id, c.cohort_id,
       c.opened_effective_date, c.closure_reason
FROM rpt.fact_watchlist_case AS c
WHERE c.employee_id = @employee_id;
