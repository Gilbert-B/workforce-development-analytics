/* ---------------------------------------------------------------------------
   validation_queries.sql
   One query, one row per check. failing_rows must be 0 for every 'error'
   check; 'info' checks report counts worth knowing but are not failures.

   Run against the WorkforceDevAnalytics database, e.g.:
       sqlcmd -S .\SQLEXPRESS -E -C -d WorkforceDevAnalytics -i sql\validation_queries.sql
   python/load_to_sql.py runs this automatically after every load.
   (No GO here, so the loader can send it as a single batch.)
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;   -- so SSMS runs this in the right database
WITH snapshot AS (
    SELECT as_of_date FROM core.data_snapshot
),
starters AS (
    SELECT e.cohort_id, COUNT(*) AS starting_headcount
    FROM core.enrolment AS e
    JOIN core.enrolment_status_event AS ev
      ON ev.enrolment_id = e.enrolment_id AND ev.event_type = 'started'
    GROUP BY e.cohort_id
),
event_dates AS (   -- one row per enrolment with each lifecycle date side by side
    SELECT
        enrolment_id,
        MAX(CASE WHEN event_type = 'enrolled'  THEN effective_date END) AS enrolled_on,
        MAX(CASE WHEN event_type = 'cancelled' THEN effective_date END) AS cancelled_on,
        MAX(CASE WHEN event_type = 'started'   THEN effective_date END) AS started_on,
        MAX(CASE WHEN event_type = 'withdrawn' THEN effective_date END) AS withdrawn_on,
        MAX(CASE WHEN event_type = 'completed' THEN effective_date END) AS completed_on
    FROM core.enrolment_status_event
    GROUP BY enrolment_id
),
checks AS (
    -- ---------- volumes ----------
    SELECT 'cohorts_loaded_at_least_3' AS check_name, 'error' AS severity,
           CASE WHEN (SELECT COUNT(*) FROM core.cohort) >= 3 THEN 0 ELSE 1 END AS failing_rows
    UNION ALL
    SELECT 'started_cohorts_outside_60_to_75_starters', 'error',
           (SELECT COUNT(*) FROM starters WHERE starting_headcount NOT BETWEEN 60 AND 75)
    UNION ALL
    SELECT 'data_snapshot_not_exactly_one_row', 'error',
           CASE WHEN (SELECT COUNT(*) FROM core.data_snapshot) = 1 THEN 0 ELSE 1 END

    -- ---------- duplicates (constraints also prevent these) ----------
    UNION ALL
    SELECT 'duplicate_enrolment_employee_cohort', 'error',
           (SELECT COUNT(*) FROM (SELECT employee_id, cohort_id FROM core.enrolment
                                  GROUP BY employee_id, cohort_id HAVING COUNT(*) > 1) AS d)
    UNION ALL
    SELECT 'duplicate_assessment_grain', 'error',
           (SELECT COUNT(*) FROM (SELECT enrolment_id, competency_id, programme_week, attempt_number
                                  FROM core.assessment
                                  GROUP BY enrolment_id, competency_id, programme_week, attempt_number
                                  HAVING COUNT(*) > 1) AS d)

    -- ---------- orphaned references ----------
    UNION ALL
    SELECT 'enrolment_without_employee', 'error',
           (SELECT COUNT(*) FROM core.enrolment AS e
            WHERE NOT EXISTS (SELECT 1 FROM core.employee AS x WHERE x.employee_id = e.employee_id))
    UNION ALL
    SELECT 'enrolment_without_cohort', 'error',
           (SELECT COUNT(*) FROM core.enrolment AS e
            WHERE NOT EXISTS (SELECT 1 FROM core.cohort AS x WHERE x.cohort_id = e.cohort_id))
    UNION ALL
    SELECT 'employee_without_enrolment', 'error',
           (SELECT COUNT(*) FROM core.employee AS emp
            WHERE NOT EXISTS (SELECT 1 FROM core.enrolment AS e WHERE e.employee_id = emp.employee_id))
    UNION ALL
    SELECT 'assessment_without_enrolment_or_competency', 'error',
           (SELECT COUNT(*) FROM core.assessment AS a
            WHERE NOT EXISTS (SELECT 1 FROM core.enrolment AS e WHERE e.enrolment_id = a.enrolment_id)
               OR NOT EXISTS (SELECT 1 FROM core.competency AS c WHERE c.competency_id = a.competency_id))

    -- A foreign key can't check this one: the session must belong to the
    -- SAME cohort as the enrolment.
    UNION ALL
    SELECT 'attendance_session_in_other_cohort', 'error',
           (SELECT COUNT(*) FROM core.attendance AS a
            JOIN core.enrolment AS e ON e.enrolment_id = a.enrolment_id
            JOIN core.scheduled_session AS ss ON ss.session_id = a.session_id
            WHERE ss.cohort_id <> e.cohort_id)

    -- ---------- week bounds ----------
    UNION ALL
    SELECT 'session_week_outside_programme', 'error',
           (SELECT COUNT(*) FROM core.scheduled_session AS ss
            JOIN core.cohort AS c ON c.cohort_id = ss.cohort_id
            WHERE ss.programme_week NOT BETWEEN 1 AND c.planned_weeks
               OR ss.session_date NOT BETWEEN c.start_date AND c.planned_end_date)
    UNION ALL
    SELECT 'assessment_week_outside_programme', 'error',
           (SELECT COUNT(*) FROM core.assessment AS a
            JOIN core.enrolment AS e ON e.enrolment_id = a.enrolment_id
            JOIN core.cohort AS c ON c.cohort_id = e.cohort_id
            WHERE a.programme_week NOT BETWEEN 1 AND c.planned_weeks)
    UNION ALL
    SELECT 'assessment_date_not_in_its_programme_week', 'error',
           (SELECT COUNT(*) FROM core.assessment AS a
            JOIN core.enrolment AS e ON e.enrolment_id = a.enrolment_id
            WHERE NOT EXISTS (SELECT 1 FROM core.scheduled_session AS ss
                              WHERE ss.cohort_id = e.cohort_id
                                AND ss.programme_week = a.programme_week
                                AND ss.session_date = a.assessment_date))

    -- ---------- status-event chronology ----------
    UNION ALL
    SELECT 'enrolment_without_enrolled_event', 'error',
           (SELECT COUNT(*) FROM core.enrolment AS e
            LEFT JOIN event_dates AS d ON d.enrolment_id = e.enrolment_id
            WHERE d.enrolled_on IS NULL)
    UNION ALL
    SELECT 'enrolled_before_hire_date', 'error',   -- found by tracing one enrolment
           (SELECT COUNT(*) FROM core.enrolment AS e
            JOIN core.employee AS emp ON emp.employee_id = e.employee_id
            WHERE e.enrolled_date < emp.hire_date)
    UNION ALL
    SELECT 'end_event_without_started_event', 'error',
           (SELECT COUNT(*) FROM event_dates
            WHERE (withdrawn_on IS NOT NULL OR completed_on IS NOT NULL) AND started_on IS NULL)
    UNION ALL
    SELECT 'events_out_of_order', 'error',
           (SELECT COUNT(*) FROM event_dates
            WHERE started_on   < enrolled_on
               OR cancelled_on < enrolled_on
               OR withdrawn_on < started_on
               OR completed_on < started_on)
    UNION ALL
    SELECT 'more_than_one_end_event', 'error',
           (SELECT COUNT(*) FROM event_dates
            WHERE (CASE WHEN cancelled_on IS NULL THEN 0 ELSE 1 END
                 + CASE WHEN withdrawn_on IS NULL THEN 0 ELSE 1 END
                 + CASE WHEN completed_on IS NULL THEN 0 ELSE 1 END) > 1)
    UNION ALL
    SELECT 'cancelled_but_also_started', 'error',
           (SELECT COUNT(*) FROM event_dates WHERE cancelled_on IS NOT NULL AND started_on IS NOT NULL)

    -- ---------- nothing from the future ----------
    UNION ALL
    SELECT 'records_after_snapshot_date', 'error',
           (SELECT COUNT(*) FROM core.enrolment_status_event, snapshot
            WHERE effective_date > as_of_date OR CAST(recorded_at AS DATE) > as_of_date)
         + (SELECT COUNT(*) FROM core.attendance AS a
            JOIN core.scheduled_session AS ss ON ss.session_id = a.session_id
            CROSS JOIN snapshot
            WHERE ss.session_date > as_of_date OR CAST(a.recorded_at AS DATE) > as_of_date)
         + (SELECT COUNT(*) FROM core.assessment, snapshot
            WHERE assessment_date > as_of_date OR CAST(recorded_at AS DATE) > as_of_date)
    UNION ALL
    SELECT 'completion_before_cohort_end', 'error',
           (SELECT COUNT(*) FROM event_dates AS d
            JOIN core.enrolment AS e ON e.enrolment_id = d.enrolment_id
            JOIN core.cohort AS c ON c.cohort_id = e.cohort_id
            WHERE d.completed_on < c.planned_end_date)

    -- ---------- attendance / assessment eligibility ----------
    UNION ALL
    SELECT 'attendance_outside_enrolment_period', 'error',
           (SELECT COUNT(*) FROM core.attendance AS a
            JOIN core.scheduled_session AS ss ON ss.session_id = a.session_id
            LEFT JOIN event_dates AS d ON d.enrolment_id = a.enrolment_id
            WHERE d.started_on IS NULL
               OR ss.session_date < d.started_on
               OR ss.session_date >= d.withdrawn_on)
    UNION ALL
    SELECT 'assessment_outside_enrolment_period', 'error',
           (SELECT COUNT(*) FROM core.assessment AS a
            LEFT JOIN event_dates AS d ON d.enrolment_id = a.enrolment_id
            WHERE d.started_on IS NULL
               OR a.assessment_date < d.started_on
               OR a.assessment_date >= d.withdrawn_on)
    UNION ALL
    SELECT 'score_outside_0_to_100', 'error',
           (SELECT COUNT(*) FROM core.assessment WHERE score NOT BETWEEN 0 AND 100)

    -- ---------- informational ----------
    UNION ALL
    SELECT 'info_unrecorded_eligible_attendance', 'info',
           (SELECT COUNT(*) FROM rpt.fact_attendance WHERE attendance_status = 'Unrecorded')
    UNION ALL
    SELECT 'info_employees_with_more_than_one_enrolment', 'info',
           (SELECT COUNT(*) FROM (SELECT employee_id FROM core.enrolment
                                  GROUP BY employee_id HAVING COUNT(*) > 1) AS r)
)
SELECT check_name, severity, failing_rows,
       CASE WHEN severity = 'info' THEN 'INFO'
            WHEN failing_rows = 0  THEN 'PASS'
            ELSE 'FAIL' END AS result
FROM checks
ORDER BY CASE severity WHEN 'error' THEN 0 ELSE 1 END, check_name;
