/* ---------------------------------------------------------------------------
   008_create_build03_tables.sql
   Build 03: payment operations. ADDITIVE: no Build 01/02 object changes.
   Needs the HORIZON dataset (Builds 01-02 to 2027-06-30) already loaded:
       python python/full_reset.py --server localhost --confirm --dataset horizon

   Three schemas:
     core  validated operational data (with keys and rules)
     stg   landing area for each ETL batch (same columns, no constraints)
     etl   load log + checkpoint, and rejected documents
   Re-runnable: drops and recreates the Build 03 objects only.
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
GO
IF SCHEMA_ID(N'stg') IS NULL EXEC (N'CREATE SCHEMA stg');
IF SCHEMA_ID(N'etl') IS NULL EXEC (N'CREATE SCHEMA etl');
GO

-- children first
DROP TABLE IF EXISTS core.case_rework, core.qa_error, core.qa_check, core.qa_review,
                     core.case_event, core.case_assignment, core.payment_case,
                     core.deployment, core.ops_agent, core.sla_policy, core.ops_queue,
                     core.case_type, core.ops_team;
DROP TABLE IF EXISTS stg.case_rework, stg.qa_error, stg.qa_check, stg.qa_review,
                     stg.case_event, stg.case_assignment, stg.payment_case, stg.rejected_record;
DROP TABLE IF EXISTS etl.load_run;
GO

/* ---------- reference data (from config, loaded as CSV) ---------- */
CREATE TABLE core.ops_team (
    team_id    VARCHAR(10)  NOT NULL PRIMARY KEY,
    team_name  NVARCHAR(60) NOT NULL UNIQUE
);
CREATE TABLE core.case_type (
    case_type_code VARCHAR(30)  NOT NULL PRIMARY KEY,
    case_type_name NVARCHAR(60) NOT NULL
);
CREATE TABLE core.ops_queue (
    queue_id       VARCHAR(15)  NOT NULL PRIMARY KEY,
    queue_name     NVARCHAR(60) NOT NULL,
    team_id        VARCHAR(10)  NOT NULL REFERENCES core.ops_team (team_id),
    case_type_code VARCHAR(30)  NOT NULL REFERENCES core.case_type (case_type_code)
);
-- One row per case type x priority x policy version: the SLA target in force.
CREATE TABLE core.sla_policy (
    policy_version VARCHAR(10) NOT NULL,
    case_type_code VARCHAR(30) NOT NULL REFERENCES core.case_type (case_type_code),
    priority       CHAR(2)     NOT NULL CHECK (priority IN ('P1', 'P2', 'P3')),
    target_hours   SMALLINT    NOT NULL CHECK (target_hours > 0),
    CONSTRAINT pk_sla_policy PRIMARY KEY (policy_version, case_type_code, priority)
);

/* ---------- people: one agent record per employee ---------- */
-- Graduates link to their QUALIFYING enrolment; tenured agents have none.
CREATE TABLE core.ops_agent (
    agent_id         VARCHAR(10)  NOT NULL PRIMARY KEY,
    employee_id      VARCHAR(20)  NOT NULL UNIQUE,           -- no duplicate agent per person
    enrolment_id     VARCHAR(20)  NULL REFERENCES core.enrolment (enrolment_id),
    agent_type       VARCHAR(10)  NOT NULL CHECK (agent_type IN ('Graduate', 'Tenured')),
    first_name       NVARCHAR(50) NOT NULL,
    last_name        NVARCHAR(50) NOT NULL,
    team_id          VARCHAR(10)  NOT NULL REFERENCES core.ops_team (team_id),
    primary_queue_id VARCHAR(15)  NOT NULL REFERENCES core.ops_queue (queue_id),
    start_date       DATE         NOT NULL,
    exit_date        DATE         NULL,
    exit_reason      VARCHAR(30)  NULL,
    CONSTRAINT ck_agent_enrolment CHECK (
        (agent_type = 'Graduate' AND enrolment_id IS NOT NULL) OR (agent_type = 'Tenured' AND enrolment_id IS NULL)),
    CONSTRAINT ck_agent_exit CHECK (exit_date IS NULL OR exit_date > start_date)
);
CREATE UNIQUE INDEX ux_agent_enrolment ON core.ops_agent (enrolment_id) WHERE enrolment_id IS NOT NULL;

-- One row per deployed enrolment (only Approved readiness can be deployed).
CREATE TABLE core.deployment (
    deployment_id        VARCHAR(20) NOT NULL PRIMARY KEY,
    enrolment_id         VARCHAR(20) NOT NULL UNIQUE REFERENCES core.enrolment (enrolment_id),
    agent_id             VARCHAR(10) NOT NULL UNIQUE REFERENCES core.ops_agent (agent_id),
    readiness_review_id  VARCHAR(20) NOT NULL REFERENCES core.readiness_review (readiness_review_id),
    approved_review_date DATE        NOT NULL,
    deployment_date      DATE        NOT NULL,
    team_id              VARCHAR(10) NOT NULL REFERENCES core.ops_team (team_id),
    queue_id             VARCHAR(15) NOT NULL REFERENCES core.ops_queue (queue_id),
    CONSTRAINT ck_deploy_after_approval CHECK (deployment_date > approved_review_date)
);

/* ---------- cases (loaded by the MongoDB ETL) ---------- */
-- One row per payment-exception case. first_resolved_at and final_resolved_at
-- are BOTH kept: a reopen never erases the first resolution.
CREATE TABLE core.payment_case (
    case_id            VARCHAR(20)  NOT NULL PRIMARY KEY,
    case_type_code     VARCHAR(30)  NOT NULL REFERENCES core.case_type (case_type_code),
    priority           CHAR(2)      NOT NULL CHECK (priority IN ('P1', 'P2', 'P3')),
    channel            VARCHAR(30)  NOT NULL,
    amount_band        VARCHAR(15)  NOT NULL,
    queue_id           VARCHAR(15)  NOT NULL REFERENCES core.ops_queue (queue_id),
    received_at        DATETIME2(0) NOT NULL,
    sla_policy_version VARCHAR(10)  NOT NULL,
    sla_target_hours   SMALLINT     NOT NULL,     -- stored at receipt: later policy changes don't rewrite history
    status             VARCHAR(10)  NOT NULL CHECK (status IN ('open', 'resolved', 'reopened')),
    resolution_code    VARCHAR(40)  NULL,
    first_resolved_at  DATETIME2(0) NULL,
    final_resolved_at  DATETIME2(0) NULL,
    source_updated_at  DATETIME2(0) NOT NULL,     -- MongoDB updated_at (the incremental watermark)
    etl_run_id         INT          NOT NULL,
    CONSTRAINT ck_case_first_after_received CHECK (first_resolved_at IS NULL OR first_resolved_at >= received_at),
    CONSTRAINT ck_case_final_after_first CHECK (final_resolved_at IS NULL OR final_resolved_at >= first_resolved_at),
    -- "resolved" always has a final resolution; an open or reopened case never does
    CONSTRAINT ck_case_resolved_status CHECK (
        (status = 'resolved' AND final_resolved_at IS NOT NULL) OR (status <> 'resolved' AND final_resolved_at IS NULL))
);
CREATE TABLE core.case_assignment (
    case_id        VARCHAR(20)  NOT NULL REFERENCES core.payment_case (case_id),
    assignment_seq TINYINT      NOT NULL,
    agent_id       VARCHAR(10)  NOT NULL REFERENCES core.ops_agent (agent_id),
    assigned_at    DATETIME2(0) NOT NULL,
    CONSTRAINT pk_case_assignment PRIMARY KEY (case_id, assignment_seq)
);
-- Full status history: reopen and re-resolve are NEW events, never edits.
CREATE TABLE core.case_event (
    case_id    VARCHAR(20)  NOT NULL REFERENCES core.payment_case (case_id),
    event_seq  TINYINT      NOT NULL,
    event_type VARCHAR(15)  NOT NULL
        CHECK (event_type IN ('created', 'assigned', 'in_progress', 'pending_info', 'resolved', 'reopened')),
    event_at   DATETIME2(0) NOT NULL,
    agent_id   VARCHAR(10)  NULL REFERENCES core.ops_agent (agent_id),
    CONSTRAINT pk_case_event PRIMARY KEY (case_id, event_seq)
);
-- QA exists only for SAMPLED cases: QA results are not case outcomes.
CREATE TABLE core.qa_review (
    case_id       VARCHAR(20)  NOT NULL PRIMARY KEY REFERENCES core.payment_case (case_id),
    reviewed_at   DATETIME2(0) NOT NULL,
    reviewer_role VARCHAR(30)  NOT NULL,
    score         TINYINT      NOT NULL CHECK (score BETWEEN 0 AND 100),
    passed        BIT          NOT NULL
);
CREATE TABLE core.qa_check (                 -- six weighted checklist items per review
    case_id   VARCHAR(20) NOT NULL REFERENCES core.qa_review (case_id),
    item_code VARCHAR(40) NOT NULL,
    weight    TINYINT     NOT NULL,
    passed    BIT         NOT NULL,
    CONSTRAINT pk_qa_check PRIMARY KEY (case_id, item_code)
);
CREATE TABLE core.qa_error (
    case_id   VARCHAR(20) NOT NULL REFERENCES core.qa_review (case_id),
    error_seq TINYINT     NOT NULL,
    category  VARCHAR(15) NOT NULL CHECK (category IN ('procedural', 'financial', 'compliance')),
    severity  VARCHAR(10) NOT NULL CHECK (severity IN ('minor', 'major', 'critical')),
    CONSTRAINT pk_qa_error PRIMARY KEY (case_id, error_seq)
);
CREATE TABLE core.case_rework (
    case_id    VARCHAR(20)  NOT NULL REFERENCES core.payment_case (case_id),
    rework_seq TINYINT      NOT NULL,
    rework_at  DATETIME2(0) NOT NULL,
    reason     VARCHAR(30)  NOT NULL CHECK (reason IN ('qa_failed', 'customer_reopened')),
    CONSTRAINT pk_case_rework PRIMARY KEY (case_id, rework_seq)
);
GO

/* ---------- staging: one ETL batch at a time (no constraints) ---------- */
SELECT TOP (0) * INTO stg.payment_case    FROM core.payment_case;
SELECT TOP (0) * INTO stg.case_assignment FROM core.case_assignment;
SELECT TOP (0) * INTO stg.case_event      FROM core.case_event;
SELECT TOP (0) * INTO stg.qa_review       FROM core.qa_review;
SELECT TOP (0) * INTO stg.qa_check        FROM core.qa_check;
SELECT TOP (0) * INTO stg.qa_error        FROM core.qa_error;
SELECT TOP (0) * INTO stg.case_rework     FROM core.case_rework;
GO

/* ---------- ETL control ---------- */
-- One row per ETL run. The checkpoint (updated_at, case_id) is saved after
-- EVERY committed batch, so an interrupted run resumes where it stopped.
CREATE TABLE etl.load_run (
    run_id                INT IDENTITY(1, 1) PRIMARY KEY,
    mode                  VARCHAR(12)  NOT NULL CHECK (mode IN ('full', 'incremental')),
    status                VARCHAR(12)  NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at            DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    finished_at           DATETIME2(0) NULL,
    docs_read             INT          NOT NULL DEFAULT 0,
    docs_loaded           INT          NOT NULL DEFAULT 0,
    docs_rejected         INT          NOT NULL DEFAULT 0,
    checkpoint_updated_at DATETIME2(0) NULL,
    checkpoint_case_id    VARCHAR(20)  NULL
);
-- Documents that failed validation: never loaded, always explained.
CREATE TABLE stg.rejected_record (
    rejected_id       INT IDENTITY(1, 1) PRIMARY KEY,
    run_id            INT            NOT NULL REFERENCES etl.load_run (run_id),
    case_id           VARCHAR(40)    NOT NULL,
    reason            VARCHAR(200)   NOT NULL,
    source_updated_at DATETIME2(0)   NULL,
    raw_document      NVARCHAR(MAX)  NOT NULL
);
GO
PRINT 'Build 03 tables created.';
GO
