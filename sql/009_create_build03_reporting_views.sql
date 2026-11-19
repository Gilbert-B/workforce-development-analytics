/* ---------------------------------------------------------------------------
   009_create_build03_reporting_views.sql
   Build 03 reporting views for Report 02 (and Report 03's 30/60/90-day work).
   "Now" for open / overdue cases = core.data_snapshot.as_of_date, end of day.
   Re-runnable.
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
GO

/* ===== dim_agent: one row per agent ===== */
CREATE OR ALTER VIEW rpt.dim_agent AS
SELECT
    a.agent_id, a.employee_id, a.enrolment_id, a.agent_type,
    CONCAT(a.first_name, N' ', a.last_name) AS agent_name,
    a.team_id, t.team_name, a.primary_queue_id, q.queue_name AS primary_queue_name,
    e.cohort_id,                                    -- NULL for tenured agents
    a.start_date, a.exit_date, a.exit_reason,
    CASE WHEN a.exit_date IS NULL OR a.exit_date > s.as_of_date THEN 1 ELSE 0 END AS is_active_at_snapshot,
    d.deployment_date, d.readiness_review_id
FROM core.ops_agent AS a
JOIN core.ops_team AS t ON t.team_id = a.team_id
JOIN core.ops_queue AS q ON q.queue_id = a.primary_queue_id
CROSS JOIN core.data_snapshot AS s
LEFT JOIN core.enrolment AS e ON e.enrolment_id = a.enrolment_id
LEFT JOIN core.deployment AS d ON d.agent_id = a.agent_id;
GO

/* ===== dim_ops_queue: one row per queue (with its team and case type) ===== */
CREATE OR ALTER VIEW rpt.dim_ops_queue AS
SELECT q.queue_id, q.queue_name, q.team_id, t.team_name, q.case_type_code, ct.case_type_name
FROM core.ops_queue AS q
JOIN core.ops_team AS t ON t.team_id = q.team_id
JOIN core.case_type AS ct ON ct.case_type_code = q.case_type_code;
GO

/* ===== fact_payment_case: one row per case ===== */
-- agent_id = the agent who made the latest resolution (or, if unresolved, the
-- latest assignee). SLA = FINAL resolution vs the ORIGINAL target, no pauses.
-- Unresolved cases have sla_met NULL and are judged by is_overdue_open instead.
CREATE OR ALTER VIEW rpt.fact_payment_case AS
WITH snap AS (
    SELECT DATEADD(MINUTE, 23 * 60 + 59, CAST(as_of_date AS DATETIME2(0))) AS now_at FROM core.data_snapshot
), c AS (
    SELECT pc.*,
           DATEADD(HOUR, pc.sla_target_hours, pc.received_at) AS due_at,
           COALESCE(
               (SELECT TOP (1) ev.agent_id FROM core.case_event AS ev
                WHERE ev.case_id = pc.case_id AND ev.event_type = 'resolved' ORDER BY ev.event_seq DESC),
               (SELECT TOP (1) ca.agent_id FROM core.case_assignment AS ca
                WHERE ca.case_id = pc.case_id ORDER BY ca.assignment_seq DESC)) AS agent_id,
           (SELECT COUNT(*) FROM core.case_rework AS r WHERE r.case_id = pc.case_id) AS rework_count
    FROM core.payment_case AS pc
)
SELECT
    c.case_id, c.agent_id, c.queue_id, c.case_type_code, c.priority, c.channel, c.amount_band,
    c.received_at, CAST(c.received_at AS DATE) AS received_date,
    c.status, c.resolution_code, c.first_resolved_at, c.final_resolved_at,
    CAST(c.final_resolved_at AS DATE) AS final_resolved_date,
    c.sla_target_hours, c.due_at,
    CAST(DATEDIFF(MINUTE, c.received_at, c.first_resolved_at) / 60.0 AS DECIMAL(9,2)) AS first_resolution_hours,
    CAST(DATEDIFF(MINUTE, c.received_at, c.final_resolved_at) / 60.0 AS DECIMAL(9,2)) AS final_resolution_hours,
    CASE WHEN c.final_resolved_at IS NULL THEN NULL
         WHEN c.final_resolved_at <= c.due_at THEN 1 ELSE 0 END AS sla_met,
    CASE WHEN c.final_resolved_at IS NULL THEN 1 ELSE 0 END AS is_open,
    CASE WHEN c.final_resolved_at IS NULL AND snap.now_at > c.due_at THEN 1 ELSE 0 END AS is_overdue_open,
    c.rework_count,
    CASE WHEN c.rework_count > 0 THEN 1 ELSE 0 END AS has_rework,
    CASE WHEN c.final_resolved_at IS NOT NULL AND c.rework_count = 0 THEN 1 ELSE 0 END AS first_time_right,
    CASE WHEN qa.case_id IS NULL THEN 0 ELSE 1 END AS qa_sampled,
    CAST(qa.passed AS INT) AS qa_passed,                         -- NULL = not sampled (not "failed")
    DATEDIFF(DAY, a.start_date, CAST(c.received_at AS DATE)) AS days_since_agent_start,
    CASE WHEN a.agent_type = 'Tenured' THEN 'Tenured'
         WHEN DATEDIFF(DAY, a.start_date, CAST(c.received_at AS DATE)) < 30 THEN '0-30 days'
         WHEN DATEDIFF(DAY, a.start_date, CAST(c.received_at AS DATE)) < 60 THEN '31-60 days'
         WHEN DATEDIFF(DAY, a.start_date, CAST(c.received_at AS DATE)) < 90 THEN '61-90 days'
         ELSE '90+ days' END AS tenure_band,
    CASE WHEN a.agent_type = 'Tenured' THEN 5                    -- sort order for tenure_band in Power BI
         WHEN DATEDIFF(DAY, a.start_date, CAST(c.received_at AS DATE)) < 30 THEN 1
         WHEN DATEDIFF(DAY, a.start_date, CAST(c.received_at AS DATE)) < 60 THEN 2
         WHEN DATEDIFF(DAY, a.start_date, CAST(c.received_at AS DATE)) < 90 THEN 3
         ELSE 4 END AS tenure_band_order
FROM c
CROSS JOIN snap
JOIN core.ops_agent AS a ON a.agent_id = c.agent_id
LEFT JOIN core.qa_review AS qa ON qa.case_id = c.case_id;
GO

/* ===== fact_case_event: one row per status event (full history) ===== */
CREATE OR ALTER VIEW rpt.fact_case_event AS
SELECT ev.case_id, ev.event_seq, ev.event_type, ev.event_at, CAST(ev.event_at AS DATE) AS event_date, ev.agent_id
FROM core.case_event AS ev;
GO

/* ===== fact_qa_review: one row per SAMPLED case review ===== */
CREATE OR ALTER VIEW rpt.fact_qa_review AS
SELECT
    qa.case_id, f.agent_id, f.queue_id, f.case_type_code, f.tenure_band, f.tenure_band_order,
    qa.reviewed_at, CAST(qa.reviewed_at AS DATE) AS reviewed_date,
    qa.score, CAST(qa.passed AS INT) AS passed,
    (SELECT COUNT(*) FROM core.qa_error AS e WHERE e.case_id = qa.case_id) AS error_count,
    CASE WHEN EXISTS (SELECT 1 FROM core.qa_error AS e WHERE e.case_id = qa.case_id AND e.severity = 'critical')
         THEN 1 ELSE 0 END AS has_critical_error
FROM core.qa_review AS qa
JOIN rpt.fact_payment_case AS f ON f.case_id = qa.case_id;
GO

/* ===== fact_agent_day: one row per agent x day WORKED =====
   Days = the agent's scheduled weekdays (start .. day before exit, up to the
   snapshot) PLUS any other day with recorded activity (weekend cover: case
   resolution runs on the clock, so some cases are resolved on a Saturday or
   Sunday). An exit never produces artificial zero-performance days.
   Built straight from the core tables in one pass: stacking it on
   fact_payment_case / fact_qa_review made SQL Server re-evaluate those views
   and the query took minutes. Credited agent = same rule as fact_payment_case. */
CREATE OR ALTER VIEW rpt.fact_agent_day AS
WITH last_res AS (          -- latest 'resolved' event per case: the final resolution and its agent
    SELECT case_id, agent_id, CAST(event_at AS DATE) AS resolved_date,
           ROW_NUMBER() OVER (PARTITION BY case_id ORDER BY event_seq DESC) AS rn
    FROM core.case_event WHERE event_type = 'resolved'
), last_asg AS (
    SELECT case_id, agent_id, ROW_NUMBER() OVER (PARTITION BY case_id ORDER BY assignment_seq DESC) AS rn
    FROM core.case_assignment
), credited AS (
    SELECT pc.case_id, CAST(pc.received_at AS DATE) AS received_date,
           CASE WHEN pc.final_resolved_at IS NOT NULL THEN r.resolved_date END AS resolved_date,
           COALESCE(r.agent_id, a.agent_id) AS agent_id,
           CASE WHEN pc.final_resolved_at <= DATEADD(HOUR, pc.sla_target_hours, pc.received_at) THEN 1 ELSE 0 END AS sla_met,
           DATEDIFF(MINUTE, pc.received_at, pc.final_resolved_at) / 60.0 AS resolution_hours
    FROM core.payment_case AS pc
    LEFT JOIN last_res AS r ON r.case_id = pc.case_id AND r.rn = 1
    LEFT JOIN last_asg AS a ON a.case_id = pc.case_id AND a.rn = 1
), received AS (
    SELECT agent_id, received_date AS work_date, COUNT(*) AS cases_received
    FROM credited GROUP BY agent_id, received_date
), resolved AS (
    SELECT agent_id, resolved_date AS work_date, COUNT(*) AS cases_resolved, SUM(sla_met) AS cases_sla_met,
           CAST(AVG(resolution_hours) AS DECIMAL(9,2)) AS avg_resolution_hours
    FROM credited WHERE resolved_date IS NOT NULL GROUP BY agent_id, resolved_date
), qa AS (
    SELECT c.agent_id, CAST(q.reviewed_at AS DATE) AS work_date, COUNT(*) AS qa_reviews,
           SUM(CAST(q.passed AS INT)) AS qa_passed, AVG(CAST(q.score AS DECIMAL(6,2))) AS qa_avg_score
    FROM core.qa_review AS q JOIN credited AS c ON c.case_id = q.case_id
    GROUP BY c.agent_id, CAST(q.reviewed_at AS DATE)
), scheduled AS (
    SELECT a.agent_id, d.[date] AS work_date
    FROM core.ops_agent AS a
    CROSS JOIN core.data_snapshot AS s
    JOIN rpt.dim_date AS d
      ON d.is_weekday = 1
     AND d.[date] >= a.start_date
     AND d.[date] <= s.as_of_date
     AND (a.exit_date IS NULL OR d.[date] < a.exit_date)
    WHERE d.[date] >= (SELECT MIN(CAST(received_at AS DATE)) FROM core.payment_case)
), days AS (
    SELECT agent_id, work_date FROM scheduled
    UNION SELECT agent_id, work_date FROM received
    UNION SELECT agent_id, work_date FROM resolved
)
SELECT
    d.agent_id, d.work_date,
    CASE WHEN sc.agent_id IS NULL THEN 0 ELSE 1 END AS is_scheduled_day,  -- 0 = extra day worked (weekend cover)
    CASE WHEN ag.agent_type = 'Tenured' THEN NULL ELSE DATEDIFF(DAY, ag.start_date, d.work_date) END AS days_since_start,
    ISNULL(r.cases_received, 0) AS cases_received,
    ISNULL(v.cases_resolved, 0) AS cases_resolved,
    ISNULL(v.cases_sla_met, 0) AS cases_sla_met,
    v.avg_resolution_hours,                                     -- NULL on days with no resolution
    ISNULL(q.qa_reviews, 0) AS qa_reviews,
    ISNULL(q.qa_passed, 0) AS qa_passed,
    q.qa_avg_score                                              -- NULL on days with no QA review
FROM days AS d
JOIN core.ops_agent AS ag ON ag.agent_id = d.agent_id
LEFT JOIN scheduled AS sc ON sc.agent_id = d.agent_id AND sc.work_date = d.work_date
LEFT JOIN received AS r ON r.agent_id = d.agent_id AND r.work_date = d.work_date
LEFT JOIN resolved AS v ON v.agent_id = d.agent_id AND v.work_date = d.work_date
LEFT JOIN qa AS q ON q.agent_id = d.agent_id AND q.work_date = d.work_date;
GO
PRINT 'Build 03 reporting views created.';
GO
