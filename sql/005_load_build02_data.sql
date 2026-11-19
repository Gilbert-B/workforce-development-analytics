/* ---------------------------------------------------------------------------
   005_load_build02_data.sql
   SSMS route: loads the Build 02 CSVs with BULK INSERT.
   (python/load_build02_to_sql.py does the same job from the command line.)

   BEFORE RUNNING
   1. Build 01 must already be loaded (000 -> 001 -> 002 -> 003).
   2. Run 004_create_build02_tables.sql.
   3. Copy the repo's data\synthetic\build02\*.csv files to a folder SQL Server
      can read, e.g. C:\WorkforceData\build02\ (the SQL Server service account
      reads the files, not you, so avoid C:\Users\... folders).
   4. Set @data_folder below (keep the trailing backslash).

   Re-runnable: empties the six Build 02 tables and reloads them in ONE
   transaction, so a failure part-way leaves the previous rows untouched.
   Build 01 tables are never touched.
   Empty CSV fields load as NULL (e.g. a manual referral has no trigger week).
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;   -- any error rolls back the whole transaction

DECLARE @data_folder NVARCHAR(400) = N'C:\WorkforceData\build02\';   -- <== CHANGE ME

DECLARE @tables TABLE (load_order INT PRIMARY KEY, table_name SYSNAME);
INSERT INTO @tables VALUES
    (1, 'certification_type'), (2, 'watchlist_case'), (3, 'watchlist_case_event'),
    (4, 'coaching_action'), (5, 'certification_attempt'), (6, 'readiness_review');

DECLARE @i INT, @table SYSNAME, @sql NVARCHAR(MAX), @rows INT;

BEGIN TRANSACTION;

SET @i = 6;                                   -- children first when deleting
WHILE @i >= 1
BEGIN
    SELECT @table = table_name FROM @tables WHERE load_order = @i;
    EXEC (N'DELETE FROM core.' + @table);
    SET @i -= 1;
END

SET @i = 1;                                   -- parents first when loading
WHILE @i <= 6
BEGIN
    SELECT @table = table_name FROM @tables WHERE load_order = @i;
    SET @sql = N'BULK INSERT core.' + @table
             + N' FROM ''' + @data_folder + @table + N'.csv'''
             + N' WITH (FORMAT = ''CSV'', FIRSTROW = 2, FIELDTERMINATOR = '','','
             + N' ROWTERMINATOR = ''0x0a'', CHECK_CONSTRAINTS);'
             + N' SELECT @rows_out = COUNT(*) FROM core.' + @table + N';';
    EXEC sp_executesql @sql, N'@rows_out INT OUTPUT', @rows_out = @rows OUTPUT;
    PRINT CONCAT('  loaded ', @rows, ' rows into core.', @table);
    SET @i += 1;
END

COMMIT TRANSACTION;
PRINT 'Build 02 load complete. Next: 006_create_build02_reporting_views.sql, then build02_validation_queries.sql.';
GO
