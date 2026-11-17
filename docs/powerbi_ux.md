# Power BI report: how the Overview page is built

The report lives in `powerbi/` as a **Power BI Project (PBIP)**. Every page, visual, theme and model object is a text file, so changes can be reviewed in Git like code.

```
powerbi/
├─ workforcedevelopmentanalytics.pbip          open THIS in Power BI Desktop
├─ workforcedevelopmentanalytics.Report/       the report, in PBIR format (JSON)
│  ├─ definition/report.json                   report settings + which theme is used
│  ├─ definition/pages/<id>/page.json          page size, name, visual interactions
│  ├─ definition/pages/<id>/visuals/<name>/visual.json   one file per visual
│  └─ StaticResources/RegisteredResources/WorkforceIntelligence.json   theme in use
├─ workforcedevelopmentanalytics.SemanticModel/ the model, in TMDL (plain text)
│  └─ definition/tables/*.tmdl                 tables, columns, measures, M queries
├─ themes/WorkforceIntelligence.json            reusable copy of the theme (source)
└─ tools/build_overview_page.py                 generator used to scaffold the page
```

Never committed (blocked by `.gitignore`): `.pbi/` folders (the `cache.abf` data cache and per-machine settings) and any `.pbix`.

---

## The page at a glance (1920 × 1080)

| Area | Visual(s) | Data |
|---|---|---|
| Header | 2 text boxes | Static title and subtitle |
| Top right | Card `snapshotLabel` | `[Snapshot Label]`, built from `rpt dim_snapshot` |
| Left rail | Slicer `cohortSlicer`; text box `definitionsPanel` | `rpt dim_cohort[cohort_name]`; static definitions |
| KPI row | 6 cards (`kpi…`) | Starting Headcount, Active (Snapshot), Completed (Snapshot), Average Competency Score, Recorded Attendance Rate, Attendance Recording Rate |
| Left chart | Stacked bar `statusByCohort` | Cohort × Active / Completed / Withdrawn (Snapshot) |
| Right chart | Line `competencyTrend` | Programme week × Average Competency Score, one line per cohort |

## How each part works

**Theme: all styling in one file.** The theme sets colours (`dataColors`), fonts (`textClasses`) and defaults per visual type (`visualStyles`): white tiles, light borders, card font sizes and the page background. Visuals hold only layout and data, so restyling the report means editing the theme. To change it, edit `powerbi/themes/WorkforceIntelligence.json`, copy it over the one in `StaticResources/RegisteredResources/`, then reopen the report. Alternatively, use **View → Themes → Customize current theme** in Desktop.

**Layout: a grid.** The generator's constants define a 40 px margin, 16 px gaps, a 320 px left rail, a 150 px KPI row and two charts below it. In a `visual.json`, `position` holds `x`, `y`, `width` and `height` in page pixels, and `z` sets which visual sits on top. After opening the report, move things in Desktop; there's no need to touch the JSON.

**The KPI cards are bound to measures.** No value is typed in anywhere. Each card's `query.queryState.Values` points to a model measure, and `displayName` sets the label under the number.

**Training status uses existing measures as series.** The stacked bar puts `cohort_name` on the axis, with three existing measures as the stacked series. `dataPoint` + `selector.metadata` pins one colour to each measure: Active blue, Completed teal, Withdrawn brick.

**Competency progression is compared by programme week.** The axis is `programme_week`, set to **Categorical** so weeks 1–8 appear as labels, and sorted ascending. Cohort 3 has no Week 7–8 assessments yet, so its line simply stops. Missing weeks are never zeros.

**The snapshot label updates by itself.** `rpt.dim_snapshot` is a one-row SQL view of the dataset's as-of date. In Power BI it's a **disconnected** table, with no relationships, so no slicer can change it. `[Snapshot Label]` formats it as `Data as of 2 Nov 2026 | Synthetic data`. After the data is regenerated and the report refreshed, the label changes with it.

**Interactions: only the slicer moves the KPIs.** `page.json → visualInteractions` sets clicks on either chart to `NoFilter` for the six KPI cards. Clicking a bar still filters the line chart and vice versa, but the headline numbers always describe the selected cohorts, never an accidental click. To change this in Desktop, select a chart, then use **Format → Edit interactions**.

## Changing the page safely
1. Close Power BI Desktop before editing any file in `powerbi/` outside Desktop.
2. Changes made in Desktop are saved back into these JSON and TMDL files. Review them with `git diff` before committing.
3. `tools/build_overview_page.py` **regenerates the page's visuals from scratch**. Re-running it discards changes made in Desktop, so only run it on purpose, for example to reset the layout.
