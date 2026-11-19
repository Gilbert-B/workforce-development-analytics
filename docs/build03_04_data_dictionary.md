# Data dictionary: Builds 03–04 (operations and outcomes)

These views feed Reports 02 and 03. Source tables are in `sql/008_create_build03_tables.sql`; views are in `sql/009_create_build03_reporting_views.sql` (Build 03) and `sql/011_create_build04_outcome_views.sql` (Build 04). "Snapshot" is `core.data_snapshot.as_of_date` (2027-06-30), and "now" means the end of that day.

## Source: MongoDB `wda_ops.payment_cases` (one document per case)
- **Identity and case details:** `_id`, `case_type`, `priority`, `channel`, `amount_band`, `received_at`, `queue`, `sla {policy_version, target_hours}`.
- **Nested arrays:** `assignments[]`, `events[]`, `qa {checklist[6], errors[]}` and `rework[]`.
- **Resolution:** `resolution {first_resolved_at, final_resolved_at}`.
- **Load tracking:** `status` and `updated_at`.
- **Into SQL:** the ETL flattens each document into `core.payment_case` + `case_assignment`, `case_event`, `qa_review`, `qa_check`, `qa_error` and `case_rework`.
- **Replacement:** each case is replaced as a whole on every load.

## Build 03 views (Report 02)

| View | Grain / key | Notes |
|---|---|---|
| `rpt.dim_agent` | agent (`agent_id`) | 109 graduates (`AG-G…`, with `enrolment_id`, `cohort_id`) and 40 tenured agents (`AG-T…`, no enrolment). `is_active_at_snapshot`, `exit_date` / `exit_reason` (observed only) |
| `rpt.dim_ops_queue` | queue (`queue_id`) | 5 queues, each with one case type, in 3 teams |
| `rpt.fact_payment_case` | case (`case_id`) | **Credited agent** = latest resolver, else the latest assignee. `due_at = received_at + target`. `sla_met` is 1/0 for resolved cases and **NULL when open**. `is_open` and `is_overdue_open` are at the snapshot. `first_time_right = resolved and no rework`. `qa_passed` is **NULL if not sampled**. `tenure_band` / `tenure_band_order` = days from the agent's start to `received_date` (0-30, 31-60, 61-90, 90+, Tenured). `received_month` is the trend axis |
| `rpt.fact_case_event` | case × `event_seq` | Full history; a reopen adds events and never overwrites. Not imported into Power BI |
| `rpt.fact_qa_review` | sampled case | `score` 0–100, `passed` (≥ 85), `error_count`, `has_critical_error`, `reviewed_date` / `reviewed_month` |
| `rpt.fact_qa_check` | sampled case × checklist item | 6 weighted items (weights total 100); `passed` 1/0 |
| `rpt.fact_agent_day` | agent × day worked | Days = scheduled weekdays in employment **plus** any day with activity (`is_scheduled_day = 0` for weekend cover). Received / resolved / SLA-met / QA counts that day. Built in one pass from the core tables, for speed |

## Build 04 views (Report 03)

| View | Grain / key | Notes |
|---|---|---|
| `rpt.graduate_training_record` | deployed enrolment | `final_competency_score` (latest week with all 5 competencies), `attendance_rate_pct` (present ÷ recorded), `certified_first_attempt` (both mandatory certifications passed at attempt 1), `watchlisted_in_training`, `coaching_actions`, `readiness_reviews` |
| `rpt.fact_outcome_window` | graduate × window (1, 2, 3) | Windows are days 1-30, 31-60 and 61-90 from the agent's `start_date`, as [start, end). `window_status`: Complete, Not yet reached, or Left before window end. **Metrics are NULL unless Complete**. `is_proficient` = SLA met ≥ 80% **and** first-time right ≥ 97%, using the rounded percentages shown |
| `rpt.dim_graduate` | graduate agent (`agent_id`) | Training record + deployment + `competency_band` (thirds by final competency), `retained_90_days` (1 / 0 / NULL if day 90 not reached), `proficiency_status`, `days_to_proficiency` (30 / 60 / 90, else NULL) |

## Model relationships added (all one-to-many, single direction)

| From (many side) | To (one side) |
|---|---|
| `fact_payment_case`, `fact_qa_review`, `fact_qa_check`, `fact_agent_day` | `dim_agent` (`agent_id`) |
| `fact_payment_case`, `fact_qa_review`, `fact_qa_check` | `dim_ops_queue` (`queue_id`) |
| `fact_payment_case.received_date`, `fact_qa_review.reviewed_date`, `fact_qa_check.reviewed_date`, `fact_agent_day.work_date` | `dim_date` |
| `fact_outcome_window`, `fact_payment_case`, `fact_agent_day` | `dim_graduate` (`agent_id`; tenured agents have no `dim_graduate` row) |

**No relationship joins the training facts (Report 01) to the operations facts.** The link between them is `dim_graduate`, built in SQL. Benchmark measures (`… (Tenured Benchmark)`) remove `dim_agent`, `dim_graduate` and tenure-band filters, but keep queue, team, priority and date filters.

## Measure semantics (selected)

| Measure | Definition |
|---|---|
| SLA Met % | `SUM(sla_met) / COUNT(sla_met)`: resolved cases only, because open cases are blank |
| First-Time-Right % | resolved with no rework ÷ resolved |
| QA Pass % | passed ÷ reviews (sampled cases only) |
| Resolved per Agent-Day | resolved (by resolution date) ÷ days worked |
| 90-Day Retention % | `retained_90_days` = 1 ÷ graduates who have reached day 90 |
| Proficient by Day 90 % | retained to day 90 **and** proficient in any window ÷ retained to day 90 |
| Window … % | sums over complete windows only (incomplete windows are blank) |
