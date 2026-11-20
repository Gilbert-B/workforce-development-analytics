"""Page building blocks for the two LIGHT reports of the suite (Report 02 and Report 03).

DESIGN: the same "designed canvas" technique as Report 01, in a light style.
Everything static (header band, logo, titles, tile and panel frames with soft
shadows, icons, labels, footers) is drawn ONCE into a page background image
(SVG -> PNG). Power BI visuals sit on top and show only live data: numbers,
charts, tables, slicers, tabs. Static text can therefore never overlap or clip
a value, and every number card gets generous room.

    y    0-232  header band: logo, eyebrow, title, snapshot pill, tabs, slicers
    y  212-340  KPI tiles (float over the band's lower edge)
    y  356+     panels
SVGs are written to powerbi/design/, PNGs to the report's RegisteredResources
(rendered with Playwright; see render_backgrounds()).
"""

from __future__ import annotations

import html
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pbir_lib import (FONT, S_PAGE, S_PAGES, button, category_filter, colour, container, field, literal, page_link,
                      props, proj, textbox, value_selector, write_json)

PBI = Path(__file__).resolve().parents[1]
DESIGN = PBI / "design"
SHARED_MODEL = "../workforcedevelopmentanalytics.SemanticModel"    # Report 01's model: shared, not copied
REPORT01 = PBI / "workforcedevelopmentanalytics.Report"

W, H, X0, XR = 1920, 1080, 48, 1872
SPAN = XR - X0
GAP = 16
HERO_H = 232
KPI_Y, KPI_H = 212, 136
BODY_Y = 364
BOTTOM = H - 34                 # panels end here; the footer line sits below

ICONS = {  # 24x24 stroke icons (shared look with Report 01)
    "users": '<path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"/><path d="M2 21c.8-4 3.6-6 7-6s6.2 2 7 6"/><path d="M16 3.5a4 4 0 0 1 0 7.5M22 21c-.5-3-2.3-5-5-5.6"/>',
    "cap": '<path d="m2 9 10-5 10 5-10 5z"/><path d="M6 11v5c3 2.5 9 2.5 12 0v-5"/>',
    "star": '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z"/>',
    "check": '<rect x="3" y="4" width="18" height="17" rx="3"/><path d="m8 13 3 3 5-6"/>',
    "doc": '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
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
    hero_text: str = "#C9DBF2"         # eyebrow / labels on the band
    good: str = "#1F9E8F"
    warn: str = "#C98A1B"
    bad: str = "#D1553F"
    neutral: str = "#8A96A8"


def text(size, colour_, weight="Segoe UI") -> dict:
    return {"fontFamily": weight, "fontSize": f"{size}pt", "color": colour_}


# ---------------------------------------------------------------- SVG helpers (background)
def esc(t: str) -> str:
    return html.escape(t, quote=False)


def wrap(t: str, max_px: float, size: float) -> list[str]:
    """Split text into lines that fit max_px (approximate Segoe UI width: 0.55 x font size per char)."""
    per_line = max(8, int(max_px / (size * 0.55)))
    words, lines, cur = t.split(), [], ""
    for w_ in words:
        if len(cur) + len(w_) + 1 > per_line and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = f"{cur} {w_}".strip()
    if cur:
        lines.append(cur)
    return lines


def svg_text(x, y, t, size=13, fill="#5B6B80", weight=400, spacing=0.0, opacity=1.0, anchor="start") -> str:
    return (f'<text x="{x}" y="{y}" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" fill-opacity="{opacity}" letter-spacing="{spacing}" '
            f'text-anchor="{anchor}">{esc(t)}</text>')


def svg_icon(name: str, x, y, size, stroke, width=2.0) -> str:
    s = size / 24
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{stroke}" stroke-width="{width}" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>')


def svg_card(x, y, w, h, fill="#FFFFFF", r=16) -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" filter="url(#shadow)"/>'


class Page:
    """One page: Power BI visuals (live data) + SVG decoration (background image)."""

    def __init__(self, pal: Palette, page_id: str, display: str):
        self.pal, self.id, self.display = pal, page_id, display
        self.visuals: list[dict] = []
        self.svg: list[str] = []
        self.z = 10
        self.kpis: list[str] = []          # card visuals that chart clicks must not filter
        self.charts: list[str] = []
        self.background = ""                # PNG file name, set by write_report

    def add(self, name: str, x, y, w, h, visual: dict, filters: list[dict] | None = None, hidden=False) -> dict:
        v = container(name, x, y, w, h, self.z, visual, hidden=hidden)
        if filters:
            v["filterConfig"] = {"filters": filters}
        self.visuals.append(v)
        self.z += 1
        return v

    # ------------------------------------------------------------ header band
    def header(self, eyebrow: str, title: str, tabs: list[tuple[str, str]], active: str | None,
               snapshot: tuple[str, str], back=False, logo="trend") -> None:
        p = self.pal
        self.svg += [
            f'<rect x="0" y="0" width="{W}" height="{HERO_H}" fill="url(#hero)"/>',
            f'<rect x="0" y="0" width="{W}" height="{HERO_H}" fill="url(#dots)"/>',
            *[f'<circle cx="1760" cy="-30" r="{r}" fill="none" stroke="#FFFFFF" stroke-opacity="{o}" stroke-width="1.5"/>'
              for r, o in ((150, .10), (240, .07), (330, .05), (420, .035))],
            f'<rect x="{X0}" y="34" width="52" height="52" rx="14" fill="#FFFFFF" fill-opacity=".14" '
            f'stroke="#FFFFFF" stroke-opacity=".25"/>',
            svg_icon(logo, X0 + 13, 47, 26, "#FFFFFF", 2.2),
            svg_text(X0 + 72, 52, eyebrow, 12.5, p.hero_text, 600, 1.4),
            svg_text(X0 + 72, 90, title, 32, "#FFFFFF", 700),
            f'<rect x="1452" y="34" width="420" height="40" rx="20" fill="#FFFFFF" fill-opacity=".10" '
            f'stroke="#FFFFFF" stroke-opacity=".22"/>',
        ]
        self.add("hdrSnapshot", 1462, 34, 400, 40, card_visual(*snapshot, size=10, colour_="#FFFFFF", font="regular"))
        x = X0
        for page_id, label in tabs:
            is_active = page_id == active
            w = 34 + 9 * len(label)
            self.add(f"tab_{page_id}", x, 160, w, 40, button(
                label, link=None if is_active else page_link(page_id), fg=p.accent if is_active else "#E3ECF8",
                fill="#FFFFFF" if is_active else None, fill_alpha=100 if is_active else 0,
                hover_fill="#FFFFFF", hover_alpha=85, size=10,
                tooltip=None if is_active else f"Go to {label}"))
            x += w + 8
        if back:
            self.add("btnBack", XR - 132, 160, 132, 40, button(
                "\u2190  Back", link={"type": "Back"}, fg="#FFFFFF", fill="#FFFFFF", fill_alpha=16,
                hover_fill="#FFFFFF", hover_alpha=75, size=10, tooltip="Back to the page you came from"))

    def slicer(self, name: str, x: int, w: int, table: str, column: str, label: str, sync: str) -> None:
        p = self.pal
        self.svg.append(svg_text(x + 2, 108, label.upper(), 10.5, p.hero_text, 600, 1.2))
        self.add(name, x, 116, w, 36, {
            "visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [proj("Column", table, column, label)]}}},
            "objects": {"data": props(mode="Dropdown"),
                        "header": props(show=False),
                        "selection": props(selectAllCheckboxEnabled=True, singleSelect=False),
                        "items": props(fontColor=colour(p.ink), background=colour(p.surface), textSize=10)},
            "visualContainerObjects": {"background": props(show=True, color=colour("#FFFFFF"), transparency=0)},
            "syncGroup": {"groupName": sync, "fieldChanges": True, "filterChanges": True}})

    # ------------------------------------------------------------ tiles and panels
    def kpi(self, prefix: str, x, y, w, h, label: str, table: str, measure: str, context: str, accent: str,
            filters: list[dict] | None = None, icon: str = "target") -> None:
        p = self.pal
        self.svg += [svg_card(x, y, w, h),
                     f'<rect x="{x}" y="{y}" width="{w}" height="4" rx="2" fill="{accent}"/>',
                     f'<circle cx="{x + 38}" cy="{y + 38}" r="20" fill="{accent}" fill-opacity=".12"/>',
                     svg_icon(icon, x + 27, y + 27, 22, accent, 2)]
        lines = wrap(label.upper(), w - 82, 11)[:2]
        top = y + 36 if len(lines) == 1 else y + 29
        self.svg += [svg_text(x + 68, top + i * 15, ln, 11, p.muted, 600, 0.8) for i, ln in enumerate(lines)]
        ctx = wrap(context, w - 36, 11)
        if len(ctx) > 1:
            raise ValueError(f"KPI context too long for one line ({prefix}): {context!r}")
        self.svg.append(svg_text(x + 20, y + h - 16, context, 11, p.neutral))
        # the ONLY visual in the tile: the number, in its own band between the label and the context line,
        # tall enough that Power BI's card padding never clips it
        self.add(prefix, x + 12, y + 52, w - 24, h - 52 - 34, card_visual(table, measure, size=22, colour_=p.ink),
                 filters)
        self.kpis.append(prefix)

    def kpi_row(self, tiles: list[tuple], y=KPI_Y, h=KPI_H) -> None:
        """tiles: (prefix, label, table, measure, context, accent, filters|None, icon)."""
        n = len(tiles)
        w = (SPAN - GAP * (n - 1)) // n
        for i, t in enumerate(tiles):
            self.kpi(t[0], X0 + i * (w + GAP), y, w, h, *t[1:6],
                     filters=t[6] if len(t) > 6 else None, icon=t[7] if len(t) > 7 else "target")

    def panel(self, name: str, x, y, w, h, title: str, subtitle: str = "") -> tuple[int, int, int, int]:
        """White panel (drawn in the background) with a title; returns the chart rectangle."""
        p = self.pal
        self.svg += [svg_card(x, y, w, h),
                     f'<rect x="{x + 20}" y="{y + 22}" width="4" height="20" rx="2" fill="{p.accent}"/>',
                     svg_text(x + 34, y + 38, title, 16, p.ink, 600)]
        if subtitle:
            sub = wrap(subtitle, w - 56, 12.5)[0]
            self.svg.append(svg_text(x + 34, y + 60, sub, 12.5, p.muted))
        top = 74 if subtitle else 54
        return x + 14, y + top, w - 28, h - top - 12

    def surface(self, x, y, w, h) -> None:
        self.svg.append(svg_card(x, y, w, h))

    def bullets(self, x, y, w, items: list[str], size=15.0, gap=12, colour_: str | None = None,
                bullet: str | None = None) -> int:
        """Wrapped bullet list drawn in the background; returns the y below the last line."""
        line_h = size * 1.45
        for item in items:
            lines = wrap(item, w - 22, size)
            self.svg.append(f'<circle cx="{x + 5}" cy="{y - size * 0.33:.1f}" r="3" fill="{bullet or self.pal.accent}"/>')
            for ln in lines:
                self.svg.append(svg_text(x + 20, round(y, 1), ln, size, colour_ or self.pal.ink))
                y += line_h
            y += gap
        return int(y)

    def chart(self, name: str, rect, visual: dict, filters: list[dict] | None = None) -> None:
        self.add(name, *rect, visual, filters)
        self.charts.append(name)

    def note(self, name: str, x, y, w, h, runs: list[list[tuple[str, dict]]]) -> None:
        self.add(name, x, y, w, h, textbox(runs))

    def interactions(self) -> list[dict]:
        """Chart clicks cross-filter other charts, but never the headline KPI numbers."""
        return [{"source": c, "target": k, "type": "NoFilter"} for c in self.charts for k in self.kpis]

    def background_svg(self) -> str:
        p = self.pal
        return "".join([
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
            "<defs>",
            f'<linearGradient id="hero" x1="0" y1="0" x2="1" y2=".35"><stop offset="0" stop-color="{p.hero_from}"/>'
            f'<stop offset="1" stop-color="{p.hero_to}"/></linearGradient>',
            '<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
            '<circle cx="2" cy="2" r="1.1" fill="#FFFFFF" fill-opacity=".07"/></pattern>',
            f'<radialGradient id="glow" cx="92%" cy="100%" r="55%"><stop offset="0" stop-color="{p.accent}" '
            f'stop-opacity=".07"/><stop offset="1" stop-color="{p.accent}" stop-opacity="0"/></radialGradient>',
            '<filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">'
            f'<feDropShadow dx="0" dy="4" stdDeviation="9" flood-color="{p.ink}" flood-opacity=".08"/></filter>',
            "</defs>",
            f'<rect width="{W}" height="{H}" fill="{p.canvas}"/>',
            f'<rect width="{W}" height="{H}" fill="url(#glow)"/>',
            *self.svg, "</svg>"])


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
    pg.svg.append(svg_text(X0 + 4, H - 12, message, 11.5, pg.pal.neutral))


# ---------------------------------------------------------------- writing a report
def page_json(pg: Page, extra: dict | None = None) -> dict:
    # NB: the "image" property holds an object that is ALSO called "image" (how Desktop writes it)
    img = {"image": {"image": {
        "name": literal(pg.background),
        "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1,
                                                 "ItemName": pg.background}}},
        "scaling": literal("Fit")}}}
    page = {"$schema": S_PAGE, "name": pg.id, "displayName": pg.display, "displayOption": "FitToPage",
            "height": H, "width": W,
            "objects": {"background": [{"properties": {**img, "transparency": literal(0)}}],
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


def render_backgrounds(jobs: list[tuple[Path, Path]]) -> None:
    """SVG -> PNG with Playwright's Chromium (Node). The PNGs are committed, so only the builder needs this."""
    script = Path(__file__).with_name("render_svg.js")
    spec = json.dumps([{"svg": str(s), "png": str(p)} for s, p in jobs])
    subprocess.run(["node", str(script), spec], check=True)


def write_report(report: Path, theme: Path, pages: list[tuple[Page, dict | None]], pbip_name: str,
                 design_prefix: str) -> None:
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
    if resources.exists():
        shutil.rmtree(resources)
    resources.mkdir(parents=True)
    shutil.copyfile(theme, resources / theme.name)
    DESIGN.mkdir(parents=True, exist_ok=True)
    jobs = []
    for pg, _ in pages:
        slug = pg.display.lower().replace(" ", "-")
        pg.background = f"{design_prefix}-{slug}.png"
        svg_path = DESIGN / f"{design_prefix}-{slug}.svg"
        svg_path.write_text(pg.background_svg(), encoding="utf-8", newline="\n")
        jobs.append((svg_path, resources / pg.background))
    render_backgrounds(jobs)
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
            "items": [{"name": theme.name, "path": theme.name, "type": "CustomTheme"}]
            + [{"name": pg.background, "path": pg.background, "type": "Image"} for pg, _ in pages]}],
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
        print(f"  {pg.display:<26} {len(pg.visuals):>3} visuals  background {pg.background}")
