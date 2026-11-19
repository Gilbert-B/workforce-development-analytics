/* ---------------------------------------------------------------------------
   build04_validation_queries.sql
   Essential Build 04 checks (outcome windows, retention, proficiency).
   One row per check; 'error' rows must be 0. Run by python/build_all.py.
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
WITH snap AS (SELECT as_of_date FROM core.data_snapshot),
checks AS (
    SELECT 'graduates_differ_from_graduate_agents' AS check_name, 'error' AS severity,
           ABS((SELECT COUNT(*) FROM rpt.dim_graduate)
             - (SELECT COUNT(*) FROM core.ops_agent WHERE agent_type = 'Graduate')) AS failing_rows
    UNION ALL
    SELECT 'not_three_windows_per_graduate', 'error',
           (SELECT COUNT(*) FROM (SELECT agent_id FROM rpt.fact_outcome_window GROUP BY agent_id
                                  HAVING COUNT(*) <> 3 OR COUNT(DISTINCT window_order) <> 3) AS x)
    UNION ALL
    SELECT 'metrics_on_incomplete_window', 'error',            -- not measured = NULL, never zero
           (SELECT COUNT(*) FROM rpt.fact_outcome_window
            WHERE is_complete = 0 AND (cases_received IS NOT NULL OR sla_met_pct IS NOT NULL OR is_proficient IS NOT NULL))
    UNION ALL
    SELECT 'complete_window_not_yet_ended', 'error',
           (SELECT COUNT(*) FROM rpt.fact_outcome_window CROSS JOIN snap
            WHERE is_complete = 1 AND window_end > DATEADD(DAY, 1, snap.as_of_date))
    UNION ALL
    SELECT 'complete_window_after_exit', 'error',
           (SELECT COUNT(*) FROM rpt.fact_outcome_window AS w JOIN core.ops_agent AS a ON a.agent_id = w.agent_id
            WHERE w.is_complete = 1 AND a.exit_date < w.window_end)
    UNION ALL
    SELECT 'window_cases_differ_from_case_fact', 'error',      -- complete windows hold exactly the agent's cases
           (SELECT COUNT(*) FROM rpt.fact_outcome_window AS w
            WHERE w.is_complete = 1 AND w.cases_received <>
                  (SELECT COUNT(*) FROM rpt.fact_payment_case AS f WHERE f.agent_id = w.agent_id
                     AND f.received_date >= w.window_start AND f.received_date < w.window_end))
    UNION ALL
    SELECT 'retention_flag_inconsistent', 'error',
           (SELECT COUNT(*) FROM rpt.dim_graduate CROSS JOIN snap
            WHERE (retained_90_days = 1 AND exit_date < day_90_date)
               OR (retained_90_days = 0 AND (exit_date IS NULL OR exit_date >= day_90_date))
               OR (retained_90_days IS NULL AND day_90_date <= snap.as_of_date))
    UNION ALL
    SELECT 'proficiency_flag_differs_from_standard', 'error',  -- SLA >= 80% and first-time-right >= 97%
           (SELECT COUNT(*) FROM rpt.fact_outcome_window
            WHERE is_complete = 1 AND is_proficient <>
                  CASE WHEN sla_met_pct >= 80 AND first_time_right_pct >= 97 THEN 1 ELSE 0 END)
    UNION ALL
    SELECT 'days_to_proficiency_inconsistent', 'error',
           (SELECT COUNT(*) FROM rpt.dim_graduate AS g
            WHERE g.days_to_proficiency IS NOT NULL AND g.days_to_proficiency <> 30 *
                  (SELECT MIN(window_order) FROM rpt.fact_outcome_window AS w
                   WHERE w.agent_id = g.agent_id AND w.is_proficient = 1))
    UNION ALL
    SELECT 'graduate_without_training_record', 'error',
           (SELECT COUNT(*) FROM rpt.dim_graduate WHERE final_competency_score IS NULL OR readiness_reviews IS NULL)
    -- information
    UNION ALL SELECT 'info_graduates', 'info', (SELECT COUNT(*) FROM rpt.dim_graduate)
    UNION ALL SELECT 'info_retained_90_days', 'info', (SELECT SUM(retained_90_days) FROM rpt.dim_graduate)
    UNION ALL SELECT 'info_proficient_by_day_90', 'info', (SELECT COUNT(*) FROM rpt.dim_graduate WHERE days_to_proficiency IS NOT NULL)
    UNION ALL SELECT 'info_complete_windows', 'info', (SELECT SUM(is_complete) FROM rpt.fact_outcome_window)
)
SELECT check_name, severity, failing_rows,
       CASE WHEN severity = 'info' THEN 'INFO' WHEN failing_rows = 0 THEN 'PASS' ELSE 'FAIL' END AS result
FROM checks
ORDER BY CASE severity WHEN 'error' THEN 0 ELSE 1 END, check_name;
