/* ---------------------------------------------------------------------------
   000_create_database.sql
   Creates the local, fully synthetic Build 01 database if it doesn't exist.
   Engine: SQL Server 2017+ (Express or Developer edition is fine).

   Run from the repository root, e.g. (Windows, SQL Server Express):
       sqlcmd -S .\SQLEXPRESS -E -C -i sql\000_create_database.sql
   Or open this file in SSMS and press Execute.
--------------------------------------------------------------------------- */
IF DB_ID(N'WorkforceDevAnalytics') IS NULL
BEGIN
    CREATE DATABASE WorkforceDevAnalytics;
    PRINT 'Created database WorkforceDevAnalytics.';
END
ELSE
    PRINT 'Database WorkforceDevAnalytics already exists.';
GO
