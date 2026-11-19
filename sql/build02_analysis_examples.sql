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

/* 9. KPI populations side by side, per cohort. Every KPI keeps its own grain,
      and the people OUTSIDE each KPI's denominator are shown, not dropped:
        cases          -> actioned | not actioned
        completed      -> fully / partly certified | attempted, none passed | not attempted
        mandatory pairs (completed x mandatory certification) -> attempted | not attempted
        completed      -> approved | deferred | not reviewed   (latest review)
      The same split per enrolment, with its evidence, is in
      build02_audit_queries.sql (query 2). */
WITH cases AS (
    SELECT cohort_id, COUNT(*) AS cases, SUM(has_action) AS actioned
    FROM rpt.fact_watchlist_case GROUP BY cohort_id
), completed AS (
    SELECT d.enrolment_id, d.cohort_id,
           (SELECT COUNT(*) FROM rpt.dim_certification WHERE mandatory_for_readiness = 1) AS mandatory_total,
           (SELECT COUNT(DISTINCT a.certification_id) FROM rpt.fact_certification_attempt AS a
            WHERE a.enrolment_id = d.enrolment_id) AS pairs_attempted,
           (SELECT COUNT(DISTINCT a.certification_id) FROM rpt.fact_certification_attempt AS a
            WHERE a.enrolment_id = d.enrolment_id AND a.is_passed = 1) AS passed,
           (SELECT r.decision FROM rpt.fact_readiness_review AS r
            WHERE r.enrolment_id = d.enrolment_id AND r.is_latest_review = 1) AS latest_decision
    FROM rpt.dim_enrolment AS d
    WHERE d.status_as_of_snapshot = 'Completed'
)
SELECT
    co.cohort_id,
    ISNULL(ca.cases, 0)                         AS cases,
    ISNULL(ca.actioned, 0)                      AS cases_actioned,
    ISNULL(ca.cases - ca.actioned, 0)           AS cases_not_actioned,
    COUNT(c.enrolment_id)                       AS completed,
    SUM(CASE WHEN c.passed = c.mandatory_total THEN 1 ELSE 0 END)                AS fully_certified,
    SUM(CASE WHEN c.passed > 0 AND c.passed < c.mandatory_total THEN 1 ELSE 0 END) AS partly_certified,
    SUM(CASE WHEN c.passed = 0 AND c.pairs_attempted > 0 THEN 1 ELSE 0 END)     AS attempted_none_passed,
    SUM(CASE WHEN c.pairs_attempted = 0 THEN 1 ELSE 0 END)                      AS not_attempted,
    ISNULL(SUM(c.pairs_attempted), 0)                                           AS mandatory_pairs_attempted,
    ISNULL(SUM(c.mandatory_total - c.pairs_attempted), 0)                       AS mandatory_pairs_not_attempted,
    SUM(CASE WHEN c.latest_decision = 'Approved' THEN 1 ELSE 0 END)             AS approved,
    SUM(CASE WHEN c.latest_decision = 'Deferred' THEN 1 ELSE 0 END)             AS deferred,
    SUM(CASE WHEN c.enrolment_id IS NOT NULL AND c.latest_decision IS NULL THEN 1 ELSE 0 END) AS not_reviewed
FROM rpt.dim_cohort AS co
LEFT JOIN cases AS ca ON ca.cohort_id = co.cohort_id
LEFT JOIN completed AS c ON c.cohort_id = co.cohort_id
GROUP BY co.cohort_id, ca.cases, ca.actioned
ORDER BY co.cohort_id;

/* 10. "As of any date": the TIME-AWARE pattern.
       is_open_at_snapshot and is_latest_review describe the snapshot only.
       For another date (on or before the snapshot), filter by BOTH the
       effective date and the recorded date, then pick the latest row. */
DECLARE @as_of DATE = '2026-10-20';   -- <== try other dates up to 2026-11-02 (e.g. 2026-06-15)
DECLARE @as_of_end DATETIME2(0) = DATEADD(MINUTE, 23 * 60 + 59, CAST(@as_of AS DATETIME2(0)));

-- 10a. Cases open on @as_of: opened (and entered) by then, not closed (and entered) by then
SELECT c.cohort_id, COUNT(DISTINCT c.enrolment_id) AS open_watchlist_enrolments_on_date
FROM rpt.fact_watchlist_case AS c
WHERE c.opened_effective_date <= @as_of AND c.opened_recorded_at <= @as_of_end
  AND NOT EXISTS (SELECT 1 FROM rpt.fact_watchlist_event AS ev
                  WHERE ev.watchlist_case_id = c.watchlist_case_id AND ev.event_type = 'Closed'
                    AND ev.effective_date <= @as_of AND ev.recorded_at <= @as_of_end)
GROUP BY c.cohort_id;

-- 10b. Readiness decision in force on @as_of: the latest review entered by then
WITH known AS (
    SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.enrolment_id ORDER BY r.review_number DESC) AS rn
    FROM rpt.fact_readiness_review AS r
    WHERE r.review_date <= @as_of AND r.recorded_at <= @as_of_end
)
SELECT cohort_id, decision, COUNT(*) AS enrolments
FROM known WHERE rn = 1
GROUP BY cohort_id, decision
ORDER BY cohort_id, decision;
