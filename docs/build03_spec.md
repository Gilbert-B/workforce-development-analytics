# Build 03: Payment Operations data (specification)

**Status:** draft for owner and ChatGPT review. **Nothing is implemented yet.**

**Feeds:** Report 02 (BI-03), and the 30/60/90-day analysis in Report 03 (Build 04).

**All data is synthetic:** a fictional payments operations team.

## 1. What Build 03 adds, in one picture
```text
generator (Python)  ──►  MongoDB  payment_cases      (case-management documents)
        │                     │
        │                     ▼  python/etl  (extract → flatten → validate → upsert, incremental)
        ▼                SQL Server  stg ─► core ─► rpt  ──►  shared Power BI model ──► Report 02
 deployment & agents  ─────────────────────▲
 (relational CSV, like Builds 01–02)
```
- **MongoDB** holds what is document-shaped by nature: one payment-exception case with its events, assignments, QA checklist and rework history.
- **HR and staffing facts** (deployments, agents) stay relational CSV, like Builds 01–02.

## 2. Timeline: baseline kept, horizon added (the E1 rule)
- **Baseline dataset (frozen):**
  - **As of:** 2026-11-02.
  - **Data:** `data/synthetic/` as now.
  - **Reference numbers:** unchanged (208 / 199 / 63 / 127 …).
  - **Report 01:** keeps validating against it.
- **Horizon dataset (new):**
  - **As of:** **2027-06-30**.
  - **Data:** `data/synthetic_horizon/`.
  - **How:** the Build 01 and 02 generators re-run with `--as-of-date 2027-06-30`. They already guarantee that every baseline row reappears unchanged; Cohort 3 then finishes training, sits its exams and gets readiness reviews.
  - **What Build 03 adds:** operations data from August 2026 to June 2027.
- **Choosing a dataset:** `full_reset.py --dataset baseline|horizon` loads one or the other. The default stays `baseline` until the horizon dataset passes its checks (section 7). Then it is promoted as the suite default and the reference numbers are updated once.

## 3. Business rules (fictional policy, all values in `config/build03_synthetic.toml`)
| Area | Rule |
|---|---|
| Deployment | Only enrolments whose readiness review is **Approved** are deployed. Start date: 5–15 business days after the approval is recorded. One deployment per enrolment, to one team and one queue. |
| Tenured agents | About 40 experienced agents (not from any cohort) form the comparison baseline. Their `employee_id`s are new and there is no enrolment. |
| Exits | A small share of agents leave (for example 8% within 180 days of deployment). They have no cases after their exit date. This is needed for retention in Build 04. |
| Case types | returned payment · duplicate payment · failed validation · missing beneficiary details · screening hit (manual review) |
| Priority and SLA | P1 = 4 h, P2 = 24 h, P3 = 72 h, calendar hours from received to resolved. SLA met = resolved within target. The target is stored on the case at receipt (policy version), so later policy changes don't rewrite history. |
| Productivity ramp | New agents start at about 50% of tenured throughput and accuracy, then reach about 95% over about 90 days on a learning curve. Higher final training competency and a first-attempt certification pass mean a *slightly* faster ramp, with noise. These are associations to discover, not deterministic rules. |
| QA sampling | 25% of cases are sampled in an agent's first 30 days, 10% after that. A checklist of 6 items gives a QA score of 0–100; pass mark 85. Errors are categorised procedural, financial or compliance, each with a severity. |
| Rework | A critical QA error, or a reopened case, creates a rework record; the case's resolved time moves accordingly. |
| Missing data | Never imputed. Unresolved cases at the horizon stay open, and a 30/60/90-day window that hasn't ended by the horizon is marked **incomplete** rather than shown as zero. |

## 4. MongoDB document contract (collection `payment_cases`)
```json
{
  "_id": "PC-000123",
  "schema_version": 1,
  "case_type": "returned_payment",
  "priority": "P2",
  "channel": "bank_portal",
  "amount_band": "1k-10k",
  "received_at": "2027-02-03T09:14:00",
  "queue": "Q-RETURNS",
  "sla": { "policy_version": "B03-R1", "target_hours": 24 },
  "assignments": [ { "agent_id": "AG-0042", "assigned_at": "2027-02-03T09:20:00" } ],
  "events": [ { "type": "created", "at": "..." }, { "type": "in_progress", "at": "..." },
              { "type": "resolved", "at": "...", "by": "AG-0042" } ],
  "resolution": { "code": "funds_returned", "resolved_at": "2027-02-03T15:02:00" },
  "qa": { "sampled": true, "reviewed_at": "...", "score": 83,
          "checklist": [ { "item": "beneficiary_verified", "passed": true } ],
          "errors": [ { "category": "procedural", "severity": "minor" } ] },
  "rework": [ { "at": "...", "reason": "qa_critical_error" } ],
  "updated_at": "2027-02-04T10:00:00"
}
```
- **Event types:** `created`, `assigned`, `in_progress`, `pending_info`, `resolved`, `reopened`, `closed`.
- **`updated_at`** drives incremental loading (the watermark).
- **A small, controlled set of malformed documents** (about 0.2%) is inserted on purpose: a missing `received_at`, resolution before receipt, or an unknown `case_type`. They demonstrate rejection logging.

## 5. ETL (Python, `python/etl/`)
1. **Extract:** read documents with `updated_at` after the last watermark (table `etl.load_log`).
2. **Flatten** into `stg` tables, one per array: case, assignment, event, QA review, QA error, rework.
3. **Validate** required fields, allowed values and chronology. Failures go to `stg.rejected_record` with a reason, and are never loaded.
4. **Upsert** `stg` → `core` with `MERGE`, so a re-run changes nothing.
5. **Record** the run: watermark, counts read, loaded and rejected.

**Incremental demo:** load documents up to 2027-05-31, run the ETL, then add June's cases plus updates to some May cases (reopened and rework). Run it again: only new or changed documents are processed.

**Local setup:** MongoDB Community Server (free) or Docker, plus `pymongo`. SQL Server stays as it is.

## 6. SQL tables (additive) and grain
| Table (`core`) | One row per |
|---|---|
| `ops_team`, `ops_queue`, `case_type`, `sla_policy` | reference value (`sla_policy`: case type × priority × policy version) |
| `ops_agent` | agent (graduate: has `enrolment_id`; tenured: none), with start and exit dates |
| `deployment` | deployed enrolment (FK `enrolment_id`, approving `readiness_review_id`) |
| `payment_case` | case (received, priority, type, queue, SLA target, resolved_at, current status) |
| `case_assignment` | assignment of a case to an agent |
| `case_event` | case status event |
| `qa_review` / `qa_error` | sampled review / error found in it |
| `case_rework` | rework instance |

**Reporting views (`rpt`) for Report 02:**
- `dim_agent`, `dim_team`, `dim_queue`, `dim_case_type`;
- `fact_payment_case`, with resolution hours, SLA met, first-time-right and days since deployment;
- `fact_case_event`;
- `fact_qa_review`;
- `fact_agent_day`: agent × business day, with cases handled and resolved, average resolution hours, QA score. It drives fast trend visuals.

**In the shared model:** facts relate through `dim_agent` (which carries `enrolment_id`) and `dim_date`. Report 01's existing objects stay unchanged; the model check confirms this.

## 7. Expected volumes and key checks
**Expected volumes** (confirmed after generation):
- about 110–130 graduate agents and 40 tenured;
- about **200–300k cases** (configurable `scale`, timed before any increase);
- about 1–1.5 M events.

**Key checks** (SQL validation plus a few tests):
1. The baseline dataset reproduces the frozen reference numbers exactly, and Report 01 is unchanged.
2. The horizon dataset contains every baseline row unchanged.
3. Deployments happen only for approved enrolments, after the approval is recorded; one per enrolment.
4. Cases are worked only by agents between their start and exit dates.
5. Case chronology holds: received ≤ assigned ≤ resolved; QA after resolution; rework after its trigger.
6. SLA met agrees with the policy target stored on each case.
7. **ETL:** a re-run is idempotent (same counts and checksums); an incremental run processes only changed documents; documents read = loaded + rejected; every malformed document is rejected with a reason.
8. **30/60/90-day windows:** marked complete only if they ended by the horizon.
9. Report 02's measures are checked against an independent SQL reference script, as in BI-02.

## 8. Decisions taken (routine; flag if you disagree)
- **Tenured agents:** include them, because they give Report 03 a benchmark.
- **Datasets:** two side by side (baseline and horizon) instead of replacing the baseline. This is the simplest way to honour "freeze the baseline, promote later".
- **Volume:** start at about 250k cases; increase only if the reports need it.
