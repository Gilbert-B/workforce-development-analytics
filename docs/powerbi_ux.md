# Power BI report: how the pages are built (UX-02, showcase design)

The report lives in `powerbi/` as a **Power BI Project (PBIP)**. Every page, visual, bookmark, theme and model object is a text file, so changes can be reviewed in Git.

```
powerbi/
├─ workforcedevelopmentanalytics.pbip            open THIS in Power BI Desktop
├─ workforcedevelopmentanalytics.Report/definition/
│  ├─ report.json                                 theme + registered images
│  ├─ pages/<id>/page.json                        page size, background image, interactions
│  ├─ pages/<id>/visuals/<name>/visual.json       one file per visual
│  └─ bookmarks/*.bookmark.json                   one file per bookmark
├─ …Report/StaticResources/RegisteredResources/   dark theme + background PNGs (what Power BI uses)
├─ design/overview-background.svg, about-background.svg   background SOURCE files
├─ themes/WorkforceIntelligenceDark.json          theme source (the light UX-01 theme is kept as an alternative)
└─ tools/build_overview_page.py                   generator: layout grid → SVGs + pages + bookmarks
```

---

## The core technique: a designed canvas

The page uses **two layers**:
1. **The background image** carries everything static: the navigation rail, panels, card frames, icons, labels, context lines, chip tracks and button outlines. It's drawn as SVG and exported to PNG.
2. **The visuals** carry only data and actions. They have transparent backgrounds and sit exactly on the drawn frames: the KPI numbers, slicer, charts, titles and invisible buttons.

**Why:** every pixel of the look is controlled in one image, so the report looks designed rather than assembled, and visuals stay simple. The visual positions and the SVG drawing come from the **same layout constants** in the generator, so they can't drift apart.

**Trade-off:** static text drawn in the image, such as KPI labels or the "Definitions" text, is edited in the SVG rather than in Desktop. Everything with data stays in Power BI.

## Interactions on the Overview page

| You click | What happens | How it's built |
|---|---|---|
| A cohort tile | Filters every visual | Slicer on `rpt dim_cohort[cohort_name]`, horizontal tiles |
| Status / Attendance quality | Swaps the left chart and its title | Two **bookmarks** that show one set of visuals and hide the other |
| By cohort / By competency | Swaps the line chart for a competency × week heatmap | Two more bookmarks, same pattern |
| Definitions | Slides the definitions drawer over the page | Bookmark that **shows** 4 hidden visuals: dark scrim, panel, text, Close button |
| ✕ Close | Hides the drawer | Bookmark that hides the same 4 visuals |
| Reset | Clears the cohort selection, restores both default views and closes the drawer | Bookmark that also applies data state to the slicer |
| About (in the rail) | Opens the About page | Button with a **Page navigation** action |
| Clicking inside a chart | Highlights the other charts, but never changes the KPI numbers | `page.json → visualInteractions` set to `NoFilter` |

**How the toggles work:** each toggle is a pair of chips. The selected chip is a non-clickable "On" button with a teal fill, and the other is a clickable "Off" button linked to a bookmark. Each bookmark shows the right title, chart and chips and hides the rest. Its options are **"Selected visuals"** and **no data**, so a toggle never resets your cohort selection.

**To see it in Desktop:** open **View → Selection** and **View → Bookmarks**. Click a bookmark and watch which visuals it hides. In Desktop itself, **Ctrl + click** activates a button.

## Visuals worth knowing about
- **Attendance quality:** a 100% stacked bar using the existing `[Eligible Attendance Sessions]` measure, split by `attendance_status`. Present is teal, Absent coral and Unrecorded slate, so missing registers are visible rather than hidden.
- **Competency heatmap:** a matrix with competency rows and week columns. `[Average Competency Score]` uses **conditional-format background colours** on a gradient from dark navy (low) to teal (high).
- **Colours tied to values:** cohort lines and attendance statuses use `dataPoint` selectors, so "2026 Cohort 2" is always teal whatever the sort order. New cohorts take the theme's next colours.

## Changing things
- **A colour or font everywhere:** edit the theme, copy it into `RegisteredResources/`, then reopen the report.
- **The background (frames, icons, static labels):** edit `design/*.svg`, export it to PNG at **1920 × 1080**, and replace the PNG in `RegisteredResources/`. Any SVG tool works, for example Inkscape (*Export PNG Image*) or a browser screenshot.
- **Layout or bookmarks:** change them in Desktop, as usual. Re-running `tools/build_overview_page.py` rebuilds **both pages and all bookmarks** from scratch and discards Desktop edits, so only re-run it on purpose.
- Always **close Desktop** before editing files in `powerbi/` outside it, and review `git diff` before committing.

## Waiting for new measures (proposed to ChatGPT)
Data-driven KPI context lines, SVG progress bars, the "current week" marker for in-progress cohorts, and the Cohorts / Skills / Attendance / Trainee 360 pages. The rail already shows those pages as "soon".
