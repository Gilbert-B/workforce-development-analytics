/* ---------------------------------------------------------------------------
   bi03_measure_reference.sql
   Reference values for the BI-03 (Report 02, Payment Operations) measures,
   computed INDEPENDENTLY from the core tables, NOT from the rpt view flags
   (sla_met, is_open, is_overdue_open, first_time_right, tenure_band...) that
   the DAX uses. If a view or a measure is wrong, the two will disagree.

   Output: one row per measure x slice ('ALL', each queue, each tenure band),
   with numerator, denominator and value.

   Run in SSMS against WorkforceDevAnalytics (horizon dataset + Build 03 loaded).
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
SET NOCOUNT ON;

DECLARE @snap DATE = (SELECT as_of_date FROM core.data_snapshot);
-- "now" for overdue = end of the snapshot day (same rule as the views)
DECLARE @now DATETIME2(0) = DATEADD(MINUTE, 23 * 60 + 59, CAST(@snap AS DATETIME2(0)));

WITH
-- the agent a case is credited to: the latest 'resolved' event, else the latest assignment
credited AS (
    SELECT pc.case_id,
           COALESCE(
               (SELECT TOP (1) ev.agent_id FROM core.case_event AS ev
                WHERE ev.case_id = pc.case_id AND ev.event_type = 'resolved' ORDER BY ev.event_at DESC, ev.event_seq DESC),
               (SELECT TOP (1) ca.agent_id FROM core.case_assignment AS ca
                WHERE ca.case_id = pc.case_id ORDER BY ca.assigned_at DESC, ca.assignment_seq DESC)) AS agent_id
    FROM core.payment_case AS pc
),
cases AS (
    SELECT pc.case_id, pc.queue_id,
           CASE WHEN a.agent_type = 'Tenured' THEN 'Tenured'
                WHEN DATEDIFF(DAY, a.start_date, CAST(pc.received_at AS DATE)) < 30 THEN '0-30 days'
                WHEN DATEDIFF(DAY, a.start_date, CAST(pc.received_at AS DATE)) < 60 THEN '31-60 days'
                WHEN DATEDIFF(DAY, a.start_date, CAST(pc.received_at AS DATE)) < 90 THEN '61-90 days'
                ELSE '90+ days' END AS band,
           CASE WHEN pc.final_resolved_at IS NOT NULL THEN 1 ELSE 0 END AS resolved,
           -- SLA: final resolution against the ORIGINAL target (target from the policy table)
           CASE WHEN pc.final_resolved_at IS NOT NULL
                 AND pc.final_resolved_at <= DATEADD(HOUR, p.target_hours, pc.received_at) THEN 1 ELSE 0 END AS met,
           CASE WHEN pc.final_resolved_at IS NULL AND @now > DATEADD(HOUR, p.target_hours, pc.received_at) THEN 1 ELSE 0 END AS overdue,
           CASE WHEN pc.final_resolved_at IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM core.case_event AS e WHERE e.case_id = pc.case_id AND e.event_type = 'reopened')
                THEN 1 ELSE 0 END AS ftr,
           DATEDIFF(MINUTE, pc.received_at, pc.final_resolved_at) / 60.0 AS hours,
           q.passed AS qa_passed, q.score AS qa_score,
           CASE WHEN EXISTS (SELECT 1 FROM core.qa_error AS x WHERE x.case_id = pc.case_id AND x.severity = 'critical')
                THEN 1 ELSE 0 END AS qa_critical
    FROM core.payment_case AS pc
    JOIN credited AS c ON c.case_id = pc.case_id
    JOIN core.ops_agent AS a ON a.agent_id = c.agent_id
    JOIN core.sla_policy AS p ON p.policy_version = pc.sla_policy_version
                             AND p.case_type_code = pc.case_type_code AND p.priority = pc.priority
    LEFT JOIN core.qa_review AS q ON q.case_id = pc.case_id
),
sliced AS (
    SELECT 'ALL' AS slice_type, 'ALL' AS slice, * FROM cases
    UNION ALL SELECT 'queue', queue_id, * FROM cases
    UNION ALL SELECT 'tenure_band', band, * FROM cases
),
agg AS (
    SELECT slice_type, slice,
           COUNT(*) AS received, SUM(resolved) AS resolved, SUM(1 - resolved) AS open_cases,
           SUM(overdue) AS overdue, SUM(met) AS met, SUM(ftr) AS ftr,
           AVG(hours) AS avg_hours,
           SUM(CASE WHEN qa_passed IS NOT NULL THEN 1 ELSE 0 END) AS qa_reviews,
           SUM(CAST(qa_passed AS INT)) AS qa_pass,
           AVG(CAST(qa_score AS DECIMAL(6,2))) AS qa_avg_score,
           SUM(CASE WHEN qa_passed IS NOT NULL THEN qa_critical ELSE 0 END) AS qa_critical
    FROM sliced GROUP BY slice_type, slice
)
SELECT slice_type, slice, measure, numerator, denominator,
       CAST(CASE WHEN denominator IS NULL THEN numerator
                 ELSE 100.0 * numerator / NULLIF(denominator, 0) END AS DECIMAL(10,1)) AS value
FROM agg
CROSS APPLY (VALUES
    ('Cases Received',              received,      NULL),
    ('Cases Resolved',              resolved,      NULL),
    ('Open Cases (Snapshot)',       open_cases,    NULL),
    ('Overdue Open Cases (Snapshot)', overdue,     NULL),
    ('SLA Met %',                   met,           resolved),
    ('First-Time-Right %',          ftr,           resolved),
    ('Avg Resolution Hours',        avg_hours,     NULL),
    ('QA Reviews',                  qa_reviews,    NULL),
    ('QA Sample Rate %',            qa_reviews,    resolved),
    ('QA Pass %',                   qa_pass,       qa_reviews),
    ('Avg QA Score',                qa_avg_score,  NULL),
    ('QA Critical Error %',         qa_critical,   qa_reviews)
) AS v(measure, numerator, denominator)
ORDER BY CASE slice_type WHEN 'ALL' THEN 0 WHEN 'queue' THEN 1 ELSE 2 END, slice, measure;

-- agents and productivity (agent grain / agent-day grain)
SELECT 'Active Agents (Snapshot)' AS measure,
       SUM(CASE WHEN exit_date IS NULL OR exit_date > @snap THEN 1 ELSE 0 END) AS value
FROM core.ops_agent
UNION ALL SELECT 'Graduate Agents (Snapshot)', SUM(CASE WHEN agent_type = 'Graduate' AND (exit_date IS NULL OR exit_date > @snap) THEN 1 ELSE 0 END) FROM core.ops_agent
UNION ALL SELECT 'Agents Exited', SUM(CASE WHEN exit_date <= @snap THEN 1 ELSE 0 END) FROM core.ops_agent;

-- productivity: resolved cases per agent-day worked (days = scheduled weekdays in
-- employment + any other day with activity; resolutions credited by final-resolution date)
WITH last_res AS (
    SELECT case_id, agent_id, CAST(event_at AS DATE) AS d,
           ROW_NUMBER() OVER (PARTITION BY case_id ORDER BY event_seq DESC) AS rn
    FROM core.case_event WHERE event_type = 'resolved'
), res AS (
    SELECT r.agent_id, r.d FROM core.payment_case AS pc
    JOIN last_res AS r ON r.case_id = pc.case_id AND r.rn = 1
    WHERE pc.final_resolved_at IS NOT NULL
), sched AS (
    SELECT a.agent_id, d.[date] AS d FROM core.ops_agent AS a
    JOIN rpt.dim_date AS d ON d.is_weekday = 1 AND d.[date] >= a.start_date AND d.[date] <= @snap
                          AND (a.exit_date IS NULL OR d.[date] < a.exit_date)
    WHERE d.[date] >= (SELECT MIN(CAST(received_at AS DATE)) FROM core.payment_case)
), recv AS (       -- days with a case received (credited agent = latest resolver, else latest assignee)
    SELECT COALESCE(r.agent_id, (SELECT TOP (1) ca.agent_id FROM core.case_assignment AS ca
                                 WHERE ca.case_id = pc.case_id ORDER BY ca.assignment_seq DESC)) AS agent_id,
           CAST(pc.received_at AS DATE) AS d
    FROM core.payment_case AS pc LEFT JOIN last_res AS r ON r.case_id = pc.case_id AND r.rn = 1
), days AS (SELECT agent_id, d FROM sched UNION SELECT agent_id, d FROM res UNION SELECT agent_id, d FROM recv)
SELECT ISNULL(a.agent_type, 'ALL') AS agent_type,
       COUNT(*) AS agent_days,
       SUM(x.resolved) AS cases_resolved,
       CAST(1.0 * SUM(x.resolved) / COUNT(*) AS DECIMAL(5,2)) AS resolved_per_agent_day
FROM days AS dd
JOIN core.ops_agent AS a ON a.agent_id = dd.agent_id
CROSS APPLY (SELECT COUNT(*) AS resolved FROM res WHERE res.agent_id = dd.agent_id AND res.d = dd.d) AS x
GROUP BY ROLLUP(a.agent_type);
