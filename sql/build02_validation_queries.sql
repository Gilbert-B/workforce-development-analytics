/* ---------------------------------------------------------------------------
   build02_validation_queries.sql
   One query, one row per check (same pattern as validation_queries.sql).
   failing_rows must be 0 for every 'error' check. 'story' checks prove a
   required synthetic storyline exists (1 = missing). 'info' rows are counts.

   These checks recompute the rules from the core tables INDEPENDENTLY of the
   Python generator, so a bug in one is caught by the other.

       sqlcmd -S localhost -E -C -d WorkforceDevAnalytics -i sql\build02_validation_queries.sql
   python/load_build02_to_sql.py runs this automatically after every load.
   (No GO here, so the loader can send it as one batch.)
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
WITH snapshot AS (
    SELECT as_of_date FROM core.data_snapshot
),
life AS (   -- one row per enrolment: lifecycle dates (effective and recorded)
    SELECT
        enrolment_id,
        MAX(CASE WHEN event_type = 'started'   THEN effective_date END) AS started_on,
        MAX(CASE WHEN event_type = 'withdrawn' THEN effective_date END) AS withdrawn_on,
        MAX(CASE WHEN event_type = 'completed' THEN effective_date END) AS completed_on,
        MAX(CASE WHEN event_type = 'completed' THEN recorded_at    END) AS completed_recorded,
        MIN(CASE WHEN event_type IN ('withdrawn', 'completed', 'cancelled') THEN recorded_at END) AS exit_recorded
    FROM core.enrolment_status_event
    GROUP BY enrolment_id
),
cases AS (  -- one row per case with its open/close dates
    SELECT
        c.watchlist_case_id, c.enrolment_id, c.opened_effective_date, c.opened_recorded_at,
        (SELECT COUNT(*) FROM core.watchlist_case_event AS o
         WHERE o.watchlist_case_id = c.watchlist_case_id AND o.event_type = 'Opened') AS opened_events,
        op.effective_date AS opened_event_date,
        cl.effective_date AS closed_on,
        cl.closure_reason
    FROM core.watchlist_case AS c
    LEFT JOIN core.watchlist_case_event AS op
           ON op.watchlist_case_id = c.watchlist_case_id AND op.event_type = 'Opened'
    LEFT JOIN core.watchlist_case_event AS cl
           ON cl.watchlist_case_id = c.watchlist_case_id AND cl.event_type = 'Closed'
),
attempts AS (
    SELECT ca.*, ct.pass_mark, ct.max_attempts, ct.policy_version AS type_policy,
           LAG(ca.result)       OVER (PARTITION BY ca.enrolment_id, ca.certification_id ORDER BY ca.attempt_number) AS prev_result,
           LAG(ca.attempt_date) OVER (PARTITION BY ca.enrolment_id, ca.certification_id ORDER BY ca.attempt_number) AS prev_date
    FROM core.certification_attempt AS ca
    JOIN core.certification_type AS ct ON ct.certification_id = ca.certification_id
),
-- Evidence each review COULD have seen: records entered before the review day.
review_evidence AS (
    SELECT
        r.readiness_review_id,
        CASE WHEN l.completed_recorded < r.review_date THEN 1 ELSE 0 END AS completion_known,
        CASE WHEN NOT EXISTS (
                 SELECT 1 FROM core.certification_type AS ct
                 WHERE ct.mandatory_for_readiness = 1
                   AND NOT EXISTS (SELECT 1 FROM core.certification_attempt AS ca
                                   WHERE ca.enrolment_id = r.enrolment_id
                                     AND ca.certification_id = ct.certification_id
                                     AND ca.result = 'Passed'
                                     AND ca.recorded_at < r.review_date))
             THEN 1 ELSE 0 END AS certifications_known,
        -- latest programme week with EVERY competency scored, entered before the review day
        (SELECT TOP (1) CAST(AVG(CAST(a.score AS DECIMAL(6,2))) AS DECIMAL(4,1))
         FROM core.assessment AS a
         WHERE a.enrolment_id = r.enrolment_id AND a.recorded_at < r.review_date
         GROUP BY a.programme_week
         HAVING COUNT(*) = (SELECT COUNT(*) FROM core.competency)
         ORDER BY a.programme_week DESC) AS latest_full_week_score
    FROM core.readiness_review AS r
    LEFT JOIN life AS l ON l.enrolment_id = r.enrolment_id
),
completed_pop AS (   -- one row per enrolment COMPLETED at the snapshot, with its populations
    SELECT
        d.enrolment_id,
        (SELECT COUNT(*) FROM core.certification_type WHERE mandatory_for_readiness = 1) AS mandatory_total,
        (SELECT COUNT(DISTINCT a.certification_id) FROM core.certification_attempt AS a
         JOIN core.certification_type AS ct ON ct.certification_id = a.certification_id AND ct.mandatory_for_readiness = 1
         WHERE a.enrolment_id = d.enrolment_id) AS pairs_attempted,
        (SELECT COUNT(DISTINCT a.certification_id) FROM core.certification_attempt AS a
         JOIN core.certification_type AS ct ON ct.certification_id = a.certification_id AND ct.mandatory_for_readiness = 1
         WHERE a.enrolment_id = d.enrolment_id AND a.result = 'Passed') AS mandatory_passed,
        (SELECT r.decision FROM rpt.fact_readiness_review AS r
         WHERE r.enrolment_id = d.enrolment_id AND r.is_latest_review = 1) AS latest_decision
    FROM rpt.dim_enrolment AS d
    WHERE d.status_as_of_snapshot = 'Completed'
),
checks AS (
    -- ================= B. relational integrity and chronology =================
    SELECT 'case_outside_enrolment_period' AS check_name, 'error' AS severity,
           (SELECT COUNT(*) FROM cases AS c LEFT JOIN life AS l ON l.enrolment_id = c.enrolment_id
            WHERE l.started_on IS NULL OR c.opened_effective_date < l.started_on
               OR l.exit_recorded <= c.opened_recorded_at) AS failing_rows   -- opened after an exit was on record
    UNION ALL
    SELECT 'case_without_exactly_one_opened_event', 'error',
           (SELECT COUNT(*) FROM cases WHERE opened_events <> 1)
    UNION ALL
    SELECT 'case_opened_event_date_mismatch', 'error',
           (SELECT COUNT(*) FROM cases WHERE opened_event_date <> opened_effective_date)
    UNION ALL
    SELECT 'case_closed_before_opened', 'error',
           (SELECT COUNT(*) FROM cases WHERE closed_on < opened_effective_date)
    UNION ALL
    SELECT 'overlapping_watchlist_cases', 'error',   -- never two open cases at once per enrolment
           (SELECT COUNT(*) FROM cases AS a JOIN cases AS b
              ON b.enrolment_id = a.enrolment_id AND b.watchlist_case_id <> a.watchlist_case_id
             AND b.opened_effective_date >= a.opened_effective_date
            WHERE a.closed_on IS NULL OR b.opened_effective_date <= a.closed_on)
    UNION ALL
    SELECT 'open_case_on_enrolment_with_recorded_exit', 'error',
           (SELECT COUNT(*) FROM cases AS c JOIN life AS l ON l.enrolment_id = c.enrolment_id
            WHERE c.closed_on IS NULL AND l.exit_recorded IS NOT NULL)
    UNION ALL
    SELECT 'coaching_action_outside_its_case', 'error',
           (SELECT COUNT(*) FROM core.coaching_action AS a JOIN cases AS c ON c.watchlist_case_id = a.watchlist_case_id
            WHERE a.action_date < c.opened_effective_date OR a.action_date > c.closed_on)
    UNION ALL
    SELECT 'coaching_action_after_trainee_left', 'error',
           (SELECT COUNT(*) FROM core.coaching_action AS a
            JOIN cases AS c ON c.watchlist_case_id = a.watchlist_case_id
            JOIN life AS l ON l.enrolment_id = c.enrolment_id
            WHERE a.action_date >= l.withdrawn_on OR a.action_date > l.completed_on)
    UNION ALL
    SELECT 'attempt_without_completion_or_not_after_it', 'error',
           (SELECT COUNT(*) FROM attempts AS a LEFT JOIN life AS l ON l.enrolment_id = a.enrolment_id
            WHERE l.completed_on IS NULL OR a.attempt_date <= l.completed_on)
    UNION ALL
    SELECT 'attempt_over_max_attempts', 'error',
           (SELECT COUNT(*) FROM attempts WHERE attempt_number > max_attempts)
    UNION ALL
    SELECT 'attempt_result_disagrees_with_pass_mark', 'error',
           (SELECT COUNT(*) FROM attempts
            WHERE (score >= pass_mark AND result <> 'Passed') OR (score < pass_mark AND result <> 'Failed'))
    UNION ALL
    SELECT 'attempt_numbers_not_consecutive', 'error',
           (SELECT COUNT(*) FROM (SELECT enrolment_id, certification_id FROM core.certification_attempt
                                  GROUP BY enrolment_id, certification_id
                                  HAVING MAX(attempt_number) <> COUNT(*)) AS g)
    UNION ALL
    SELECT 'retake_not_after_a_failed_attempt', 'error',
           (SELECT COUNT(*) FROM attempts
            WHERE attempt_number > 1 AND (prev_result <> 'Failed' OR attempt_date <= prev_date))
    UNION ALL
    SELECT 'attempt_policy_version_mismatch', 'error',
           (SELECT COUNT(*) FROM attempts WHERE policy_version <> type_policy)
    UNION ALL
    SELECT 'review_without_completion_or_not_after_it', 'error',
           (SELECT COUNT(*) FROM core.readiness_review AS r LEFT JOIN life AS l ON l.enrolment_id = r.enrolment_id
            WHERE l.completed_on IS NULL OR r.review_date <= l.completed_on)
    UNION ALL
    SELECT 'review_numbers_not_consecutive', 'error',
           (SELECT COUNT(*) FROM (SELECT enrolment_id FROM core.readiness_review
                                  GROUP BY enrolment_id HAVING MAX(review_number) <> COUNT(*)) AS g)
    UNION ALL
    SELECT 'reviews_out_of_date_order', 'error',
           (SELECT COUNT(*) FROM core.readiness_review AS a JOIN core.readiness_review AS b
              ON b.enrolment_id = a.enrolment_id AND b.review_number = a.review_number + 1
            WHERE b.review_date <= a.review_date)
    UNION ALL
    SELECT 'approved_without_all_gates_and_signoff', 'error',
           (SELECT COUNT(*) FROM core.readiness_review
            WHERE decision = 'Approved'
              AND (completion_gate_passed = 0 OR certification_gate_passed = 0
                   OR competency_gate_passed = 0 OR signoff_recorded = 0))
    UNION ALL
    SELECT 'review_gates_disagree_with_recorded_evidence', 'error',
           (SELECT COUNT(*) FROM core.readiness_review AS r
            JOIN review_evidence AS ev ON ev.readiness_review_id = r.readiness_review_id
            WHERE r.completion_gate_passed    <> ev.completion_known
               OR r.certification_gate_passed <> ev.certifications_known
               OR ISNULL(r.review_competency_score, -1) <> ISNULL(ev.latest_full_week_score, -1))
    UNION ALL
    -- The threshold lives in config, not SQL. Check it was applied CONSISTENTLY:
    -- every score that passed the gate is above every score that failed it.
    SELECT 'competency_gate_applied_inconsistently', 'error',
           (SELECT COUNT(*) FROM (SELECT policy_version FROM core.readiness_review
                                  WHERE review_competency_score IS NOT NULL
                                  GROUP BY policy_version
                                  HAVING MAX(CASE WHEN competency_gate_passed = 0 THEN review_competency_score END)
                                      >= MIN(CASE WHEN competency_gate_passed = 1 THEN review_competency_score END)) AS g)
    UNION ALL
    SELECT 'records_after_snapshot_date', 'error',
           (SELECT COUNT(*) FROM core.watchlist_case, snapshot
            WHERE opened_effective_date > as_of_date OR CAST(opened_recorded_at AS DATE) > as_of_date)
         + (SELECT COUNT(*) FROM core.watchlist_case_event, snapshot
            WHERE effective_date > as_of_date OR CAST(recorded_at AS DATE) > as_of_date)
         + (SELECT COUNT(*) FROM core.coaching_action, snapshot
            WHERE action_date > as_of_date OR CAST(recorded_at AS DATE) > as_of_date)
         + (SELECT COUNT(*) FROM core.certification_attempt, snapshot
            WHERE attempt_date > as_of_date OR CAST(recorded_at AS DATE) > as_of_date)
         + (SELECT COUNT(*) FROM core.readiness_review, snapshot
            WHERE review_date > as_of_date OR CAST(recorded_at AS DATE) > as_of_date)
    UNION ALL
    SELECT 'certification_or_review_in_unfinished_cohort', 'error',
           (SELECT COUNT(*) FROM rpt.dim_cohort AS dc
            JOIN core.enrolment AS e ON e.cohort_id = dc.cohort_id
            WHERE dc.schedule_status <> 'Finished'
              AND (EXISTS (SELECT 1 FROM core.certification_attempt AS ca WHERE ca.enrolment_id = e.enrolment_id)
                OR EXISTS (SELECT 1 FROM core.readiness_review AS r WHERE r.enrolment_id = e.enrolment_id)))

    -- ================= C. reconciliations (core vs reporting views) =================
    UNION ALL
    SELECT 'open_cases_not_total_minus_closed', 'error',
           ABS((SELECT COUNT(*) FROM rpt.fact_watchlist_case WHERE is_open_at_snapshot = 1)
               - ((SELECT COUNT(*) FROM core.watchlist_case)
                  - (SELECT COUNT(*) FROM core.watchlist_case_event AS ev, snapshot
                     WHERE ev.event_type = 'Closed' AND ev.effective_date <= as_of_date)))
    UNION ALL
    SELECT 'coaching_actions_not_counted_exactly_once', 'error',
           ABS((SELECT COUNT(*) FROM core.coaching_action) - (SELECT COUNT(*) FROM rpt.fact_coaching_action))
         + ABS((SELECT COUNT(*) FROM core.coaching_action) - (SELECT SUM(action_count) FROM rpt.fact_watchlist_case))
    UNION ALL
    SELECT 'attempts_not_counted_exactly_once', 'error',
           ABS((SELECT COUNT(*) FROM core.certification_attempt) - (SELECT COUNT(*) FROM rpt.fact_certification_attempt))
    UNION ALL
    SELECT 'not_exactly_one_latest_review_per_reviewed_enrolment', 'error',
           (SELECT COUNT(*) FROM (SELECT enrolment_id FROM rpt.fact_readiness_review
                                  GROUP BY enrolment_id HAVING SUM(is_latest_review) <> 1) AS g)

    -- ================= KPI populations: each split must add back up to its whole =================
    -- (unactioned, unattempted and unreviewed are reported separately, never dropped)
    UNION ALL
    SELECT 'population_cases_actioned_plus_unactioned', 'error',
           ABS((SELECT COUNT(*) FROM core.watchlist_case)
               - (SELECT COUNT(*) FROM rpt.fact_watchlist_case WHERE has_action = 1)
               - (SELECT COUNT(*) FROM rpt.fact_watchlist_case WHERE has_action = 0))
    UNION ALL
    SELECT 'population_completed_by_certification_status', 'error',
           ABS((SELECT COUNT(*) FROM completed_pop)
               - (SELECT COUNT(*) FROM completed_pop WHERE mandatory_passed = mandatory_total)
               - (SELECT COUNT(*) FROM completed_pop WHERE mandatory_passed > 0 AND mandatory_passed < mandatory_total)
               - (SELECT COUNT(*) FROM completed_pop WHERE mandatory_passed = 0 AND pairs_attempted > 0)
               - (SELECT COUNT(*) FROM completed_pop WHERE pairs_attempted = 0))
    UNION ALL
    SELECT 'population_completed_by_latest_review', 'error',
           ABS((SELECT COUNT(*) FROM completed_pop)
               - (SELECT COUNT(*) FROM completed_pop WHERE latest_decision = 'Approved')
               - (SELECT COUNT(*) FROM completed_pop WHERE latest_decision = 'Deferred')
               - (SELECT COUNT(*) FROM completed_pop WHERE latest_decision IS NULL))
    UNION ALL
    SELECT 'population_pairs_attempted_plus_unattempted', 'error',
           ABS((SELECT COUNT(*) FROM completed_pop) * (SELECT COUNT(*) FROM core.certification_type
                                                       WHERE mandatory_for_readiness = 1)
               - (SELECT SUM(pairs_attempted) FROM completed_pop)
               - (SELECT SUM(mandatory_total - pairs_attempted) FROM completed_pop))

    -- ================= required synthetic storylines (1 = missing) =================
    UNION ALL
    SELECT 'story_coached_case_closed_as_improved', 'story',
           CASE WHEN EXISTS (SELECT 1 FROM rpt.fact_watchlist_case WHERE has_action = 1 AND closure_reason = 'Improved') THEN 0 ELSE 1 END
    UNION ALL
    SELECT 'story_coached_case_ended_without_improvement', 'story',
           CASE WHEN EXISTS (SELECT 1 FROM rpt.fact_watchlist_case
                             WHERE has_action = 1 AND closure_reason IN ('Withdrawn', 'Programme ended')) THEN 0 ELSE 1 END
    UNION ALL
    SELECT 'story_case_not_yet_actioned', 'story',
           CASE WHEN EXISTS (SELECT 1 FROM rpt.fact_watchlist_case WHERE has_action = 0) THEN 0 ELSE 1 END
    UNION ALL
    SELECT 'story_enrolment_with_two_episodes', 'story',
           CASE WHEN EXISTS (SELECT 1 FROM rpt.fact_watchlist_case WHERE episode_number >= 2) THEN 0 ELSE 1 END
    UNION ALL
    SELECT 'story_failed_then_passed_on_retake', 'story',
           CASE WHEN EXISTS (SELECT 1 FROM rpt.fact_certification_attempt WHERE is_retake = 1 AND is_passed = 1) THEN 0 ELSE 1 END
    UNION ALL
    SELECT 'story_failed_every_allowed_attempt', 'story',
           CASE WHEN EXISTS (SELECT 1 FROM rpt.fact_certification_attempt AS a JOIN core.certification_type AS ct
                               ON ct.certification_id = a.certification_id
                             WHERE a.pair_passed = 0 AND a.pair_attempt_count = ct.max_attempts) THEN 0 ELSE 1 END
    UNION ALL
    SELECT 'story_completed_without_any_attempt', 'story',
           CASE WHEN EXISTS (SELECT 1 FROM life AS l WHERE l.completed_on IS NOT NULL
                               AND NOT EXISTS (SELECT 1 FROM core.certification_attempt AS ca
                                               WHERE ca.enrolment_id = l.enrolment_id)) THEN 0 ELSE 1 END
    UNION ALL
    SELECT 'story_completed_but_not_reviewed', 'story',
           CASE WHEN EXISTS (SELECT 1 FROM life AS l WHERE l.completed_on IS NOT NULL
                               AND NOT EXISTS (SELECT 1 FROM core.readiness_review AS r
                                               WHERE r.enrolment_id = l.enrolment_id)) THEN 0 ELSE 1 END
    UNION ALL
    SELECT 'story_latest_review_deferred', 'story',
           CASE WHEN EXISTS (SELECT 1 FROM rpt.fact_readiness_review
                             WHERE is_latest_review = 1 AND decision = 'Deferred') THEN 0 ELSE 1 END
    UNION ALL
    SELECT 'story_approved_after_earlier_deferral', 'story',
           CASE WHEN EXISTS (SELECT 1 FROM core.readiness_review AS a JOIN core.readiness_review AS d
                               ON d.enrolment_id = a.enrolment_id AND d.review_number < a.review_number
                             WHERE a.decision = 'Approved' AND d.decision = 'Deferred') THEN 0 ELSE 1 END
    UNION ALL
    SELECT 'story_in_progress_cohort_has_open_cases', 'story',
           CASE WHEN NOT EXISTS (SELECT 1 FROM rpt.dim_cohort WHERE schedule_status = 'In progress') THEN 0  -- no cohort in training at this snapshot (e.g. the 2027 horizon)
                WHEN EXISTS (SELECT 1 FROM rpt.fact_watchlist_case AS c JOIN rpt.dim_cohort AS dc
                               ON dc.cohort_id = c.cohort_id
                             WHERE dc.schedule_status = 'In progress' AND c.is_open_at_snapshot = 1) THEN 0 ELSE 1 END

    -- ================= informational =================
    UNION ALL
    SELECT 'info_open_watchlist_enrolments_at_snapshot', 'info',
           (SELECT COUNT(DISTINCT enrolment_id) FROM rpt.fact_watchlist_case WHERE is_open_at_snapshot = 1)
    UNION ALL
    SELECT 'info_cases_opened_after_unrecorded_withdrawal', 'info',   -- staff could not know yet
           (SELECT COUNT(*) FROM cases AS c JOIN life AS l ON l.enrolment_id = c.enrolment_id
            WHERE l.withdrawn_on <= c.opened_effective_date)
    UNION ALL
    SELECT 'info_cases_without_any_action', 'info',
           (SELECT COUNT(*) FROM rpt.fact_watchlist_case WHERE has_action = 0)
    UNION ALL
    SELECT 'info_completed_without_any_attempt', 'info',
           (SELECT COUNT(*) FROM completed_pop WHERE pairs_attempted = 0)
    UNION ALL
    SELECT 'info_completed_mandatory_pairs_not_attempted', 'info',
           (SELECT SUM(mandatory_total - pairs_attempted) FROM completed_pop)
    UNION ALL
    SELECT 'info_completed_not_reviewed', 'info',
           (SELECT COUNT(*) FROM completed_pop WHERE latest_decision IS NULL)
    UNION ALL
    SELECT 'info_build01_enrolments', 'info', (SELECT COUNT(*) FROM core.enrolment)
    UNION ALL
    SELECT 'info_build01_assessment_rows', 'info', (SELECT COUNT(*) FROM core.assessment)
)
SELECT check_name, severity, failing_rows,
       CASE WHEN severity = 'info' THEN 'INFO'
            WHEN failing_rows = 0  THEN 'PASS'
            ELSE 'FAIL' END AS result
FROM checks
ORDER BY CASE severity WHEN 'error' THEN 0 WHEN 'story' THEN 1 ELSE 2 END, check_name;
