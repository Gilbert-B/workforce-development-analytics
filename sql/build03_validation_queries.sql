/* ---------------------------------------------------------------------------
   build03_validation_queries.sql
   Essential Build 03 checks: one row per check; 'error' rows must be 0.
       python python/load_build03_to_sql.py --server localhost --validate-only
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
WITH latest_review AS (
    SELECT enrolment_id, decision,
           ROW_NUMBER() OVER (PARTITION BY enrolment_id ORDER BY review_number DESC) AS rn
    FROM core.readiness_review
), last_run AS (
    SELECT TOP (1) * FROM etl.load_run WHERE status = 'succeeded' ORDER BY run_id DESC
), checks AS (
    -- deployment and agents
    SELECT 'deployment_without_latest_approval' AS check_name, 'error' AS severity,
           (SELECT COUNT(*) FROM core.deployment AS d
            LEFT JOIN latest_review AS l ON l.enrolment_id = d.enrolment_id AND l.rn = 1
            WHERE ISNULL(l.decision, '') <> 'Approved') AS failing_rows
    UNION ALL
    SELECT 'deployment_before_approval_recorded', 'error',
           (SELECT COUNT(*) FROM core.deployment AS d JOIN core.readiness_review AS r
              ON r.readiness_review_id = d.readiness_review_id
            WHERE d.deployment_date <= CAST(r.recorded_at AS DATE))
    UNION ALL
    SELECT 'graduate_agent_without_deployment', 'error',
           (SELECT COUNT(*) FROM core.ops_agent AS a WHERE a.agent_type = 'Graduate'
              AND NOT EXISTS (SELECT 1 FROM core.deployment AS d WHERE d.agent_id = a.agent_id))
    UNION ALL
    SELECT 'more_than_one_agent_per_employee', 'error',
           (SELECT COUNT(*) FROM (SELECT employee_id FROM core.ops_agent GROUP BY employee_id HAVING COUNT(*) > 1) AS x)
    UNION ALL
    SELECT 'work_outside_employment_period', 'error',          -- no assignments before start or after exit
           (SELECT COUNT(*) FROM core.case_assignment AS ca JOIN core.ops_agent AS a ON a.agent_id = ca.agent_id
            WHERE CAST(ca.assigned_at AS DATE) < a.start_date OR CAST(ca.assigned_at AS DATE) >= a.exit_date)
    -- case chronology and history
    UNION ALL
    SELECT 'event_before_case_received', 'error',
           (SELECT COUNT(*) FROM core.case_event AS e JOIN core.payment_case AS c ON c.case_id = e.case_id
            WHERE e.event_at < c.received_at)
    UNION ALL
    SELECT 'events_out_of_sequence', 'error',
           (SELECT COUNT(*) FROM core.case_event AS a JOIN core.case_event AS b
              ON b.case_id = a.case_id AND b.event_seq = a.event_seq + 1 WHERE b.event_at < a.event_at)
    UNION ALL
    SELECT 'resolved_case_missing_resolution_event', 'error',
           (SELECT COUNT(*) FROM core.payment_case AS c WHERE c.first_resolved_at IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM core.case_event AS e WHERE e.case_id = c.case_id
                              AND e.event_type = 'resolved' AND e.event_at = c.first_resolved_at))
    UNION ALL
    SELECT 'rework_without_reopen_event', 'error',             -- history is added, never overwritten
           (SELECT COUNT(*) FROM core.case_rework AS r
            WHERE NOT EXISTS (SELECT 1 FROM core.case_event AS e WHERE e.case_id = r.case_id
                              AND e.event_type = 'reopened' AND e.event_at = r.rework_at))
    UNION ALL
    SELECT 'sla_target_differs_from_policy', 'error',
           (SELECT COUNT(*) FROM core.payment_case AS c JOIN core.sla_policy AS p
              ON p.policy_version = c.sla_policy_version AND p.case_type_code = c.case_type_code AND p.priority = c.priority
            WHERE p.target_hours <> c.sla_target_hours)
    -- QA
    UNION ALL
    SELECT 'qa_review_before_first_resolution', 'error',
           (SELECT COUNT(*) FROM core.qa_review AS q JOIN core.payment_case AS c ON c.case_id = q.case_id
            WHERE q.reviewed_at < c.first_resolved_at)
    UNION ALL
    SELECT 'qa_not_six_items_or_weights_not_100', 'error',
           (SELECT COUNT(*) FROM (SELECT case_id FROM core.qa_check GROUP BY case_id
                                  HAVING COUNT(*) <> 6 OR SUM(weight) <> 100) AS x)
    UNION ALL
    SELECT 'qa_score_differs_from_passed_weights', 'error',
           (SELECT COUNT(*) FROM core.qa_review AS q
            WHERE q.score <> (SELECT SUM(CASE WHEN k.passed = 1 THEN k.weight ELSE 0 END)
                              FROM core.qa_check AS k WHERE k.case_id = q.case_id))
    UNION ALL
    SELECT 'qa_pass_flag_inconsistent', 'error',               -- every pass scores above every fail
           CASE WHEN (SELECT MIN(score) FROM core.qa_review WHERE passed = 1)
                   > (SELECT MAX(score) FROM core.qa_review WHERE passed = 0) THEN 0 ELSE 1 END
    -- ETL reconciliation
    UNION ALL
    SELECT 'etl_run_counts_do_not_add_up', 'error',             -- every document read is loaded or rejected
           (SELECT COUNT(*) FROM etl.load_run WHERE docs_read <> docs_loaded + docs_rejected)
    UNION ALL
    SELECT 'rejected_without_reason', 'error',
           (SELECT COUNT(*) FROM stg.rejected_record WHERE LEN(reason) = 0)
    UNION ALL
    SELECT 'event_numbering_has_gaps', 'error',               -- each case's history is 1..n (replaced as a whole)
           (SELECT COUNT(*) FROM (SELECT case_id FROM core.case_event GROUP BY case_id
                                  HAVING MAX(event_seq) <> COUNT(*)) AS x)
    -- information
    UNION ALL SELECT 'info_cases_loaded', 'info', (SELECT COUNT(*) FROM core.payment_case)
    UNION ALL SELECT 'info_documents_rejected', 'info', (SELECT COUNT(DISTINCT case_id) FROM stg.rejected_record)
    UNION ALL SELECT 'info_cases_open_at_snapshot', 'info', (SELECT SUM(is_open) FROM rpt.fact_payment_case)
    UNION ALL SELECT 'info_open_cases_overdue', 'info', (SELECT SUM(is_overdue_open) FROM rpt.fact_payment_case)
    UNION ALL SELECT 'info_agents', 'info', (SELECT COUNT(*) FROM core.ops_agent)
    UNION ALL SELECT 'info_agents_exited', 'info', (SELECT COUNT(*) FROM core.ops_agent WHERE exit_date IS NOT NULL)
    UNION ALL SELECT 'info_etl_runs', 'info', (SELECT COUNT(*) FROM etl.load_run)
)
SELECT check_name, severity, failing_rows,
       CASE WHEN severity = 'info' THEN 'INFO' WHEN failing_rows = 0 THEN 'PASS' ELSE 'FAIL' END AS result
FROM checks
ORDER BY CASE severity WHEN 'error' THEN 0 ELSE 1 END, check_name;
