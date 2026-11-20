"""Page building blocks for the two LIGHT reports of the suite (Report 02 and Report 03).

DESIGN PRINCIPLE: everything stays an editable Power BI object.
  * Styling lives in the report THEME (generated here from the report's Palette):
    every card, chart and table gets a white rounded "card" container with a
    soft shadow, and title / subtitle fonts, from the theme. A visual added later
    in Desktop picks up the same look automatically.
  * Each visual carries only its CONTENT: its fields and its title / subtitle
    text (Format pane > General > Title). Power BI lays the title, subtitle and
    value out itself, so nothing can overlap or clip.
  * KPI tile = ONE card visual: title = label, subtitle = context line.
  * Header = a band image (decoration only, no text), text boxes for eyebrow and
    title, button tabs, slicers with their own titles. Icons are small SVG image
    visuals: swap or delete them like any other visual.

    y    0-232  header band          y  212-348  KPI cards          y  364+  charts
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from pbir_lib import (FONT, S_PAGE, S_PAGES, button, category_filter, colour, container, field, image, literal,
                      page_link, props, proj, textbox, value_selector, write_json)

PBI = Path(__file__).resolve().parents[1]
SHARED_MODEL = "../workforcedevelopmentanalytics.SemanticModel"    # Report 01's model: shared, not copied
REPORT01 = PBI / "workforcedevelopmentanalytics.Report"

W, H, X0, XR = 1920, 1080, 48, 1872
SPAN = XR - X0
GAP = 16
HERO_H = 232
KPI_Y, KPI_H = 212, 136
BODY_Y = 364
BOTTOM = H - 34                 # charts end here; the footer text box sits below

ICONS = {  # 24x24 stroke icons (same family as Report 01)
    "users": '<path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"/><path d="M2 21c.8-4 3.6-6 7-6s6.2 2 7 6"/><path d="M16 3.5a4 4 0 0 1 0 7.5M22 21c-.5-3-2.3-5-5-5.6"/>',
    "cap": '<path d="m2 9 10-5 10 5-10 5z"/><path d="M6 11v5c3 2.5 9 2.5 12 0v-5"/>',
    "star": '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z"/>',
    "doc": '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h5"/>',
    "shield": '<path d="M12 3 4 6v6c0 4.5 3.4 8.2 8 9 4.6-.8 8-4.5 8-9V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "alert": '<path d="M12 3 2.5 20h19z"/><path d="M12 10v4.5M12 17.2v.3"/>',
    "inbox": '<path d="M3 13 6 5h12l3 8v6H3z"/><path d="M3 13h5l1.5 3h5L16 13h5"/>',
    "trend": '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    "rework": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "gauge": '<path d="M4 18a9 9 0 1 1 16 0"/><path d="m12 13 4-5"/>',
    "calendar": '<rect x="3" y="4" width="18" height="17" rx="3"/><path d="M3 9h18M8 2v4M16 2v4"/>',
}
CARD_TYPES = ["card", "lineClusteredColumnComboChart", "clusteredColumnChart", "clusteredBarChart", "lineChart",
              "tableEx", "pivotTable", "scatterChart", "columnChart", "barChart", "multiRowCard"]


@dataclass(frozen=True)
class Palette:
    canvas: str
    surface: str
    ink: str
    muted: str
    border: str
    accent: str
    accent_soft: str
    hero_from: str = "#0A1F3D"         # header band gradient
    hero_to: str = "#0B5CAD"
    hero_text: str = "#C9DBF2"         # eyebrow / slicer titles on the band
    good: str = "#1F9E8F"
    warn: str = "#C98A1B"
    bad: str = "#D1553F"
    neutral: str = "#8A96A8"


def text(size, colour_, weight="Segoe UI") -> dict:
    return {"fontFamily": weight, "fontSize": f"{size}pt", "color": colour_}


def icon_svg(name: str, stroke: str) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
            f'stroke="{stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


def band_svg(pal: Palette) -> str:
    """Header band decoration only (gradient, rings, dots): no text, so nothing in it ever needs editing."""
    return "".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{HERO_H}" viewBox="0 0 {W} {HERO_H}">',
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2=".35"><stop offset="0" stop-color="{pal.hero_from}"/>'
        f'<stop offset="1" stop-color="{pal.hero_to}"/></linearGradient>'
        '<pattern id="d" width="22" height="22" patternUnits="userSpaceOnUse">'
        '<circle cx="2" cy="2" r="1.1" fill="#FFFFFF" fill-opacity=".07"/></pattern></defs>',
        f'<rect width="{W}" height="{HERO_H}" fill="url(#g)"/><rect width="{W}" height="{HERO_H}" fill="url(#d)"/>',
        *[f'<circle cx="1760" cy="-30" r="{r}" fill="none" stroke="#FFFFFF" stroke-opacity="{o}" stroke-width="1.5"/>'
          for r, o in ((150, .10), (240, .07), (330, .05), (420, .035))],
        "</svg>"])


def chrome(title: str | None = None, subtitle: str | None = None, *, background: bool = True) -> dict:
    """Per-visual container settings: ONLY the text. Fonts, colours, border and shadow come from the theme."""
    out = {}
    if title is not None:
        out["title"] = props(show=True, text=title)
    if subtitle is not None:
        out["subTitle"] = props(show=True, text=subtitle)
    if not background:
        out["background"] = props(show=False)
        out["border"] = props(show=False)
        out["dropShadow"] = props(show=False)
    return out


class Panel(tuple):
    """A chart rectangle that remembers the title and subtitle the chart should show."""
    title: str
    subtitle: str


class Page:
    """One report page: a list of Power BI visuals plus the SVG assets they use."""

    def __init__(self, pal: Palette, page_id: str, display: str):
        self.pal, self.id, self.display = pal, page_id, display
        self.visuals: list[dict] = []
        self.assets: dict[str, str] = {}   # resource file name -> SVG text
        self.z = 10
        self.kpis: list[str] = []          # card visuals that chart clicks must not filter
        self.charts: list[str] = []

    def add(self, name: str, x, y, w, h, visual: dict, filters: list[dict] | None = None, hidden=False,
            container_objects: dict | None = None) -> dict:
        if container_objects:
            vco = visual.setdefault("visualContainerObjects", {})
            vco.update(container_objects)
        v = container(name, x, y, w, h, self.z, visual, hidden=hidden)
        if filters:
            v["filterConfig"] = {"filters": filters}
        self.visuals.append(v)
        self.z += 1
        return v

    def icon(self, name: str, x, y, size, stroke: str) -> None:
        fname = f"icon-{name}-{stroke.lstrip('#').lower()}.svg"
        self.assets[fname] = icon_svg(name, stroke)
        self.add(f"icon_{name}_{x}_{y}", x, y, size, size, image(fname))

    # ------------------------------------------------------------ header band
    def header(self, eyebrow: str, title: str, tabs: list[tuple[str, str]], active: str | None,
               snapshot: tuple[str, str], back=False, logo="trend", band_file: str = "band.svg") -> None:
        p = self.pal
        self.assets[band_file] = band_svg(p)
        self.add("hdrBand", 0, 0, W, HERO_H, image(band_file))
        self.icon(logo, X0 + 12, 46, 28, "#FFFFFF")
        self.add("hdrEyebrow", X0 + 60, 30, 1000, 32, textbox([[(eyebrow, text(9.5, p.hero_text, "Segoe UI Semibold"))]]))
        self.add("hdrTitle", X0 + 60, 54, 1000, 60, textbox([[(title, text(24, "#FFFFFF", "Segoe UI Bold"))]]))
        self.add("hdrSnapshot", 1452, 30, 420, 46, card_visual(*snapshot, size=10, colour_="#FFFFFF", font="regular"),
                 container_objects={"background": props(show=True, color=colour("#FFFFFF"), transparency=88),
                                    "border": props(show=True, color=colour("#FFFFFF"), radius=22, width=1),
                                    "dropShadow": props(show=False)})
        x = X0
        for page_id, label in tabs:
            is_active = page_id == active
            w = 34 + 9 * len(label)
            self.add(f"tab_{page_id}", x, 162, w, 40, button(
                label, link=None if is_active else page_link(page_id), fg=p.accent if is_active else "#E3ECF8",
                fill="#FFFFFF" if is_active else None, fill_alpha=100 if is_active else 0,
                hover_fill="#FFFFFF", hover_alpha=85, size=10,
                tooltip=None if is_active else f"Go to {label}"))
            x += w + 8
        if back:
            self.add("btnBack", XR - 132, 162, 132, 40, button(
                "\u2190  Back", link={"type": "Back"}, fg="#FFFFFF", fill="#FFFFFF", fill_alpha=16,
                hover_fill="#FFFFFF", hover_alpha=75, size=10, tooltip="Back to the page you came from"))

    def slicer(self, name: str, x: int, w: int, table: str, column: str, label: str, sync: str) -> None:
        """Dropdown slicer on the band; its own title is the label (editable in the Format pane)."""
        p = self.pal
        self.add(name, x, 92, w, 64, {
            "visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [proj("Column", table, column, label)]}}},
            "objects": {"data": props(mode="Dropdown"),
                        "header": props(show=False),
                        "selection": props(selectAllCheckboxEnabled=True, singleSelect=False),
                        "items": props(fontColor=colour(p.ink), background=colour(p.surface), textSize=10)},
            "syncGroup": {"groupName": sync, "fieldChanges": True, "filterChanges": True}},
            container_objects={"title": props(show=True, text=label, fontColor=colour(p.hero_text), fontSize=8,
                                              fontFamily=FONT["semibold"]),
                               "background": props(show=False), "border": props(show=False),
                               "dropShadow": props(show=False), "padding": props(top=0, bottom=0, left=0, right=0)})

    # ------------------------------------------------------------ KPI cards
    def kpi(self, prefix: str, x, y, w, h, label: str, table: str, measure: str, context: str, accent: str,
            filters: list[dict] | None = None, icon: str = "target") -> None:
        """ONE card visual: title = label, subtitle = context, value = the measure. Plus a swappable icon."""
        self.add(prefix, x, y, w, h, card_visual(table, measure, size=22, colour_=self.pal.ink), filters,
                 container_objects=chrome(label, context))
        self.icon(icon, x + w - 42, y + h - 40, 24, accent)      # bottom-right corner: never under the title
        self.kpis.append(prefix)

    def kpi_row(self, tiles: list[tuple], y=KPI_Y, h=KPI_H) -> None:
        """tiles: (prefix, label, table, measure, context, accent, filters|None, icon)."""
        n = len(tiles)
        w = (SPAN - GAP * (n - 1)) // n
        for i, t in enumerate(tiles):
            self.kpi(t[0], X0 + i * (w + GAP), y, w, h, *t[1:6],
                     filters=t[6] if len(t) > 6 else None, icon=t[7] if len(t) > 7 else "target")

    # ------------------------------------------------------------ charts and text panels
    def panel(self, name: str, x, y, w, h, title: str, subtitle: str = "") -> Panel:
        """The rectangle a chart will fill; the chart shows `title` / `subtitle` in its own header."""
        r = Panel((x, y, w, h))
        r.title, r.subtitle = title, subtitle
        return r

    def chart(self, name: str, rect, visual: dict, filters: list[dict] | None = None) -> None:
        co = chrome(rect.title, rect.subtitle or None) if isinstance(rect, Panel) else None
        self.add(name, *rect, visual, filters, container_objects=co)
        self.charts.append(name)

    def text_panel(self, name: str, x, y, w, h, title: str, items: list[str], size=11, note: str | None = None) -> None:
        """A white text card (heading + bullet paragraphs): an ordinary, editable text box."""
        p = self.pal
        paras = [[(title, text(13, p.ink, "Segoe UI Semibold"))], [("", text(6, p.ink))]]
        for item in items:
            paras.append([("\u2022  " + item, text(size, p.ink))])
            paras.append([("", text(4, p.ink))])
        if note:
            paras.append([(note, text(size - 1, p.muted, "Segoe UI Semibold"))])
        self.add(name, x, y, w, h, textbox(paras),
                 container_objects={"background": props(show=True, color=colour(p.surface), transparency=0),
                                    "border": props(show=True, color=colour(p.border), radius=14, width=1),
                                    "dropShadow": props(show=True, color=colour(p.ink), transparency=92,
                                                        position="Outer", preset="Custom", shadowBlur=12,
                                                        shadowDistance=3, shadowSpread=0, angle=90),
                                    "padding": props(top=18, bottom=14, left=22, right=22)})

    def note(self, name: str, x, y, w, h, runs: list[list[tuple[str, dict]]]) -> None:
        self.add(name, x, y, w, h, textbox(runs))

    def interactions(self) -> list[dict]:
        """Chart clicks cross-filter other charts, but never the headline KPI numbers."""
        return [{"source": c, "target": k, "type": "NoFilter"} for c in self.charts for k in self.kpis]


# ---------------------------------------------------------------- visuals
def card_visual(table: str, measure: str, size=24, colour_="#0F1B2D", font="bold") -> dict:
    return {"visualType": "card",
            "query": {"queryState": {"Values": {"projections": [proj("Measure", table, measure)]}}},
            # labelDisplayUnits 1 = "None": show 49,995, not Power BI's automatic "50K"
            "objects": {"labels": props(fontFamily=FONT[font], fontSize=size, color=colour(colour_), labelDisplayUnits=1),
                        "categoryLabels": props(show=False)},
            # no title unless the caller gives one (KPI cards do, via chrome())
            "visualContainerObjects": {"title": props(show=False), "subTitle": props(show=False)}}


def _axes(pal: Palette, x_title: str | None = None, y_title: str | None = None, categorical=True) -> dict:
    cat = props(showAxisTitle=bool(x_title), **({"titleText": x_title} if x_title else {}),
                **({"axisType": "Categorical"} if categorical else {}), labelColor=colour(pal.muted))
    val = props(showAxisTitle=bool(y_title), **({"titleText": y_title} if y_title else {}),
                labelColor=colour(pal.neutral), gridlineShow=True, gridlineColor=colour("#EEF1F5"))
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
                     # data labels on, except on benchmark lines: one constant line needs no label on every column
                     "labels": props(show=True, color=colour(pal.ink), fontSize=9)
                     + [{"properties": {"show": literal(False)}, "selector": {"metadata": f"{m[0]}.{m[1]}"}}
                        for m in lines if "Benchmark" in m[1]],
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


def colour_scale(table_: str, measure: str, low: str, high: str) -> dict:
    """Conditional background colour (gradient) for one measure column of a table or matrix."""
    return {"properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {
                "Input": field("Measure", table_, measure),
                "FillRule": {"linearGradient2": {
                    "min": {"color": {"Literal": {"Value": f"'{low}'"}}},
                    "max": {"color": {"Literal": {"Value": f"'{high}'"}}},
                    "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'noColor'"}}}}}}}}}}},
            "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"{table_}.{measure}"}}


def table(columns: list[tuple], *, sort: dict | None = None, font=10,
          scales: list[tuple[str, str]] | None = None, low="#FBE3DC", high="#CDEDE7") -> dict:
    """columns: (kind, table, name, label) with kind 'Column' or 'Measure'.
    scales: [(table, measure)] measure columns to shade from `low` (worst) to `high` (best)."""
    values = props(fontSize=font)
    values += [colour_scale(t, m_, low, high) for t, m_ in (scales or [])]
    return {"visualType": "tableEx",
            "query": {"queryState": {"Values": {"projections": [proj(k, t, n, label) for k, t, n, label in columns]}},
                      **({"sortDefinition": sort} if sort else {})},
            "objects": {"columnHeaders": props(wordWrap=True, fontSize=9, fontFamily=FONT["semibold"]),
                        "values": values,
                        "grid": props(rowPadding=7, gridHorizontal=True, gridHorizontalColor=colour("#EEF1F5"))}}


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
    pg.note("footer", X0, H - 30, 1600, 28, [[(message, text(8, pg.pal.neutral))]])


# ---------------------------------------------------------------- theme
def theme(pal: Palette, name: str, data_colours: list[str]) -> dict:
    """The report theme: ALL shared styling. Card-like visuals get a white rounded container with a soft
    shadow and consistent title / subtitle fonts; everything else (text boxes, buttons, images) stays bare."""
    solid = lambda c: {"solid": {"color": c}}                                   # noqa: E731
    card_chrome = {
        "background": [{"show": True, "color": solid(pal.surface), "transparency": 0}],
        "border": [{"show": True, "color": solid(pal.border), "radius": 14, "width": 1}],
        "dropShadow": [{"show": True, "color": solid(pal.ink), "transparency": 92, "position": "Outer",
                        "preset": "Custom", "shadowBlur": 12, "shadowDistance": 3, "shadowSpread": 0, "angle": 90}],
        "padding": [{"top": 12, "bottom": 10, "left": 16, "right": 16}],
        "title": [{"show": True, "fontColor": solid(pal.ink), "fontSize": 12, "fontFamily": FONT["semibold"],
                   "alignment": "left", "titleWrap": True}],
        "subTitle": [{"show": True, "fontColor": solid(pal.muted), "fontSize": 9, "fontFamily": FONT["regular"],
                      "alignment": "left", "titleWrap": True}],
        "visualHeader": [{"show": False}],
    }
    styles = {
        "*": {"*": {
            "background": [{"show": False}], "border": [{"show": False}], "dropShadow": [{"show": False}],
            "title": [{"show": False}], "visualHeader": [{"show": False}],
            "legend": [{"show": True, "position": "Top", "labelColor": solid(pal.muted), "fontSize": 9}],
            "categoryAxis": [{"labelColor": solid(pal.muted), "titleColor": solid(pal.muted), "gridlineShow": False}],
            "valueAxis": [{"labelColor": solid(pal.neutral), "titleColor": solid(pal.neutral),
                           "gridlineColor": solid("#EEF1F5"), "gridlineStyle": "dotted"}],
            "labels": [{"color": solid(pal.ink), "fontSize": 9}]}},
        "page": {"*": {"background": [{"color": solid(pal.canvas), "transparency": 0}],
                       "outspace": [{"color": solid(pal.canvas), "transparency": 0}]}},
        "card": {"*": {**card_chrome,
                       "title": [{**card_chrome["title"][0], "fontColor": solid(pal.muted), "fontSize": 9}],
                       "subTitle": [{**card_chrome["subTitle"][0], "fontColor": solid(pal.neutral), "fontSize": 8}],
                       "labels": [{"color": solid(pal.ink), "fontSize": 22, "fontFamily": FONT["bold"]}],
                       "categoryLabels": [{"show": False}]}},
        "tableEx": {"*": {**card_chrome,
                          "columnHeaders": [{"fontColor": solid(pal.muted), "backColor": solid(pal.surface),
                                             "fontFamily": FONT["semibold"], "fontSize": 9, "outline": "Bottom only"}],
                          "values": [{"fontColorPrimary": solid(pal.ink), "backColorPrimary": solid(pal.surface),
                                      "fontColorSecondary": solid(pal.ink), "backColorSecondary": solid("#F7F8FB"),
                                      "fontSize": 10}],
                          "grid": [{"gridHorizontalColor": solid("#EEF1F5"), "rowPadding": 6}]}},
    }
    for t in CARD_TYPES:
        styles.setdefault(t, {"*": dict(card_chrome)})
    return {"name": name, "dataColors": data_colours, "foreground": pal.ink, "foregroundNeutralSecondary": pal.muted,
            "foregroundNeutralTertiary": pal.neutral, "background": pal.surface, "backgroundLight": pal.canvas,
            "backgroundNeutral": pal.border, "tableAccent": pal.accent, "good": pal.good, "neutral": pal.warn,
            "bad": pal.bad, "maximum": pal.good, "center": "#F2E3C4", "minimum": pal.bad,
            "textClasses": {"title": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": pal.ink},
                            "header": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": pal.ink},
                            "label": {"fontFace": "Segoe UI", "fontSize": 10, "color": pal.muted},
                            "callout": {"fontFace": "Segoe UI Bold", "fontSize": 22, "color": pal.ink}},
            "visualStyles": styles}


# ---------------------------------------------------------------- writing a report
def page_json(pg: Page, extra: dict | None = None) -> dict:
    page = {"$schema": S_PAGE, "name": pg.id, "displayName": pg.display, "displayOption": "FitToPage",
            "height": H, "width": W,
            "objects": {"background": [{"properties": {"color": colour(pg.pal.canvas), "transparency": literal(0)}}],
                        "outspace": [{"properties": {"color": colour(pg.pal.canvas), "transparency": literal(0)}}]}}
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


def write_report(report: Path, theme_path: Path, theme_json: dict, pages: list[tuple[Page, dict | None]],
                 pbip_name: str) -> None:
    """Write a complete PBIR report folder (+ .pbip) that uses the SHARED model. Rebuilds pages from scratch."""
    definition = report / "definition"
    resources = report / "StaticResources" / "RegisteredResources"
    theme_path.write_text(json.dumps(theme_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (report.parent / pbip_name).write_text(json.dumps(
        {"version": "1.0", "artifacts": [{"report": {"path": report.name}}],
         "settings": {"enableAutoRecovery": True}}, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_json(report / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": SHARED_MODEL}}})
    write_json(definition / "version.json",
               {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
                "version": "2.0.0"})
    if resources.exists():
        shutil.rmtree(resources)
    resources.mkdir(parents=True)
    shutil.copyfile(theme_path, resources / theme_path.name)
    assets: dict[str, str] = {}
    for pg, _ in pages:
        assets.update(pg.assets)
    for fname, svg in sorted(assets.items()):
        (resources / fname).write_text(svg, encoding="utf-8", newline="\n")
    r01 = json.loads((REPORT01 / "definition" / "report.json").read_text(encoding="utf-8"))
    base = r01["themeCollection"]["baseTheme"]
    write_json(definition / "report.json", {
        "$schema": r01["$schema"],
        "themeCollection": {"baseTheme": base,
                            "customTheme": {"name": theme_path.name, "reportVersionAtImport": base["reportVersionAtImport"],
                                            "type": "RegisteredResources"}},
        "objects": r01["objects"],
        "resourcePackages": [p for p in r01["resourcePackages"] if p["name"] == "SharedResources"]
        + [{"name": "RegisteredResources", "type": "RegisteredResources",
            "items": [{"name": theme_path.name, "path": theme_path.name, "type": "CustomTheme"}]
            + [{"name": f, "path": f, "type": "Image"} for f in sorted(assets)]}],
        "settings": r01["settings"]})
    shutil.copytree(REPORT01 / "StaticResources" / "SharedResources", report / "StaticResources" / "SharedResources",
                    dirs_exist_ok=True)
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
