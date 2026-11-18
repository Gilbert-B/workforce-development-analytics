/* ---------------------------------------------------------------------------
   001_create_schema.sql
   Build 01 tables. Two schemas:
     core  - the loaded synthetic records, one table per business record
     rpt   - reporting views for Power BI (created in 002_reporting_views.sql)

   Re-runnable: drops and recreates the core tables. That is safe because
   all Build 01 data is synthetic and can be regenerated and reloaded.

   Constraints document the grain of each table:
     PRIMARY KEY / UNIQUE  -> "one row per ..."
     FOREIGN KEY           -> every reference points at a real record
     CHECK                 -> values a business rule allows
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
GO

IF SCHEMA_ID(N'core') IS NULL EXEC (N'CREATE SCHEMA core');
IF SCHEMA_ID(N'rpt')  IS NULL EXEC (N'CREATE SCHEMA rpt');
GO

-- Drop in reverse dependency order (children before parents).
-- Build 02 tables (if present) reference core.enrolment, so they go first.
-- Reload Build 02 afterwards with 004-006 or python/load_build02_to_sql.py.
DROP TABLE IF EXISTS core.readiness_review;
DROP TABLE IF EXISTS core.certification_attempt;
DROP TABLE IF EXISTS core.coaching_action;
DROP TABLE IF EXISTS core.watchlist_case_event;
DROP TABLE IF EXISTS core.watchlist_case;
DROP TABLE IF EXISTS core.certification_type;
DROP TABLE IF EXISTS core.assessment;
DROP TABLE IF EXISTS core.attendance;
DROP TABLE IF EXISTS core.enrolment_status_event;
DROP TABLE IF EXISTS core.enrolment;
DROP TABLE IF EXISTS core.scheduled_session;
DROP TABLE IF EXISTS core.competency;
DROP TABLE IF EXISTS core.employee;
DROP TABLE IF EXISTS core.cohort;
DROP TABLE IF EXISTS core.data_snapshot;
GO

-- The as-of date the data represents. Exactly one row.
CREATE TABLE core.data_snapshot (
    as_of_date        DATE         NOT NULL PRIMARY KEY,
    seed              INT          NOT NULL,
    generator_version VARCHAR(20)  NOT NULL
);

-- One row per scheduled training cohort.
CREATE TABLE core.cohort (
    cohort_id         VARCHAR(20)  NOT NULL PRIMARY KEY,
    cohort_name       NVARCHAR(50) NOT NULL UNIQUE,
    start_date        DATE         NOT NULL,
    planned_end_date  DATE         NOT NULL,
    planned_weeks     TINYINT      NOT NULL CHECK (planned_weeks BETWEEN 1 AND 52),
    delivery_mode     VARCHAR(20)  NOT NULL CHECK (delivery_mode IN ('In person', 'Virtual')),
    CONSTRAINT ck_cohort_dates CHECK (planned_end_date > start_date)
);

-- One row per synthetic person. Deliberately has NO cohort column:
-- a person can enrol in more than one cohort (see core.enrolment).
CREATE TABLE core.employee (
    employee_id       VARCHAR(20)  NOT NULL PRIMARY KEY,
    first_name        NVARCHAR(50) NOT NULL,
    last_name         NVARCHAR(50) NOT NULL,
    hire_date         DATE         NOT NULL
);

-- One row per core competency on the rubric.
CREATE TABLE core.competency (
    competency_id     VARCHAR(20)  NOT NULL PRIMARY KEY,
    competency_name   NVARCHAR(60) NOT NULL UNIQUE,
    display_order     TINYINT      NOT NULL UNIQUE
);

-- One row per employee per cohort: the link between a person and a cohort.
CREATE TABLE core.enrolment (
    enrolment_id      VARCHAR(20)  NOT NULL PRIMARY KEY,
    employee_id       VARCHAR(20)  NOT NULL REFERENCES core.employee (employee_id),
    cohort_id         VARCHAR(20)  NOT NULL REFERENCES core.cohort (cohort_id),
    enrolled_date     DATE         NOT NULL,
    CONSTRAINT uq_enrolment_employee_cohort UNIQUE (employee_id, cohort_id)
);

-- One row per lifecycle event. effective_date = when the status applies
-- in the business; recorded_at = when someone entered it in the system.
-- In Build 01 each event type can happen at most once per enrolment.
CREATE TABLE core.enrolment_status_event (
    status_event_id   VARCHAR(20)  NOT NULL PRIMARY KEY,
    enrolment_id      VARCHAR(20)  NOT NULL REFERENCES core.enrolment (enrolment_id),
    event_type        VARCHAR(20)  NOT NULL
        CHECK (event_type IN ('enrolled', 'cancelled', 'started', 'withdrawn', 'completed')),
    effective_date    DATE         NOT NULL,
    recorded_at       DATETIME2(0) NOT NULL,
    CONSTRAINT uq_status_event_type UNIQUE (enrolment_id, event_type),
    CONSTRAINT ck_recorded_not_before_effective
        CHECK (CAST(recorded_at AS DATE) >= effective_date)
);

-- One row per planned training session for a cohort.
CREATE TABLE core.scheduled_session (
    session_id        VARCHAR(30)  NOT NULL PRIMARY KEY,
    cohort_id         VARCHAR(20)  NOT NULL REFERENCES core.cohort (cohort_id),
    programme_week    TINYINT      NOT NULL CHECK (programme_week >= 1),
    session_day       TINYINT      NOT NULL CHECK (session_day BETWEEN 1 AND 7),
    session_date      DATE         NOT NULL,
    CONSTRAINT uq_session_cohort_date UNIQUE (cohort_id, session_date)
);

-- One row per RECORDED attendance mark (enrolment x session).
-- A missing row means "not recorded", which is not the same as "Absent".
-- rpt.fact_attendance turns the gaps into explicit 'Unrecorded' rows.
CREATE TABLE core.attendance (
    enrolment_id      VARCHAR(20)  NOT NULL REFERENCES core.enrolment (enrolment_id),
    session_id        VARCHAR(30)  NOT NULL REFERENCES core.scheduled_session (session_id),
    attendance_status VARCHAR(10)  NOT NULL CHECK (attendance_status IN ('Present', 'Absent')),
    recorded_at       DATETIME2(0) NOT NULL,
    CONSTRAINT pk_attendance PRIMARY KEY (enrolment_id, session_id)
);

-- One row per enrolment x competency x programme week x attempt.
CREATE TABLE core.assessment (
    assessment_id     VARCHAR(20)  NOT NULL PRIMARY KEY,
    enrolment_id      VARCHAR(20)  NOT NULL REFERENCES core.enrolment (enrolment_id),
    competency_id     VARCHAR(20)  NOT NULL REFERENCES core.competency (competency_id),
    programme_week    TINYINT      NOT NULL CHECK (programme_week >= 1),
    attempt_number    TINYINT      NOT NULL DEFAULT 1 CHECK (attempt_number >= 1),
    assessment_date   DATE         NOT NULL,
    score             TINYINT      NOT NULL CHECK (score BETWEEN 0 AND 100),
    rubric_version    VARCHAR(10)  NOT NULL,
    recorded_at       DATETIME2(0) NOT NULL,
    CONSTRAINT uq_assessment_grain UNIQUE (enrolment_id, competency_id, programme_week, attempt_number)
);
GO
-- No extra indexes yet: the largest table has ~7k rows. Revisit when the
-- payment-case data (hundreds of thousands of rows) arrives in a later build.

PRINT 'Build 01 core schema created.';
GO
