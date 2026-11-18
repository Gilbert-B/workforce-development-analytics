/* ---------------------------------------------------------------------------
   007_reset_build02_objects.sql
   EXPLICIT RESET: removes everything Build 02 added to the database:
     * the six rpt views (006),
     * the Build 01 drop guard trigger (004), dropped first,
     * the six core tables (004).
   Build 01 tables, views and rows are NOT touched.

   When to run it: before rebuilding Build 01 (001_create_schema.sql or
   python/load_to_sql.py) while Build 02 is loaded. Build 02 tables have
   foreign keys to core.enrolment, so Build 01 can't be rebuilt underneath them.

   Full reset in SSMS, in this order:
     007 -> 000 -> 001 -> 002 -> 003 -> validation_queries.sql
         -> 004 -> 005 -> 006 -> build02_validation_queries.sql
   Or in one command:  python python/full_reset.py --server localhost --confirm

   Safe to run any time (everything is IF EXISTS). All data is synthetic and
   is reloaded from the committed CSVs.
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
GO

-- The guard goes FIRST, so the table drops below can never be blocked by it.
DROP TRIGGER IF EXISTS trg_protect_build01_from_partial_drop ON DATABASE;

DROP VIEW IF EXISTS rpt.fact_readiness_review;
DROP VIEW IF EXISTS rpt.fact_certification_attempt;
DROP VIEW IF EXISTS rpt.fact_coaching_action;
DROP VIEW IF EXISTS rpt.fact_watchlist_event;
DROP VIEW IF EXISTS rpt.fact_watchlist_case;
DROP VIEW IF EXISTS rpt.dim_certification;

-- children before parents (foreign keys)
DROP TABLE IF EXISTS core.readiness_review;
DROP TABLE IF EXISTS core.certification_attempt;
DROP TABLE IF EXISTS core.coaching_action;
DROP TABLE IF EXISTS core.watchlist_case_event;
DROP TABLE IF EXISTS core.watchlist_case;
DROP TABLE IF EXISTS core.certification_type;
GO

PRINT 'Build 02 objects removed. Build 01 can now be rebuilt (000 -> 001 -> 002 -> 003).';
GO
