/* ---------------------------------------------------------------------------
   002_reporting_views.sql
   Reporting layer (schema rpt) for Power BI. Power BI should import these
   views, never the core tables, so business rules live in one place.

   Run AFTER loading data (views don't store data, so order only matters
   for testing them; re-running this file is always safe).

   Contents
     dim_cohort, dim_enrolment, dim_employee, dim_competency,
     dim_programme_week, dim_date, dim_snapshot
     fact_attendance            every ELIGIBLE enrolment x session, with
                                gaps made explicit as 'Unrecorded'
     fact_assessment            one row per competency score
     fact_enrolment_status_event + enrolment_status_history
     fn_enrolment_status_as_of  status of every enrolment on any date
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
GO

/* ===== dim_cohort ======================================================== */
-- schedule_status describes the cohort's TIMETABLE as of the snapshot date.
-- It says nothing about whether individual trainees completed.
CREATE OR ALTER VIEW rpt.dim_cohort AS
SELECT
    c.cohort_id,
    c.cohort_name,
    c.start_date,
    c.planned_end_date,
    c.planned_weeks,
    c.delivery_mode,
    CASE
        WHEN s.as_of_date <  c.start_date       THEN 'Scheduled'
        WHEN s.as_of_date <= c.planned_end_date THEN 'In progress'
        ELSE 'Finished'
    END AS schedule_status,
    -- How many programme weeks have at least started by the snapshot date
    (SELECT COUNT(DISTINCT ss.programme_week)
     FROM core.scheduled_session AS ss
     WHERE ss.cohort_id = c.cohort_id
       AND ss.session_date <= s.as_of_date) AS weeks_started
FROM core.cohort AS c
CROSS JOIN core.data_snapshot AS s;
GO

/* ===== fact_enrolment_status_event ======================================= */
CREATE OR ALTER VIEW rpt.fact_enrolment_status_event AS
SELECT
    ev.status_event_id,
    ev.enrolment_id,
    e.cohort_id,
    e.employee_id,
    ev.event_type,
    ev.effective_date,
    ev.recorded_at,
    CASE WHEN ev.event_type IN ('withdrawn', 'completed', 'cancelled') THEN 1 ELSE 0 END AS is_end_event
FROM core.enrolment_status_event AS ev
JOIN core.enrolment AS e ON e.enrolment_id = ev.enrolment_id;
GO

/* ===== enrolment_status_history ========================================== */
-- Turns point-in-time events into periods: each status is valid from its
-- effective date up to (but not including) the next event's date.
-- LEAD() looks at the next row for the same enrolment.
CREATE OR ALTER VIEW rpt.enrolment_status_history AS
WITH ordered AS (
    SELECT
        ev.enrolment_id,
        ev.event_type,
        ev.effective_date,
        -- tie-breaker if two events share a date: the lifecycle order
        CASE ev.event_type
            WHEN 'enrolled'  THEN 1 WHEN 'cancelled' THEN 2 WHEN 'started' THEN 3
            WHEN 'withdrawn' THEN 4 WHEN 'completed' THEN 5
        END AS lifecycle_order
    FROM core.enrolment_status_event AS ev
)
SELECT
    o.enrolment_id,
    CASE o.event_type
        WHEN 'enrolled'  THEN 'Enrolled (not started)'
        WHEN 'cancelled' THEN 'Cancelled before start'
        WHEN 'started'   THEN 'Active'
        WHEN 'withdrawn' THEN 'Withdrawn'
        WHEN 'completed' THEN 'Completed'
    END AS status,
    o.effective_date AS valid_from,
    LEAD(o.effective_date) OVER (
        PARTITION BY o.enrolment_id ORDER BY o.effective_date, o.lifecycle_order
    ) AS valid_to        -- NULL = still the current status
FROM ordered AS o;
GO

/* ===== fn_enrolment_status_as_of ========================================= */
-- Status of every enrolment on @as_of_date. Only events effective on or
-- before that date are considered, so nothing from the future can leak in.
-- Example:  SELECT status, COUNT(*) FROM rpt.fn_enrolment_status_as_of('2026-10-15') GROUP BY status;
CREATE OR ALTER FUNCTION rpt.fn_enrolment_status_as_of (@as_of_date DATE)
RETURNS TABLE
AS RETURN
SELECT
    e.enrolment_id,
    e.cohort_id,
    e.employee_id,
    h.status,
    h.valid_from AS status_since
FROM core.enrolment AS e
JOIN rpt.enrolment_status_history AS h
  ON  h.enrolment_id = e.enrolment_id
  AND h.valid_from <= @as_of_date
  AND (h.valid_to IS NULL OR h.valid_to > @as_of_date);
GO

/* ===== dim_enrolment ===================================================== */
-- One row per enrolment with its status on the snapshot date. Employee
-- name is copied in so Power BI doesn't need an extra employee table for
-- labels (a person can appear in several enrolments).
CREATE OR ALTER VIEW rpt.dim_enrolment AS
SELECT
    e.enrolment_id,
    e.employee_id,
    CONCAT(emp.first_name, N' ', emp.last_name) AS employee_name,
    e.cohort_id,
    e.enrolled_date,
    st.effective_date AS start_date,
    ISNULL(cur.status, 'Enrolled (not started)') AS status_as_of_snapshot,
    cur.status_since,
    CASE WHEN st.enrolment_id IS NULL THEN 0 ELSE 1 END AS has_started
FROM core.enrolment AS e
JOIN core.employee AS emp ON emp.employee_id = e.employee_id
CROSS JOIN core.data_snapshot AS s
LEFT JOIN core.enrolment_status_event AS st
       ON st.enrolment_id = e.enrolment_id AND st.event_type = 'started'
OUTER APPLY (
    SELECT f.status, f.status_since
    FROM rpt.fn_enrolment_status_as_of(s.as_of_date) AS f
    WHERE f.enrolment_id = e.enrolment_id
) AS cur;
GO

/* ===== dim_employee ====================================================== */
CREATE OR ALTER VIEW rpt.dim_employee AS
SELECT
    emp.employee_id,
    CONCAT(emp.first_name, N' ', emp.last_name) AS employee_name,
    emp.hire_date,
    (SELECT COUNT(*) FROM core.enrolment AS e WHERE e.employee_id = emp.employee_id) AS enrolment_count
FROM core.employee AS emp;
GO

/* ===== dim_competency ==================================================== */
CREATE OR ALTER VIEW rpt.dim_competency AS
SELECT competency_id, competency_name, display_order
FROM core.competency;
GO

/* ===== dim_snapshot ====================================================== */
-- One row: the as-of date of the loaded synthetic dataset. Power BI imports
-- it as a DISCONNECTED table (no relationships) so the report can show
-- "data as of ..." from the data itself, and the label updates whenever the
-- data is regenerated, reloaded and the report refreshed.
CREATE OR ALTER VIEW rpt.dim_snapshot AS
SELECT as_of_date
FROM core.data_snapshot;
GO

/* ===== dim_programme_week ================================================ */
-- Programme week 1..N. Lets Power BI compare Week 3 with Week 3 across
-- cohorts that ran on different calendar dates.
CREATE OR ALTER VIEW rpt.dim_programme_week AS
WITH digits AS (
    SELECT n FROM (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)) AS d(n)
), numbers AS (
    SELECT tens.n * 10 + ones.n + 1 AS week_number
    FROM digits AS tens CROSS JOIN digits AS ones
)
SELECT
    CAST(week_number AS TINYINT) AS programme_week,
    CONCAT('Week ', week_number) AS week_label
FROM numbers
WHERE week_number <= (SELECT MAX(planned_weeks) FROM core.cohort);
GO

/* ===== dim_date ========================================================== */
-- A calendar covering every date in the data (up to 1,000 days).
-- Built from a numbers list instead of a stored table, so it always
-- matches whatever data is loaded.
CREATE OR ALTER VIEW rpt.dim_date AS
WITH digits AS (
    SELECT n FROM (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)) AS d(n)
), numbers AS (
    SELECT h.n * 100 + t.n * 10 + o.n AS n
    FROM digits AS h CROSS JOIN digits AS t CROSS JOIN digits AS o
), bounds AS (
    SELECT
        (SELECT MIN(enrolled_date) FROM core.enrolment) AS first_date,
        (SELECT MAX(d) FROM (VALUES
            ((SELECT MAX(planned_end_date) FROM core.cohort)),
            ((SELECT MAX(as_of_date) FROM core.data_snapshot))) AS v(d)) AS last_date
), dates AS (
    SELECT DATEADD(DAY, numbers.n, bounds.first_date) AS [date]
    FROM numbers CROSS JOIN bounds
    WHERE DATEADD(DAY, numbers.n, bounds.first_date) <= bounds.last_date
)
SELECT
    [date],
    YEAR([date])                       AS [year],
    MONTH([date])                      AS month_number,
    DATENAME(MONTH, [date])            AS month_name,
    -- Monday of the week (independent of server language settings)
    DATEADD(DAY, -((DATEDIFF(DAY, '19000101', [date])) % 7), [date]) AS week_start_monday,
    DATENAME(WEEKDAY, [date])          AS day_name,
    CASE WHEN DATEDIFF(DAY, '19000101', [date]) % 7 < 5 THEN 1 ELSE 0 END AS is_weekday
FROM dates;
GO

/* ===== fact_attendance =================================================== */
-- Grain: one ELIGIBLE enrolment x scheduled session up to the snapshot date.
-- Eligible = the enrolment had started by the session date and had not
-- withdrawn before it. Sessions with no recorded mark become 'Unrecorded'
-- rather than silently counting as absences.
CREATE OR ALTER VIEW rpt.fact_attendance AS
SELECT
    e.enrolment_id,
    e.cohort_id,
    e.employee_id,
    ss.session_id,
    ss.session_date,
    ss.programme_week,
    ISNULL(a.attendance_status, 'Unrecorded') AS attendance_status,
    CASE WHEN a.attendance_status = 'Present' THEN 1 ELSE 0 END AS is_present,
    CASE WHEN a.attendance_status = 'Absent'  THEN 1 ELSE 0 END AS is_absent,
    CASE WHEN a.attendance_status IS NULL     THEN 1 ELSE 0 END AS is_unrecorded
FROM core.enrolment AS e
JOIN core.enrolment_status_event AS st
  ON st.enrolment_id = e.enrolment_id AND st.event_type = 'started'
JOIN core.scheduled_session AS ss
  ON ss.cohort_id = e.cohort_id
 AND ss.session_date >= st.effective_date
CROSS JOIN core.data_snapshot AS s
LEFT JOIN core.enrolment_status_event AS wd
  ON wd.enrolment_id = e.enrolment_id AND wd.event_type = 'withdrawn'
LEFT JOIN core.attendance AS a
  ON a.enrolment_id = e.enrolment_id AND a.session_id = ss.session_id
WHERE ss.session_date <= s.as_of_date
  AND (wd.effective_date IS NULL OR ss.session_date < wd.effective_date);
GO

/* ===== fact_assessment =================================================== */
-- Grain: one enrolment x competency x programme week x attempt.
-- previous_week_score uses LAG() and is only filled when the previous row
-- is exactly the prior week, so a missed week never produces a misleading
-- two-week "weekly" change.
CREATE OR ALTER VIEW rpt.fact_assessment AS
WITH scored AS (
    SELECT
        a.assessment_id,
        a.enrolment_id,
        e.cohort_id,
        e.employee_id,
        a.competency_id,
        a.programme_week,
        a.attempt_number,
        a.assessment_date,
        a.score,
        a.rubric_version,
        LAG(a.programme_week) OVER (PARTITION BY a.enrolment_id, a.competency_id ORDER BY a.programme_week) AS prev_week,
        LAG(a.score)          OVER (PARTITION BY a.enrolment_id, a.competency_id ORDER BY a.programme_week) AS prev_score
    FROM core.assessment AS a
    JOIN core.enrolment AS e ON e.enrolment_id = a.enrolment_id
    WHERE a.attempt_number = 1
)
SELECT
    assessment_id, enrolment_id, cohort_id, employee_id, competency_id,
    programme_week, attempt_number, assessment_date, score, rubric_version,
    CASE WHEN prev_week = programme_week - 1 THEN prev_score END AS previous_week_score,
    -- CAST: score is TINYINT (0-255), which cannot hold a negative change
    CASE WHEN prev_week = programme_week - 1 THEN CAST(score AS INT) - prev_score END AS week_over_week_change
FROM scored;
GO

PRINT 'Build 01 reporting views created.';
GO
