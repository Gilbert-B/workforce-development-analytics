"""Scaffold the 'Workforce Intelligence Overview' page as PBIR JSON files.

WHAT THIS IS
    A one-time generator. It writes the page, its 13 visuals, and registers
    the custom theme in the Power BI Project (PBIP) under powerbi/.
    After you open and save the report in Power BI Desktop, DESKTOP IS THE
    SOURCE OF TRUTH. Re-running this script OVERWRITES the page's visuals,
    so only re-run it deliberately (e.g. to reset the layout).

HOW A PBIR PAGE IS STORED
    <name>.Report/definition/pages/<pageId>/page.json          page settings
    <name>.Report/definition/pages/<pageId>/visuals/<id>/visual.json
                                                               one per visual
    Each visual.json = position (x, y, width, height, z) + visual type +
    query (which model fields go into which "role") + a few formatting
    overrides. Colours/fonts come from the theme, not from the visuals.

USAGE (from the repository root, with Power BI Desktop CLOSED)
    python powerbi/tools/build_overview_page.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REPORT = REPO / "powerbi" / "workforcedevelopmentanalytics.Report"
DEFINITION = REPORT / "definition"
THEME_SOURCE = REPO / "powerbi" / "themes" / "WorkforceIntelligence.json"
PAGE_ID = "0f2c0daa0493675582ab"          # keep the existing page's id
PAGE_NAME = "Workforce Intelligence Overview"

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
VISUAL_SCHEMA = f"{SCHEMA}/visualContainer/2.13.0/schema.json"
PAGE_SCHEMA = f"{SCHEMA}/page/2.1.0/schema.json"

# --------------------------------------------------------------------------
# LAYOUT GRID (pixels on a 1920 x 1080 page). Change numbers here to move
# things; everything below reads from these constants.
# --------------------------------------------------------------------------
PAGE_W, PAGE_H = 1920, 1080
MARGIN = 40                     # outer margin on every side
GAP = 16                        # space between tiles
RAIL_W = 320                    # left rail: cohort selector + definitions
HEADER_H = 88                   # title + subtitle band
CONTENT_X = MARGIN + RAIL_W + GAP + 8          # 384: where the main area starts
CONTENT_W = PAGE_W - MARGIN - CONTENT_X        # 1496
TOP = MARGIN + HEADER_H                        # 128: first row under the header
KPI_H = 150
KPI_COUNT = 6
KPI_W = (CONTENT_W - GAP * (KPI_COUNT - 1)) // KPI_COUNT   # 236
CHART_Y = TOP + KPI_H + 20                     # 298
CHART_H = PAGE_H - MARGIN - CHART_Y            # 742
STATUS_W = 724
TREND_X = CONTENT_X + STATUS_W + GAP           # 1124
TREND_W = PAGE_W - MARGIN - TREND_X            # 756

# Model names exactly as they appear in Power BI (note the space after "rpt")
ENROL, ATTEND, COMPET, COHORT, WEEK, SNAP = (
    "rpt dim_enrolment", "rpt fact_attendance", "rpt dim_competency",
    "rpt dim_cohort", "rpt dim_programme_week", "rpt dim_snapshot")

# The six approved KPI cards: (visual id, table, measure, label on the card)
KPIS = [
    ("kpiStartingHeadcount", ENROL,  "Starting Headcount",            "Starting headcount"),
    ("kpiActiveTrainees",    ENROL,  "Active Trainees (Snapshot)",    "Active trainees (end of day)"),
    ("kpiCompletedTrainees", ENROL,  "Completed Trainees (Snapshot)", "Completed trainees"),
    ("kpiAvgCompetency",     COMPET, "Average Competency Score",      "Average competency score (0-100)"),
    ("kpiRecordedAttendance", ATTEND, "Recorded Attendance Rate",     "Recorded attendance rate"),
    ("kpiRecordingRate",     ATTEND, "Attendance Recording Rate",     "Attendance recording rate"),
]

# Training-status series and their colours (restrained: blue / teal / brick)
STATUS_SERIES = [
    ("Active Trainees (Snapshot)",    "Active",    "#1F4E79"),
    ("Completed Trainees (Snapshot)", "Completed", "#2A9D8F"),
    ("Withdrawn Trainees (Snapshot)", "Withdrawn", "#A8573F"),
]


# --------------------------------------------------------------------------
# Small helpers that build the JSON fragments Power BI expects.
# --------------------------------------------------------------------------
def literal(value) -> dict:
    """PBIR stores formatting values as expressions. Strings are wrapped in
    single quotes, numbers get a 'D' suffix (e.g. 28D), booleans stay as-is."""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (int, float)):
        text = f"{value}D"
    else:
        text = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": text}}}


def colour(hex_code: str) -> dict:
    return {"solid": {"color": literal(hex_code)}}


def props(**kwargs) -> list[dict]:
    """One formatting 'object' with properties, e.g. props(show=True)."""
    return [{"properties": {k: (v if isinstance(v, dict) else literal(v)) for k, v in kwargs.items()}}]


def measure(table: str, name: str, label: str | None = None) -> dict:
    p = {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
         "queryRef": f"{table}.{name}", "nativeQueryRef": name}
    if label:
        p["displayName"] = label
    return p


def column(table: str, name: str, label: str | None = None) -> dict:
    p = {"field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
         "queryRef": f"{table}.{name}", "nativeQueryRef": name}
    if label:
        p["displayName"] = label
    return p


def container(title: str | None = None, subtitle: str | None = None) -> dict:
    """Formatting of the visual's frame (title, subtitle). Style comes from the theme."""
    objs = {}
    if title:
        objs["title"] = props(show=True, text=title)
    else:
        objs["title"] = props(show=False)
    if subtitle:
        objs["subTitle"] = props(show=True, text=subtitle)
    return objs


def visual_file(name: str, x: int, y: int, w: int, h: int, z: int, visual: dict) -> dict:
    return {
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": z * 1000, "width": w, "height": h, "tabOrder": z * 1000},
        "visual": visual,
    }


def textbox(paragraphs: list[list[tuple[str, dict]]]) -> dict:
    """paragraphs = [[(text, textStyle), ...], ...] - one inner list per line."""
    return {
        "visualType": "textbox",
        "objects": {"general": [{"properties": {"paragraphs": [
            {"textRuns": [{"value": text, "textStyle": style} for text, style in runs]}
            for runs in paragraphs]}}]},
        "drillFilterOtherVisuals": True,
    }


# --------------------------------------------------------------------------
# The visuals on the page
# --------------------------------------------------------------------------
def build_visuals() -> list[dict]:
    visuals = []
    z = 1

    # Header: title + subtitle (static text)
    visuals.append(visual_file("headerTitle", MARGIN, MARGIN - 8, 1100, 52, z, textbox([
        [("Workforce Intelligence Overview",
          {"fontFamily": "Segoe UI Semibold", "fontSize": "24pt", "color": "#0B2545"})],
    ]))); z += 1
    visuals.append(visual_file("headerSubtitle", MARGIN, MARGIN + 42, 1100, 34, z, textbox([
        [("Payments Operations Associate onboarding  |  fictional digital payments provider  |  all cohorts compared by programme week",
          {"fontFamily": "Segoe UI", "fontSize": "11pt", "color": "#5B6573"})],
    ]))); z += 1

    # Dynamic snapshot label (top right): a card showing the [Snapshot Label] text measure
    visuals.append(visual_file("snapshotLabel", PAGE_W - MARGIN - 420, MARGIN - 4, 420, 56, z, {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [measure(SNAP, "Snapshot Label")]}}},
        "objects": {
            "labels": props(fontSize=12, color=colour("#5B6573")),
            "categoryLabels": props(show=False),
        },
        "visualContainerObjects": {
            **container(None),
            "background": props(show=False),
            "border": props(show=False),
            "visualHeader": props(show=False),
        },
        "drillFilterOtherVisuals": True,
    })); z += 1

    # Left rail: cohort selector (multi-select list with "Select all")
    visuals.append(visual_file("cohortSlicer", MARGIN, TOP, RAIL_W, 236, z, {
        "visualType": "slicer",
        "query": {"queryState": {"Values": {"projections": [column(COHORT, "cohort_name", "Cohort")]}}},
        "objects": {
            "data": props(mode="Basic"),
            "selection": props(selectAllCheckboxEnabled=True, singleSelect=False),
            "header": props(show=True, text="Cohort"),
        },
        "visualContainerObjects": container(None),
        "drillFilterOtherVisuals": True,
    })); z += 1

    # Left rail: definitions panel (static text with the approved definitions)
    h = {"fontFamily": "Segoe UI Semibold", "fontSize": "10pt", "color": "#1B2430"}
    t = {"fontFamily": "Segoe UI", "fontSize": "10pt", "color": "#5B6573"}
    visuals.append(visual_file("definitionsPanel", MARGIN, TOP + 236 + GAP, RAIL_W,
                               PAGE_H - MARGIN - (TOP + 236 + GAP), z, {
        **textbox([
            [("How to read this page", {**h, "fontSize": "12pt"})],
            [("", t)],
            [("Snapshot measures  ", h), ("Active and Completed are each trainee's status at the end of the snapshot day. A trainee who completes on the last programme day counts as Completed that day.", t)],
            [("", t)],
            [("Recorded attendance rate  ", h), ("Present / (Present + Absent). Unrecorded sessions are excluded, never counted as absent.", t)],
            [("", t)],
            [("Attendance recording rate  ", h), ("Recorded sessions / eligible sessions: how complete the attendance registers are.", t)],
            [("", t)],
            [("Competency progression  ", h), ("Cohorts are compared by programme week, not calendar date. Weeks not yet reached are blank, not zero.", t)],
            [("", t)],
            [("All figures come from a fully synthetic dataset.", {**t, "fontSize": "9pt"})],
        ]),
        "visualContainerObjects": {
            "background": props(show=True, color=colour("#FFFFFF")),
            "border": props(show=True, color=colour("#E3E7ED"), radius=6),
        },
    })); z += 1

    # KPI row: six cards
    for i, (vid, table, name, label) in enumerate(KPIS):
        x = CONTENT_X + i * (KPI_W + GAP)
        visuals.append(visual_file(vid, x, TOP, KPI_W, KPI_H, z, {
            "visualType": "card",
            "query": {"queryState": {"Values": {"projections": [measure(table, name, label)]}}},
            "visualContainerObjects": {
                **container(None),     # no title: the card shows its own label
            },
            "drillFilterOtherVisuals": True,
        })); z += 1

    # Training status by cohort: stacked bar, one bar per cohort
    visuals.append(visual_file("statusByCohort", CONTENT_X, CHART_Y, STATUS_W, CHART_H, z, {
        "visualType": "barChart",
        "query": {
            "queryState": {
                "Category": {"projections": [column(COHORT, "cohort_name", "Cohort")]},
                "Y": {"projections": [measure(ENROL, m, label) for m, label, _ in STATUS_SERIES]},
            },
            "sortDefinition": {"sort": [{"field": column(COHORT, "cohort_name")["field"],
                                         "direction": "Ascending"}], "isDefaultSort": False},
        },
        "objects": {
            "dataPoint": [{"properties": {"fill": colour(c)},
                           "selector": {"metadata": f"{ENROL}.{m}"}} for m, _, c in STATUS_SERIES],
            "labels": props(show=True, color=colour("#FFFFFF"), fontSize=10),
            "legend": props(show=True, position="Top"),
            "categoryAxis": props(showAxisTitle=False),
            "valueAxis": props(showAxisTitle=False, gridlineShow=True),
        },
        "visualContainerObjects": container(
            "Training status by cohort",
            "Starters only: Active + Completed + Withdrawn = starting headcount (snapshot)"),
        "drillFilterOtherVisuals": True,
    })); z += 1

    # Weekly competency progression: one line per cohort, by programme week
    visuals.append(visual_file("competencyTrend", TREND_X, CHART_Y, TREND_W, CHART_H, z, {
        "visualType": "lineChart",
        "query": {
            "queryState": {
                "Category": {"projections": [column(WEEK, "programme_week", "Programme week")]},
                "Y": {"projections": [measure(COMPET, "Average Competency Score", "Average score")]},
                "Series": {"projections": [column(COHORT, "cohort_name", "Cohort")]},
            },
            "sortDefinition": {"sort": [{"field": column(WEEK, "programme_week")["field"],
                                         "direction": "Ascending"}], "isDefaultSort": False},
        },
        "objects": {
            # Categorical: show weeks 1..8 as labels, not a continuous number line
            "categoryAxis": props(axisType="Categorical", showAxisTitle=True, titleText="Programme week"),
            "valueAxis": props(showAxisTitle=True, titleText="Average competency score (0-100)", gridlineShow=True),
            "lineStyles": props(strokeWidth=3, showMarker=True),
            "legend": props(show=True, position="Top"),
        },
        "visualContainerObjects": container(
            "Weekly competency progression",
            "Average core competency score by programme week; in-progress cohorts stop at their latest assessed week"),
        "drillFilterOtherVisuals": True,
    })); z += 1

    return visuals


def page_json(visual_names: list[str]) -> dict:
    kpi_ids = [k[0] for k in KPIS]
    # Interaction design: only the COHORT SLICER changes the headline KPIs.
    # Clicking a bar or a line point filters/highlights the other chart but
    # leaves the KPI cards alone, so the headline numbers always describe
    # the selected cohorts, not an accidental click.
    interactions = [{"source": src, "target": tgt, "type": "NoFilter"}
                    for src in ("statusByCohort", "competencyTrend") for tgt in kpi_ids]
    return {
        "$schema": PAGE_SCHEMA,
        "name": PAGE_ID,
        "displayName": PAGE_NAME,
        "displayOption": "FitToPage",
        "height": PAGE_H,
        "width": PAGE_W,
        "visualInteractions": interactions,
    }


def register_theme() -> None:
    """Copy the theme into the report and reference it from report.json."""
    target_dir = REPORT / "StaticResources" / "RegisteredResources"
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(THEME_SOURCE, target_dir / THEME_SOURCE.name)

    path = DEFINITION / "report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    base_version = report["themeCollection"]["baseTheme"]["reportVersionAtImport"]
    report["themeCollection"]["customTheme"] = {
        "name": THEME_SOURCE.name,
        "reportVersionAtImport": base_version,
        "type": "RegisteredResources",
    }
    packages = [p for p in report["resourcePackages"] if p["name"] != "RegisteredResources"]
    packages.append({"name": "RegisteredResources", "type": "RegisteredResources",
                     "items": [{"name": THEME_SOURCE.name, "path": THEME_SOURCE.name,
                                "type": "CustomTheme"}]})
    report["resourcePackages"] = packages
    write_json(path, report)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    page_dir = DEFINITION / "pages" / PAGE_ID
    visuals_dir = page_dir / "visuals"
    if visuals_dir.exists():
        shutil.rmtree(visuals_dir)          # start the page's visuals from scratch
    visuals = build_visuals()
    for v in visuals:
        write_json(visuals_dir / v["name"] / "visual.json", v)
    write_json(page_dir / "page.json", page_json([v["name"] for v in visuals]))
    register_theme()
    print(f"Wrote page '{PAGE_NAME}' with {len(visuals)} visuals and registered theme {THEME_SOURCE.name}")
    for v in visuals:
        p = v["position"]
        print(f"  {v['name']:<22} {v['visual']['visualType']:<10} x={p['x']:<5} y={p['y']:<5} {p['width']}x{p['height']}")


if __name__ == "__main__":
    main()
