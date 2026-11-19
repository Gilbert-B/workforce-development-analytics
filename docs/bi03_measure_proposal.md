# BI-03 measure and relationship proposal (FOR REVIEW: not implemented)

**Branch:** `bi/03-payment-operations`, from `main` at `ec62743` (the Build 03 merge).
**Scope:** Report 02 (Payment Operations) on the shared semantic model. No model, DAX or report file has changed yet.
**Reference values:** `sql/bi03_measure_reference.sql`. It computes every measure from the **core tables**, not from the `rpt` view flags the DAX uses. Claude's environment, horizon dataset, 2027-06-30.

---

## 0. Data-layer fixes made while preparing this (routine; flagged for visibility)
1. **`rpt.fact_agent_day` took minutes to run.** It was stacked on `fact_payment_case` / `fact_qa_review`, and SQL Server re-evaluated those views inside it. A Power BI import would have been just as slow. It's now rebuilt in one pass from the core tables; the full validation run takes 3 s.
2. **Weekend work.** Resolution time runs on the clock, so 16% of final resolutions land on a Saturday or Sunday. The agent-day grid held weekdays only, so productivity lost 8,162 resolutions. The grid now has scheduled weekdays **plus** any day with recorded activity, flagged `is_scheduled_day = 0`.
3. **24 resolutions by agents after their exit date** (amendment 8). In the generator, a teammate on the same queue now takes the case over: a new `assigned` event is added, and the history is kept. A new check, `event_by_agent_outside_employment`, guards it, and so does `agent_day_misses_cases`. Build 03 checks: **26 of 26**.
4. **`tenure_band_order`** (1–5) was added to `fact_payment_case` and `fact_qa_review`, so the bands sort correctly.

Headline totals are unchanged (50,035 cases; 249 open; 19 overdue). Agent attribution moved for 24 cases.

---

## 1. Decision needed first: promote the horizon dataset (planned under E1)
**Why it's forced:** Reports 01 and 02 share **one** model, which points at **one** database. Once the Build 03 tables are in the model, refreshing against the baseline database fails, because those tables don't exist there.

**Recommendation:** promote the 2027-06-30 horizon as the suite default now, as `build03_spec.md` §2 planned once Build 03 passed. This means:
- `full_reset.py` defaults to `horizon`. `--dataset baseline` stays available, and the frozen numbers stay documented.
- Report 01's structure is unchanged, but its numbers move to the horizon: **Active 0 · Completed 189 · Total enrolments 208** (baseline was 71 / 127 / 208). All three cohorts are complete, so Report 01 tells a completed-programme story. Its "in progress" cohort story becomes history.
- Report 01's reference values get re-validated once, in the BI-03 owner run.

**Alternative:** two databases and two models. This reverses ARCH-01 (one shared model). Not recommended.

---

## 2. Relationships (all one-to-many, single direction, active; no orphans or NULL keys, verified)
| One side | Many side | Key | Rows (many) |
|---|---|---|---|
| `rpt dim_agent` (149, unique) | `rpt fact_payment_case` | `agent_id` | 50,035 |
| `rpt dim_agent` | `rpt fact_qa_review` | `agent_id` | 5,676 |
| `rpt dim_agent` | `rpt fact_agent_day` | `agent_id` | 32,342 |
| `rpt dim_ops_queue` (5) | `rpt fact_payment_case` | `queue_id` | 50,035 |
| `rpt dim_ops_queue` | `rpt fact_qa_review` | `queue_id` | 5,676 |
| `rpt dim_date` | `rpt fact_payment_case` | `received_date` | |
| `rpt dim_date` | `rpt fact_qa_review` | `reviewed_date` | |
| `rpt dim_date` | `rpt fact_agent_day` | `work_date` | |

**Not added:**
- **`dim_agent → dim_enrolment`.** A cohort link belongs to Report 03 (BI-04); `cohort_id` stays a label on `dim_agent`.
- **`fact_case_event`** is not imported in BI-03, because no visual needs event-level history yet.
- **The existing 14 relationships** are unchanged. `dim_date` already filters attendance and assessment; there is no path between the Report 01 and Report 02 facts, so no ambiguity.

**Date roles (decision B1):**
- **Case measures are dated by the day the case was received.** "SLA met % in March" means: of the cases received in March and since resolved, the share resolved within SLA.
- **QA measures are dated by review date.**
- **Productivity is dated by the day worked.**

The alternative is an inactive `final_resolved_date` relationship plus `USERELATIONSHIP` measures. That's more measures for little gain, because `fact_agent_day` already gives resolutions by resolution date.

**Queue filter caveat:** a queue slicer filters cases and QA, but not `fact_agent_day`, which has no queue. Productivity visuals use `dim_agent[primary_queue_name]` / `team_name` instead.

---

## 3. Measures (DAX drafts)
**Rules:**
- **Counts** are wrapped in `COALESCE(…, 0)`, so cards show 0 instead of blank.
- **Ratios** use `DIVIDE`, so an empty denominator shows blank.
- **Status flags** use `KEEPFILTERS`, which respects a user's own selection.
- **"(Snapshot)"** marks values as at 2027-06-30.

### Cases (home table `rpt fact_payment_case`)
```dax
Cases Received = COALESCE ( COUNTROWS ( 'rpt fact_payment_case' ), 0 )

Cases Resolved =
COALESCE ( CALCULATE ( COUNTROWS ( 'rpt fact_payment_case' ),
                       KEEPFILTERS ( 'rpt fact_payment_case'[is_open] = 0 ) ), 0 )

Open Cases (Snapshot) =
COALESCE ( CALCULATE ( COUNTROWS ( 'rpt fact_payment_case' ),
                       KEEPFILTERS ( 'rpt fact_payment_case'[is_open] = 1 ) ), 0 )

Overdue Open Cases (Snapshot) =
COALESCE ( CALCULATE ( COUNTROWS ( 'rpt fact_payment_case' ),
                       KEEPFILTERS ( 'rpt fact_payment_case'[is_overdue_open] = 1 ) ), 0 )

-- sla_met is blank for open cases; COUNT ignores blanks, so the denominator is resolved cases only
SLA Met % =
DIVIDE ( SUM ( 'rpt fact_payment_case'[sla_met] ), COUNT ( 'rpt fact_payment_case'[sla_met] ) )

First-Time-Right % =
DIVIDE ( SUM ( 'rpt fact_payment_case'[first_time_right] ), [Cases Resolved] )

Avg Resolution Hours = AVERAGE ( 'rpt fact_payment_case'[final_resolution_hours] )

-- share of RESOLVED cases picked for QA (both sides dated by received date)
QA Sample Rate % =
DIVIDE ( CALCULATE ( COUNTROWS ( 'rpt fact_payment_case' ),
                     KEEPFILTERS ( 'rpt fact_payment_case'[qa_sampled] = 1 ) ),
         [Cases Resolved] )
```

### QA (home table `rpt fact_qa_review`; sampled cases only)
```dax
QA Reviews = COALESCE ( COUNTROWS ( 'rpt fact_qa_review' ), 0 )
QA Pass % = DIVIDE ( SUM ( 'rpt fact_qa_review'[passed] ), COUNTROWS ( 'rpt fact_qa_review' ) )
Avg QA Score = AVERAGE ( 'rpt fact_qa_review'[score] )
QA Critical Error % = DIVIDE ( SUM ( 'rpt fact_qa_review'[has_critical_error] ), COUNTROWS ( 'rpt fact_qa_review' ) )
```

### Agents and productivity
```dax
Active Agents (Snapshot) =
COALESCE ( CALCULATE ( COUNTROWS ( 'rpt dim_agent' ),
                       KEEPFILTERS ( 'rpt dim_agent'[is_active_at_snapshot] = 1 ) ), 0 )

Agent-Days Worked = COALESCE ( COUNTROWS ( 'rpt fact_agent_day' ), 0 )

Resolved per Agent-Day =
DIVIDE ( SUM ( 'rpt fact_agent_day'[cases_resolved] ), COUNTROWS ( 'rpt fact_agent_day' ) )
```

**Sort-by and formats:**
- `tenure_band` sorts by `tenure_band_order`.
- `%` measures display with 1 decimal place; hours and per-day values with 1–2 decimals.

---

## 4. Expected values (`sql/bi03_measure_reference.sql`; the views agree exactly)
| Measure | All | 0-30 d | 31-60 d | 61-90 d | 90+ d | Tenured |
|---|---|---|---|---|---|---|
| Cases Received | 50,035 | 3,370 | 3,824 | 3,974 | 19,843 | 19,024 |
| Cases Resolved | 49,786 | 3,370 | 3,824 | 3,974 | 19,661 | 18,957 |
| SLA Met % | **82.6** | 74.5 | 79.6 | 80.7 | 83.3 | 84.2 |
| First-Time-Right % | **97.9** | 95.6 | 96.8 | 97.6 | 98.0 | 98.3 |
| Avg Resolution Hours | 26.5 | 33.9 | 30.0 | 28.0 | 25.6 | 25.0 |
| QA Reviews | 5,676 | 859 | 601 | 374 | 1,915 | 1,927 |
| QA Pass % | **96.5** | 92.7 | 96.7 | 97.3 | 96.9 | 97.6 |

**Totals for all cases:**
- **Snapshot:** Open Cases 249; Overdue Open Cases 19.
- **QA:** Sample Rate 11.4%; Avg QA Score 98.4; Critical Error 2.6%.
- **Agents and productivity:** Active Agents 138 (99 graduates); Agent-Days Worked 32,342; Resolved per Agent-Day 1.54 (graduates 1.49, tenured 1.63).

**By queue:** SLA Met % ranges from Q-SCREEN 78.3% (2-hour P1 target) to Q-VALIDATE 83.8%. All five queues are in the reference SQL output.

**Note on the walkthrough table:** its first-time-right column averaged over *all* cases, open ones included (Tenured 98.0%). The measure above uses resolved cases only (98.3%), which is the correct denominator.

---

## 5. Report 02 pages (light, after the measures are approved)
1. **Operations overview:**
   - cards: Cases Received, SLA Met %, Open / Overdue (Snapshot), First-Time-Right %, QA Pass %;
   - monthly trend of cases received and SLA met %;
   - queue table.
2. **Graduate ramp-up:**
   - SLA, first-time-right and QA pass % by tenure band, with tenured agents as the benchmark;
   - resolved per agent-day by agent type.
3. **Quality:** QA pass %, average score and critical-error % by queue and tenure band.

It uses the existing `PaymentOperationsLight` theme and stays lighter than Report 01, without the same level of UX polish.

---

## 6. Decisions requested
| # | Question | Recommendation |
|---|---|---|
| **B0** | Promote the horizon as the suite default (Report 01's numbers move to 0 / 189 / 208)? | **Yes.** It's required by the shared model and planned under E1 |
| **B1** | Date roles: cases by received date, QA by review date, productivity by day worked? | **Yes** |
| **B2** | The 15 measures above, as drafted? | **Approve** |
