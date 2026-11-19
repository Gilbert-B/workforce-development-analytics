"""Build Report 02 (Payment Operations Performance) as PBIR files.

ARCH-01 scope: a SHELL that proves a second report can use the shared
semantic model. Its definition.pbir points at Report 01's model folder
("byPath"), exactly like Report 01 does, so both reports read the same
tables, relationships and measures. No operational visuals yet (BI-03).

Design: light "operations command centre": white cards on a pale canvas,
navy accent, the suite's shared status colours (good / warning / bad / neutral).

USAGE (repository root, Power BI Desktop CLOSED)
    python powerbi/tools/build_payment_operations.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pbir_lib import FONT, S_PAGE, S_PAGES, colour, container, literal, proj, props, shape, textbox, write_json

REPO = Path(__file__).resolve().parents[2]
PBI = REPO / "powerbi"
REPORT = PBI / "PaymentOperations.Report"
DEFINITION = REPORT / "definition"
RESOURCES = REPORT / "StaticResources" / "RegisteredResources"
THEME = PBI / "themes" / "PaymentOperationsLight.json"
SHARED_MODEL = "../workforcedevelopmentanalytics.SemanticModel"    # Report 01's model: shared, not copied
REPORT01 = PBI / "workforcedevelopmentanalytics.Report"

# light command-centre palette (themes/PaymentOperationsLight.json)
CANVAS, SURFACE, INK, MUTED, BORDER, ACCENT = "#F5F7FA", "#FFFFFF", "#0F1B2D", "#5B6B80", "#DCE3EC", "#0B5CAD"
GOOD, WARN, BAD = "#1F9E8F", "#C98A1B", "#D1553F"
W, H, X0 = 1920, 1080, 64
PAGE_ID = "c1a7e3b9d5f2a8c4e6b0"

ENROL, SNAP, RREV = "rpt dim_enrolment", "rpt dim_snapshot", "rpt fact_readiness_review"


def text_style(size, colour_=INK, weight="Segoe UI"):
    return {"fontFamily": weight, "fontSize": f"{size}pt", "color": colour_}


def card(table, measure, size=30, colour_=INK, font="bold"):
    return {"visualType": "card",
            "query": {"queryState": {"Values": {"projections": [proj("Measure", table, measure)]}}},
            "objects": {"labels": props(fontFamily=FONT[font], fontSize=size, color=colour(colour_)),
                        "categoryLabels": props(show=False)}}


def tile(prefix, x, y, w, h, z, label, table, measure, context, accent):
    """White KPI card: surface + accent bar + label + number + context (all editable visuals)."""
    return [container(f"{prefix}Surface", x, y, w, h, z, shape(SURFACE, 0, BORDER, 0)),
            container(f"{prefix}Accent", x, y, 6, h, z + 1, shape(accent, 0)),
            container(f"{prefix}Label", x + 24, y + 18, w - 40, 28, z + 2, textbox([[(label, text_style(9, MUTED, "Segoe UI Semibold"))]])),
            container(prefix, x + 14, y + 44, w - 28, 64, z + 3, card(table, measure)),
            container(f"{prefix}Context", x + 24, y + h - 42, w - 40, 30, z + 4, textbox([[(context, text_style(9, MUTED))]]))]


def visuals() -> list[dict]:
    v = [container("eyebrow", X0, 36, 900, 28, 10, textbox([[("PAYMENT OPERATIONS PERFORMANCE · REPORT 02 OF 3",
                                                               text_style(10, ACCENT, "Segoe UI Semibold"))]])),
         container("title", X0, 60, 1200, 60, 11, textbox([[("Payment Operations Performance",
                                                             {"fontFamily": "Segoe UI Bold", "fontSize": "28pt", "color": INK})]])),
         container("snapshotSurface", 1416, 44, 440, 44, 12, shape(SURFACE, 0, BORDER, 0)),
         container("snapshotLabel", 1428, 46, 416, 40, 13, card(SNAP, "Snapshot Label", 10, MUTED, "regular")),
         container("shellNote", X0, 128, 1500, 56, 14, textbox([
             [("Shell (ARCH-01). ", text_style(11, INK, "Segoe UI Semibold")),
              ("This report has no model of its own: it reads the shared Workforce Intelligence semantic model "
               "that Report 01 uses. The numbers below are existing shared measures, proving the link.", text_style(11, MUTED))]]))]
    z, w, gap, y = 100, 448, 16, 208
    tiles = [("kpiApproved", "APPROVED FOR READINESS (SNAPSHOT)", RREV, "Ready / Approved (Snapshot)",
              "The deployment pool for payment operations", GOOD),
             ("kpiCompleted", "COMPLETED TRAINEES (SNAPSHOT)", ENROL, "Completed Trainees (Snapshot)",
              "Shared Report 01 measure", ACCENT),
             ("kpiEnrolments", "TOTAL ENROLMENTS", ENROL, "Total Enrolments", "Shared Report 01 measure", ACCENT)]
    for i, (prefix, label, table, measure, context, accent) in enumerate(tiles):
        v += tile(prefix, X0 + i * (w + gap), y, w, 150, z, label, table, measure, context, accent); z += 10
    plan_y = 390
    v.append(container("planSurface", X0, plan_y, 1376, 300, z, shape(SURFACE, 0, BORDER, 0))); z += 1
    v.append(container("planText", X0 + 28, plan_y + 22, 1320, 260, z, textbox([
        [("Coming in BI-03", text_style(14, INK, "Segoe UI Semibold"))],
        [("Queue health and backlog · throughput and productivity · resolution time · accuracy, errors and rework "
          "· quality assurance · SLA compliance · exception management.", text_style(11, MUTED))],
        [("Built on the same shared model: new operations tables are ADDED to it, and existing Report 01 "
          "tables, relationships and measures stay unchanged.", text_style(11, MUTED))]]))); z += 1
    v.append(container("suiteSurface", X0 + 1392, plan_y, 1792 - 1392, 300, z, shape(SURFACE, 0, BORDER, 0))); z += 1
    v.append(container("suiteText", X0 + 1416, plan_y + 22, 360, 260, z, textbox([
        [("WORKFORCE INTELLIGENCE SUITE", text_style(9, ACCENT, "Segoe UI Semibold"))],
        [("01  Workforce Development & Readiness", text_style(11, INK, "Segoe UI Semibold"))],
        [("workforcedevelopmentanalytics.pbip", text_style(9, MUTED))],
        [("02  Payment Operations Performance", text_style(11, ACCENT, "Segoe UI Semibold"))],
        [("this report · payment-operations.pbip", text_style(9, MUTED))],
        [("03  Workforce Outcomes & Training Effectiveness", text_style(11, INK, "Segoe UI Semibold"))],
        [("planned (Build 04)", text_style(9, MUTED))]]))); z += 1
    v.append(container("syntheticNote", X0, 1030, 1200, 30, z, textbox([[(
        "All data is synthetic: a fictional payments operations organisation.", text_style(9, MUTED))]])))
    return v


def main() -> None:
    (PBI / "payment-operations.pbip").write_text(json.dumps(
        {"version": "1.0", "artifacts": [{"report": {"path": "PaymentOperations.Report"}}],
         "settings": {"enableAutoRecovery": True}}, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_json(REPORT / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": SHARED_MODEL}}})
    write_json(DEFINITION / "version.json",
               {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
                "version": "2.0.0"})
    # report.json: same base theme and settings as Report 01, its own light custom theme
    r01 = json.loads((REPORT01 / "definition" / "report.json").read_text(encoding="utf-8"))
    base = r01["themeCollection"]["baseTheme"]
    report = {"$schema": r01["$schema"],
              "themeCollection": {"baseTheme": base,
                                  "customTheme": {"name": THEME.name, "reportVersionAtImport": base["reportVersionAtImport"],
                                                  "type": "RegisteredResources"}},
              "objects": r01["objects"],
              "resourcePackages": [p for p in r01["resourcePackages"] if p["name"] == "SharedResources"]
              + [{"name": "RegisteredResources", "type": "RegisteredResources",
                  "items": [{"name": THEME.name, "path": THEME.name, "type": "CustomTheme"}]}],
              "settings": r01["settings"]}
    write_json(DEFINITION / "report.json", report)
    shared = REPORT / "StaticResources" / "SharedResources"
    shutil.copytree(REPORT01 / "StaticResources" / "SharedResources", shared, dirs_exist_ok=True)
    RESOURCES.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(THEME, RESOURCES / THEME.name)

    page_dir = DEFINITION / "pages" / PAGE_ID
    if (page_dir / "visuals").exists():
        shutil.rmtree(page_dir / "visuals")
    vis = visuals()
    for v in vis:
        write_json(page_dir / "visuals" / v["name"] / "visual.json", v)
    write_json(page_dir / "page.json", {
        "$schema": S_PAGE, "name": PAGE_ID, "displayName": "Operations overview (shell)", "displayOption": "FitToPage",
        "height": H, "width": W,
        "objects": {"background": [{"properties": {"color": colour(CANVAS), "transparency": literal(0)}}],
                    "outspace": [{"properties": {"color": colour("#E9EEF4"), "transparency": literal(0)}}]}})
    write_json(DEFINITION / "pages" / "pages.json", {"$schema": S_PAGES, "pageOrder": [PAGE_ID], "activePageName": PAGE_ID})
    print(f"Report 02 shell written: {len(vis)} visuals, model = {SHARED_MODEL}")


if __name__ == "__main__":
    main()
