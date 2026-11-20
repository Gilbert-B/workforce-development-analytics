/* ---------------------------------------------------------------------------
   010_reset_build03_objects.sql
   Removes everything Build 03 added (views, tables, stg/etl objects).
   Run it BEFORE rebuilding Build 01 or Build 02: Build 03 tables reference
   core.enrolment and core.readiness_review. python/full_reset.py runs it first.
   Safe any time (IF EXISTS).
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
GO
DROP VIEW IF EXISTS rpt.dim_graduate, rpt.fact_outcome_window, rpt.graduate_training_record,
                    rpt.fact_agent_day, rpt.fact_qa_check, rpt.fact_qa_review, rpt.fact_case_event, rpt.fact_payment_case,
                    rpt.dim_ops_queue, rpt.dim_agent;
DROP TABLE IF EXISTS core.case_rework, core.qa_error, core.qa_check, core.qa_review,
                     core.case_event, core.case_assignment, core.payment_case,
                     core.deployment, core.ops_agent, core.sla_policy, core.ops_queue,
                     core.case_type, core.ops_team;
DROP TABLE IF EXISTS stg.case_rework, stg.qa_error, stg.qa_check, stg.qa_review,
                     stg.case_event, stg.case_assignment, stg.payment_case, stg.rejected_record;
DROP TABLE IF EXISTS etl.load_run;
GO
PRINT 'Build 03 objects removed.';
GO
