/* ---------------------------------------------------------------------------
   004_create_build02_tables.sql
   Build 02 source tables: watch-list cases, coaching, certification, readiness.
   ADDITIVE ONLY: no Build 01 table, column or view is changed.

   Run AFTER Build 01 is loaded (000 -> 001 -> 002 -> 003, or load_to_sql.py),
   because these tables point at core.enrolment.

   Re-runnable: drops and recreates the six Build 02 tables only.

   Grain (one row per ...):
     certification_type    certification x policy version
     watchlist_case        support episode for ONE enrolment
     watchlist_case_event  Opened / Closed transition of a case
     coaching_action       completed, documented action for a case
     certification_attempt enrolment x certification x attempt number
     readiness_review      dated readiness decision for an enrolment

   Rules that need another table (e.g. "attempt after completion", "no two
   open cases at once") can't be CHECK constraints; they are tested in
   build02_validation_queries.sql instead.
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
GO

DROP TABLE IF EXISTS core.readiness_review;
DROP TABLE IF EXISTS core.certification_attempt;
DROP TABLE IF EXISTS core.coaching_action;
DROP TABLE IF EXISTS core.watchlist_case_event;
DROP TABLE IF EXISTS core.watchlist_case;
DROP TABLE IF EXISTS core.certification_type;
GO

-- Reference data: one row per certification and policy version.
-- The names are FICTIONAL internal certifications, not regulatory ones.
CREATE TABLE core.certification_type (
    certification_id        VARCHAR(10)  NOT NULL PRIMARY KEY,
    certification_code      VARCHAR(10)  NOT NULL,
    certification_name      NVARCHAR(80) NOT NULL,
    mandatory_for_readiness BIT          NOT NULL,
    pass_mark               TINYINT      NOT NULL CHECK (pass_mark BETWEEN 0 AND 100),
    max_attempts            TINYINT      NOT NULL CHECK (max_attempts >= 1),
    policy_version          VARCHAR(10)  NOT NULL,
    CONSTRAINT uq_certification_code_policy UNIQUE (certification_code, policy_version)
);

-- One support / watch-list episode for one enrolment (never for a person
-- globally: the same person in two cohorts has independent cases).
-- Opening a case is a staff decision, not a dropout prediction.
CREATE TABLE core.watchlist_case (
    watchlist_case_id       VARCHAR(20)  NOT NULL PRIMARY KEY,
    enrolment_id            VARCHAR(20)  NOT NULL REFERENCES core.enrolment (enrolment_id),
    opened_effective_date   DATE         NOT NULL,
    opened_recorded_at      DATETIME2(0) NOT NULL,
    primary_reason_code     VARCHAR(30)  NOT NULL
        CHECK (primary_reason_code IN ('LOW_ATTENDANCE', 'LOW_COMPETENCY', 'DECLINING_SCORES', 'MANUAL_REFERRAL')),
    severity                VARCHAR(10)  NOT NULL CHECK (severity IN ('Low', 'Medium', 'High')),
    trigger_programme_week  TINYINT      NULL CHECK (trigger_programme_week BETWEEN 1 AND 52),
    source_type             VARCHAR(20)  NOT NULL CHECK (source_type IN ('Observed signal', 'Manual referral')),
    policy_version          VARCHAR(10)  NOT NULL,
    CONSTRAINT ck_case_recorded_not_before_opened CHECK (CAST(opened_recorded_at AS DATE) >= opened_effective_date),
    -- a manual referral has no triggering week or signal; an observed signal has both
    CONSTRAINT ck_case_source_consistent CHECK (
        (source_type = 'Manual referral' AND primary_reason_code = 'MANUAL_REFERRAL' AND trigger_programme_week IS NULL)
     OR (source_type = 'Observed signal' AND primary_reason_code <> 'MANUAL_REFERRAL' AND trigger_programme_week IS NOT NULL))
);

-- Case history as events, so a later closure never overwrites the opening.
-- UNIQUE (case, event_type): exactly one Opened and at most one Closed.
CREATE TABLE core.watchlist_case_event (
    watchlist_event_id      VARCHAR(20)  NOT NULL PRIMARY KEY,
    watchlist_case_id       VARCHAR(20)  NOT NULL REFERENCES core.watchlist_case (watchlist_case_id),
    event_type              VARCHAR(10)  NOT NULL CHECK (event_type IN ('Opened', 'Closed')),
    effective_date          DATE         NOT NULL,
    recorded_at             DATETIME2(0) NOT NULL,
    closure_reason          VARCHAR(20)  NULL
        CHECK (closure_reason IN ('Improved', 'Withdrawn', 'Programme ended', 'Administrative')),
    recorded_by_role        VARCHAR(40)  NOT NULL,
    CONSTRAINT uq_case_event_type UNIQUE (watchlist_case_id, event_type),
    CONSTRAINT ck_case_event_recorded CHECK (CAST(recorded_at AS DATE) >= effective_date),
    CONSTRAINT ck_closure_reason_only_on_close CHECK (
        (event_type = 'Closed' AND closure_reason IS NOT NULL)
     OR (event_type = 'Opened' AND closure_reason IS NULL))
);

-- One COMPLETED, documented action. Planned actions are not stored.
-- action_note_code is a controlled code: no free-text comments about people.
CREATE TABLE core.coaching_action (
    coaching_action_id      VARCHAR(20)  NOT NULL PRIMARY KEY,
    watchlist_case_id       VARCHAR(20)  NOT NULL REFERENCES core.watchlist_case (watchlist_case_id),
    action_date             DATE         NOT NULL,
    recorded_at             DATETIME2(0) NOT NULL,
    action_type             VARCHAR(30)  NOT NULL
        CHECK (action_type IN ('1:1 coaching', 'Attendance follow-up', 'Skills practice', 'Supervisor check-in')),
    staff_role              VARCHAR(40)  NOT NULL,
    followup_recommended    BIT          NOT NULL,
    action_note_code        VARCHAR(30)  NOT NULL
        CHECK (action_note_code IN ('NOTE-COACH-GOALS', 'NOTE-ATT-PLAN', 'NOTE-PRACTICE-SET', 'NOTE-SUPERVISOR-REVIEW')),
    CONSTRAINT ck_action_recorded CHECK (CAST(recorded_at AS DATE) >= action_date)
);

-- One ACTUAL attempt. "Not attempted" is the absence of rows, never a row.
CREATE TABLE core.certification_attempt (
    certification_attempt_id VARCHAR(25) NOT NULL PRIMARY KEY,
    enrolment_id            VARCHAR(20)  NOT NULL REFERENCES core.enrolment (enrolment_id),
    certification_id        VARCHAR(10)  NOT NULL REFERENCES core.certification_type (certification_id),
    attempt_number          TINYINT      NOT NULL CHECK (attempt_number >= 1),
    attempt_date            DATE         NOT NULL,
    recorded_at             DATETIME2(0) NOT NULL,
    score                   TINYINT      NOT NULL CHECK (score BETWEEN 0 AND 100),
    result                  VARCHAR(10)  NOT NULL CHECK (result IN ('Passed', 'Failed')),
    policy_version          VARCHAR(10)  NOT NULL,
    CONSTRAINT uq_attempt_grain UNIQUE (enrolment_id, certification_id, attempt_number),
    CONSTRAINT ck_attempt_recorded CHECK (CAST(recorded_at AS DATE) >= attempt_date)
);

-- One explicit readiness DECISION. The gate flags and score are the
-- evidence as it stood at review time; later events never rewrite them.
CREATE TABLE core.readiness_review (
    readiness_review_id     VARCHAR(20)  NOT NULL PRIMARY KEY,
    enrolment_id            VARCHAR(20)  NOT NULL REFERENCES core.enrolment (enrolment_id),
    review_number           TINYINT      NOT NULL CHECK (review_number >= 1),
    review_date             DATE         NOT NULL,
    recorded_at             DATETIME2(0) NOT NULL,
    decision                VARCHAR(10)  NOT NULL CHECK (decision IN ('Approved', 'Deferred')),
    decision_reason_code    VARCHAR(40)  NOT NULL CHECK (decision_reason_code IN (
        'ALL_GATES_MET_SIGNED_OFF', 'CERTIFICATION_PENDING', 'CERTIFICATION_NOT_MET',
        'COMPETENCY_BELOW_THRESHOLD', 'INSUFFICIENT_COMPETENCY_EVIDENCE', 'SIGNOFF_PENDING')),
    reviewer_role           VARCHAR(40)  NOT NULL,
    policy_version          VARCHAR(10)  NOT NULL,
    completion_gate_passed  BIT          NOT NULL,
    certification_gate_passed BIT        NOT NULL,
    competency_gate_passed  BIT          NOT NULL,
    review_competency_score DECIMAL(4,1) NULL CHECK (review_competency_score BETWEEN 0 AND 100),
    signoff_recorded        BIT          NOT NULL,
    CONSTRAINT uq_review_number UNIQUE (enrolment_id, review_number),
    CONSTRAINT ck_review_recorded CHECK (CAST(recorded_at AS DATE) >= review_date),
    -- the core rule: no approval without every gate AND an explicit sign-off
    CONSTRAINT ck_approved_needs_all_evidence CHECK (
        decision = 'Deferred'
     OR (completion_gate_passed = 1 AND certification_gate_passed = 1
         AND competency_gate_passed = 1 AND signoff_recorded = 1)),
    CONSTRAINT ck_decision_reason_consistent CHECK (
        (decision = 'Approved' AND decision_reason_code = 'ALL_GATES_MET_SIGNED_OFF')
     OR (decision = 'Deferred' AND decision_reason_code <> 'ALL_GATES_MET_SIGNED_OFF')),
    -- missing evidence is never a pass (and never imputed as zero)
    CONSTRAINT ck_competency_gate_needs_score CHECK (
        competency_gate_passed = 0 OR review_competency_score IS NOT NULL)
);
GO
-- No extra indexes: the largest Build 02 table has a few hundred rows.

PRINT 'Build 02 core tables created.';
GO
