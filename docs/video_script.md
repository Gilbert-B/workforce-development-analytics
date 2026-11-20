# Video script: Workforce Intelligence Suite

Two deliverables:
- **A. Hero walkthrough (about 2 min 45 s, with narration).** It tells one story across the three reports.
- **B. Three silent loops (10–15 s each).** They sit beside the text on the portfolio page.

The numbers below are what the reports show on the synthetic 30 Jun 2027 data. If a number on screen differs, say what's on screen.

---

## Before you record (5 minutes)
- **Data:** run `python python\build_all.py --server localhost`, then open each report and **Refresh**, so every visual is loaded before you hit record.
- **Screen:**
  - set display scaling to **100%** and resolution to 1920 × 1080 if you can;
  - close notifications (Windows **Focus**/Do not disturb);
  - hide the taskbar if possible.
- **Power BI Desktop:**
  - **View → Full screen**, or press **F11**, to hide the ribbon and panes;
  - collapse the **Filters** pane;
  - make sure every slicer is set to **All** (clear any selections).
- **Recorder:** **Windows + Alt + R** (Xbox Game Bar), OBS Studio or Loom. Record **1080p, 30 fps**, with your microphone on for video A.
- **Mouse:** move slowly and deliberately, and pause about 1 second on each thing you talk about. Viewers follow the cursor.
- **Open order:** Report 01 → Report 02 → Report 03. Have all three already open in separate Desktop windows, and switch with **Alt + Tab**, so no refresh happens on camera.

> **Tip:** record the narration separately and lay it over the screen recording if that's easier. Clipchamp is free in Windows and works for this. Short pauses are fine; you can trim them.

---

## A. Hero walkthrough (≈ 2:45)

| # | Time | On screen (what to do) | Narration (read at a calm pace) |
|---|---|---|---|
| 1 | 0:00–0:15 | **Report 01 · Overview**, untouched. Slowly sweep the cursor across the six KPI cards. | "This is the Workforce Intelligence Suite: three Power BI reports for a fictional payments company. It trains new operations staff in eight-week cohorts, then deploys them to resolve payment exceptions. One question runs through it: does our training produce people who perform, and how quickly?" |
| 2 | 0:15–0:30 | Click **2026 Cohort 3** in the cohort slicer, then click it again to clear. On the competency chart, click **By competency**, then **By cohort**. | "Report one follows the academy. Cohorts are compared by programme week, not calendar date, so a cohort that started later is still compared fairly week for week. Every card and chart follows the cohort selection." |
| 3 | 0:30–0:45 | On **Cohorts**, right-click a trainee row → **Drill through → Trainee 360**. Pause on the attendance and "this trainee vs cohort" charts. | "Any trainee opens a 360 view: their attendance, where unrecorded is kept separate from absent, and their competency against their own cohort in the same week." |
| 4 | 0:45–0:55 | Click **Readiness** in the left rail. Hover the approval cards. | "Trainees who complete are certified and reviewed for readiness. A hundred and nine were approved and deployed." |
| 5 | 0:55–1:10 | **Alt + Tab → Report 02 · Operations overview.** Hover **Cases received 49,995** and **SLA met 82.8%**, then the monthly chart. | "Report two is the operations floor. About fifty thousand payment exceptions came in. They live as documents in MongoDB, as a case system would hold them. A Python pipeline loads them incrementally into SQL Server, rejects malformed documents with a reason, and reconciles the counts." |
| 6 | 1:10–1:20 | In the **Queue league table**, click **Screening hits**; watch the page filter. Click it again to clear. | "Click any queue and the page filters, while the headline numbers stay fixed. Screening hits have the tightest targets, two hours for priority one, and the lowest SLA rate." |
| 7 | 1:20–1:40 | Click the **Graduate ramp-up** tab. Hover **75.3%** (first 30 days), **83.5%** (after 90 days), **84.2%** (tenured), then the *SLA met by tenure band* chart. | "Here's the heart of it. In their first thirty days, new graduates meet SLA on seventy-five percent of cases. Experienced agents manage eighty-four. After ninety days the gap is under one point, and productivity rises from about one case per day to one point six." |
| 8 | 1:40–1:50 | In the **Agent league table**, right-click a graduate → **Drill through → Agent 360**. Pause, then click **← Back**. | "Every agent has a profile too: monthly volume, SLA and their own ramp against the benchmark, only for the months they actually worked." |
| 9 | 1:50–2:05 | **Alt + Tab → Report 03 · Outcomes overview.** Hover **90-day retention 95.4%**, **Proficient by day 90 74.0%**, then the 30/60/90 chart. | "Report three joins the two worlds. For each graduate it follows their first thirty, sixty and ninety days. Ninety-five percent stayed past day ninety, and three in four reached the proficiency standard, on average after about two months." |
| 10 | 2:05–2:25 | Click the **Training effectiveness** tab. Hover the *Proficiency by competency band* chart (24.3% vs 8.3%), then the scatter, then the *What the data says* panel. | "So does training predict performance? Moderately. A quarter of the top third by training score were proficient within thirty days, against eight percent of the bottom third. But by day ninety most of the bottom third had caught up. A training score is a reason to support someone, not a verdict." |
| 11 | 2:25–2:35 | Click **Graduate roster**, right-click a graduate → **Drill through → Graduate journey**. | "And every graduate's journey, from academy to day ninety, is one click away." |
| 12 | 2:35–2:45 | Return to **Outcomes overview** (or show the model view, `model.png` style). Hold still. | "All three reports share one semantic model, built and tested from code, with synthetic data throughout. The full project, pipeline and documentation are on GitHub." |

**Word count:** about 400 words, roughly 2 min 40 s at a natural pace. If you run long, drop step 4 or step 11.

---

## B. Silent loops (10–15 s each, no narration)

Record each one separately and trim tightly. Each loop should start and end on the same view, so it repeats cleanly.

| Loop | Report / page | What to do |
|---|---|---|
| **1. Drill-through** | Report 02 · Graduate ramp-up | Right-click an agent in the league table → **Drill through → Agent 360**. Hold about 3 s. Click **← Back**. |
| **2. One click filters everything** | Report 01 · Overview | Click **2026 Cohort 1** → hold 2 s → **2026 Cohort 2** → hold 2 s → **2026 Cohort 3** → hold 2 s → click again to clear. |
| **3. Training → outcomes** | Report 03 · Outcomes overview | Open the **Academy cohort** slicer, pick **2026 Cohort 1**, hold 3 s, then switch to **2026 Cohort 3**, hold 3 s, then reset to **All**. |

---

## After recording
1. **Hero video:** upload it to **YouTube as Unlisted** (or Loom), and send me the link. The website will embed it, so the large file stays out of git.
2. **Loops:** send me the raw files, or put them in a shared folder. I'll trim and compress them to small web MP4s (and GIF fallbacks) for the portfolio page.
3. **Then say "yes, add portfolio-website"** and I'll build the project page around the video, loops, screenshots and case study.
