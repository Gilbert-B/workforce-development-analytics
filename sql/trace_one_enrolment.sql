/* ---------------------------------------------------------------------------
   trace_one_enrolment.sql
   Follow ONE synthetic person through every layer: core tables -> status
   history -> as-of status -> reporting facts. Use it to understand how the
   rules work, or to debug a number that looks wrong in Power BI.

   Default: EMP-00025, who withdrew from Cohort 1 and re-enrolled in Cohort 3.
   Change @employee_id to trace anyone else (IDs are in employee.csv).

       sqlcmd -S .\SQLEXPRESS -E -C -d WorkforceDevAnalytics -i sql\trace_one_enrolment.sql
--------------------------------------------------------------------------- */
SET NOCOUNT ON;
DECLARE @employee_id VARCHAR(20) = 'EMP-00025';

PRINT '1. The person (core.employee) - one row, no cohort column';
SELECT employee_id, first_name, last_name, hire_date
FROM core.employee WHERE employee_id = @employee_id;

PRINT '2. Their enrolments (core.enrolment) - one row per cohort they joined';
SELECT enrolment_id, cohort_id, enrolled_date
FROM core.enrolment WHERE employee_id = @employee_id ORDER BY enrolled_date;

PRINT '3. Lifecycle events (core.enrolment_status_event) - effective vs recorded';
SELECT ev.enrolment_id, ev.event_type, ev.effective_date, ev.recorded_at
FROM core.enrolment_status_event AS ev
JOIN core.enrolment AS e ON e.enrolment_id = ev.enrolment_id
WHERE e.employee_id = @employee_id
ORDER BY ev.enrolment_id, ev.effective_date;

PRINT '4. Events turned into periods (rpt.enrolment_status_history, via LEAD)';
SELECT h.enrolment_id, h.status, h.valid_from, h.valid_to
FROM rpt.enrolment_status_history AS h
JOIN core.enrolment AS e ON e.enrolment_id = h.enrolment_id
WHERE e.employee_id = @employee_id
ORDER BY h.enrolment_id, h.valid_from;

PRINT '5. Status on three dates (rpt.fn_enrolment_status_as_of) - no future leakage';
SELECT d.check_date, f.enrolment_id, f.status
FROM (VALUES (CAST('2026-06-16' AS DATE)), ('2026-06-17'), ('2026-10-01')) AS d(check_date)
CROSS APPLY rpt.fn_enrolment_status_as_of(d.check_date) AS f
WHERE f.employee_id = @employee_id
ORDER BY d.check_date, f.enrolment_id;

PRINT '6. Attendance per week (rpt.fact_attendance) - stops at withdrawal, gaps = Unrecorded';
SELECT enrolment_id, programme_week,
       COUNT(*) AS eligible_sessions, SUM(is_present) AS present,
       SUM(is_absent) AS absent, SUM(is_unrecorded) AS unrecorded
FROM rpt.fact_attendance
WHERE employee_id = @employee_id
GROUP BY enrolment_id, programme_week
ORDER BY enrolment_id, programme_week;

PRINT '7. Scores per week (rpt.fact_assessment) - missing week = absent on Friday, not zero';
SELECT enrolment_id, programme_week,
       COUNT(*) AS competencies_scored,
       CAST(AVG(CAST(score AS DECIMAL(6,2))) AS DECIMAL(5,1)) AS avg_score
FROM rpt.fact_assessment
WHERE employee_id = @employee_id
GROUP BY enrolment_id, programme_week
ORDER BY enrolment_id, programme_week;
