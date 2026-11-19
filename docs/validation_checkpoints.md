# Validation checkpoints (owner, Windows)

Two checkpoints cover everything that needs your machine. Each lists the exact commands and what you should see. The expected numbers come from Claude's environment (SQL Server 2025 on Linux and MongoDB 7.0, both in Docker). The Power BI checks have **not** been run by Claude, because Power BI Desktop doesn't run there.

---

## Checkpoint A: data pipeline (about 5 minutes)

**Prerequisites:**
- **SQL Server 2022 Developer** on `localhost`.
- **MongoDB** on `localhost:27017`: either `docker run -d --name wda-mongo -p 27017:27017 mongo:7.0` in Docker Desktop, or the free Community Server installed as a service.
- **Python 3.11 or later.**

```powershell
git fetch origin
git checkout bi/03-payment-operations
git pull
pip install -r requirements.txt
python python\generate_build03_data.py          # case documents (not committed)  ~10 s
python python\build_all.py --server localhost   # Builds 01-04, MongoDB, ETL, checks  ~1 min
python -m pytest                                 # with $env:WDA_SQL_SERVER = "localhost"
```

**What you should see:**

| Step | Output |
|---|---|
| generate | `ops_agent.csv 149 rows`, `deployment.csv 109`, `payment_cases_phase1.jsonl 44164`, `payment_cases_phase2.jsonl 49995`, `phase 2 new or changed documents: 6171` |
| build_all 1 | Build 01 `26 of 26`, Build 02 `49 of 49` |
| build_all 3–6 | Phase 1: 44,164 documents. ETL: 44,064 loaded + 100 rejected. Phase 2: 5,931 new documents. ETL: reads 6,171, the documents that are new or changed |
| build_all 8 | Build 03 `26 of 26 checks OK`; Build 04 `14 of 14 checks OK`; `MongoDB 50095 = SQL cases 49995 + rejected 100 … OK` |
| end | `Suite build complete: all checks OK` |
| pytest | **171 passed** |

**If MongoDB isn't running:** `build_all` stops at step 3 with `ServerSelectionTimeoutError`. Start it and run `build_all` again; it's safe to re-run.

---

## Checkpoint B: the three reports in Power BI Desktop (about 20 minutes)

**Before you start:**
- Run Checkpoint A first, so the database holds the 2027-06-30 data.
- Turn on **Settings → Options → Preview features → Power BI Project (.pbip) save option**.

All three `.pbip` files open the **same** model folder. **Open one at a time** and close it before opening the next.

### B1. Report 02: Payment Operations (`powerbi\payment-operations.pbip`)
1. **Open and refresh.**
   - Open the file and click **Refresh**. The model loads 8 more tables than before. Expect about 50k case rows; the refresh takes under a minute.
   - **If Desktop shows a DAX or relationship error, stop and send me the message.**
2. **Operations overview cards:**
   - Cases Received **49,995**
   - SLA Met **82.8%**
   - First-Time Right **98.0%**
   - QA Pass **96.7%**
   - Open **248**
   - Overdue **19**
3. **Graduate ramp-up:**
   - SLA met, first 30 days **75.3%**
   - after 90 days **83.5%**
   - tenured benchmark **84.2%**
   - FTR, first 30 days **96.2%**
   - resolved per agent-day **1.54**
   - **Chart:** SLA by tenure band rises 75.3 → 80.2 → 81.2 → 83.5 → 84.2 (Tenured), with a flat benchmark line.
4. **Quality:**
   - **Cards:** QA reviews **5,675**, sample rate **11.4%**, pass **96.7%**, average score **98.5**, critical errors **2.3%**.
   - **Checklist chart:** "Documentation complete" and "Customer communication" fail most often.
5. **Interactions:**
   - **Tabs:** each tab switches page.
   - **Slicers:** Team, Queue and Priority filter the page and stay in sync across pages.
   - **Charts:** clicking a chart filters the other charts but not the KPI cards.
6. **Drill-through:**
   - On *Graduate ramp-up*, right-click an agent in the league table → **Drill through → Agent 360**.
   - The page shows that agent's name, profile line and numbers, and **← Back** returns.
7. **Save** with Ctrl+S, then close.

### B2. Report 03: Workforce Outcomes (`powerbi\workforce-outcomes.pbip`)
1. **Open and refresh.**
2. **Outcomes overview cards:**
   - Graduates Deployed **109**
   - 90-Day Retention **95.4%**
   - Proficient by Day 90 **74.0%**
   - Avg Days to Proficiency **64**
   - SLA met days 61–90 **81.2%**
   - Gap to tenured **−3.1**
3. **30/60/90 charts:**
   - SLA met 75.3 → 80.1 → 81.2.
   - First-time right 96.2 → 97.1 → 97.8.
   - The tenured line is at 84.2 / 98.4.
4. **Training effectiveness:**
   - **Proficiency by competency band:** by day 30, Top third **24.3%**, Middle **11.1%**, Bottom **8.3%**.
   - **Watch list:** retention No **96.6%**, Yes **90.5%**.
   - **Scatter:** one dot per graduate.
5. **Graduate roster:** right-click a graduate → **Drill through → Graduate journey**. It shows three windows, and windows cut short by an exit show blank metrics.
6. **Slicers:** the **Academy cohort** slicer changes every page.

### B3. Report 01: Workforce Development (`powerbi\workforcedevelopmentanalytics.pbip`)
Report 01 now reads the 2027-06-30 data, where all three cohorts have finished. **Refresh**, then check:

| Card | Expected (2027-06-30) | Was (2026-11-02) |
|---|---|---|
| Starting headcount | **199** | 199 |
| Active trainees | **0** | 71 |
| Completed | **189** | 127 |
| Avg competency | **67.2** | |
| Recorded attendance | **91.9%** | |
| Recording rate | **93.1%** | |

- **Layout:** all pages, bookmarks and Trainee 360 are unchanged.
- **Header wording:** the Coaching and Readiness headers now say "AT THE DATA SNAPSHOT" instead of "2 NOV 2026".

### B4. Screenshots for the portfolio
After B1–B3, take these at **1920 × 1080**, in Desktop full-screen view or with **File → Export → PDF**. Save each as PNG under `docs/screenshots/` using the names below.

| File | Report / page |
|---|---|
| `01_overview.png` | Report 01 · Overview |
| `01_trainee360.png` | Report 01 · Trainee 360 (drill through from Cohorts) |
| `02_overview.png` | Report 02 · Operations overview |
| `02_rampup.png` | Report 02 · Graduate ramp-up |
| `02_agent360.png` | Report 02 · Agent 360 |
| `03_overview.png` | Report 03 · Outcomes overview |
| `03_effectiveness.png` | Report 03 · Training effectiveness |
| `03_journey.png` | Report 03 · Graduate journey |
| `model.png` | Model view (Desktop, Model tab), whole diagram |

---

## What to send back
- **Checkpoint A:** the last line of `build_all` and the pytest total.
- **For each report:** "cards match", or the cards that differ, plus any error message, verbatim.
- **Checkpoint B4:** the screenshots, committed or attached.
