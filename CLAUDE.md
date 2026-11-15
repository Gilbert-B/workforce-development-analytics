# Working agreement for this repository

Standing rules for anyone, human or AI, implementing changes here.

## Purpose
This is a portfolio project **and** a hands-on skills project. The owner must be able to run, inspect, modify, troubleshoot and explain every part of it. Working, understandable code matters more than sophistication.

## Roles
- **Owner:** makes the decisions, builds the Power BI report, and runs everything locally.
- **ChatGPT:** BI architecture, business rules, KPI semantics, data model, DAX and report UX review.
- **Claude Code:** implements *approved* Python, SQL, tests, repository and (later) website work. Doesn't redesign approved business rules; raises concerns instead.

## Every significant implementation must include
1. **Why:** in 2–4 sentences, the problem it solves, why this approach, the main trade-off, and what would change at scale. Put it in `docs/decisions.md`.
2. **Exact commands** to run it on the owner's Windows machine, with prerequisites.
3. **What you should see:** expected output, row counts, test results, and a query to verify the result.
4. **Evidence, reported honestly:** commands actually run and their real output. Say where they were run (Claude's environment or the owner's machine).
5. **Readable code:** clear names, comments on non-obvious logic, no unnecessary frameworks. One synthetic record must be traceable from generation to reporting output (`sql/trace_one_enrolment.sql`).
6. **Data contracts:** grain, keys, joins, nulls, dates and uniqueness, documented in `docs/data_dictionary.md`.
7. **Occasional small practical exercise:** optional and never blocking. Then review the owner's attempt.

Teach at the point of use. No long theory.

## Update format
**Built** · **Reason** · **Run it yourself** · **What you should see** · **One concept to understand** · **Decisions needed / next slice** (blockers only)

## Scope and privacy
- Implement only the approved build slice. Later capabilities (MongoDB, payment cases, certification and readiness, 90-day performance, website) need their own approval.
- **All data is synthetic.** Never add original or client Power BI files, queries, connection details, identifiers or personal data. `.gitignore` blocks Power BI files and private working documents by default.
- No credentials in the repository; use environment variables (`.env.example`).
- Keep the "original project" vs "portfolio edition" distinction accurate in all text.

## Before committing
- `python python/generate_synthetic_data.py`: committed CSVs must match (`git status` shows no change)
- `python -m pytest`: generator tests
- With SQL Server: `python python/load_to_sql.py --server ...` → all checks OK, then `python -m pytest tests/test_sql_integration.py`
- Update `docs/build_log.md` reference numbers if the data changed
