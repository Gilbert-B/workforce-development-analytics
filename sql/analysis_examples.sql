/* ---------------------------------------------------------------------------
   analysis_examples.sql
   Reference answers for the first Power BI measures. When a DAX measure
   is built, compare it against the matching query here — if the numbers
   differ, one of them has a filter-context or definition problem.

   Run against WorkforceDevAnalytics, e.g.:
       sqlcmd -S .\SQLEXPRESS -E -C -d WorkforceDevAnalytics -i sql\analysis_examples.sql
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;   -- so SSMS runs this in the right database
SET NOCOUNT ON;

-- 1. Starting Cohort Headcount: enrolments with a 'started' event.
--    Distinct employees shown separately (a person can repeat training).
SELECT
    e.cohort_id,
    COUNT(*)                      AS starting_headcount,
    COUNT(DISTINCT e.employee_id) AS distinct_employees
FROM core.enrolment AS e
JOIN core.enrolment_status_event AS ev
  ON ev.enrolment_id = e.enrolment_id AND ev.event_type = 'started'
GROUP BY e.cohort_id
ORDER BY e.cohort_id;

-- 2. Active Trainees as of a date (Rule 2): started on or before the date,
--    with no withdrawn/completed event effective on or before it.
--    Change @as_of to test other dates; future events never count.
DECLARE @as_of DATE = '2026-06-15';
SELECT cohort_id, status, COUNT(*) AS enrolments
FROM rpt.fn_enrolment_status_as_of(@as_of)
GROUP BY cohort_id, status
ORDER BY cohort_id, status;

-- Same rule written directly against the events, as a cross-check:
SELECT e.cohort_id, COUNT(*) AS active_trainees
FROM core.enrolment AS e
WHERE EXISTS (SELECT 1 FROM core.enrolment_status_event AS s
              WHERE s.enrolment_id = e.enrolment_id AND s.event_type = 'started'
                AND s.effective_date <= @as_of)
  AND NOT EXISTS (SELECT 1 FROM core.enrolment_status_event AS x
                  WHERE x.enrolment_id = e.enrolment_id
                    AND x.event_type IN ('withdrawn', 'completed')
                    AND x.effective_date <= @as_of)
GROUP BY e.cohort_id
ORDER BY e.cohort_id;

-- 3. Attendance by cohort: eligible sessions, recorded, unrecorded, and
--    the rate calculated two ways (the definition choice matters).
SELECT
    cohort_id,
    COUNT(*)                         AS eligible_scheduled_sessions,
    SUM(is_present)                  AS present,
    SUM(is_absent)                   AS absent,
    SUM(is_unrecorded)               AS unrecorded,
    CAST(100.0 * SUM(is_present) / NULLIF(SUM(is_present) + SUM(is_absent), 0) AS DECIMAL(5,1))
                                     AS recorded_attendance_rate_pct,   -- present / recorded
    CAST(100.0 * SUM(is_present) / NULLIF(COUNT(*), 0) AS DECIMAL(5,1))
                                     AS present_of_eligible_pct         -- present / all eligible
FROM rpt.fact_attendance
GROUP BY cohort_id
ORDER BY cohort_id;

-- 4. Average core competency score by cohort and programme week
--    (Week 1 vs Week 1 across cohorts — Rule 5).
SELECT
    cohort_id,
    programme_week,
    COUNT(DISTINCT enrolment_id)          AS assessed_enrolments,
    CAST(AVG(CAST(score AS DECIMAL(6,2))) AS DECIMAL(5,1)) AS avg_core_score
FROM rpt.fact_assessment
GROUP BY cohort_id, programme_week
ORDER BY cohort_id, programme_week;

-- 5. Week-over-week change, two different definitions:
--    a) change in the cohort AVERAGE (what a simple DAX measure gives)
--    b) average of each person's own change (only people assessed both weeks)
WITH weekly AS (
    SELECT cohort_id, programme_week, AVG(CAST(score AS DECIMAL(6,2))) AS avg_score
    FROM rpt.fact_assessment
    GROUP BY cohort_id, programme_week
)
SELECT
    w.cohort_id,
    w.programme_week,
    CAST(w.avg_score - LAG(w.avg_score) OVER (PARTITION BY w.cohort_id ORDER BY w.programme_week)
         AS DECIMAL(5,1)) AS change_in_cohort_average,
    (SELECT CAST(AVG(CAST(f.week_over_week_change AS DECIMAL(6,2))) AS DECIMAL(5,1))
     FROM rpt.fact_assessment AS f
     WHERE f.cohort_id = w.cohort_id AND f.programme_week = w.programme_week) AS avg_individual_change
FROM weekly AS w
ORDER BY w.cohort_id, w.programme_week;
