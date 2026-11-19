/* ---------------------------------------------------------------------------
   011_create_build04_outcome_views.sql
   Build 04: workforce outcomes and training effectiveness (Report 03).

   Joins what each graduate did IN TRAINING (Builds 01-02) to how they
   performed in their first 30 / 60 / 90 days IN OPERATIONS (Build 03).
   No new source data: these are views over the existing core tables.

     rpt.dim_graduate         one row per deployed graduate agent: training
                              record, deployment, retention, proficiency
     rpt.fact_outcome_window  one row per graduate x window (days 1-30,
                              31-60, 61-90 after starting in operations)

   Honest-window rules (Build 03 spec, amendment 8):
     - A window counts only if it ENDED by the snapshot and the graduate was
       still employed at its end. Otherwise it is 'Not yet reached' or
       'Left before window end' and its metrics are NULL, never zero.
     - Retention uses observed employment periods only.
   Proficiency standard (documented in docs/decisions.md, D46): a complete
   window with SLA met >= 80% AND first-time-right >= 97%, i.e. roughly the
   tenured agents' level (84% / 98%) less a small tolerance.
   Re-runnable. Needs Builds 01-03 loaded.
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
GO

/* ===== training record per enrolment (graduates only) ===== */
CREATE OR ALTER VIEW rpt.graduate_training_record AS
WITH weekly AS (            -- average score per week where all competencies were assessed
    SELECT enrolment_id, programme_week, AVG(CAST(score AS DECIMAL(6,2))) AS week_score,
           COUNT(DISTINCT competency_id) AS competencies
    FROM core.assessment GROUP BY enrolment_id, programme_week
), final_week AS (
    SELECT enrolment_id, week_score,
           ROW_NUMBER() OVER (PARTITION BY enrolment_id ORDER BY programme_week DESC) AS rn
    FROM weekly WHERE competencies = (SELECT COUNT(*) FROM core.competency)
), attendance AS (
    SELECT enrolment_id,
           SUM(CASE WHEN attendance_status = 'Present' THEN 1 ELSE 0 END) AS present,
           SUM(CASE WHEN attendance_status IN ('Present', 'Absent') THEN 1 ELSE 0 END) AS recorded
    FROM core.attendance GROUP BY enrolment_id
), first_pass AS (          -- mandatory certifications passed at the FIRST attempt
    SELECT a.enrolment_id, COUNT(DISTINCT a.certification_id) AS passed_first
    FROM core.certification_attempt AS a
    JOIN core.certification_type AS t ON t.certification_id = a.certification_id AND t.mandatory_for_readiness = 1
    WHERE a.attempt_number = 1 AND a.result = 'Passed'
    GROUP BY a.enrolment_id
), watch AS (
    SELECT w.enrolment_id, COUNT(*) AS watchlist_cases,
           (SELECT COUNT(*) FROM core.coaching_action AS c
            JOIN core.watchlist_case AS w2 ON w2.watchlist_case_id = c.watchlist_case_id
            WHERE w2.enrolment_id = w.enrolment_id) AS coaching_actions
    FROM core.watchlist_case AS w GROUP BY w.enrolment_id
), reviews AS (
    SELECT enrolment_id, COUNT(*) AS readiness_reviews FROM core.readiness_review GROUP BY enrolment_id
)
SELECT
    d.enrolment_id,
    f.week_score AS final_competency_score,
    CAST(100.0 * at.present / NULLIF(at.recorded, 0) AS DECIMAL(5,1)) AS attendance_rate_pct,
    CASE WHEN ISNULL(fp.passed_first, 0) = (SELECT COUNT(*) FROM core.certification_type WHERE mandatory_for_readiness = 1)
         THEN 'Yes' ELSE 'No' END AS certified_first_attempt,
    ISNULL(w.watchlist_cases, 0) AS watchlist_cases,
    CASE WHEN w.watchlist_cases > 0 THEN 'Yes' ELSE 'No' END AS watchlisted_in_training,
    ISNULL(w.coaching_actions, 0) AS coaching_actions,
    r.readiness_reviews,
    CASE WHEN r.readiness_reviews = 1 THEN 'Yes' ELSE 'No' END AS approved_at_first_review
FROM core.deployment AS d
LEFT JOIN final_week AS f ON f.enrolment_id = d.enrolment_id AND f.rn = 1
LEFT JOIN attendance AS at ON at.enrolment_id = d.enrolment_id
LEFT JOIN first_pass AS fp ON fp.enrolment_id = d.enrolment_id
LEFT JOIN watch AS w ON w.enrolment_id = d.enrolment_id
LEFT JOIN reviews AS r ON r.enrolment_id = d.enrolment_id;
GO

/* ===== fact_outcome_window: graduate x window ===== */
CREATE OR ALTER VIEW rpt.fact_outcome_window AS
WITH windows AS (
    SELECT * FROM (VALUES (1, 'Days 1-30', 0, 30), (2, 'Days 31-60', 30, 60), (3, 'Days 61-90', 60, 90))
        AS v(window_order, window_label, from_day, to_day)
), gw AS (
    SELECT a.agent_id, w.window_order, w.window_label, w.from_day, w.to_day,
           DATEADD(DAY, w.from_day, a.start_date) AS window_start,
           DATEADD(DAY, w.to_day, a.start_date) AS window_end,             -- exclusive
           CASE WHEN a.exit_date IS NOT NULL AND a.exit_date < DATEADD(DAY, w.to_day, a.start_date)
                     AND a.exit_date <= s.as_of_date THEN 'Left before window end'
                WHEN DATEADD(DAY, w.to_day, a.start_date) > DATEADD(DAY, 1, s.as_of_date) THEN 'Not yet reached'
                ELSE 'Complete' END AS window_status
    FROM core.ops_agent AS a CROSS JOIN windows AS w CROSS JOIN core.data_snapshot AS s
    WHERE a.agent_type = 'Graduate'
), cases AS (
    SELECT g.agent_id, g.window_order,
           COUNT(*) AS cases_received,
           SUM(1 - f.is_open) AS cases_resolved,
           SUM(ISNULL(f.sla_met, 0)) AS sla_met_cases,
           SUM(f.first_time_right) AS first_time_right_cases,
           SUM(f.qa_sampled) AS qa_reviews,
           SUM(ISNULL(f.qa_passed, 0)) AS qa_passed,
           AVG(f.final_resolution_hours) AS avg_resolution_hours
    FROM gw AS g
    JOIN rpt.fact_payment_case AS f
      ON f.agent_id = g.agent_id AND f.received_date >= g.window_start AND f.received_date < g.window_end
    GROUP BY g.agent_id, g.window_order
), days AS (
    SELECT g.agent_id, g.window_order, COUNT(*) AS agent_days, SUM(d.cases_resolved) AS resolved_on_days
    FROM gw AS g
    JOIN rpt.fact_agent_day AS d
      ON d.agent_id = g.agent_id AND d.work_date >= g.window_start AND d.work_date < g.window_end
    GROUP BY g.agent_id, g.window_order
), joined AS (
    SELECT g.*, CASE WHEN g.window_status = 'Complete' THEN 1 ELSE 0 END AS is_complete,
           c.cases_received, c.cases_resolved, c.sla_met_cases, c.first_time_right_cases,
           c.qa_reviews, c.qa_passed, c.avg_resolution_hours, d.agent_days, d.resolved_on_days,
           -- rounded once here, so the proficiency flag uses exactly the values people see
           CAST(100.0 * c.sla_met_cases / NULLIF(c.cases_resolved, 0) AS DECIMAL(5,1)) AS sla_pct,
           CAST(100.0 * c.first_time_right_cases / NULLIF(c.cases_resolved, 0) AS DECIMAL(5,1)) AS ftr_pct
    FROM gw AS g
    LEFT JOIN cases AS c ON c.agent_id = g.agent_id AND c.window_order = g.window_order
    LEFT JOIN days AS d ON d.agent_id = g.agent_id AND d.window_order = g.window_order
)
SELECT
    agent_id, window_order, window_label, window_start, window_end, window_status, is_complete,
    -- metrics only for complete windows (NULL = not measured, never zero)
    CASE WHEN is_complete = 1 THEN ISNULL(cases_received, 0) END AS cases_received,
    CASE WHEN is_complete = 1 THEN ISNULL(cases_resolved, 0) END AS cases_resolved,
    CASE WHEN is_complete = 1 THEN ISNULL(sla_met_cases, 0) END AS sla_met_cases,
    CASE WHEN is_complete = 1 THEN ISNULL(first_time_right_cases, 0) END AS first_time_right_cases,
    CASE WHEN is_complete = 1 THEN ISNULL(qa_reviews, 0) END AS qa_reviews,
    CASE WHEN is_complete = 1 THEN ISNULL(qa_passed, 0) END AS qa_passed,
    CASE WHEN is_complete = 1 THEN CAST(avg_resolution_hours AS DECIMAL(9,2)) END AS avg_resolution_hours,
    CASE WHEN is_complete = 1 THEN ISNULL(agent_days, 0) END AS agent_days,
    CASE WHEN is_complete = 1 THEN ISNULL(resolved_on_days, 0) END AS resolved_on_agent_days,
    CASE WHEN is_complete = 1 THEN sla_pct END AS sla_met_pct,
    CASE WHEN is_complete = 1 THEN ftr_pct END AS first_time_right_pct,
    CASE WHEN is_complete = 0 THEN NULL
         WHEN sla_pct >= 80 AND ftr_pct >= 97 THEN 1 ELSE 0 END AS is_proficient
FROM joined;
GO

/* ===== dim_graduate: one row per deployed graduate agent ===== */
CREATE OR ALTER VIEW rpt.dim_graduate AS
WITH prof AS (
    SELECT agent_id,
           MIN(CASE WHEN is_proficient = 1 THEN window_order END) AS first_proficient_window,
           MAX(CASE WHEN is_complete = 1 THEN window_order ELSE 0 END) AS last_complete_window,
           MAX(CASE WHEN window_status = 'Left before window end' THEN 1 ELSE 0 END) AS left_early
    FROM rpt.fact_outcome_window GROUP BY agent_id
), scored AS (
    SELECT t.*, NTILE(3) OVER (ORDER BY t.final_competency_score DESC, t.enrolment_id) AS competency_tercile
    FROM rpt.graduate_training_record AS t
)
SELECT
    a.agent_id, a.enrolment_id, a.employee_id,
    CONCAT(a.first_name, N' ', a.last_name) AS graduate_name,
    e.cohort_id, c.cohort_name,
    a.team_id, tm.team_name, a.primary_queue_id, q.queue_name AS primary_queue_name,
    d.approved_review_date, d.deployment_date, a.start_date,
    DATEDIFF(DAY, d.approved_review_date, d.deployment_date) AS days_approval_to_deployment,
    a.exit_date, a.exit_reason,
    -- training record
    t.final_competency_score,
    CASE t.competency_tercile WHEN 1 THEN 'Top third' WHEN 2 THEN 'Middle third' ELSE 'Bottom third' END AS competency_band,
    t.competency_tercile AS competency_band_order,
    t.attendance_rate_pct, t.certified_first_attempt, t.watchlist_cases, t.watchlisted_in_training,
    t.coaching_actions, t.readiness_reviews, t.approved_at_first_review,
    -- retention (observed only): NULL while day 90 has not been reached
    DATEADD(DAY, 90, a.start_date) AS day_90_date,
    CASE WHEN a.exit_date IS NOT NULL AND a.exit_date < DATEADD(DAY, 90, a.start_date) AND a.exit_date <= s.as_of_date THEN 0
         WHEN DATEADD(DAY, 90, a.start_date) > DATEADD(DAY, 1, s.as_of_date) THEN NULL
         ELSE 1 END AS retained_90_days,
    CASE WHEN a.exit_date IS NULL OR a.exit_date > s.as_of_date THEN 1 ELSE 0 END AS is_active_at_snapshot,
    -- time to proficiency
    CASE WHEN p.first_proficient_window = 1 THEN 'By day 30'
         WHEN p.first_proficient_window = 2 THEN 'By day 60'
         WHEN p.first_proficient_window = 3 THEN 'By day 90'
         WHEN p.left_early = 1 THEN 'Left before proficient'
         WHEN p.last_complete_window = 3 THEN 'Not yet by day 90'
         ELSE 'Too early to tell' END AS proficiency_status,
    CASE WHEN p.first_proficient_window IS NOT NULL THEN p.first_proficient_window
         WHEN p.left_early = 1 THEN 5 WHEN p.last_complete_window = 3 THEN 4 ELSE 6 END AS proficiency_status_order,
    CASE WHEN p.first_proficient_window IS NOT NULL THEN 30 * p.first_proficient_window END AS days_to_proficiency
FROM core.ops_agent AS a
CROSS JOIN core.data_snapshot AS s
JOIN core.deployment AS d ON d.agent_id = a.agent_id
JOIN core.enrolment AS e ON e.enrolment_id = a.enrolment_id
JOIN core.cohort AS c ON c.cohort_id = e.cohort_id
JOIN core.ops_team AS tm ON tm.team_id = a.team_id
JOIN core.ops_queue AS q ON q.queue_id = a.primary_queue_id
JOIN scored AS t ON t.enrolment_id = a.enrolment_id
JOIN prof AS p ON p.agent_id = a.agent_id
WHERE a.agent_type = 'Graduate';
GO
PRINT 'Build 04 outcome views created.';
GO
