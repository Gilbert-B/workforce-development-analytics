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

## The core technique: a designed canvas, with everything you'd edit kept in Power BI

The page uses **two layers**:
1. **The background image** holds only shapes you'd rarely change: the dark gradient, grid texture, glows, the rail strip, rounded card and panel frames, button outlines and the active-page highlight. It holds **no text and no icons**.
2. **Power BI visuals** hold everything else, so all of it can be edited in Desktop:
   - **text boxes** for every label, heading, note and context line;
   - **image visuals** for every icon, one small SVG file each (`icon-<name>-<colour>.svg`);
   - **buttons** for Definitions, Reset, the toggle chips and the navigation clicks;
   - **data visuals**: the cards, slicer and charts.

**To rename a KPI,** edit its text box, e.g. `kpiActiveTraineesLabel`. **To change an icon,** select the image visual, then **Format → Image → Browse**. The background only needs redrawing if you want different *shapes*.

**Why:** the background gives a designed look, and Power BI objects keep everything editable. The visual positions and the background frames come from the **same layout constants** in the generator, so they line up.

**Formats learned from Power BI Desktop** (they differ from what you might guess):
- the page background image is nested: `"image": {"image": {...}}`;
- visual font settings need a full font stack, e.g. `'Segoe UI Bold', wf_segoe-ui_bold, helvetica, arial, sans-serif`;
- button text needs a per-state entry **and** a master `show` entry with no selector.

## Interactions on the Overview page

| You click | What happens | How it's built |
|---|---|---|
| A cohort tile | Filters every visual | Slicer on `rpt dim_cohort[cohort_name]`, horizontal tiles |
| Status / Attendance quality | Swaps the left chart and its title | Two **bookmarks** that show one set of visuals and hide the other |
| By cohort / By competency | Swaps the line chart for a competency × week heatmap | Two more bookmarks, same pattern |
| Definitions | Slides the definitions drawer over the page | Bookmark that **shows** 4 hidden visuals: dark scrim, panel, text, Close button |
| ✕ Close | Hides the drawer | Bookmark that hides the same 4 visuals |
| Reset view | Restores both default panels and closes the drawer; **keeps** your cohort selection | Display-only bookmark |
| Clear filters | Clears the cohort selection; **keeps** the current panels | Data-only bookmark targeting the slicer |
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
- **The background shapes (frames, panels, rail):** edit `design/*.svg`, export it to PNG at **1920 × 1080**, and replace the PNG in `RegisteredResources/`. Any SVG tool works, for example Inkscape (*Export PNG Image*) or a browser screenshot.
- **Layout or bookmarks:** change them in Desktop, as usual. Re-running `tools/build_overview_page.py` rebuilds **both pages and all bookmarks** from scratch and discards Desktop edits, so only re-run it on purpose.
- Always **close Desktop** before editing files in `powerbi/` outside it, and review `git diff` before committing.

## Data-driven extras (ChatGPT-approved measures, D24)
- **Card context lines:** two cards show text **measures**, e.g. "208 enrolments · 9 cancelled before start", so the line changes with the cohort selection. The other cards keep static descriptions.
- **Progress bars:** an image visual whose picture is an **SVG measure**, i.e. DAX that returns `data:image/svg+xml;utf8,<svg …>`. The bar width is the rate, clamped to 0–100%.
- **Current-week marker:** a small gold card in the competency panel. It appears only when exactly one in-progress cohort is selected, e.g. "Currently in Week 7".
- **Planned pages:** Cohorts, Skills, Attendance and Trainee 360 show as "planned" in the rail, with no click action until they're built.

---

## UX-03 pages (Cohort Intelligence, Competency & Skills, Attendance & Participation, Trainee 360)

**Where they live:** each page is a folder under `definition/pages/<id>/`, built by `cohort_page()`, `skills_page()`, `attendance_page()` and `trainee_page()` in the generator. They share helpers:
- `header()`: eyebrow, title, snapshot label, Clear filters or Back, cohort tiles and the optional week selector;
- `panel_title()`, `kpi_tile()` and `heatmap()`;
- `page_svg()`: the background for each page.

**Synced slicers:** the cohort tiles on every page are the same *sync group* (`"syncGroup": {"groupName": "CohortSelection"}`), so selecting Cohort 3 on one page keeps it selected on the others. To see this in Desktop, open **View → Sync slicers**.

**Drill-through (Trainee 360):** the page has `"type": "Drillthrough"`, a page filter on `rpt dim_enrolment[enrolment_id]`, and a `pageBinding` linking the two. It's hidden in the page tabs.
**To use it:** on **Cohort Intelligence**, right-click any row of the **Enrolments** table → **Drill through → Trainee 360 — Training**. **← Back** returns you.
**To change the drill-through field in Desktop:** open the Trainee 360 page → **Visualizations → Build visual** → the **Drill through** well.

**Filters on a single visual:** the "Unrecorded enrolment-sessions" card uses the existing `[Eligible Attendance Sessions]`, with its own filter `attendance_status = Unrecorded`. Select the card and look at **Filters on this visual**.

**Grain in the labels:** attendance counts are **enrolment-sessions** (one per trainee per session), not distinct sessions. Status counts are **enrolments**, not people. Snapshot measures are labelled as snapshot / to date.

## D26 additions
- **Skills header strip:** `Paired WoW Competency Change` sits next to the week selector and follows both selectors. It answers "how much did the *same* trainees improve on their previous week?", which the trend chart can't, because its weekly means mix different trainees.
- **Trainee 360 benchmark:** the lower-right panel plots `Average Competency Score` (*This trainee*, teal) against `Cohort Same-Week Average` (*Cohort, same week*, gold) by programme week.

## BI-02 pages (Coaching & Watch List, Certification & Readiness, Trainee 360 extension)
**Builders:** `coaching_page()`, `readiness_page()` and the extended `trainee_page()` in `tools/build_overview_page.py`. They share `kpi_row()` (equal KPI tiles) and `no_filter_on()` (chart clicks never change KPI numbers).

**Snapshot vs trend:**
- Every KPI card is "at the snapshot (2 Nov 2026)".
- The only time-based chart is *Watch-list movement by effective date*, labelled as an event trend.
- There are no date relationships, so a date filter can't change a snapshot number.

**Populations are never summed.** The *Populations outside the rates* card lists unactioned cases, completers with no attempt, unattempted certifications and unreviewed completers as **separate** lines.

**Trainee 360 is taller** (1824 px, *Fit to width*): scroll down for the readiness banner and four history tables. An empty table means *no record*, not a failure.

**Built-in counts:** three charts use Power BI's *Count of* a column (row counts). Select the chart → **Build visual** to see the aggregation.

