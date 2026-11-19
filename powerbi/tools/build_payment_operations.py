"""Build Report 02, Payment Operations Performance, as PBIR files (BI-03).

The report has no model of its own: definition.pbir points at Report 01's
semantic model folder ("byPath"), so all three reports share one set of
tables, relationships and measures (D41). The operations tables and measures
are added to that model by powerbi/tools/build_model.py.

Pages
    1. Operations overview   volume, SLA, backlog, queue league table
    2. Graduate ramp-up      learning curve by tenure band vs the tenured benchmark
    3. Quality               QA sample, pass rate, checklist failures, heatmap
    4. Agent 360             drill-through: one agent's profile and trend (hidden tab)
    5. About                 definitions, data lineage, caveats

USAGE (repository root, Power BI Desktop CLOSED)
    python powerbi/tools/build_payment_operations.py
Re-running rebuilds every page from scratch (changes made in Desktop are lost).
"""

from __future__ import annotations

from pathlib import Path

from pbir_lib import shape
from suite_light import (GAP, SPAN, X0, H, Page, Palette, bar_chart, column_chart, combo_chart, drillthrough, eq,
                         footer, heatmap, line_chart, sort_by, table, text, text_card, write_report)

REPO = Path(__file__).resolve().parents[2]
PBI = REPO / "powerbi"
REPORT = PBI / "PaymentOperations.Report"
THEME = PBI / "themes" / "PaymentOperationsLight.json"

PAL = Palette(canvas="#F5F7FA", surface="#FFFFFF", ink="#0F1B2D", muted="#5B6B80", border="#DCE3EC",
              accent="#0B5CAD", accent_soft="#CFE0F3")
TENURED = "#2E3A4B"           # benchmark colour (tenured agents)

OVERVIEW, RAMP, QUALITY, AGENT, ABOUT = ("c1a7e3b9d5f2a8c4e6b0", "d2b8f4c0e6a3b9d5f7c1", "e3c9a5d1f7b4c0e6a8d2",
                                         "f4d0b6e2a8c5d1f7b9e3", "a5e1c7f3b9d6e2a8c0f4")
TABS = [(OVERVIEW, "Operations overview"), (RAMP, "Graduate ramp-up"), (QUALITY, "Quality"), (ABOUT, "About")]

PC, QA, QC, AG, AD, Q, SNAP = ("rpt fact_payment_case", "rpt fact_qa_review", "rpt fact_qa_check", "rpt dim_agent",
                               "rpt fact_agent_day", "rpt dim_ops_queue", "rpt dim_snapshot")
SNAPSHOT = (SNAP, "Snapshot Label")
EYEBROW = "PAYMENT OPERATIONS PERFORMANCE · REPORT 02 OF 3"
BAND = (PC, "tenure_band", "Tenure band")
BAND_SORT = sort_by(PC, "tenure_band_order")


def m(table: str, name: str, label: str | None = None) -> tuple:
    return (table, name, label or name)


def slicers(pg: Page) -> None:
    """Team, queue and month: synced across the analysis pages."""
    pg.slicer("slTeam", 1100, 230, Q, "team_name", "Team", "OpsTeam")
    pg.slicer("slQueue", 1346, 250, Q, "queue_name", "Queue", "OpsQueue")
    pg.slicer("slPriority", 1612, 260, PC, "priority", "Priority", "OpsPriority")


# ------------------------------------------------------------------ 1. overview
def overview() -> Page:
    pg = Page(PAL, OVERVIEW, "Operations overview")
    pg.header(EYEBROW, "Payment Operations Performance", TABS, OVERVIEW, SNAPSHOT)
    slicers(pg)
    pg.kpi_row([
        ("kpiReceived", "CASES RECEIVED", PC, "Cases Received", "Payment exceptions, Aug 2026 – Jun 2027", PAL.accent),
        ("kpiSla", "SLA MET", PC, "SLA Met %", "Final resolution within the original target", PAL.good),
        ("kpiFtr", "FIRST-TIME RIGHT", PC, "First-Time-Right %", "Resolved with no rework", PAL.good),
        ("kpiQa", "QA PASS RATE", QA, "QA Pass %", "Sampled cases, score ≥ 85 of 100", PAL.accent),
        ("kpiOpen", "OPEN CASES (SNAPSHOT)", PC, "Open Cases (Snapshot)", "Unresolved at 30 Jun 2027", PAL.warn),
        ("kpiOverdue", "OVERDUE OPEN (SNAPSHOT)", PC, "Overdue Open Cases (Snapshot)", "Open and past the SLA target", PAL.bad),
    ])
    y1, h1 = 324, 380
    wl = 1180
    pg.chart("chMonthly", pg.panel("monthly", X0, y1, wl, h1, "Monthly volume and SLA met",
                                   "Columns: cases received · line: SLA met % (resolved cases, by month received)"),
             combo_chart(PAL, (PC, "received_month", "Month received"), [m(PC, "Cases Received")],
                         [m(PC, "SLA Met %")], col_colours=[PAL.accent_soft], line_colours=[PAL.accent],
                         sort=sort_by(PC, "received_month")))
    pg.chart("chPriority", pg.panel("priority", X0 + wl + GAP, y1, SPAN - wl - GAP, h1, "SLA met by priority",
                                    "P1 targets are 4 h (2 h for screening hits), P2 24 h, P3 72 h"),
             column_chart(PAL, (PC, "priority", "Priority"), [m(PC, "SLA Met %"), m(PC, "SLA Met % (Tenured Benchmark)", "Tenured agents")],
                          colours=[PAL.accent, TENURED], sort=sort_by(PC, "priority")))
    y2, h2 = y1 + h1 + GAP, H - (y1 + h1 + GAP) - 28
    pg.chart("tbQueues", pg.panel("queues", X0, y2, wl, h2, "Queue league table",
                                  "Click a queue to filter the page · open and overdue are as at the snapshot"),
             table([("Column", Q, "queue_name", "Queue"), ("Column", Q, "team_name", "Team"),
                    ("Measure", PC, "Cases Received", "Cases"), ("Measure", PC, "SLA Met %", "SLA met"),
                    ("Measure", PC, "First-Time-Right %", "First-time right"), ("Measure", QA, "QA Pass %", "QA pass"),
                    ("Measure", PC, "Median Resolution Hours", "Median hours"),
                    ("Measure", PC, "Open Cases (Snapshot)", "Open"), ("Measure", PC, "Overdue Open Cases (Snapshot)", "Overdue")],
                   sort=sort_by(PC, "Cases Received", "Measure", "Descending")))
    pg.chart("chBacklog", pg.panel("backlog", X0 + wl + GAP, y2, SPAN - wl - GAP, h2, "Open backlog at the snapshot",
                                   "Open cases by queue; overdue = past the SLA target"),
             column_chart(PAL, (Q, "queue_name", "Queue"),
                          [m(PC, "Open Cases (Snapshot)", "Open"), m(PC, "Overdue Open Cases (Snapshot)", "Overdue")],
                          colours=[PAL.warn, PAL.bad], kind="clusteredBarChart",
                          sort=sort_by(PC, "Open Cases (Snapshot)", "Measure", "Descending")))
    footer(pg, "All data is synthetic: a fictional payments operations organisation. "
                                                "SLA is judged on FINAL resolution against the ORIGINAL target; open cases "
                                                "are never counted as met or missed.")
    return pg


# ------------------------------------------------------------------ 2. ramp-up
def ramp_up() -> Page:
    pg = Page(PAL, RAMP, "Graduate ramp-up")
    pg.header(EYEBROW, "Graduate ramp-up: the first 90 days", TABS, RAMP, SNAPSHOT)
    slicers(pg)
    first30 = [eq("first30", PC, "tenure_band", "0-30 days")]
    mature = [eq("mature", PC, "tenure_band", "90+ days")]
    pg.kpi_row([
        ("kpiGrads", "GRADUATE AGENTS (SNAPSHOT)", AG, "Graduate Agents (Snapshot)", "Deployed from the academy, still employed", PAL.accent),
        ("kpiSla30", "SLA MET · FIRST 30 DAYS", PC, "SLA Met %", "Graduates in their first 30 days", PAL.warn, first30),
        ("kpiSla90", "SLA MET · AFTER 90 DAYS", PC, "SLA Met %", "Graduates with 90+ days in role", PAL.good, mature),
        ("kpiBench", "TENURED BENCHMARK", PC, "SLA Met % (Tenured Benchmark)", "Experienced agents, same filters", TENURED),
        ("kpiFtr30", "FIRST-TIME RIGHT · FIRST 30 DAYS", PC, "First-Time-Right %", "No rework, first 30 days", PAL.warn, first30),
        ("kpiProd", "RESOLVED PER AGENT-DAY", AD, "Resolved per Agent-Day", "All agents, days worked", PAL.accent),
    ])
    y1, h1 = 324, 352
    w3 = (SPAN - 2 * GAP) // 3
    pg.chart("chSlaBand", pg.panel("slaBand", X0, y1, w3, h1, "SLA met by tenure band",
                                   "Graduates by days since starting · line = tenured agents"),
             combo_chart(PAL, BAND, [m(PC, "SLA Met %")], [m(PC, "SLA Met % (Tenured Benchmark)", "Tenured benchmark")],
                         col_colours=[PAL.accent], line_colours=[TENURED], sort=BAND_SORT))
    pg.chart("chFtrBand", pg.panel("ftrBand", X0 + w3 + GAP, y1, w3, h1, "First-time right by tenure band",
                                   "Resolved without a QA failure or customer reopen"),
             combo_chart(PAL, BAND, [m(PC, "First-Time-Right %")],
                         [m(PC, "First-Time-Right % (Tenured Benchmark)", "Tenured benchmark")],
                         col_colours=[PAL.good], line_colours=[TENURED], sort=BAND_SORT))
    pg.chart("chProdBand", pg.panel("prodBand", X0 + 2 * (w3 + GAP), y1, SPAN - 2 * (w3 + GAP), h1,
                                    "Resolved cases per agent-day", "Productivity rises as new agents ramp up"),
             column_chart(PAL, (AD, "tenure_band", "Tenure band"), [m(AD, "Resolved per Agent-Day")],
                          colours=[PAL.accent], sort=sort_by(AD, "tenure_band_order")))
    y2, h2 = y1 + h1 + GAP, H - (y1 + h1 + GAP) - 28
    pg.chart("chHours", pg.panel("hours", X0, y2, w3, h2, "Median resolution hours",
                                 "Received to final resolution, by tenure band"),
             column_chart(PAL, BAND, [m(PC, "Median Resolution Hours")], colours=[PAL.warn], sort=BAND_SORT))
    pg.chart("tbAgents", pg.panel("agents", X0 + w3 + GAP, y2, SPAN - w3 - GAP, h2, "Agent league table",
                                  "Right-click an agent → Drill through → Agent 360"),
             table([("Column", AG, "agent_name", "Agent (synthetic)"), ("Column", AG, "agent_id", "Agent ID"),
                    ("Column", AG, "agent_type", "Type"), ("Column", AG, "start_date", "Started"),
                    ("Measure", PC, "Cases Received", "Cases"), ("Measure", PC, "SLA Met %", "SLA met"),
                    ("Measure", PC, "First-Time-Right %", "First-time right"), ("Measure", QA, "QA Pass %", "QA pass"),
                    ("Measure", AD, "Resolved per Agent-Day", "Per day")],
                   sort=sort_by(PC, "SLA Met %", "Measure", "Descending"), font=9))
    footer(pg, "Tenure band = days between the agent's start and the day the case was "
                                                "received. The benchmark ignores agent and tenure filters but keeps team, "
                                                "queue and priority.")
    return pg


# ------------------------------------------------------------------ 3. quality
def quality() -> Page:
    pg = Page(PAL, QUALITY, "Quality")
    pg.header(EYEBROW, "Quality assurance and rework", TABS, QUALITY, SNAPSHOT)
    slicers(pg)
    pg.kpi_row([
        ("kpiReviews", "QA REVIEWS", QA, "QA Reviews", "A sample of resolved cases", PAL.accent),
        ("kpiSample", "QA SAMPLE RATE", PC, "QA Sample Rate %", "25% in an agent's first 30 days, 10% after", PAL.accent),
        ("kpiPass", "QA PASS RATE", QA, "QA Pass %", "Weighted checklist score ≥ 85", PAL.good),
        ("kpiScore", "AVERAGE QA SCORE", QA, "Avg QA Score", "Six weighted items, 0–100", PAL.good),
        ("kpiCritical", "CRITICAL ERRORS", QA, "QA Critical Error %", "Financial or compliance error", PAL.bad),
        ("kpiRework", "REWORKED CASES", PC, "Reworked Cases", "QA failure or customer reopen", PAL.warn),
    ])
    y1, h1 = 324, 352
    wl = 860
    pg.chart("chItems", pg.panel("items", X0, y1, wl, h1, "Which checklist items fail most",
                                 "Share of reviewed cases failing each item"),
             bar_chart(PAL, (QC, "item_name", "Checklist item"), m(QC, "Checklist Item Fail %", "Fail rate"), PAL.bad,
                       sort=sort_by(QC, "Checklist Item Fail %", "Measure", "Descending")))
    pg.chart("chHeat", pg.panel("heat", X0 + wl + GAP, y1, SPAN - wl - GAP, h1, "QA pass rate: queue × tenure band",
                                "Darker = higher pass rate · small cells are noisy"),
             heatmap(PAL, (Q, "queue_name", "Queue"), (QA, "tenure_band", "Tenure band"), m(QA, "QA Pass %", "QA pass"),
                     low="#FBE3DC", high="#9FD8CF"))
    y2, h2 = y1 + h1 + GAP, H - (y1 + h1 + GAP) - 28
    pg.chart("chQaTrend", pg.panel("qaTrend", X0, y2, wl, h2, "QA pass rate by review month",
                                   "Dated by the review, not by when the case arrived"),
             line_chart(PAL, (QA, "reviewed_month", "Review month"), [m(QA, "QA Pass %"), m(QA, "QA Critical Error %", "Critical errors")],
                        [PAL.good, PAL.bad], sort=sort_by(QA, "reviewed_month")))
    pg.chart("chFtrQueue", pg.panel("ftrQueue", X0 + wl + GAP, y2, SPAN - wl - GAP, h2, "First-time right and rework by queue",
                                    "Rework is added to the case history; it never overwrites the first resolution"),
             combo_chart(PAL, (Q, "queue_name", "Queue"), [m(PC, "Reworked Cases", "Reworked cases")],
                         [m(PC, "First-Time-Right %")], col_colours=[PAL.warn], line_colours=[PAL.good],
                         sort=sort_by(PC, "Reworked Cases", "Measure", "Descending")))
    footer(pg, "QA results exist only for sampled cases; an unsampled case is 'not "
                                                "reviewed', never 'passed' or 'failed'.")
    return pg


# ------------------------------------------------------------------ 4. agent 360 (drill-through)
def agent_360() -> Page:
    pg = Page(PAL, AGENT, "Agent 360")
    pg.header(EYEBROW + " · DRILL-THROUGH", "Agent 360", TABS, None, SNAPSHOT, back=True)
    pg.add("agTitleSurface", X0, 176, SPAN, 96, pg_shape(PAL.surface, PAL.border))
    pg.add("agTitle", X0 + 16, 180, SPAN - 32, 46, text_card(AG, "Agent Title", 18, PAL.ink, "bold"))
    pg.add("agProfile", X0 + 16, 226, SPAN - 32, 40, text_card(AG, "Agent Profile Label", 10, PAL.muted))
    pg.kpi_row([
        ("kpiAgCases", "CASES RECEIVED", PC, "Cases Received", "Credited to this agent", PAL.accent),
        ("kpiAgSla", "SLA MET", PC, "SLA Met %", "Resolved cases", PAL.good),
        ("kpiAgFtr", "FIRST-TIME RIGHT", PC, "First-Time-Right %", "No rework", PAL.good),
        ("kpiAgQa", "QA PASS RATE", QA, "QA Pass %", "Sampled cases only", PAL.accent),
        ("kpiAgProd", "RESOLVED PER DAY", AD, "Resolved per Agent-Day", "Days worked", PAL.accent),
        ("kpiAgDays", "DAYS WORKED", AD, "Agent-Days Worked", "Within employment only", PAL.neutral),
    ], y=288, h=120)
    y1, h1 = 424, 300
    half = (SPAN - GAP) // 2
    pg.chart("chAgMonthly", pg.panel("agMonthly", X0, y1, half, h1, "Monthly cases and SLA met"),
             combo_chart(PAL, (PC, "received_month", "Month received"), [m(PC, "Cases Received")], [m(PC, "SLA Met %")],
                         col_colours=[PAL.accent_soft], line_colours=[PAL.accent], sort=sort_by(PC, "received_month")))
    pg.chart("chAgBand", pg.panel("agBand", X0 + half + GAP, y1, SPAN - half - GAP, h1, "This agent's ramp vs the tenured benchmark"),
             combo_chart(PAL, BAND, [m(PC, "SLA Met %")], [m(PC, "SLA Met % (Tenured Benchmark)", "Tenured benchmark")],
                         col_colours=[PAL.accent], line_colours=[TENURED], sort=BAND_SORT))
    y2 = y1 + h1 + GAP
    pg.chart("tbAgCases", pg.panel("agCases", X0, y2, SPAN, H - y2 - 20, "Cases (most recent first)",
                                   "First and final resolution are both kept; rework adds history"),
             table([("Column", PC, "case_id", "Case"), ("Column", PC, "received_at", "Received"),
                    ("Column", PC, "case_type_code", "Type"), ("Column", PC, "priority", "Priority"),
                    ("Column", PC, "status", "Status"), ("Column", PC, "final_resolution_hours", "Hours to final"),
                    ("Column", PC, "sla_met", "SLA met (1/0)"), ("Column", PC, "rework_count", "Rework"),
                    ("Column", PC, "qa_passed", "QA passed (1/0, blank = not sampled)")],
                   sort=sort_by(PC, "received_at", direction="Descending"), font=9))
    return pg


def pg_shape(fill: str, outline: str) -> dict:
    return shape(fill, 0, outline, 0)


# ------------------------------------------------------------------ 5. about
def about() -> Page:
    pg = Page(PAL, ABOUT, "About")
    pg.header(EYEBROW, "About this report", TABS, ABOUT, SNAPSHOT)
    half = (SPAN - GAP) // 2
    blocks = [
        ("What it shows", [
            "A fictional payments operations team handles five kinds of payment exception: returned, duplicate, "
            "failed validation, missing beneficiary and sanctions-screening hits.",
            "109 graduates of the training academy (Report 01) joined 40 tenured agents between Aug 2026 and Jun 2027.",
            "The question: how quickly do new graduates reach the standard of experienced agents, and where does "
            "quality slip?"]),
        ("Key definitions", [
            "SLA met: FINAL resolution within the ORIGINAL target hours (no pauses). Open cases are never counted "
            "as met or missed; they are 'overdue' once past their target.",
            "First-time right: resolved with no rework (no QA failure and no customer reopen).",
            "QA: a sample (25% in an agent's first 30 days, 10% after) scored on six weighted items; pass = 85+.",
            "Tenure band: days from the agent's start to the day the case was received."]),
        ("Where the data comes from", [
            "Cases are JSON documents in MongoDB (as a case-management system would hold them).",
            "A Python ETL loads them incrementally into SQL Server (checkpoint on updated_at + id, idempotent, "
            "bad documents rejected with a reason) and reconciles counts.",
            "SQL views (rpt schema) feed one shared Power BI model used by all three reports."]),
        ("Read with care", [
            "All people, cases and numbers are synthetic.",
            "Small slices (one agent, one queue in one month) are noisy.",
            "The benchmark compares like with like on team, queue and priority, but not on case difficulty."]),
    ]
    for i, (title, lines) in enumerate(blocks):
        x = X0 + (i % 2) * (half + GAP)
        y = 184 + (i // 2) * 430
        pg.panel(f"about{i}", x, y, half, 410, title)
        pg.note(f"aboutText{i}", x + 12, y + 50, half - 24, 350,
                [[("•  " + line, text(11, PAL.ink))] for line in lines])
    return pg


def main() -> None:
    pages = [(overview(), None), (ramp_up(), None), (quality(), None),
             (agent_360(), drillthrough(AG, "agent_id", "agent360")), (about(), None)]
    write_report(REPORT, THEME, pages, "payment-operations.pbip")
    print(f"Report 02 written ({len(pages)} pages) on the shared model")


if __name__ == "__main__":
    main()
