"""Build Report 03, Workforce Outcomes & Training Effectiveness, as PBIR files (BI-04).

Same shared semantic model as Reports 01 and 02 (definition.pbir -> byPath).
Its tables (rpt dim_graduate, rpt fact_outcome_window) come from Build 04
(sql/011_create_build04_outcome_views.sql) and are added to the model by
powerbi/tools/build_model.py.

Pages
    1. Outcomes overview        retention, proficiency, the 30/60/90-day curve vs tenured agents
    2. Training effectiveness   do training results predict early operations performance?
    3. Graduate roster          every deployed graduate, training -> outcome (drill-through source)
    4. Graduate journey         drill-through: one graduate from academy to day 90 (hidden tab)
    5. Method                   windows, proficiency standard, honest-window rules, caveats

USAGE (repository root, Power BI Desktop CLOSED)
    python powerbi/tools/build_workforce_outcomes.py
"""

from __future__ import annotations

from pathlib import Path

from pbir_lib import proj
from suite_light import (svg_text, BODY_Y, BOTTOM, GAP, KPI_Y, SPAN, X0, Page, Palette, column_chart, combo_chart, drillthrough,
                         eq, footer, heatmap, sort_by, table, text_card, write_report)

REPO = Path(__file__).resolve().parents[2]
PBI = REPO / "powerbi"
REPORT = PBI / "WorkforceOutcomes.Report"
THEME = PBI / "themes" / "WorkforceOutcomesLight.json"

PAL = Palette(canvas="#F4F3F9", surface="#FFFFFF", ink="#17132B", muted="#5E5A73", border="#E0DCEB",
              accent="#5B3FA8", accent_soft="#E3DCF5", hero_from="#1A1238", hero_to="#5B3FA8", hero_text="#D5CBF2")
TENURED = "#2E3A4B"

OVERVIEW, EFFECT, ROSTER, JOURNEY, METHOD = ("b6f2d8a4c0e7b3f9d5a1", "c7a3e9b5d1f8c4a0e6b2", "d8b4f0c6e2a9d5b1f7c3",
                                             "e9c5a1d7f3b0e6c2a8d4", "f0d6b2e8a4c1f7d3b9e5")
TABS = [(OVERVIEW, "Outcomes overview"), (EFFECT, "Training effectiveness"), (ROSTER, "Graduate roster"),
        (METHOD, "Method")]
GR, OW, PC, SNAP = "rpt dim_graduate", "rpt fact_outcome_window", "rpt fact_payment_case", "rpt dim_snapshot"
SNAPSHOT = (SNAP, "Snapshot Label")
EYEBROW = "WORKFORCE OUTCOMES & TRAINING EFFECTIVENESS · REPORT 03 OF 3"
WINDOW = (OW, "window_label", "Window")
WINDOW_SORT = sort_by(OW, "window_order")
DAYS_61_90 = [eq("days6190", OW, "window_label", "Days 61-90")]
DAYS_1_30 = [eq("days130", OW, "window_label", "Days 1-30")]


def m(table_: str, name: str, label: str | None = None) -> tuple:
    return (table_, name, label or name)


TWO_ROWS = (BOTTOM - BODY_Y - GAP) // 2


def header(pg: Page, title: str, active: str | None, back=False) -> None:
    pg.header(EYEBROW + (" \u00b7 DRILL-THROUGH" if back else ""), title, TABS, active, SNAPSHOT, back=back, logo="trend")


def slicers(pg: Page) -> None:
    pg.slicer("slCohort", 1100, 230, GR, "cohort_name", "Academy cohort", "OutCohort")
    pg.slicer("slTeam", 1346, 250, GR, "team_name", "Team", "OutTeam")
    pg.slicer("slQueue", 1612, 260, GR, "primary_queue_name", "Queue", "OutQueue")


# ------------------------------------------------------------------ 1. overview
def overview() -> Page:
    pg = Page(PAL, OVERVIEW, "Outcomes overview")
    header(pg, "From academy to operations: the first 90 days", OVERVIEW)
    slicers(pg)
    pg.kpi_row([
        ("kpiDeployed", "Graduates deployed", GR, "Graduates Deployed", "Approved for readiness, then deployed", PAL.accent, None, "cap"),
        ("kpiRetention", "90-day retention", GR, "90-Day Retention %", "Still employed at day 90", PAL.good, None, "users"),
        ("kpiProficient", "Proficient by day 90", GR, "Proficient by Day 90 %", "Of graduates retained to day 90", PAL.good, None, "target"),
        ("kpiDays", "Avg days to proficiency", GR, "Avg Days to Proficiency", "Proficient graduates (30-day steps)", PAL.accent, None, "calendar"),
        ("kpiSla", "SLA met \u00b7 days 61-90", OW, "Window SLA Met %", "Graduates' third month in role", PAL.accent, DAYS_61_90, "clock"),
        ("kpiGap", "Gap to tenured \u00b7 days 61-90", OW, "Window SLA Gap vs Tenured (pts)", "SLA met, percentage points",
         PAL.warn, DAYS_61_90, "trend"),
    ])
    y1, h1 = BODY_Y, TWO_ROWS
    w3 = (SPAN - 2 * GAP) // 3
    pg.chart("chSla", pg.panel("sla", X0, y1, w3, h1, "SLA met: 30 / 60 / 90 days",
                               "Complete windows only · line = tenured agents"),
             combo_chart(PAL, WINDOW, [m(OW, "Window SLA Met %", "Graduates")],
                         [m(PC, "SLA Met % (Tenured Benchmark)", "Tenured benchmark")],
                         col_colours=[PAL.accent], line_colours=[TENURED], sort=WINDOW_SORT))
    pg.chart("chFtr", pg.panel("ftr", X0 + w3 + GAP, y1, w3, h1, "First-time right: 30 / 60 / 90 days",
                               "Resolved with no rework · line = tenured agents"),
             combo_chart(PAL, WINDOW, [m(OW, "Window First-Time-Right %", "Graduates")],
                         [m(PC, "First-Time-Right % (Tenured Benchmark)", "Tenured benchmark")],
                         col_colours=[PAL.good], line_colours=[TENURED], sort=WINDOW_SORT))
    pg.chart("chStatus", pg.panel("status", X0 + 2 * (w3 + GAP), y1, SPAN - 2 * (w3 + GAP), h1, "When graduates reach proficiency",
                                  "Standard: SLA met \u2265 80% and first-time right \u2265 97%"),
             column_chart(PAL, (GR, "proficiency_status", "Proficiency"), [m(GR, "Graduates Deployed", "Graduates")],
                          colours=[PAL.accent], kind="clusteredBarChart", sort=sort_by(GR, "proficiency_status_order")))
    y2 = y1 + h1 + GAP
    h2 = BOTTOM - y2
    wl = 1180
    pg.chart("chCohorts", pg.panel("cohortChart", X0 + wl + GAP, y2, SPAN - wl - GAP, h2, "Retention and proficiency by cohort",
                                   "Share of each cohort's graduates"),
             column_chart(PAL, (GR, "cohort_name", "Cohort"),
                          [m(GR, "90-Day Retention %", "90-day retention"), m(GR, "Proficient by Day 90 %", "Proficient by day 90")],
                          colours=[PAL.good, PAL.accent], sort=sort_by(GR, "cohort_name")))
    pg.chart("tbCohorts", pg.panel("cohorts", X0, y2, wl, h2, "By academy cohort",
                                   "Training results on the left, operations outcomes on the right"),
             table([("Column", GR, "cohort_name", "Cohort"), ("Measure", GR, "Graduates Deployed", "Deployed"),
                    ("Measure", GR, "Avg Final Competency", "Final competency"),
                    ("Measure", GR, "Certified First Attempt %", "Certified first attempt"),
                    ("Measure", GR, "90-Day Retention %", "90-day retention"),
                    ("Measure", GR, "Proficient by Day 30 %", "Proficient by day 30"),
                    ("Measure", GR, "Proficient by Day 90 %", "Proficient by day 90"),
                    ("Measure", GR, "Avg Days to Proficiency", "Avg days to proficiency")],
                   sort=sort_by(GR, "cohort_name"),
                   scales=[(GR, "90-Day Retention %"), (GR, "Proficient by Day 90 %")]))
    footer(pg, "All data is synthetic. A window counts only if it ended by the snapshot and the graduate was still "
               "employed; otherwise it is shown as not measured, never as zero.")
    return pg


# ------------------------------------------------------------------ 2. training effectiveness
def effectiveness() -> Page:
    pg = Page(PAL, EFFECT, "Training effectiveness")
    header(pg, "Does training predict early performance?", EFFECT)
    slicers(pg)
    y1 = KPI_Y
    h1 = (BOTTOM - KPI_Y - GAP) // 2
    w3 = (SPAN - 2 * GAP) // 3
    pg.chart("chHeat", pg.panel("heat", X0, y1, w3, h1, "SLA met by final training competency",
                                "Graduates split into thirds by final competency score"),
             heatmap(PAL, (GR, "competency_band", "Competency"), WINDOW, m(OW, "Window SLA Met %", "SLA met"),
                     low="#F4EFFC", high="#9C7FE0"))
    pg.chart("chProfBand", pg.panel("profBand", X0 + w3 + GAP, y1, w3, h1, "Proficiency by competency band",
                                    "Share of graduates meeting the standard by day 30 and by day 90"),
             column_chart(PAL, (GR, "competency_band", "Competency"),
                          [m(GR, "Proficient by Day 30 %", "By day 30"), m(GR, "Proficient by Day 90 %", "By day 90")],
                          colours=[PAL.accent_soft, PAL.accent], sort=sort_by(GR, "competency_band_order")))
    pg.chart("chScatter", pg.panel("scatter", X0 + 2 * (w3 + GAP), y1, SPAN - 2 * (w3 + GAP), h1,
                                   "Competency vs first-month first-time right", "One dot per graduate · days 1-30"),
             scatter((GR, "agent_id", "Graduate"), m(GR, "Avg Final Competency", "Final competency"),
                     m(OW, "Window First-Time-Right %", "First-time right, days 1-30")), DAYS_1_30)
    y2 = y1 + h1 + GAP
    h2 = BOTTOM - y2
    pg.chart("chCert", pg.panel("cert", X0, y2, w3, h2, "Certified at the first attempt?",
                                "First-time right by window: both certifications passed first time?"),
             column_chart(PAL, WINDOW, [m(OW, "Window First-Time-Right %", "First-time right")],
                          series=(GR, "certified_first_attempt", "Certified first attempt"),
                          series_colours=[("Yes", PAL.accent), ("No", "#C9BEEA")], sort=WINDOW_SORT))
    pg.chart("chWatch", pg.panel("watch", X0 + w3 + GAP, y2, w3, h2, "Watch list in training and retention",
                                 "90-day retention: was the trainee ever on the watch list?"),
             column_chart(PAL, (GR, "watchlisted_in_training", "On the training watch list"),
                          [m(GR, "90-Day Retention %", "90-day retention")], colours=[PAL.good],
                          sort=sort_by(GR, "watchlisted_in_training")))
    x = X0 + 2 * (w3 + GAP)
    pg.panel("findings", x, y2, SPAN - 2 * (w3 + GAP), h2, "What the data says")
    end = pg.bullets(x + 34, y2 + 88, SPAN - 2 * (w3 + GAP) - 64, [
        "Training predicts early performance, but only moderately: 24% of the top third by final competency met "
        "the standard in their first 30 days, against 8% of the bottom third.",
        "By day 90 most of the bottom third had caught up (72% proficient).",
        "Passing both certifications first time goes with a faster start: 16% proficient by day 30, against 9%.",
        "Trainees who were on the watch list were more likely to leave: 90.5% still employed at day 90, against 96.6%.",
        "Individual variation is large: a training score is a reason to support someone, not a verdict."],
        size=13.5, gap=8)
    pg.svg.append(svg_text(x + 34, end + 6, "Associations, not causes. Figures: all graduates, no filters.", 12,
                           PAL.muted, 600))
    footer(pg, "Complete 30-day windows only. Small groups (e.g. one cohort's bottom third) are noisy; read differences "
               "of a few points with care.")
    return pg


def scatter(details: tuple, x: tuple, y: tuple) -> dict:
    return {"visualType": "scatterChart",
            "query": {"queryState": {"Category": {"projections": [proj("Column", *details)]},
                                     "X": {"projections": [proj("Measure", *x)]},
                                     "Y": {"projections": [proj("Measure", *y)]}}},
            "objects": {"dataPoint": [{"properties": {"fill": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{PAL.accent}'"}}}}}}}],
                        "categoryAxis": [{"properties": {"showAxisTitle": {"expr": {"Literal": {"Value": "true"}}}}}],
                        "valueAxis": [{"properties": {"showAxisTitle": {"expr": {"Literal": {"Value": "true"}}}}}]}}


# ------------------------------------------------------------------ 3. roster
def roster() -> Page:
    pg = Page(PAL, ROSTER, "Graduate roster")
    header(pg, "Graduate roster", ROSTER)
    slicers(pg)
    rect = pg.panel("roster", X0, KPI_Y, SPAN, BOTTOM - KPI_Y, "Every deployed graduate: training record → outcome",
                    "Right-click a graduate \u2192 Drill through \u2192 Graduate journey \u00b7 click a column header to sort")
    pg.chart("tbRoster", rect, table([
        ("Column", GR, "graduate_name", "Graduate (synthetic)"), ("Column", GR, "agent_id", "Agent ID"),
        ("Column", GR, "cohort_name", "Cohort"), ("Column", GR, "final_competency_score", "Final competency"),
        ("Column", GR, "competency_band", "Band"), ("Column", GR, "attendance_rate_pct", "Attendance %"),
        ("Column", GR, "certified_first_attempt", "Certified 1st attempt"),
        ("Column", GR, "watchlisted_in_training", "Watch list"), ("Column", GR, "readiness_reviews", "Readiness reviews"),
        ("Column", GR, "deployment_date", "Deployed"), ("Column", GR, "primary_queue_name", "Queue"),
        ("Column", GR, "proficiency_status", "Proficiency"), ("Column", GR, "exit_reason", "Exit")],
        sort=sort_by(GR, "final_competency_score", direction="Descending"), font=9))
    footer(pg, "Names are synthetic. Proficiency status 'Not yet by day 90' means the standard was not met in any of the "
               "three windows; it does not mean the graduate failed.")
    return pg


# ------------------------------------------------------------------ 4. journey (drill-through)
def journey() -> Page:
    pg = Page(PAL, JOURNEY, "Graduate journey")
    header(pg, "Graduate journey", None, back=True)
    pg.surface(X0, KPI_Y, SPAN, 104)
    pg.add("grTitle", X0 + 20, KPI_Y + 8, SPAN - 40, 50, text_card(GR, "Graduate Title", 18, PAL.ink, "bold"))
    pg.add("grJourney", X0 + 20, KPI_Y + 58, SPAN - 40, 42, text_card(GR, "Graduate Journey Label", 10, PAL.muted))
    y1, h1 = KPI_Y + 104 + GAP, 380
    half = (SPAN - GAP) // 2
    pg.chart("chJourney", pg.panel("journeySla", X0, y1, half, h1, "SLA met and first-time right by window",
                                   "This graduate vs the tenured benchmark"),
             combo_chart(PAL, WINDOW, [m(OW, "Window SLA Met %", "SLA met"), m(OW, "Window First-Time-Right %", "First-time right")],
                         [m(PC, "SLA Met % (Tenured Benchmark)", "Tenured SLA benchmark")],
                         col_colours=[PAL.accent, PAL.good], line_colours=[TENURED], sort=WINDOW_SORT))
    pg.chart("chProd", pg.panel("journeyProd", X0 + half + GAP, y1, SPAN - half - GAP, h1, "Resolved cases per day worked",
                                "Productivity in each 30-day window"),
             column_chart(PAL, WINDOW, [m(OW, "Window Resolved per Agent-Day", "Per day")], colours=[PAL.accent],
                          sort=WINDOW_SORT))
    y2 = y1 + h1 + GAP
    pg.chart("tbWindows", pg.panel("windows", X0, y2, SPAN, BOTTOM + 20 - y2, "Window detail",
                                   "'Left before window end' and 'Not yet reached' windows are not measured (blank)"),
             table([("Column", OW, "window_label", "Window"), ("Column", OW, "window_start", "From"),
                    ("Column", OW, "window_status", "Status"), ("Column", OW, "cases_received", "Cases"),
                    ("Column", OW, "sla_met_pct", "SLA met %"), ("Column", OW, "first_time_right_pct", "First-time right %"),
                    ("Column", OW, "qa_reviews", "QA reviews"), ("Column", OW, "qa_passed", "QA passed"),
                    ("Column", OW, "agent_days", "Days worked"), ("Column", OW, "is_proficient", "Proficient (1/0)")],
                   sort=WINDOW_SORT))
    return pg


# ------------------------------------------------------------------ 5. method
def method() -> Page:
    pg = Page(PAL, METHOD, "Method")
    header(pg, "Method and definitions", METHOD)
    half = (SPAN - GAP) // 2
    blocks = [
        ("The question", [
            "Report 01 follows trainees through an 8-week academy. Report 02 follows the operations team. This report "
            "joins the two: for each graduate, how did training go, and how did their first 90 days in operations go?",
            "109 graduates were deployed between Oct 2026 and Mar 2027; every one has reached day 90 by the snapshot."]),
        ("Windows and the honest-window rule", [
            "Days 1-30, 31-60 and 61-90 after the graduate's first day in operations.",
            "A window counts only if it ended by the snapshot AND the graduate was still employed at its end.",
            "Otherwise it is 'Not yet reached' or 'Left before window end' and its metrics are blank: an exit never "
            "becomes a zero-performance month.",
            "Retention uses observed employment periods only."]),
        ("Proficiency standard", [
            "A complete window with SLA met ≥ 80% AND first-time right ≥ 97%, close to tenured agents' "
            "level (84% / 98%) less a small tolerance.",
            "Days to proficiency = the end of the first window that meets it (30, 60 or 90).",
            "Training attributes: final competency (latest week with all five competencies scored), attendance "
            "(present ÷ recorded), both mandatory certifications passed at attempt 1, ever on the watch list."]),
        ("Read with care", [
            "Synthetic data: the simulation builds in a MODERATE link between training and early performance, with "
            "large individual variation, as real studies typically find.",
            "Associations, not causes. Groups are small (about 36 graduates per competency third).",
            "Benchmarks are tenured agents across the whole period, filtered by the same team/queue only on Report 02."]),
    ]
    h = (BOTTOM - KPI_Y - GAP) // 2
    for i, (title, lines) in enumerate(blocks):
        x = X0 + (i % 2) * (half + GAP)
        y = KPI_Y + (i // 2) * (h + GAP)
        pg.panel(f"method{i}", x, y, half, h, title)
        pg.bullets(x + 34, y + 92, half - 70, lines, size=14.5, gap=10)
    return pg


def main() -> None:
    pages = [(overview(), None), (effectiveness(), None), (roster(), None),
             (journey(), drillthrough(GR, "agent_id", "journey")), (method(), None)]
    write_report(REPORT, THEME, pages, "workforce-outcomes.pbip", "r03")
    print(f"Report 03 written ({len(pages)} pages) on the shared model")


if __name__ == "__main__":
    main()
