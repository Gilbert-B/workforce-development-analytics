/* ---------------------------------------------------------------------------
   003_load_synthetic_data.sql
   Loads the synthetic CSV files into the core tables using BULK INSERT,
   so the whole database can be built from SSMS without Python.
   (python/load_to_sql.py does the same job from the command line.)

   BEFORE RUNNING
   1. Copy the CSV files from the repo's data\synthetic\ folder to a folder
      SQL Server can read, e.g. C:\WorkforceData\
      Why: BULK INSERT is executed by the SQL Server *service* account, not
      by you. That account usually cannot read C:\Users\<you>\... folders.
   2. Set @data_folder below to that folder (keep the trailing backslash).
   3. Run 000, 001 and 002 first.

   Re-runnable: deletes all core rows and reloads them in one transaction,
   so a failure part-way leaves the previous data untouched.
   Requires SQL Server 2017+ (FORMAT = 'CSV').
--------------------------------------------------------------------------- */
USE WorkforceDevAnalytics;
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;   -- any error rolls back the whole transaction

DECLARE @data_folder NVARCHAR(400) = N'C:\WorkforceData\';   -- <== CHANGE ME

-- Tables in load order: parents before children (foreign keys).
DECLARE @tables TABLE (load_order INT PRIMARY KEY, table_name SYSNAME);
INSERT INTO @tables VALUES
    (1, 'data_snapshot'), (2, 'cohort'), (3, 'employee'), (4, 'competency'),
    (5, 'enrolment'), (6, 'enrolment_status_event'), (7, 'scheduled_session'),
    (8, 'attendance'), (9, 'assessment');

DECLARE @i INT, @table SYSNAME, @sql NVARCHAR(MAX), @rows INT;

BEGIN TRANSACTION;

-- 1. Empty the tables, children first (9 down to 1).
SET @i = 9;
WHILE @i >= 1
BEGIN
    SELECT @table = table_name FROM @tables WHERE load_order = @i;
    EXEC (N'DELETE FROM core.' + @table);
    SET @i -= 1;
END

-- 2. Load each CSV, parents first (1 up to 9). BULK INSERT doesn't accept
--    a variable as the file name, so the statement is built as text
--    (dynamic SQL) and then executed. PRINT @sql shows you the result.
SET @i = 1;
WHILE @i <= 9
BEGIN
    SELECT @table = table_name FROM @tables WHERE load_order = @i;
    SET @sql = N'BULK INSERT core.' + @table
             + N' FROM ''' + @data_folder + @table + N'.csv'''
             + N' WITH (FORMAT = ''CSV'', FIRSTROW = 2, FIELDTERMINATOR = '','','
             + N' ROWTERMINATOR = ''0x0a'', CHECK_CONSTRAINTS);'
             + N' SELECT @rows_out = COUNT(*) FROM core.' + @table + N';';
    -- FORMAT 'CSV'      understands quoted fields
    -- FIRSTROW 2        skips the header row
    -- ROWTERMINATOR     the files use LF line endings
    -- (No CODEPAGE: the files are plain ASCII, checked by a test, and
    --  CODEPAGE isn't supported on SQL Server for Linux.)
    -- CHECK_CONSTRAINTS enforces the tables' CHECK rules during the load
    EXEC sp_executesql @sql, N'@rows_out INT OUTPUT', @rows_out = @rows OUTPUT;
    PRINT CONCAT('  loaded ', @rows, ' rows into core.', @table);
    SET @i += 1;
END

COMMIT TRANSACTION;
PRINT 'Load complete. Next: run validation_queries.sql.';
GO
