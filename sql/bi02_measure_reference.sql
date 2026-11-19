/* ---------------------------------------------------------------------------
   bi02_measure_reference.sql
   Reference values for the BI-02 Power BI measures, computed INDEPENDENTLY:
   straight from the core tables and core.data_snapshot, NOT from the rpt
   view flags (is_open_at_snapshot, is_latest_review, pair_passed...) that
   the DAX uses. If a view or a measure is wrong, the two will disagree.

   Output: one row per measure x cohort, plus an 'ALL' row per measure, with
   numerator, denominator and value. Compare each with Power BI (a card or
   matrix with the cohort tiles set the same way).

   Run in SSMS against WorkforceDevAnalytics (Build 01 + Build 02 loaded).
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
SET NOCOUNT ON;

DECLARE @snap DATE = (SELECT as_of_date FROM core.data_snapshot);
DECLARE @cutoff DATETIME2(0) = DATEADD(MINUTE, 23 * 60 + 59, CAST(@snap AS DATETIME2(0)));

WITH
-- status at the snapshot from the raw lifecycle events (no rpt function)
status AS (
    SELECT e.enrolment_id, e.cohort_id,
        CASE
            WHEN MAX(CASE WHEN ev.event_type = 'cancelled' AND ev.effective_date <= @snap THEN 1 END) = 1 THEN 'Cancelled'
            WHEN MAX(CASE WHEN ev.event_type = 'withdrawn' AND ev.effective_date <= @snap THEN 1 END) = 1 THEN 'Withdrawn'
            WHEN MAX(CASE WHEN ev.event_type = 'completed' AND ev.effective_date <= @snap THEN 1 END) = 1 THEN 'Completed'
            WHEN MAX(CASE WHEN ev.event_type = 'started'   AND ev.effective_date <= @snap THEN 1 END) = 1 THEN 'Active'
            ELSE 'Not started'
        END AS status
    FROM core.enrolment AS e
    JOIN core.enrolment_status_event AS ev ON ev.enrolment_id = e.enrolment_id
    GROUP BY e.enrolment_id, e.cohort_id
),
-- a case is open at the snapshot unless a Closed event is effective by then
cases AS (
    SELECT c.watchlist_case_id, c.enrolment_id, s.cohort_id, s.status,
           CASE WHEN EXISTS (SELECT 1 FROM core.watchlist_case_event AS ev
                             WHERE ev.watchlist_case_id = c.watchlist_case_id AND ev.event_type = 'Closed'
                               AND ev.effective_date <= @snap) THEN 0 ELSE 1 END AS is_open,
           CASE WHEN EXISTS (SELECT 1 FROM core.coaching_action AS a
                             WHERE a.watchlist_case_id = c.watchlist_case_id) THEN 1 ELSE 0 END AS has_action,
           -- days the case was open (to closure or snapshot): option B eligibility
           DATEDIFF(DAY, c.opened_effective_date,
                    ISNULL((SELECT MIN(ev.effective_date) FROM core.watchlist_case_event AS ev
                            WHERE ev.watchlist_case_id = c.watchlist_case_id AND ev.event_type = 'Closed'
                              AND ev.effective_date <= @snap), @snap)) AS days_open
    FROM core.watchlist_case AS c
    JOIN status AS s ON s.enrolment_id = c.enrolment_id
),
attempts AS (
    SELECT a.*, s.cohort_id FROM core.certification_attempt AS a JOIN status AS s ON s.enrolment_id = a.enrolment_id
),
pairs AS (          -- one row per attempted enrolment x certification
    SELECT enrolment_id, cohort_id, certification_id,
           MAX(CASE WHEN result = 'Passed' THEN 1 ELSE 0 END) AS passed
    FROM attempts GROUP BY enrolment_id, cohort_id, certification_id
),
completed AS (
    SELECT s.enrolment_id, s.cohort_id,
           (SELECT COUNT(*) FROM core.certification_type WHERE mandatory_for_readiness = 1) AS mandatory_total,
           (SELECT COUNT(DISTINCT p.certification_id) FROM pairs AS p
            JOIN core.certification_type AS ct ON ct.certification_id = p.certification_id AND ct.mandatory_for_readiness = 1
            WHERE p.enrolment_id = s.enrolment_id) AS mandatory_attempted,
           (SELECT COUNT(DISTINCT p.certification_id) FROM pairs AS p
            JOIN core.certification_type AS ct ON ct.certification_id = p.certification_id AND ct.mandatory_for_readiness = 1
            WHERE p.enrolment_id = s.enrolment_id AND p.passed = 1) AS mandatory_passed,
           -- latest review ENTERED by the snapshot (highest review_number)
           (SELECT TOP (1) r.decision FROM core.readiness_review AS r
            WHERE r.enrolment_id = s.enrolment_id AND r.recorded_at <= @cutoff
            ORDER BY r.review_number DESC) AS latest_decision
    FROM status AS s
    WHERE s.status = 'Completed'
),
cohorts AS (SELECT cohort_id FROM core.cohort UNION ALL SELECT 'ALL'),
m AS (
    SELECT k.cohort_id, x.*
    FROM cohorts AS k
    CROSS APPLY (
        -- 1. Open Watch-list Enrolments (Snapshot)
        SELECT 1 AS n, 'Open Watch-list Enrolments (Snapshot)' AS measure,
               (SELECT COUNT(DISTINCT enrolment_id) FROM cases WHERE is_open = 1 AND k.cohort_id IN (cohort_id, 'ALL')) AS numerator,
               CAST(NULL AS INT) AS denominator
        UNION ALL -- 2. Watch-list Rate (Snapshot): open ACTIVE enrolments / Active trainees
        SELECT 2, 'Watch-list Rate (Snapshot)',
               (SELECT COUNT(DISTINCT enrolment_id) FROM cases WHERE is_open = 1 AND status = 'Active' AND k.cohort_id IN (cohort_id, 'ALL')),
               (SELECT COUNT(*) FROM status WHERE status = 'Active' AND k.cohort_id IN (cohort_id, 'ALL'))
        UNION ALL -- 3a. Coaching Coverage, option A: all cases
        SELECT 3, 'Coaching Coverage (A: all cases)',
               (SELECT COUNT(*) FROM cases WHERE has_action = 1 AND k.cohort_id IN (cohort_id, 'ALL')),
               (SELECT COUNT(*) FROM cases WHERE k.cohort_id IN (cohort_id, 'ALL'))
        UNION ALL -- 3b. Coaching Coverage, option B: cases open at least 7 days
        SELECT 4, 'Coaching Coverage (B: open >= 7 days)',
               (SELECT COUNT(*) FROM cases WHERE has_action = 1 AND days_open >= 7 AND k.cohort_id IN (cohort_id, 'ALL')),
               (SELECT COUNT(*) FROM cases WHERE days_open >= 7 AND k.cohort_id IN (cohort_id, 'ALL'))
        UNION ALL -- 4. Unactioned Watch-list Cases
        SELECT 5, 'Unactioned Watch-list Cases',
               (SELECT COUNT(*) FROM cases WHERE has_action = 0 AND k.cohort_id IN (cohort_id, 'ALL')), NULL
        UNION ALL -- 5. Certification Attempts (rows)
        SELECT 6, 'Certification Attempts',
               (SELECT COUNT(*) FROM attempts WHERE k.cohort_id IN (cohort_id, 'ALL')), NULL
        UNION ALL -- 6. Candidate Pass Rate: passed pairs / attempted pairs
        SELECT 7, 'Certification Candidate Pass Rate',
               (SELECT COUNT(*) FROM pairs WHERE passed = 1 AND k.cohort_id IN (cohort_id, 'ALL')),
               (SELECT COUNT(*) FROM pairs WHERE k.cohort_id IN (cohort_id, 'ALL'))
        UNION ALL -- 7. First-Attempt Pass Rate
        SELECT 8, 'First-Attempt Pass Rate',
               (SELECT COUNT(*) FROM attempts WHERE attempt_number = 1 AND result = 'Passed' AND k.cohort_id IN (cohort_id, 'ALL')),
               (SELECT COUNT(*) FROM attempts WHERE attempt_number = 1 AND k.cohort_id IN (cohort_id, 'ALL'))
        UNION ALL -- 8. Mandatory Certifications Met (completed enrolments)
        SELECT 9, 'Mandatory Certifications Met',
               (SELECT COUNT(*) FROM completed WHERE mandatory_passed = mandatory_total AND k.cohort_id IN (cohort_id, 'ALL')), NULL
        UNION ALL -- 9. Unattempted Certification Opportunities (completed x mandatory, no attempt)
        SELECT 10, 'Unattempted Certification Opportunities',
               (SELECT ISNULL(SUM(mandatory_total - mandatory_attempted), 0) FROM completed WHERE k.cohort_id IN (cohort_id, 'ALL')), NULL
        UNION ALL -- 9b. Completers With No Certification Attempt
        SELECT 11, 'Completers With No Certification Attempt',
               (SELECT COUNT(*) FROM completed WHERE mandatory_attempted = 0 AND k.cohort_id IN (cohort_id, 'ALL')), NULL
        UNION ALL -- 10. Reviewed for Readiness
        SELECT 12, 'Reviewed for Readiness',
               (SELECT COUNT(*) FROM completed WHERE latest_decision IS NOT NULL AND k.cohort_id IN (cohort_id, 'ALL')), NULL
        UNION ALL -- 11. Unreviewed Completers
        SELECT 13, 'Unreviewed Completers',
               (SELECT COUNT(*) FROM completed WHERE latest_decision IS NULL AND k.cohort_id IN (cohort_id, 'ALL')), NULL
        UNION ALL -- 12. Ready / Approved (Snapshot): LATEST review = Approved
        SELECT 14, 'Ready / Approved (Snapshot)',
               (SELECT COUNT(*) FROM completed WHERE latest_decision = 'Approved' AND k.cohort_id IN (cohort_id, 'ALL')), NULL
        UNION ALL -- 13. Readiness Approval Rate: approved / latest-reviewed completed
        SELECT 15, 'Readiness Approval Rate',
               (SELECT COUNT(*) FROM completed WHERE latest_decision = 'Approved' AND k.cohort_id IN (cohort_id, 'ALL')),
               (SELECT COUNT(*) FROM completed WHERE latest_decision IS NOT NULL AND k.cohort_id IN (cohort_id, 'ALL'))
        UNION ALL -- 14. Readiness Coverage: approved / ALL completed
        SELECT 16, 'Readiness Coverage',
               (SELECT COUNT(*) FROM completed WHERE latest_decision = 'Approved' AND k.cohort_id IN (cohort_id, 'ALL')),
               (SELECT COUNT(*) FROM completed WHERE k.cohort_id IN (cohort_id, 'ALL'))
    ) AS x
)
SELECT measure, cohort_id, numerator, denominator,
       CASE WHEN denominator IS NULL THEN CAST(numerator AS VARCHAR(12))
            WHEN denominator = 0 THEN '(blank)'                       -- DIVIDE returns BLANK
            ELSE CAST(CAST(100.0 * numerator / denominator AS DECIMAL(5,1)) AS VARCHAR(12)) + '%'
       END AS expected_in_power_bi
FROM m
ORDER BY n, CASE cohort_id WHEN 'ALL' THEN 'Z' ELSE cohort_id END;
