/* ---------------------------------------------------------------------------
   build02_analysis_examples.sql
   Example business questions for Build 02, answered from the rpt views.
   Each query states its numerator, denominator and grain, because the
   classic mistake here is mixing people, enrolments, cases and attempts.
   Run them one at a time in SSMS (select a query, press F5).
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;

/* 1. Open watch-list enrolments at the snapshot, and the watch-list rate.
      Numerator: DISTINCT enrolments with an open case (not cases, not actions).
      Denominator: Active trainees at the snapshot. */
SELECT
    d.cohort_id,
    COUNT(DISTINCT CASE WHEN w.is_open_at_snapshot = 1 THEN w.enrolment_id END) AS open_watchlist_enrolments,
    COUNT(DISTINCT CASE WHEN d.status_as_of_snapshot = 'Active' THEN d.enrolment_id END) AS active_trainees,
    CAST(100.0 * COUNT(DISTINCT CASE WHEN w.is_open_at_snapshot = 1 AND d.status_as_of_snapshot = 'Active'
                                     THEN w.enrolment_id END)
         / NULLIF(COUNT(DISTINCT CASE WHEN d.status_as_of_snapshot = 'Active' THEN d.enrolment_id END), 0)
         AS DECIMAL(5,1)) AS watchlist_rate_pct
FROM rpt.dim_enrolment AS d
LEFT JOIN rpt.fact_watchlist_case AS w ON w.enrolment_id = d.enrolment_id
GROUP BY d.cohort_id
ORDER BY d.cohort_id;

/* 2. New cases by month opened, and how they closed (cases, not people). */
SELECT
    DATEFROMPARTS(YEAR(opened_effective_date), MONTH(opened_effective_date), 1) AS month_opened,
    COUNT(*) AS new_cases,
    SUM(CASE WHEN closure_reason = 'Improved' THEN 1 ELSE 0 END) AS closed_improved,
    SUM(CASE WHEN closure_reason IN ('Withdrawn', 'Programme ended', 'Administrative') THEN 1 ELSE 0 END) AS closed_other,
    SUM(is_open_at_snapshot) AS still_open
FROM rpt.fact_watchlist_case
GROUP BY DATEFROMPARTS(YEAR(opened_effective_date), MONTH(opened_effective_date), 1)
ORDER BY month_opened;

/* 3. Coaching coverage and time to first action.
      Coverage = cases with >= 1 action / ALL cases (case grain, never action rows).
      Time to first action is averaged over actioned cases only; unactioned
      cases are shown separately rather than silently dropped. */
SELECT
    cohort_id,
    COUNT(*) AS cases,
    SUM(has_action) AS actioned_cases,
    COUNT(*) - SUM(has_action) AS cases_without_action,
    CAST(100.0 * SUM(has_action) / COUNT(*) AS DECIMAL(5,1)) AS coaching_coverage_pct,
    CAST(AVG(CAST(days_to_first_action AS DECIMAL(6,2))) AS DECIMAL(5,1)) AS avg_days_to_first_action
FROM rpt.fact_watchlist_case
GROUP BY cohort_id
ORDER BY cohort_id;

/* 4. Change after coaching (DESCRIPTIVE ONLY: association, not cause).
      For actioned cases with a trigger week: the trainee's gap to the cohort
      average at the trigger week vs two weeks later. A comparable measure:
      raw scores rise for almost everyone during training. */
WITH week_avg AS (
    SELECT enrolment_id, cohort_id, programme_week, AVG(CAST(score AS DECIMAL(6,2))) AS avg_score
    FROM rpt.fact_assessment GROUP BY enrolment_id, cohort_id, programme_week
), cohort_avg AS (
    SELECT cohort_id, programme_week, AVG(CAST(score AS DECIMAL(6,2))) AS avg_score
    FROM rpt.fact_assessment GROUP BY cohort_id, programme_week
)
SELECT
    w.watchlist_case_id, w.cohort_id, w.primary_reason, w.trigger_programme_week, w.closure_reason,
    CAST(pre.avg_score - cpre.avg_score   AS DECIMAL(5,1)) AS gap_at_trigger,
    CAST(post.avg_score - cpost.avg_score AS DECIMAL(5,1)) AS gap_two_weeks_later,
    CAST((post.avg_score - cpost.avg_score) - (pre.avg_score - cpre.avg_score) AS DECIMAL(5,1)) AS gap_change
FROM rpt.fact_watchlist_case AS w
JOIN week_avg   AS pre   ON pre.enrolment_id  = w.enrolment_id AND pre.programme_week  = w.trigger_programme_week
JOIN week_avg   AS post  ON post.enrolment_id = w.enrolment_id AND post.programme_week = w.trigger_programme_week + 2
JOIN cohort_avg AS cpre  ON cpre.cohort_id  = w.cohort_id AND cpre.programme_week  = w.trigger_programme_week
JOIN cohort_avg AS cpost ON cpost.cohort_id = w.cohort_id AND cpost.programme_week = w.trigger_programme_week + 2
WHERE w.has_action = 1
ORDER BY gap_change DESC;

/* 5. Certification: attempts, first-attempt pass rate, candidate pass rate.
      Attempts = rows. First-attempt pass rate = first attempts passed / first attempts.
      Candidate pass rate = enrolment x certification PAIRS with a pass / pairs attempted.
      Completed trainees who never attempted are NOT in any denominator (see query 6). */
SELECT
    a.cohort_id,
    c.certification_name,
    COUNT(*) AS attempts,
    SUM(a.is_retake) AS retakes,
    CAST(100.0 * SUM(CASE WHEN a.is_first_attempt = 1 THEN a.is_passed END)
         / SUM(a.is_first_attempt) AS DECIMAL(5,1)) AS first_attempt_pass_pct,
    COUNT(DISTINCT a.enrolment_id) AS candidates,
    CAST(100.0 * COUNT(DISTINCT CASE WHEN a.pair_passed = 1 THEN a.enrolment_id END)
         / COUNT(DISTINCT a.enrolment_id) AS DECIMAL(5,1)) AS candidate_pass_pct
FROM rpt.fact_certification_attempt AS a
JOIN rpt.dim_certification AS c ON c.certification_id = a.certification_id
GROUP BY a.cohort_id, c.certification_name
ORDER BY a.cohort_id, c.certification_name;

/* 6. Mandatory certifications met, per completed enrolment.
      Grain: completed enrolments. Fully certified = passed EVERY mandatory one. */
WITH completed AS (
    SELECT enrolment_id, cohort_id FROM rpt.dim_enrolment WHERE status_as_of_snapshot = 'Completed'
), passes AS (
    SELECT a.enrolment_id, COUNT(DISTINCT a.certification_id) AS mandatory_passed
    FROM rpt.fact_certification_attempt AS a
    JOIN rpt.dim_certification AS c ON c.certification_id = a.certification_id AND c.mandatory_for_readiness = 1
    WHERE a.is_passed = 1
    GROUP BY a.enrolment_id
), attempted AS (
    SELECT DISTINCT enrolment_id FROM rpt.fact_certification_attempt
), required AS (   -- how many certifications are mandatory (2 under policy B02-R1)
    SELECT COUNT(*) AS n FROM rpt.dim_certification WHERE mandatory_for_readiness = 1
)
SELECT
    c.cohort_id,
    COUNT(*) AS completed_enrolments,
    SUM(CASE WHEN p.mandatory_passed = r.n THEN 1 ELSE 0 END) AS fully_certified,
    SUM(CASE WHEN p.mandatory_passed > 0 AND p.mandatory_passed < r.n THEN 1 ELSE 0 END) AS partly_certified,
    SUM(CASE WHEN at.enrolment_id IS NULL THEN 1 ELSE 0 END) AS no_attempt_yet
FROM completed AS c
CROSS JOIN required AS r
LEFT JOIN passes AS p ON p.enrolment_id = c.enrolment_id
LEFT JOIN attempted AS at ON at.enrolment_id = c.enrolment_id
GROUP BY c.cohort_id
ORDER BY c.cohort_id;

/* 7. Readiness status at the snapshot, using the LATEST review per enrolment.
      Grain: completed enrolments. "Not reviewed" is kept separate from Deferred.
      Approval rate = approved / reviewed; coverage = approved / all completed. */
WITH latest AS (
    SELECT enrolment_id, decision FROM rpt.fact_readiness_review WHERE is_latest_review = 1
)
SELECT
    d.cohort_id,
    COUNT(*) AS completed_enrolments,
    SUM(CASE WHEN l.decision = 'Approved' THEN 1 ELSE 0 END) AS approved,
    SUM(CASE WHEN l.decision = 'Deferred' THEN 1 ELSE 0 END) AS deferred,
    SUM(CASE WHEN l.decision IS NULL      THEN 1 ELSE 0 END) AS not_reviewed,
    CAST(100.0 * SUM(CASE WHEN l.decision = 'Approved' THEN 1 ELSE 0 END)
         / NULLIF(SUM(CASE WHEN l.decision IS NOT NULL THEN 1 ELSE 0 END), 0) AS DECIMAL(5,1)) AS approval_rate_pct,
    CAST(100.0 * SUM(CASE WHEN l.decision = 'Approved' THEN 1 ELSE 0 END) / COUNT(*) AS DECIMAL(5,1)) AS readiness_coverage_pct
FROM rpt.dim_enrolment AS d
LEFT JOIN latest AS l ON l.enrolment_id = d.enrolment_id
WHERE d.status_as_of_snapshot = 'Completed'
GROUP BY d.cohort_id
ORDER BY d.cohort_id;

/* 8. Deferral reasons, and days from completion to approval. */
SELECT decision, decision_reason_code, COUNT(*) AS reviews,
       CAST(AVG(CASE WHEN decision = 'Approved' THEN CAST(days_from_completion AS DECIMAL(6,1)) END)
            AS DECIMAL(5,1)) AS avg_days_to_readiness
FROM rpt.fact_readiness_review
GROUP BY decision, decision_reason_code
ORDER BY decision, reviews DESC;
