# Progress summary

*Updated 2026-11-19 · branch `bi/03-payment-operations`*

## Done (built and tested in Claude's environment)
| Area | State |
|---|---|
| Build 01–02: training data, SQL, checks | merged; horizon dataset (2027-06-30) is now the suite default |
| Build 03: MongoDB cases → Python ETL → SQL Server | merged (PR #11). Since then: faster `fact_agent_day`, handover when an agent leaves, two new checks (26/26) |
| Build 04: 30/60/90-day outcomes, training record, retention, proficiency | built (`sql/011`), 14/14 checks |
| Shared semantic model | +8 tables, +12 relationships, +44 measures, generated from the SQL; additive-only check passes; parsed by Microsoft's TMDL library |
| Report 01: Workforce Development & Readiness | unchanged apart from two header captions; now shows the 2027-06-30 numbers |
| Report 02: Payment Operations Performance | 5 pages (overview, ramp-up, quality, Agent 360 drill-through, about); schema- and model-checked |
| Report 03: Workforce Outcomes & Training Effectiveness | 5 pages (overview, effectiveness, roster, Graduate journey drill-through, method); schema- and model-checked |
| One-command build | `python python/build_all.py --server localhost` (about 50 s) |
| Tests | **171 passed** |
| Docs | README, case study, decisions D44–D48, data dictionary (Builds 03–04), validation checkpoints |

## Outstanding
1. **Owner checkpoint A** (Windows pipeline) and **checkpoint B** (all three reports in Power BI Desktop). Neither has been run yet; see `validation_checkpoints.md`.
2. **Screenshots** (checkpoint B4), then embed them in the README and the case study.
3. **Fixes** from the owner's Desktop run, if any, such as a DAX or visual-formatting issue that only Desktop can reveal.
4. **Merge** `bi/03-payment-operations` into `main` once the checkpoints pass.
5. **Website:** publish `docs/case_study.md` on the portfolio site, with the screenshots.

## Key decisions this round
- **Horizon promoted:** a shared model needs one dataset (D45).
- **Training → operations link strengthened** to a realistic, moderate effect (D46). Otherwise Report 03 would have had nothing to show.
- **Proficiency standard:** SLA met ≥ 80% and first-time right ≥ 97% in a 30-day window (D46).
- **Light reports use editable shapes**, not background images (D45).
