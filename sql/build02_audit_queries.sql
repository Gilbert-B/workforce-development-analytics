/* ---------------------------------------------------------------------------
   build02_audit_queries.sql
   AUDIT: the evidence behind Build 02's decisions, recomputed in SQL from the
   loaded tables, independently of the Python generator. It is the database
   twin of the generator's audit files:
     data/synthetic/build02/audit/review_signals.csv      (query 1)
     data/synthetic/build02/audit/readiness_evidence.csv  (query 2)
   tests/test_build02_sql_integration.py checks that the two agree row by row.

   Query 1 shows, for every weekly watch-list review, what staff could know
   AT THAT MOMENT (records entered by the review time): attendance marks,
   MISSING marks (a data-quality flag, never an absence) and competency
   evidence. Policy thresholds for the signals live in the config, so the
   signal decisions themselves are in the CSV; this query shows the inputs.

   Query 2 shows, for every enrolment whose completion is on record at the
   snapshot, the readiness evidence and its KPI population (certified /
   attempted / not attempted; approved / deferred / not reviewed).

   The four DECLAREd values must match [watchlist] in
   config/build02_synthetic.toml (a test checks this).
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
SET NOCOUNT ON;

DECLARE @first_review_week  INT = 2;   -- watchlist.first_review_after_week
DECLARE @last_review_week   INT = 7;   -- watchlist.last_review_after_week
DECLARE @review_hour        INT = 10;  -- watchlist.review_hour
DECLARE @window_weeks       INT = 2;   -- watchlist.attendance_window_weeks
DECLARE @min_recorded       INT = 4;   -- watchlist.attendance_min_recorded_sessions
DECLARE @unrecorded_flag    INT = 2;   -- watchlist.unrecorded_review_min_sessions

DECLARE @competencies INT = (SELECT COUNT(*) FROM core.competency);
DECLARE @cutoff DATETIME2(0) = (SELECT DATEADD(MINUTE, 23 * 60 + 59, CAST(as_of_date AS DATETIME2(0)))
                                FROM core.data_snapshot);    -- end of the snapshot day

/* ===== Query 1: weekly review evidence (one row per review held) ========= */
WITH weeks AS (
    SELECT n FROM (VALUES (1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11),(12)) AS v(n)
),
reviews AS (       -- review = Monday after programme week n, at @review_hour
    SELECT e.enrolment_id, e.cohort_id, w.n AS review_after_week,
           DATEADD(HOUR, @review_hour, CAST(DATEADD(DAY, 7 * w.n, c.start_date) AS DATETIME2(0))) AS review_at
    FROM core.enrolment AS e
    JOIN core.cohort AS c ON c.cohort_id = e.cohort_id
    CROSS JOIN weeks AS w
    WHERE w.n BETWEEN @first_review_week AND @last_review_week
),
held AS (          -- only reviews of trainees known to have started and not known to have left
    SELECT r.*, st.effective_date AS started_on, wd.effective_date AS known_withdrawn_on
    FROM reviews AS r
    JOIN core.enrolment_status_event AS st
      ON st.enrolment_id = r.enrolment_id AND st.event_type = 'started' AND st.recorded_at <= r.review_at
    LEFT JOIN core.enrolment_status_event AS wd
      ON wd.enrolment_id = r.enrolment_id AND wd.event_type = 'withdrawn' AND wd.recorded_at <= r.review_at
    WHERE r.review_at <= @cutoff
      AND NOT EXISTS (SELECT 1 FROM core.enrolment_status_event AS x
                      WHERE x.enrolment_id = r.enrolment_id
                        AND x.event_type IN ('withdrawn', 'completed', 'cancelled')
                        AND x.recorded_at <= r.review_at)
),
evidence AS (
    SELECT h.enrolment_id, h.cohort_id, h.review_after_week, h.review_at,
           h.review_after_week - @window_weeks + 1 AS window_start_week,
           h.review_after_week AS window_end_week,
           -- sessions the trainee should have a mark for, as far as staff knew
           (SELECT COUNT(*) FROM core.scheduled_session AS ss
            WHERE ss.cohort_id = h.cohort_id
              AND ss.programme_week BETWEEN h.review_after_week - @window_weeks + 1 AND h.review_after_week
              AND ss.session_date >= h.started_on
              AND ss.session_date < CAST(h.review_at AS DATE)
              AND (h.known_withdrawn_on IS NULL OR ss.session_date < h.known_withdrawn_on)) AS eligible_sessions,
           att.recorded_sessions, att.present_sessions,
           lf.latest_full_week, lf.latest_full_week_avg, pw.previous_week_avg, ca.cohort_same_week_avg
    FROM held AS h
    CROSS APPLY (SELECT COUNT(*) AS recorded_sessions,
                        SUM(CASE WHEN a.attendance_status = 'Present' THEN 1 ELSE 0 END) AS present_sessions
                 FROM core.attendance AS a
                 JOIN core.scheduled_session AS ss ON ss.session_id = a.session_id
                 WHERE a.enrolment_id = h.enrolment_id AND a.recorded_at <= h.review_at
                   AND ss.programme_week BETWEEN h.review_after_week - @window_weeks + 1 AND h.review_after_week) AS att
    OUTER APPLY (SELECT TOP (1) a.programme_week AS latest_full_week,
                        AVG(CAST(a.score AS DECIMAL(12,6))) AS latest_full_week_avg
                 FROM core.assessment AS a
                 WHERE a.enrolment_id = h.enrolment_id AND a.recorded_at <= h.review_at
                 GROUP BY a.programme_week
                 HAVING COUNT(*) = @competencies          -- a week counts only if EVERY competency is scored
                 ORDER BY a.programme_week DESC) AS lf
    OUTER APPLY (SELECT AVG(CAST(a.score AS DECIMAL(12,6))) AS previous_week_avg
                 FROM core.assessment AS a
                 WHERE a.enrolment_id = h.enrolment_id AND a.recorded_at <= h.review_at
                   AND a.programme_week = lf.latest_full_week - 1
                 HAVING COUNT(*) = @competencies) AS pw
    OUTER APPLY (SELECT AVG(t.trainee_avg) AS cohort_same_week_avg   -- average of trainee averages
                 FROM (SELECT a.enrolment_id, AVG(CAST(a.score AS DECIMAL(12,6))) AS trainee_avg
                       FROM core.assessment AS a
                       JOIN core.enrolment AS pe ON pe.enrolment_id = a.enrolment_id
                       WHERE pe.cohort_id = h.cohort_id AND a.programme_week = lf.latest_full_week
                         AND a.recorded_at <= h.review_at
                       GROUP BY a.enrolment_id
                       HAVING COUNT(*) = @competencies) AS t) AS ca
)
SELECT
    enrolment_id, cohort_id, review_after_week, review_at, window_start_week, window_end_week,
    eligible_sessions, recorded_sessions, present_sessions,
    eligible_sessions - recorded_sessions AS unrecorded_sessions,
    CAST(1.0 * present_sessions / NULLIF(recorded_sessions, 0) AS DECIMAL(6,4)) AS recorded_attendance_rate,
    latest_full_week,
    CAST(latest_full_week_avg AS DECIMAL(6,2)) AS latest_full_week_avg,
    CAST(cohort_same_week_avg AS DECIMAL(6,2)) AS cohort_same_week_avg,
    CAST(latest_full_week_avg - cohort_same_week_avg AS DECIMAL(6,2)) AS gap_vs_cohort,
    CAST(previous_week_avg AS DECIMAL(6,2)) AS previous_week_avg,
    CAST(latest_full_week_avg - previous_week_avg AS DECIMAL(6,2)) AS week_change,
    CASE WHEN recorded_sessions >= @min_recorded THEN 'Sufficient' ELSE 'Insufficient' END AS attendance_evidence,
    CASE WHEN eligible_sessions - recorded_sessions >= @unrecorded_flag
         THEN 'VERIFY_UNRECORDED_MARKS' ELSE 'OK' END AS attendance_dq_flag,
    CASE WHEN latest_full_week IS NULL THEN 'No fully assessed week' ELSE 'Full week available' END AS competency_evidence
FROM evidence
ORDER BY enrolment_id, review_after_week;

/* ===== Query 2: readiness evidence per completed enrolment (at snapshot) ===== */
WITH completed AS (
    SELECT e.enrolment_id, e.cohort_id, ev.effective_date AS completion_date
    FROM core.enrolment AS e
    JOIN core.enrolment_status_event AS ev
      ON ev.enrolment_id = e.enrolment_id AND ev.event_type = 'completed' AND ev.recorded_at <= @cutoff
),
week_counts AS (
    SELECT a.enrolment_id, a.programme_week, COUNT(*) AS scored, AVG(CAST(a.score AS DECIMAL(12,6))) AS week_avg
    FROM core.assessment AS a
    WHERE a.recorded_at <= @cutoff
    GROUP BY a.enrolment_id, a.programme_week
),
certs AS (         -- one row per completed enrolment x mandatory certification
    SELECT c.enrolment_id, ct.certification_id, ct.max_attempts,
           (SELECT COUNT(*) FROM core.certification_attempt AS a
            WHERE a.enrolment_id = c.enrolment_id AND a.certification_id = ct.certification_id) AS attempts,
           (SELECT COUNT(*) FROM core.certification_attempt AS a
            WHERE a.enrolment_id = c.enrolment_id AND a.certification_id = ct.certification_id
              AND a.result = 'Passed') AS passes
    FROM completed AS c
    CROSS JOIN core.certification_type AS ct
    WHERE ct.mandatory_for_readiness = 1
),
cert_summary AS (
    SELECT enrolment_id,
           COUNT(*) AS mandatory_certifications,
           SUM(CASE WHEN attempts > 0 THEN 1 ELSE 0 END) AS certifications_attempted,
           SUM(CASE WHEN passes > 0 THEN 1 ELSE 0 END) AS certifications_passed,
           SUM(CASE WHEN passes = 0 AND attempts >= max_attempts THEN 1 ELSE 0 END) AS certifications_exhausted
    FROM certs GROUP BY enrolment_id
),
latest_review AS (
    SELECT r.enrolment_id, r.review_date, r.decision, r.decision_reason_code,
           COUNT(*) OVER (PARTITION BY r.enrolment_id) AS review_count,
           ROW_NUMBER() OVER (PARTITION BY r.enrolment_id ORDER BY r.review_number DESC) AS rn
    FROM core.readiness_review AS r
)
SELECT
    c.enrolment_id, c.cohort_id, c.completion_date,
    lf.programme_week AS latest_full_week,
    CAST(lf.week_avg AS DECIMAL(4,1)) AS latest_full_week_avg,
    (SELECT COUNT(*) FROM week_counts AS w WHERE w.enrolment_id = c.enrolment_id AND w.scored < @competencies)
        AS partially_assessed_weeks,
    CASE WHEN lf.programme_week IS NULL THEN 'No fully assessed week' ELSE 'Full week available' END AS competency_evidence,
    cs.mandatory_certifications, cs.certifications_attempted, cs.certifications_passed, cs.certifications_exhausted,
    CASE WHEN cs.certifications_passed = cs.mandatory_certifications THEN 'Fully certified'
         WHEN cs.certifications_passed > 0 THEN 'Partly certified'
         WHEN cs.certifications_attempted > 0 THEN 'Attempted, none passed'
         ELSE 'Not attempted' END AS certification_population,
    ISNULL(lr.review_count, 0) AS review_count,
    lr.review_date AS latest_review_date,
    lr.decision_reason_code AS latest_decision_reason,
    -- COALESCE + CAST, not ISNULL: ISNULL would use decision's varchar(10) and cut the text to 'Not review'
    COALESCE(CAST(lr.decision AS VARCHAR(20)), 'Not reviewed') AS readiness_population
FROM completed AS c
JOIN cert_summary AS cs ON cs.enrolment_id = c.enrolment_id
OUTER APPLY (SELECT TOP (1) w.programme_week, w.week_avg FROM week_counts AS w
             WHERE w.enrolment_id = c.enrolment_id AND w.scored = @competencies
             ORDER BY w.programme_week DESC) AS lf
LEFT JOIN latest_review AS lr ON lr.enrolment_id = c.enrolment_id AND lr.rn = 1
ORDER BY c.enrolment_id;
