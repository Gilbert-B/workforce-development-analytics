"""Page building blocks for the two LIGHT reports of the suite (Report 02 and Report 03).

Report 01 uses a dark "designed canvas" (decoration drawn in background
images). Reports 02 and 03 use a simpler, fully editable approach: every
panel, card frame and tab is a real Power BI shape or button, so anything can
be moved or restyled in Desktop. One Palette per report gives each its accent.

Layout grid: 1920 x 1080, content from x=48 to x=1872 (1824 px wide).
    y   28  eyebrow / title / snapshot pill
    y  112  page tabs (left) and slicers (right)
    y  176  KPI tiles
    y  324+ panels
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from pbir_lib import (FONT, S_PAGE, S_PAGES, button, category_filter, colour, container, field, literal, page_link,
                      props, proj, shape, textbox, value_selector, write_json)

PBI = Path(__file__).resolve().parents[1]
SHARED_MODEL = "../workforcedevelopmentanalytics.SemanticModel"    # Report 01's model: shared, not copied
REPORT01 = PBI / "workforcedevelopmentanalytics.Report"

W, H, X0, XR = 1920, 1080, 48, 1872
SPAN = XR - X0
GAP = 16


@dataclass(frozen=True)
class Palette:
    canvas: str
    surface: str
    ink: str
    muted: str
    border: str
    accent: str
    accent_soft: str
    good: str = "#1F9E8F"
    warn: str = "#C98A1B"
    bad: str = "#D1553F"
    neutral: str = "#8A96A8"


def text(size, colour_, weight="Segoe UI") -> dict:
    return {"fontFamily": weight, "fontSize": f"{size}pt", "color": colour_}


class Page:
    """Collects the visuals of one page and hands out z-order and unique names."""

    def __init__(self, pal: Palette, page_id: str, display: str):
        self.pal, self.id, self.display = pal, page_id, display
        self.visuals: list[dict] = []
        self.z = 10
        self.kpis: list[str] = []          # card visuals that chart clicks must not filter
        self.charts: list[str] = []

    def add(self, name: str, x, y, w, h, visual: dict, filters: list[dict] | None = None, hidden=False) -> dict:
        v = container(name, x, y, w, h, self.z, visual, hidden=hidden)
        if filters:
            v["filterConfig"] = {"filters": filters}
        self.visuals.append(v)
        self.z += 1
        return v

    # ------------------------------------------------------------ header and navigation
    def header(self, eyebrow: str, title: str, tabs: list[tuple[str, str]], active: str | None,
               snapshot: tuple[str, str], back=False) -> None:
        p = self.pal
        self.add("hdrEyebrow", X0, 22, 1100, 28, textbox([[(eyebrow, text(10, p.accent, "Segoe UI Semibold"))]]))
        self.add("hdrTitle", X0, 44, 1300, 56, textbox([[(title, text(26, p.ink, "Segoe UI Bold"))]]))
        self.add("hdrSnapSurface", 1452, 36, 420, 44, shape(p.surface, 0, p.border, 0))
        self.add("hdrSnapshot", 1462, 38, 400, 40, card_visual(*snapshot, size=10, colour_=p.muted, font="regular"))
        x = X0
        for page_id, label in tabs:
            is_active = page_id == active
            w = 26 + 9 * len(label)
            self.add(f"tab_{page_id}", x, 112, w, 40, button(
                label, link=None if is_active else page_link(page_id), fg="#FFFFFF" if is_active else p.muted,
                fill=p.accent if is_active else None, fill_alpha=100 if is_active else 0,
                hover_fill=p.accent_soft, hover_alpha=40, size=10,
                tooltip=None if is_active else f"Go to {label}"))
            x += w + 8
        if back:
            self.add("btnBack", XR - 120, 112, 120, 40, button(
                "←  Back", link={"type": "Back"}, fg=p.accent, fill=p.surface, fill_alpha=100,
                hover_fill=p.accent_soft, hover_alpha=40, size=10, tooltip="Back to the page you came from"))
        self.add("hdrRule", X0, 160, SPAN, 1, shape(p.border, 0))

    def slicer(self, name: str, x: int, w: int, table: str, column: str, label: str, sync: str) -> None:
        p = self.pal
        self.add(f"{name}Label", x, 100, w, 22, textbox([[(label.upper(), text(7, p.muted, "Segoe UI Semibold"))]]))
        self.add(name, x, 120, w, 36, {
            "visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [proj("Column", table, column, label)]}}},
            "objects": {"data": props(mode="Dropdown"),
                        "header": props(show=False),
                        "selection": props(selectAllCheckboxEnabled=True, singleSelect=False),
                        "items": props(fontColor=colour(p.ink), background=colour(p.surface), textSize=10)},
            "syncGroup": {"groupName": sync, "fieldChanges": True, "filterChanges": True}})

    # ------------------------------------------------------------ tiles and panels
    def kpi(self, prefix: str, x, y, w, h, label: str, table: str, measure: str, context: str, accent: str,
            filters: list[dict] | None = None) -> None:
        p = self.pal
        self.add(f"{prefix}Surface", x, y, w, h, shape(p.surface, 0, p.border, 0))
        self.add(f"{prefix}Accent", x, y + 16, 4, h - 32, shape(accent, 0))
        self.add(f"{prefix}Label", x + 18, y + 12, w - 30, 28, textbox([[(label, text(8, p.muted, "Segoe UI Semibold"))]]))
        self.add(prefix, x + 8, y + 32, w - 16, 52, card_visual(table, measure, size=24, colour_=p.ink), filters)
        self.add(f"{prefix}Context", x + 18, y + h - 36, w - 30, 30, textbox([[(context, text(8, p.muted))]]))
        self.kpis.append(prefix)

    def kpi_row(self, tiles: list[tuple], y=176, h=132) -> None:
        """tiles: (prefix, label, table, measure, context, accent[, filters])."""
        n = len(tiles)
        w = (SPAN - GAP * (n - 1)) // n
        for i, t in enumerate(tiles):
            self.kpi(t[0], X0 + i * (w + GAP), y, w, h, *t[1:6], filters=t[6] if len(t) > 6 else None)

    def panel(self, name: str, x, y, w, h, title: str, subtitle: str = "") -> tuple[int, int, int, int]:
        """White panel with a title; returns the body rectangle for the chart."""
        p = self.pal
        self.add(f"{name}Panel", x, y, w, h, shape(p.surface, 0, p.border, 0))
        lines = [[(title, text(12, p.ink, "Segoe UI Semibold"))]]
        if subtitle:
            lines.append([(subtitle, text(9, p.muted))])
        self.add(f"{name}Title", x + 12, y + 8, w - 24, 52 if subtitle else 32, textbox(lines))
        top = 62 if subtitle else 44
        return x + 12, y + top, w - 24, h - top - 10

    def chart(self, name: str, rect, visual: dict, filters: list[dict] | None = None) -> None:
        self.add(name, *rect, visual, filters)
        self.charts.append(name)

    def note(self, name: str, x, y, w, h, runs: list[list[tuple[str, dict]]]) -> None:
        self.add(name, x, y, w, h, textbox(runs))

    def interactions(self) -> list[dict]:
        """Chart clicks cross-filter other charts, but never the headline KPI numbers."""
        return [{"source": c, "target": k, "type": "NoFilter"} for c in self.charts for k in self.kpis]


# ---------------------------------------------------------------- visuals
def card_visual(table: str, measure: str, size=24, colour_="#0F1B2D", font="bold") -> dict:
    return {"visualType": "card",
            "query": {"queryState": {"Values": {"projections": [proj("Measure", table, measure)]}}},
            "objects": {"labels": props(fontFamily=FONT[font], fontSize=size, color=colour(colour_)),
                        "categoryLabels": props(show=False)},
            "visualContainerObjects": {"background": props(show=False)}}


def _axes(pal: Palette, x_title: str | None = None, y_title: str | None = None, categorical=True) -> dict:
    cat = props(showAxisTitle=bool(x_title), **({"titleText": x_title} if x_title else {}),
                **({"axisType": "Categorical"} if categorical else {}), labelColor=colour(pal.muted))
    val = props(showAxisTitle=bool(y_title), **({"titleText": y_title} if y_title else {}),
                labelColor=colour(pal.neutral), gridlineShow=True, gridlineColor=colour("#E6EBF1"))
    return {"categoryAxis": cat, "valueAxis": val}


def sort_by(table: str, column: str, kind="Column", direction="Ascending") -> dict:
    return {"sort": [{"field": field(kind, table, column), "direction": direction}]}


def column_chart(pal: Palette, cat: tuple, measures: list[tuple], *, colours: list[str] | None = None,
                 kind="clusteredColumnChart", sort: dict | None = None, labels=True, label_colour=None,
                 x_title=None, series: tuple | None = None, series_colours: list[tuple] | None = None) -> dict:
    """cat = (table, column, label); measures = [(table, measure, label), ...]."""
    qs = {"Category": {"projections": [proj("Column", *cat)]},
          "Y": {"projections": [proj("Measure", *m) for m in measures]}}
    if series:
        qs["Series"] = {"projections": [proj("Column", *series)]}
    objects = {**_axes(pal, x_title),
               "labels": props(show=labels, color=colour(label_colour or pal.ink), fontSize=9)}
    if series_colours:
        objects["dataPoint"] = [{"properties": {"fill": colour(c)}, "selector": value_selector(series[0], series[1], v)}
                                for v, c in series_colours]
    elif colours:
        objects["dataPoint"] = [{"properties": {"fill": colour(c)}, "selector": {"metadata": f"{m[0]}.{m[1]}"}}
                                for m, c in zip(measures, colours)]
    v = {"visualType": kind, "query": {"queryState": qs}, "objects": objects}
    if sort:
        v["query"]["sortDefinition"] = sort
    return v


def combo_chart(pal: Palette, cat: tuple, columns: list[tuple], lines: list[tuple], *, col_colours: list[str],
                line_colours: list[str], sort: dict | None = None, x_title=None) -> dict:
    """Columns (Y) plus lines (Y2) on a shared category axis: e.g. volume + SLA %, or a band vs its benchmark."""
    dp = [{"properties": {"fill": colour(c)}, "selector": {"metadata": f"{m[0]}.{m[1]}"}}
          for m, c in list(zip(columns, col_colours)) + list(zip(lines, line_colours))]
    v = {"visualType": "lineClusteredColumnComboChart",
         "query": {"queryState": {"Category": {"projections": [proj("Column", *cat)]},
                                  "Y": {"projections": [proj("Measure", *m) for m in columns]},
                                  "Y2": {"projections": [proj("Measure", *m) for m in lines]}}},
         "objects": {**_axes(pal, x_title), "dataPoint": dp,
                     "labels": props(show=True, color=colour(pal.ink), fontSize=9),
                     "lineStyles": props(strokeWidth=3, showMarker=True, markerSize=6)}}
    if sort:
        v["query"]["sortDefinition"] = sort
    return v


def line_chart(pal: Palette, cat: tuple, measures: list[tuple], colours: list[str], *, sort=None, x_title=None,
               categorical=True) -> dict:
    v = {"visualType": "lineChart",
         "query": {"queryState": {"Category": {"projections": [proj("Column", *cat)]},
                                  "Y": {"projections": [proj("Measure", *m) for m in measures]}}},
         "objects": {**_axes(pal, x_title, categorical=categorical),
                     "dataPoint": [{"properties": {"fill": colour(c)}, "selector": {"metadata": f"{m[0]}.{m[1]}"}}
                                   for m, c in zip(measures, colours)],
                     "lineStyles": props(strokeWidth=3, showMarker=True, markerSize=5),
                     "labels": props(show=False)}}
    if sort:
        v["query"]["sortDefinition"] = sort
    return v


def bar_chart(pal: Palette, cat: tuple, measure: tuple, colour_: str, *, sort=None, labels=True) -> dict:
    return column_chart(pal, cat, [measure], colours=[colour_], kind="clusteredBarChart", sort=sort, labels=labels)


def table(columns: list[tuple], *, sort: dict | None = None, font=10) -> dict:
    """columns: (kind, table, name, label) with kind 'Column' or 'Measure'."""
    return {"visualType": "tableEx",
            "query": {"queryState": {"Values": {"projections": [proj(k, t, n, label) for k, t, n, label in columns]}},
                      **({"sortDefinition": sort} if sort else {})},
            "objects": {"columnHeaders": props(wordWrap=True, fontSize=9),
                        "values": props(fontSize=font),
                        "grid": props(rowPadding=6)}}


def heatmap(pal: Palette, rows: tuple, cols: tuple, measure: tuple, low: str, high: str) -> dict:
    """Matrix with a colour scale (e.g. queue x tenure band, QA pass %)."""
    m_table, m_name, m_label = measure
    return {"visualType": "pivotTable",
            "query": {"queryState": {"Rows": {"projections": [proj("Column", *rows)]},
                                     "Columns": {"projections": [proj("Column", *cols)]},
                                     "Values": {"projections": [proj("Measure", m_table, m_name, m_label)]}}},
            "objects": {
                "values": [{"properties": {
                    "backColor": {"solid": {"color": {"expr": {"FillRule": {
                        "Input": field("Measure", m_table, m_name),
                        "FillRule": {"linearGradient2": {
                            "min": {"color": {"Literal": {"Value": f"'{low}'"}}},
                            "max": {"color": {"Literal": {"Value": f"'{high}'"}}},
                            "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'noColor'"}}}}}}}}}},
                    "fontColorPrimary": colour(pal.ink), "fontSize": literal(10)},
                    "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"{m_table}.{m_name}"}}],
                "subTotals": props(rowSubtotals=False, columnSubtotals=False),
                "columnHeaders": props(fontSize=9, fontColor=colour(pal.muted)),
                "rowHeaders": props(fontSize=10, fontColor=colour(pal.ink)),
                "grid": props(gridVertical=True, gridVerticalColor=colour(pal.surface), gridVerticalWeight=3,
                              gridHorizontal=True, gridHorizontalColor=colour(pal.surface), gridHorizontalWeight=3,
                              rowPadding=10)}}


def text_card(table: str, measure: str, size: int, colour_: str, font="regular") -> dict:
    """A card that shows a TEXT measure (titles and profile lines on drill-through pages)."""
    return card_visual(table, measure, size=size, colour_=colour_, font=font)


def eq(name: str, table: str, column: str, value: str) -> dict:
    """Visual filter: column = text value."""
    return category_filter(name, table, column, value)


def footer(pg: Page, message: str) -> None:
    pg.note("footer", X0, H - 26, 1600, 24, [[(message, text(8, pg.pal.muted))]])


# ---------------------------------------------------------------- writing a report
def page_json(pg: Page, extra: dict | None = None) -> dict:
    page = {"$schema": S_PAGE, "name": pg.id, "displayName": pg.display, "displayOption": "FitToPage",
            "height": H, "width": W,
            "objects": {"background": [{"properties": {"color": colour(pg.pal.canvas), "transparency": literal(0)}}],
                        "outspace": [{"properties": {"color": colour("#E9EEF4"), "transparency": literal(0)}}]}}
    inter = pg.interactions()
    if inter:
        page["visualInteractions"] = inter
    page.update(extra or {})
    return page


def drillthrough(table_: str, column: str, binding: str) -> dict:
    """Page settings that make a page a drill-through target on table_[column] (hidden from the tabs)."""
    f = field("Column", table_, column)
    return {"type": "Drillthrough", "visibility": "HiddenInViewMode",
            "pageBinding": {"name": f"{binding}Binding", "type": "Drillthrough",
                            "parameters": [{"name": f"{binding}Param", "boundFilter": f"{binding}Filter", "fieldExpr": f}]},
            "filterConfig": {"filters": [{"name": f"{binding}Filter", "field": f, "type": "Categorical",
                                          "howCreated": "Drillthrough"}]}}


def write_report(report: Path, theme: Path, pages: list[tuple[Page, dict | None]], pbip_name: str) -> None:
    """Write a complete PBIR report folder (+ .pbip) that uses the SHARED model. Rebuilds pages from scratch."""
    definition = report / "definition"
    resources = report / "StaticResources" / "RegisteredResources"
    (report.parent / pbip_name).write_text(json.dumps(
        {"version": "1.0", "artifacts": [{"report": {"path": report.name}}],
         "settings": {"enableAutoRecovery": True}}, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_json(report / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": SHARED_MODEL}}})
    write_json(definition / "version.json",
               {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
                "version": "2.0.0"})
    r01 = json.loads((REPORT01 / "definition" / "report.json").read_text(encoding="utf-8"))
    base = r01["themeCollection"]["baseTheme"]
    write_json(definition / "report.json", {
        "$schema": r01["$schema"],
        "themeCollection": {"baseTheme": base,
                            "customTheme": {"name": theme.name, "reportVersionAtImport": base["reportVersionAtImport"],
                                            "type": "RegisteredResources"}},
        "objects": r01["objects"],
        "resourcePackages": [p for p in r01["resourcePackages"] if p["name"] == "SharedResources"]
        + [{"name": "RegisteredResources", "type": "RegisteredResources",
            "items": [{"name": theme.name, "path": theme.name, "type": "CustomTheme"}]}],
        "settings": r01["settings"]})
    shutil.copytree(REPORT01 / "StaticResources" / "SharedResources", report / "StaticResources" / "SharedResources",
                    dirs_exist_ok=True)
    if resources.exists():
        shutil.rmtree(resources)
    resources.mkdir(parents=True)
    shutil.copyfile(theme, resources / theme.name)
    pages_dir = definition / "pages"
    if pages_dir.exists():
        shutil.rmtree(pages_dir)
    for pg, extra in pages:
        for v in pg.visuals:
            write_json(pages_dir / pg.id / "visuals" / v["name"] / "visual.json", v)
        write_json(pages_dir / pg.id / "page.json", page_json(pg, extra))
    write_json(pages_dir / "pages.json", {"$schema": S_PAGES, "pageOrder": [pg.id for pg, _ in pages],
                                          "activePageName": pages[0][0].id})
    for pg, _ in pages:
        print(f"  {pg.display:<26} {len(pg.visuals):>3} visuals")
