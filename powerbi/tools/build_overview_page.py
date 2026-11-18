"""Build the 'showcase' Workforce Intelligence report (UX-02) as PBIR files.

WHAT THIS IS
    A generator for the dark, bookmark-driven redesign. From ONE set of
    layout constants it writes:
      - two background designs as SVG  (powerbi/design/*.svg)
      - the Overview and About pages, their visuals, and the bookmarks
      - the dark theme registration
    The SVG backgrounds are rendered to PNG separately (see
    docs/powerbi_ux.md) because Power BI page backgrounds use raster images.

    After the report is opened and saved in Power BI Desktop, DESKTOP IS THE
    SOURCE OF TRUTH. Re-running this script REBUILDS both pages and all
    bookmarks from scratch, discarding changes made in Desktop.

THE DESIGN TECHNIQUE ("designed canvas")
    Static decoration - panels, card frames, icons, navigation rail, static
    labels - is drawn once in a background image. Visuals sit on top with
    transparent backgrounds and only show DATA. Interactive behaviour comes
    from buttons and bookmarks:
      - button -> bookmark  : toggles which chart/title/chip is visible
      - button -> page      : the navigation rail
      - drawer              : hidden visuals shown by a bookmark, closed by another

USAGE (repository root, Power BI Desktop CLOSED)
    python powerbi/tools/build_overview_page.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PBI = REPO / "powerbi"
REPORT = PBI / "workforcedevelopmentanalytics.Report"
DEFINITION = REPORT / "definition"
RESOURCES = REPORT / "StaticResources" / "RegisteredResources"
DESIGN = PBI / "design"
THEME = PBI / "themes" / "WorkforceIntelligenceDark.json"

OVERVIEW = "0f2c0daa0493675582ab"          # existing page id (kept)
ABOUT = "b7e1c0a5d3f24e6a9c11"             # new page id
BG_OVERVIEW = "overview-background.png"
BG_ABOUT = "about-background.png"

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
S_VISUAL = f"{SCHEMA}/visualContainer/2.13.0/schema.json"
S_PAGE = f"{SCHEMA}/page/2.1.0/schema.json"
S_PAGES = f"{SCHEMA}/pagesMetadata/1.1.0/schema.json"
S_BOOKMARK = f"{SCHEMA}/bookmark/2.1.0/schema.json"
S_BOOKMARKS = f"{SCHEMA}/bookmarksMetadata/1.0.0/schema.json"

# ---------------------------------------------------------------- palette
NAVY, INK, CREAM, MUTED, DIM = "#071629", "#050C17", "#F6F0E4", "#9BA8B9", "#6F7D90"
GOLD, TEAL, CORAL, SKY, SLATE = "#E3A640", "#3FC1B0", "#E0705A", "#7AA7D9", "#5B6B80"

# ---------------------------------------------------------------- layout (1920 x 1080)
W, H = 1920, 1080
RAIL = 96                       # navigation rail width
HEADER_BUTTONS = {"btnDefinitions": (1500, 124), "btnResetView": (1636, 116), "btnClearFilters": (1764, 116)}
X0 = 136                        # content left edge
XR = 1880                       # content right edge
KPI_Y, KPI_W, KPI_H, KPI_GAP = 196, 280, 170, 12     # 6 x 280 + 5 x 12 = 1740 = XR - X0
PANEL_Y, PANEL_H = 384, 656
LEFT = (X0, PANEL_Y, 964, PANEL_H)                 # x, y, w, h
RIGHT = (1116, PANEL_Y, 764, PANEL_H)
NAV = [  # key, label, centre y, page it opens (None = coming later)
    ("overview", "Overview", 142, OVERVIEW),
    ("cohorts", "Cohorts", 216, None),
    ("skills", "Skills", 290, None),
    ("attendance", "Attendance", 364, None),
    ("trainee", "Trainee 360", 438, None),
    ("about", "About", 1016, ABOUT),
]

# Model names exactly as in Power BI
ENROL, ATTEND, COMPET, COHORT, WEEK, SNAP = (
    "rpt dim_enrolment", "rpt fact_attendance", "rpt dim_competency",
    "rpt dim_cohort", "rpt dim_programme_week", "rpt dim_snapshot")

# Six KPI cards: id, table, measure, LABEL (background), context line (background), icon, accent
KPIS = [
    ("kpiStartingHeadcount", ENROL, "Starting Headcount", "STARTING HEADCOUNT", "Enrolments with a start event", "users", TEAL),
    ("kpiActiveTrainees", ENROL, "Active Trainees (Snapshot)", "ACTIVE TRAINEES", "End of day at the snapshot", "play", GOLD),
    ("kpiCompletedTrainees", ENROL, "Completed Trainees (Snapshot)", "COMPLETED", "Finished the 8-week programme", "cap", TEAL),
    ("kpiAvgCompetency", COMPET, "Average Competency Score", "AVG COMPETENCY", "Score 0-100 · all assessed weeks", "star", GOLD),
    ("kpiRecordedAttendance", ATTEND, "Recorded Attendance Rate", "RECORDED ATTENDANCE", "Present ÷ recorded sessions", "check", TEAL),
    ("kpiRecordingRate", ATTEND, "Attendance Recording Rate", "RECORDING RATE", "Recorded ÷ eligible sessions", "doc", GOLD),
]

# Cards whose context line is a measure (responds to the cohort filter) ...
CONTEXT_MEASURE = {"kpiStartingHeadcount": (ENROL, "Starting Headcount Context"),
                   "kpiCompletedTrainees": (ENROL, "Completion Context")}
# ... and cards that also show an SVG progress bar drawn by a measure
BAR_MEASURE = {"kpiRecordedAttendance": (ATTEND, "Recorded Attendance Bar SVG"),
               "kpiRecordingRate": (ATTEND, "Attendance Recording Bar SVG")}

ICONS = {  # 24x24 stroke icons (drawn in the background SVG)
    "overview": '<rect x="3" y="3" width="7" height="9" rx="2"/><rect x="14" y="3" width="7" height="5" rx="2"/><rect x="14" y="12" width="7" height="9" rx="2"/><rect x="3" y="16" width="7" height="5" rx="2"/>',
    "cohorts": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5"/><circle cx="17.5" cy="9" r="2.5"/><path d="M17 14.5c2.4.2 4 1.8 4.6 4.5"/>',
    "skills": '<path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/>',
    "attendance": '<rect x="3" y="4" width="18" height="17" rx="3"/><path d="M3 9h18M8 2v4M16 2v4M8 14l2.5 2.5L16 12"/>',
    "trainee": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4.4 4.2-6.5 8-6.5s7 2.1 8 6.5"/>',
    "about": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    "users": '<path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"/><path d="M2 21c.8-4 3.6-6 7-6s6.2 2 7 6"/><path d="M16 3.5a4 4 0 0 1 0 7.5M22 21c-.5-3-2.3-5-5-5.6"/>',
    "play": '<circle cx="12" cy="12" r="9"/><path d="m10 8.5 6 3.5-6 3.5z"/>',
    "cap": '<path d="m2 9 10-5 10 5-10 5z"/><path d="M6 11v5c3 2.5 9 2.5 12 0v-5"/>',
    "star": '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z"/>',
    "check": '<rect x="3" y="4" width="18" height="17" rx="3"/><path d="m8 13 3 3 5-6"/>',
    "doc": '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    "reset": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
}


# =========================================================================
# 1. BACKGROUND DESIGNS (SVG)
# =========================================================================
def svg_icon(name: str, x: float, y: float, size: float, colour: str, width: float = 2) -> str:
    s = size / 24
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{colour}" '
            f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>')


def svg_frame(x, y, w, h, r=16) -> str:
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="#FFFFFF" fill-opacity=".035" '
            f'stroke="#FFFFFF" stroke-opacity=".09"/>')


def svg_text(x, y, text, size=13, colour=MUTED, weight=400, anchor="start", spacing=0) -> str:
    return (f'<text x="{x}" y="{y}" font-family="Segoe UI, Inter, sans-serif" font-size="{size}" '
            f'font-weight="{weight}" fill="{colour}" text-anchor="{anchor}" letter-spacing="{spacing}">{text}</text>')


def svg_base(active: str) -> list[str]:
    """Canvas, grid texture and navigation rail shared by both pages."""
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           '<defs>',
           f'<linearGradient id="base" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#081A30"/><stop offset=".7" stop-color="{INK}"/></linearGradient>',
           '<radialGradient id="glowTR" cx="88%" cy="-8%" r="55%"><stop offset="0" stop-color="#0E4A5C" stop-opacity=".8"/><stop offset="1" stop-color="#0E4A5C" stop-opacity="0"/></radialGradient>',
           f'<radialGradient id="glowBL" cx="8%" cy="105%" r="45%"><stop offset="0" stop-color="{GOLD}" stop-opacity=".10"/><stop offset="1" stop-color="{GOLD}" stop-opacity="0"/></radialGradient>',
           '<pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse"><path d="M48 0H0V48" fill="none" stroke="#FFFFFF" stroke-opacity=".025"/></pattern>',
           f'<linearGradient id="logo" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#F3C56B"/><stop offset=".55" stop-color="{GOLD}"/><stop offset="1" stop-color="#B97A22"/></linearGradient>',
           '</defs>',
           f'<rect width="{W}" height="{H}" fill="url(#base)"/>',
           f'<rect width="{W}" height="{H}" fill="url(#glowTR)"/>',
           f'<rect width="{W}" height="{H}" fill="url(#glowBL)"/>',
           f'<rect width="{W}" height="{H}" fill="url(#grid)"/>',
           # navigation rail
           f'<rect width="{RAIL}" height="{H}" fill="#030912" fill-opacity=".65"/>',
           f'<line x1="{RAIL}" y1="0" x2="{RAIL}" y2="{H}" stroke="#FFFFFF" stroke-opacity=".09"/>',
           '<rect x="22" y="28" width="52" height="52" rx="14" fill="url(#logo)"/>']
    for key, label, cy, page in NAV:
        on = key == active
        if on:
            out.append(f'<rect x="18" y="{cy-30}" width="60" height="60" rx="14" fill="{GOLD}" fill-opacity=".13"/>')
            out.append(f'<rect x="0" y="{cy-16}" width="4" height="32" rx="2" fill="{GOLD}"/>')
    return out


def overview_svg() -> str:
    out = svg_base("overview")
    # header: snapshot pill and button frames (text and icons are Power BI visuals)
    out.append(f'<rect x="1152" y="40" width="336" height="40" rx="20" fill="#FFFFFF" fill-opacity=".04" stroke="#FFFFFF" stroke-opacity=".09"/>')
    out.append(f'<circle cx="1174" cy="60" r="4" fill="{TEAL}"/><circle cx="1174" cy="60" r="8" fill="{TEAL}" fill-opacity=".25"/>')
    for x, w in HEADER_BUTTONS.values():
        out.append(f'<rect x="{x}" y="40" width="{w}" height="40" rx="12" fill="#FFFFFF" fill-opacity=".03" stroke="#FFFFFF" stroke-opacity=".09"/>')
    # cohort selector track + note
    out.append(f'<rect x="{X0}" y="120" width="540" height="52" rx="26" fill="#000000" fill-opacity=".25" stroke="#FFFFFF" stroke-opacity=".09"/>')
    # KPI frames + coloured icon tile (icon, label and context line are visuals)
    for i, (_, _, _, label, context, icon, accent) in enumerate(KPIS):
        x = X0 + i * (KPI_W + KPI_GAP)
        out.append(svg_frame(x, KPI_Y, KPI_W, KPI_H))
        out.append(f'<rect x="{x+24}" y="{KPI_Y+22}" width="40" height="40" rx="12" fill="{accent}" fill-opacity=".14"/>')
    # panels + chip tracks
    for (x, y, w, h), chip_w in ((LEFT, 230), (RIGHT, 262)):
        out.append(svg_frame(x, y, w, h))
        out.append(f'<rect x="{x+w-chip_w-28}" y="{y+24}" width="{chip_w}" height="44" rx="12" fill="#000000" fill-opacity=".25" stroke="#FFFFFF" stroke-opacity=".09"/>')
    out.append('</svg>')
    return "\n".join(out)


def about_svg() -> str:
    out = svg_base("about")
    out.append(svg_frame(X0, 130, 860, 910))
    out.append(svg_frame(1020, 130, 860, 440))
    out.append(svg_frame(1020, 590, 860, 450))
    out.append('</svg>')
    return "\n".join(out)


# =========================================================================
# 2. PBIR JSON HELPERS
# =========================================================================
def literal(value) -> dict:
    """Formatting values are expressions: 'text' in quotes, numbers with D, booleans as-is."""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (int, float)):
        text = f"{value}D"
    else:
        text = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": text}}}


def colour(hex_code: str) -> dict:
    return {"solid": {"color": literal(hex_code)}}


def props(selector: dict | None = None, **kwargs) -> list[dict]:
    entry = {"properties": {k: (v if isinstance(v, dict) else literal(v)) for k, v in kwargs.items()}}
    if selector:
        entry["selector"] = selector
    return [entry]


def field(kind: str, table: str, name: str) -> dict:
    return {kind: {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def proj(kind: str, table: str, name: str, label: str | None = None) -> dict:
    p = {"field": field(kind, table, name), "queryRef": f"{table}.{name}", "nativeQueryRef": name}
    if label:
        p["displayName"] = label
    return p


def value_selector(table: str, column: str, value: str) -> dict:
    """Selector for one category value, e.g. attendance_status = 'Present'."""
    return {"data": [{"scopeId": {"Comparison": {
        "ComparisonKind": 0, "Left": field("Column", table, column), "Right": {"Literal": {"Value": f"'{value}'"}}}}}]}


def container(name, x, y, w, h, z, visual, hidden=False) -> dict:
    v = {"$schema": S_VISUAL, "name": name,
         "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z},
         "visual": visual}
    if hidden:
        v["isHidden"] = True
    return v


def textbox(runs_by_line: list[list[tuple[str, dict]]], align: str | None = None) -> dict:
    def para(runs):
        p = {"textRuns": [{"value": t, "textStyle": s} for t, s in runs]}
        if align:
            p["horizontalTextAlignment"] = align
        return p
    return {"visualType": "textbox", "objects": {"general": [{"properties": {
        "paragraphs": [para(r) for r in runs_by_line]}}]}}


# ---- icons: one small SVG file per icon + colour, shown in an image visual --
ICON_FILES: set[str] = set()


def icon_file(name: str, hex_code: str) -> str:
    """Register an icon SVG (written in main()) and return its resource name."""
    fname = f"icon-{name}-{hex_code.lstrip('#').lower()}.svg"
    ICON_FILES.add(fname)
    return fname


def icon_svg(fname: str) -> str:
    _, name, hex_code = fname.removesuffix(".svg").split("-", 2)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" '
            f'stroke="#{hex_code}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


def image_from_measure(table: str, measure: str) -> dict:
    """Image visual whose picture is the SVG data-URL returned by a measure."""
    return {"visualType": "image", "objects": {
        "general": props(imageUrl={"expr": field("Measure", table, measure)}),
        "imageScaling": props(imageScalingType="Fit")}}


def image(fname: str) -> dict:
    return {"visualType": "image", "objects": {
        "general": props(imageUrl={"expr": {"ResourcePackageItem": {
            "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": fname}}}),
        "imageScaling": props(imageScalingType="Fit")}}


# Power BI expects a full font STACK in visual formatting (learned from Desktop)
FONT = {"regular": "'Segoe UI', wf_segoe-ui_normal, helvetica, arial, sans-serif",
        "semibold": "'Segoe UI Semibold', wf_segoe-ui_semibold, helvetica, arial, sans-serif",
        "bold": "'Segoe UI Bold', wf_segoe-ui_bold, helvetica, arial, sans-serif"}


def style(size=13, colour_=CREAM, weight="Segoe UI") -> dict:
    return {"fontFamily": weight, "fontSize": f"{size}pt", "color": colour_}


def button(text: str, *, link: dict | None, fg=MUTED, fill: str | None = None, fill_alpha=0,
           hover_fill="#FFFFFF", hover_alpha=92, size=10, tooltip: str | None = None) -> dict:
    """Action button. fill_alpha / hover_alpha are TRANSPARENCY percentages (100 = invisible)."""
    objects = {
        # two entries: per-state text settings, plus the master "show text" switch
        "text": props({"id": "default"}, show=bool(text), text=text, fontColor=colour(fg),
                      fontSize=size, fontFamily=FONT["semibold"]) + props(show=bool(text)),
        "fill": props({"id": "default"}, show=True, fillColor=colour(fill or "#000000"),
                      transparency=100 - fill_alpha if fill else 100),
        "outline": props({"id": "default"}, show=False),
        "icon": props({"id": "default"}, show=False),
    }
    objects["fill"] += props({"id": "hover"}, show=True, fillColor=colour(hover_fill), transparency=hover_alpha)
    vco = {}
    if link:
        vco["visualLink"] = props(show=True, **link)
    if tooltip:
        vco.setdefault("visualLink", props(show=False))
        vco["visualLink"][0]["properties"]["tooltip"] = literal(tooltip)
    return {"visualType": "actionButton", "objects": objects, "visualContainerObjects": vco,
            "drillFilterOtherVisuals": True}


def shape(fill: str, transparency: int, outline: str | None = None, outline_transparency: int = 0) -> dict:
    """Rectangle shape. Like buttons, shapes keep formatting PER STATE: the
    values live under selector {"id": "default"}, plus a master 'show' entry."""
    d = {"id": "default"}
    objects = {
        "shape": props(tileShape="rectangle"),
        "fill": props(d, show=True, fillColor=colour(fill), transparency=transparency) + props(show=True),
        "outline": (props(d, show=True, lineColor=colour(outline), weight=1, transparency=outline_transparency)
                    + props(show=True)) if outline else (props(d, show=False) + props(show=False)),
    }
    return {"visualType": "shape", "objects": objects}


def bookmark_link(name: str) -> dict:
    return {"type": "Bookmark", "bookmark": name}


def page_link(page: str) -> dict:
    return {"type": "PageNavigation", "navigationSection": page}


# =========================================================================
# 3. OVERVIEW PAGE VISUALS
# =========================================================================
def nav_decor(current_key: str, z: int) -> list[dict]:
    """Logo text, nav icons and labels as editable visuals (frames are in the background)."""
    out = [container("logoText", 22, 36, 52, 36, z, textbox([[("WI", {"fontFamily": "Segoe UI Bold",
                                                                     "fontSize": "14pt", "color": "#1A1205"})]], "center"))]
    z += 1
    for key, label, cy, page in NAV:
        on = key == current_key
        tone = GOLD if on else ("#6F7D90" if page else "#3E4A5C")
        out.append(container(f"navIcon_{key}", 35, cy - 13, 26, 26, z, image(icon_file(key, tone)))); z += 1
        lines = [[(label, {"fontFamily": "Segoe UI Semibold" if on else "Segoe UI", "fontSize": "7pt", "color": tone})]]
        if page is None:
            lines.append([("planned", {"fontFamily": "Segoe UI", "fontSize": "6pt", "color": "#3E4A5C"})])
        out.append(container(f"navLabel_{key}", 4, cy + 22, 88, 34 if page is None else 24, z,
                             textbox(lines, "center"))); z += 1
    return out


def nav_buttons(current: str, z: int) -> list[dict]:
    out = []
    for key, label, cy, page in NAV:
        if page is None or page == current:
            continue      # 'coming later' items are decoration only; current page needs no link
        out.append(container(f"nav_{key}", 18, cy - 30, 60, 74, z,
                             button("", link=page_link(page), hover_alpha=90, tooltip=f"Go to {label}")))
        z += 1
    return out


def overview_visuals() -> list[dict]:
    v, z = [], 1000

    def add(name, x, y, w, h, visual, **kw):
        nonlocal z
        v.append(container(name, x, y, w, h, z, visual, **kw)); z += 1

    # Rail decoration + header text (all editable in Desktop)
    v.extend(nav_decor("overview", 100)); z = 1000
    add("headerEyebrow", X0 - 6, 34, 900, 30, textbox([[("PAYMENTS OPERATIONS · ONBOARDING INTELLIGENCE",
        {"fontFamily": "Segoe UI Semibold", "fontSize": "10pt", "color": GOLD})]]))
    add("headerTitle", X0 - 6, 58, 1000, 64, textbox([[("Workforce Intelligence Overview",
        {"fontFamily": "Segoe UI Bold", "fontSize": "30pt", "color": CREAM})]]))
    add("snapshotLabel", 1186, 42, 296, 36, {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [proj("Measure", SNAP, "Snapshot Label")]}}},
        "objects": {"labels": props(fontSize=10, color=colour("#C9D2DE"), fontFamily=FONT["regular"]),
                    "categoryLabels": props(show=False)}})
    for name, text, target, tip in (
            ("btnDefinitions", "ⓘ  Definitions", "bmDrawerOpen", "Show definitions"),
            ("btnResetView", "↺  Reset view", "bmResetView", "Restore the default panels (keeps your cohort selection)"),
            ("btnClearFilters", "✕  Clear filters", "bmClearFilters", "Clear the cohort selection (keeps the current panels)")):
        x, w = HEADER_BUTTONS[name]
        add(name, x, 40, w, 40, button(text, link=bookmark_link(target), fg="#C9D2DE", hover_alpha=90, size=10,
                                       tooltip=tip))
    add("cohortNote", 686, 132, 520, 30, textbox([[("Cohorts compared by programme week, not calendar date",
        {"fontFamily": "Segoe UI", "fontSize": "10pt", "color": "#7F8EA2"})]]))

    # Cohort selector: horizontal tiles inside the drawn track
    add("cohortSlicer", X0 + 8, 124, 524, 44, {
        "visualType": "slicer",
        "query": {"queryState": {"Values": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]}}},
        "objects": {
            "data": props(mode="Basic"),
            "general": props(orientation=1),
            "selection": props(selectAllCheckboxEnabled=False, singleSelect=False),
            "header": props(show=False),
            "items": props(fontColor=colour("#D8DEE6"), background=colour("#0B1D33"),
                           outlineStyle=0, textSize=11),
        }})

    # KPI cards: icon + label + number + context line (frame is in the background)
    for i, (vid, table, name, label, context, icon, accent) in enumerate(KPIS):
        x = X0 + i * (KPI_W + KPI_GAP)
        add(f"{vid}Icon", x + 33, KPI_Y + 31, 22, 22, image(icon_file(icon, accent)))
        add(f"{vid}Label", x + 70, KPI_Y + 28, KPI_W - 80, 30, textbox([[(label,
            {"fontFamily": "Segoe UI Semibold", "fontSize": "9pt", "color": MUTED})]]))
        if vid in CONTEXT_MEASURE:          # data-driven context line
            ctable, cmeasure = CONTEXT_MEASURE[vid]
            add(f"{vid}Context", x + 4, KPI_Y + 134, KPI_W - 8, 30, {
                "visualType": "card",
                "query": {"queryState": {"Values": {"projections": [proj("Measure", ctable, cmeasure)]}}},
                "objects": {"labels": props(fontFamily=FONT["regular"], fontSize=9, color=colour("#8FA0B4")),
                            "categoryLabels": props(show=False)}})
        else:                               # static description
            add(f"{vid}Context", x + 10, KPI_Y + 134, KPI_W - 20, 30, textbox([[(context,
                {"fontFamily": "Segoe UI", "fontSize": "10pt", "color": "#8FA0B4"})]], "center"))
        if vid in BAR_MEASURE:              # SVG progress bar drawn by a measure
            btable, bmeasure = BAR_MEASURE[vid]
            add(f"{vid}Bar", x + 20, KPI_Y + 122, KPI_W - 40, 10, image_from_measure(btable, bmeasure))
        add(vid, x + 14, KPI_Y + 62, KPI_W - 28, 58, {
            "visualType": "card",
            "query": {"queryState": {"Values": {"projections": [proj("Measure", table, name)]}}},
            "objects": {"labels": props(fontFamily=FONT["bold"], fontSize=32, color=colour(CREAM)),
                        "categoryLabels": props(show=False)}})

    # ---- left panel: Status  <->  Attendance quality
    lx, ly, lw, _ = LEFT
    chip_x = lx + lw - 230 - 28
    add("leftTitleStatus", lx + 22, ly + 18, 640, 64, textbox([
        [("Training pipeline by cohort", style(14, CREAM, "Segoe UI Semibold"))],
        [("Starters only · Active + Completed + Withdrawn = starting headcount", style(10, "#8FA0B4"))]]))
    add("leftTitleAttendance", lx + 22, ly + 18, 640, 64, textbox([
        [("Attendance quality by cohort", style(14, CREAM, "Segoe UI Semibold"))],
        [("Share of eligible sessions · Unrecorded is shown, never counted as absent", style(10, "#8FA0B4"))]]),
        hidden=True)
    for name, x, w, text, on, target, hidden in (
            ("chipStatusOn", chip_x + 4, 76, "Status", True, None, False),
            ("chipStatusOff", chip_x + 4, 76, "Status", False, "bmLeftStatus", True),
            ("chipAttendanceOn", chip_x + 82, 144, "Attendance quality", True, None, True),
            ("chipAttendanceOff", chip_x + 82, 144, "Attendance quality", False, "bmLeftAttendance", False)):
        add(name, x, ly + 28, w, 36, button(
            text, link=bookmark_link(target) if target else None,
            fg=TEAL if on else MUTED, fill=TEAL if on else None, fill_alpha=16 if on else 0,
            hover_alpha=100 if on else 92), hidden=hidden)

    status_series = [("Active Trainees (Snapshot)", "Active", GOLD),
                     ("Completed Trainees (Snapshot)", "Completed", TEAL),
                     ("Withdrawn Trainees (Snapshot)", "Withdrawn", CORAL)]
    add("chartStatus", lx + 20, ly + 86, lw - 40, PANEL_H - 106, {
        "visualType": "barChart",
        "query": {"queryState": {
            "Category": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]},
            "Y": {"projections": [proj("Measure", ENROL, m, label) for m, label, _ in status_series]}},
            "sortDefinition": {"sort": [{"field": field("Column", COHORT, "cohort_name"), "direction": "Ascending"}]}},
        "objects": {
            "dataPoint": [{"properties": {"fill": colour(c)}, "selector": {"metadata": f"{ENROL}.{m}"}}
                          for m, _, c in status_series],
            "labels": props(show=True, color=colour("#06111F"), fontSize=11),
            "categoryAxis": props(showAxisTitle=False, fontSize=11),
            "valueAxis": props(showAxisTitle=False)}})
    add("chartAttendance", lx + 20, ly + 86, lw - 40, PANEL_H - 106, {
        "visualType": "hundredPercentStackedBarChart",
        "query": {"queryState": {
            "Category": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]},
            "Series": {"projections": [proj("Column", ATTEND, "attendance_status", "Attendance")]},
            "Y": {"projections": [proj("Measure", ATTEND, "Eligible Attendance Sessions", "Share of eligible sessions")]},
            "Tooltips": {"projections": [proj("Measure", ATTEND, "Eligible Attendance Sessions", "Sessions (count)")]}},
            "sortDefinition": {"sort": [{"field": field("Column", COHORT, "cohort_name"), "direction": "Ascending"}]}},
        "objects": {
            "dataPoint": [{"properties": {"fill": colour(c)}, "selector": value_selector(ATTEND, "attendance_status", s)}
                          for s, c in (("Present", TEAL), ("Absent", CORAL), ("Unrecorded", SLATE))],
            "labels": props(show=True, color=colour("#06111F"), fontSize=11, labelPrecision=1),
            "categoryAxis": props(showAxisTitle=False, fontSize=11),
            "valueAxis": props(showAxisTitle=False)}}, hidden=True)

    # ---- right panel: By cohort (lines)  <->  By competency (heatmap)
    rx, ry, rw, _ = RIGHT
    chip_x = rx + rw - 262 - 28
    add("currentWeekMarker", rx + rw - 250, ry + 82, 226, 30, {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [proj("Measure", COHORT, "Current Training Week Label")]}}},
        "objects": {"labels": props(fontFamily=FONT["semibold"], fontSize=10, color=colour(GOLD)),
                    "categoryLabels": props(show=False)}})
    add("rightTitleCohort", rx + 22, ry + 18, 460, 64, textbox([
        [("Weekly competency progression", style(14, CREAM, "Segoe UI Semibold"))],
        [("Average core score (0-100) by programme week", style(10, "#8FA0B4"))]]))
    add("rightTitleCompetency", rx + 22, ry + 18, 460, 64, textbox([
        [("Competency × programme week", style(14, CREAM, "Segoe UI Semibold"))],
        [("Average score per competency; darker = lower, brighter = higher", style(10, "#8FA0B4"))]]), hidden=True)
    for name, x, w, text, on, target, hidden in (
            ("chipCohortOn", chip_x + 4, 100, "By cohort", True, None, False),
            ("chipCohortOff", chip_x + 4, 100, "By cohort", False, "bmRightCohort", True),
            ("chipCompetencyOn", chip_x + 106, 152, "By competency", True, None, True),
            ("chipCompetencyOff", chip_x + 106, 152, "By competency", False, "bmRightCompetency", False)):
        add(name, x, ry + 28, w, 36, button(
            text, link=bookmark_link(target) if target else None,
            fg=TEAL if on else MUTED, fill=TEAL if on else None, fill_alpha=16 if on else 0,
            hover_alpha=100 if on else 92), hidden=hidden)

    cohort_colours = (("2026 Cohort 1", SKY), ("2026 Cohort 2", TEAL), ("2026 Cohort 3", GOLD))
    add("chartTrend", rx + 20, ry + 86, rw - 40, PANEL_H - 106, {
        "visualType": "lineChart",
        "query": {"queryState": {
            "Category": {"projections": [proj("Column", WEEK, "programme_week", "Programme week")]},
            "Y": {"projections": [proj("Measure", COMPET, "Average Competency Score", "Average score")]},
            "Series": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]}},
            "sortDefinition": {"sort": [{"field": field("Column", WEEK, "programme_week"), "direction": "Ascending"}]}},
        "objects": {
            "dataPoint": [{"properties": {"fill": colour(c)}, "selector": value_selector(COHORT, "cohort_name", n)}
                          for n, c in cohort_colours],
            "categoryAxis": props(axisType="Categorical", showAxisTitle=True, titleText="Programme week"),
            "valueAxis": props(showAxisTitle=False),
            "lineStyles": props(strokeWidth=4, showMarker=True, markerSize=6),
            "labels": props(show=False)}})
    add("chartHeatmap", rx + 20, ry + 96, rw - 40, PANEL_H - 116, {
        "visualType": "pivotTable",
        "query": {"queryState": {
            "Rows": {"projections": [proj("Column", COMPET, "competency_name", "Competency")]},
            "Columns": {"projections": [proj("Column", WEEK, "week_label", "Week")]},
            "Values": {"projections": [proj("Measure", COMPET, "Average Competency Score", "Average score")]}},
            "sortDefinition": {"sort": [{"field": field("Column", COMPET, "competency_name"), "direction": "Ascending"}]}},
        "objects": {
            "values": [{"properties": {
                "backColor": {"solid": {"color": {"expr": {"FillRule": {
                    "Input": field("Measure", COMPET, "Average Competency Score"),
                    "FillRule": {"linearGradient2": {
                        "min": {"color": {"Literal": {"Value": "'#0B2A3E'"}}},
                        "max": {"color": {"Literal": {"Value": "'#3FC1B0'"}}},
                        "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'noColor'"}}}}}}}}}},
                "fontColorPrimary": colour(CREAM),
                "fontSize": literal(11)},
                # every data cell (wildcard) OF this measure (metadata = the projection's queryRef)
                "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}],
                             "metadata": f"{COMPET}.Average Competency Score"}}],
            "subTotals": props(rowSubtotals=False, columnSubtotals=False),
            # sizes chosen so the competency names + 8 week columns fit the 724px panel
            "columnHeaders": props(fontSize=10, fontColor=colour("#8FA0B4")),
            "rowHeaders": props(fontSize=11, fontColor=colour("#D8DEE6")),
            "grid": props(gridVertical=True, gridVerticalColor=colour(NAVY), gridVerticalWeight=3,
                          gridHorizontal=True, gridHorizontalColor=colour(NAVY), gridHorizontalWeight=3,
                          rowPadding=26)}}, hidden=True)

    # ---- definitions drawer (hidden until the Definitions button is clicked)
    add("drawerScrim", 0, 0, W, H, shape("#030810", 40), hidden=True)
    add("drawerPanel", W - 520, 0, 520, H, shape("#0B1D33", 0, outline=GOLD, outline_transparency=60), hidden=True)
    h3, p = style(11, GOLD, "Segoe UI Semibold"), style(11, "#C4CDD8")
    add("drawerText", W - 480, 36, 440, 760, textbox([
        [("DEFINITIONS", style(10, GOLD, "Segoe UI Semibold"))],
        [("How to read this page", style(20, CREAM, "Segoe UI Bold"))], [("", p)],
        [("Snapshot measures", h3)],
        [("Active and Completed are each trainee's status at the end of the snapshot day. A trainee completing on the last programme day counts as Completed that day.", p)], [("", p)],
        [("Recorded attendance rate", h3)],
        [("Present ÷ (Present + Absent). Unrecorded sessions are excluded and never counted as absent.", p)], [("", p)],
        [("Attendance recording rate", h3)],
        [("Recorded ÷ eligible sessions: how complete the attendance registers are.", p)], [("", p)],
        [("Competency progression", h3)],
        [("Cohorts are compared by programme week, not calendar date. Weeks not yet reached are blank, not zero.", p)], [("", p)],
        [("Data", h3)],
        [("Fully synthetic dataset generated for this portfolio project. No real people or organisations.", p)]]),
        hidden=True)
    add("drawerClose", W - 480, 820, 120, 44, button(
        "✕  Close", link=bookmark_link("bmDrawerClose"), fg=CREAM, fill="#FFFFFF", fill_alpha=6,
        hover_alpha=85, size=11), hidden=True)

    v.extend(nav_buttons(OVERVIEW, z))
    return v


# =========================================================================
# 4. ABOUT PAGE
# =========================================================================
def about_visuals() -> list[dict]:
    v, z = [], 1000
    h, p, b = style(18, CREAM, "Segoe UI Semibold"), style(13, "#C4CDD8"), style(13, CREAM, "Segoe UI Semibold")

    def add(name, x, y, w, h, visual, **kw):
        nonlocal z
        v.append(container(name, x, y, w, h, z, visual, **kw)); z += 1

    v.extend(nav_decor("about", 100)); z = 1000
    add("aboutEyebrow", X0 - 6, 34, 900, 30, textbox([[("ABOUT THIS REPORT",
        {"fontFamily": "Segoe UI Semibold", "fontSize": "10pt", "color": GOLD})]]))
    add("aboutTitle", X0 - 6, 58, 1100, 64, textbox([[("Workforce Development & Performance Intelligence",
        {"fontFamily": "Segoe UI Bold", "fontSize": "26pt", "color": CREAM})]]))
    add("aboutStory", X0 + 24, 154, 812, 860, textbox([
        [("The business question", h)],
        [("A fictional digital payments provider trains Payments Operations Associates in recurring cohorts. Leaders need to know whether each cohort is on track: who started, who is still training, how attendance and core competencies develop, and how cohorts compare at the same stage of the programme.", p)], [("", p)],
        [("What this page set shows", h)],
        [("Overview: ", b), ("headcount, training status, attendance quality and weekly competency progression, with cohort selection, bookmarked views and an on-page definitions drawer.", p)],
        [("Cohorts, Skills, Attendance, Trainee 360: ", b), ("planned for later builds.", p)], [("", p)],
        [("Rules that keep the numbers honest", h)],
        [("•  Status is calculated from dated lifecycle events, not overwritten flags.", p)],
        [("•  Unrecorded attendance is shown separately and never counted as absent.", p)],
        [("•  Cohorts are compared by programme week; weeks not yet reached are blank, not zero.", p)],
        [("•  The snapshot date comes from the data itself and updates on refresh.", p)], [("", p)],
        [("Original project vs Portfolio Edition", h)],
        [("Original (professional): ", b), ("a single-cohort learner-performance Power BI dashboard built on Azure SQL, Power Query and an Import model.", p)],
        [("Portfolio Edition (this report): ", b), ("a fictional banking/fintech scenario with multiple cohorts, a new Python and SQL pipeline, a redesigned model and report, and 100% synthetic data. None of it comes from the original project.", p)]]))
    add("aboutPipeline", 1044, 154, 812, 400, textbox([
        [("How it's built", h)],
        [("1  ", b), ("Python generator creates reproducible synthetic CSVs (fixed seed and as-of date).", p)],
        [("2  ", b), ("SQL Server: core tables with keys and constraints, reporting views, 24 validation checks.", p)],
        [("3  ", b), ("Power BI semantic model: 8 tables, single-direction relationships, explicit DAX measures.", p)],
        [("4  ", b), ("Report stored as a Power BI Project (PBIR + TMDL) in Git: every visual is a reviewable file.", p)],
        [("5  ", b), ("60 automated tests and validation queries, run on Linux and on Windows.", p)]]))
    add("aboutDesign", 1044, 614, 812, 410, textbox([
        [("Design techniques on display", h)],
        [("•  Designed background canvas (SVG → PNG) with transparent visuals on top", p)],
        [("•  Icon navigation rail with page-navigation buttons", p)],
        [("•  Bookmark toggles: Status ↔ Attendance quality, By cohort ↔ Competency heatmap", p)],
        [("•  Definitions drawer opened and closed by bookmarks", p)],
        [("•  Conditional-format heatmap and a custom dark theme", p)],
        [("•  Interactions tuned so chart clicks never change the headline KPIs", p)]]))
    v.extend(nav_buttons(ABOUT, z))
    return v


# =========================================================================
# 5. PAGES, INTERACTIONS AND BOOKMARKS
# =========================================================================
def page_json(page_id: str, display: str, background: str, interactions=None) -> dict:
    # NB: the property "image" contains an object that is ALSO called "image"
    # (this nesting is how Power BI Desktop writes it).
    img = {"image": {"image": {
        "name": literal(background),
        "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1,
                                                 "ItemName": background}}},
        "scaling": literal("Fit")}}}
    page = {"$schema": S_PAGE, "name": page_id, "displayName": display, "displayOption": "FitToPage",
            "height": H, "width": W,
            "objects": {"background": [{"properties": {**img, "transparency": literal(0)}}],
                        "outspace": [{"properties": {"color": colour(INK), "transparency": literal(0)}}]}}
    if interactions:
        page["visualInteractions"] = interactions
    return page


def overview_interactions(visuals: list[dict]) -> list[dict]:
    """Chart clicks must not filter the KPI numbers (only the slicer does)."""
    kpis = [k[0] for k in KPIS]
    kpis += [f"{k}Context" for k in CONTEXT_MEASURE] + [f"{k}Bar" for k in BAR_MEASURE]
    charts = ["chartStatus", "chartAttendance", "chartTrend", "chartHeatmap"]
    return [{"source": c, "target": k, "type": "NoFilter"} for c in charts for k in kpis]


def bookmark(name: str, display: str, show: list[str], hide: list[str], types: dict,
             data_targets: list[str] | None = None) -> dict:
    """Display-only bookmark that changes visibility of the listed visuals only."""
    targets = show + hide + (data_targets or [])
    containers = {n: {"singleVisual": {"visualType": types[n]}} for n in show}
    containers.update({n: {"singleVisual": {"visualType": types[n], "display": {"mode": "hidden"}}} for n in hide})
    for n in data_targets or []:
        containers[n] = {"singleVisual": {"visualType": types[n]}, "filters": {"byExpr": []}}
    return {"$schema": S_BOOKMARK, "displayName": display, "name": name,
            "options": {"targetVisualNames": targets, "applyOnlyToTargetVisuals": True,
                        **({"suppressDisplay": True} if data_targets else {"suppressData": True})},
            "explorationState": {"version": "1.3", "activeSection": OVERVIEW,
                                 "sections": {OVERVIEW: {"visualContainers": containers}}}}


def bookmarks(types: dict) -> list[dict]:
    left_status = ["leftTitleStatus", "chipStatusOn", "chipAttendanceOff", "chartStatus"]
    left_att = ["leftTitleAttendance", "chipStatusOff", "chipAttendanceOn", "chartAttendance"]
    right_cohort = ["rightTitleCohort", "chipCohortOn", "chipCompetencyOff", "chartTrend"]
    right_comp = ["rightTitleCompetency", "chipCohortOff", "chipCompetencyOn", "chartHeatmap"]
    drawer = ["drawerScrim", "drawerPanel", "drawerText", "drawerClose"]
    return [
        bookmark("bmLeftStatus", "Left panel · Status", left_status, left_att, types),
        bookmark("bmLeftAttendance", "Left panel · Attendance quality", left_att, left_status, types),
        bookmark("bmRightCohort", "Right panel · By cohort", right_cohort, right_comp, types),
        bookmark("bmRightCompetency", "Right panel · By competency", right_comp, right_cohort, types),
        bookmark("bmDrawerOpen", "Definitions · open", drawer, [], types),
        bookmark("bmDrawerClose", "Definitions · close", [], drawer, types),
        # Reset view: layout only - keeps the user's cohort selection
        bookmark("bmResetView", "Reset view", left_status + right_cohort, left_att + right_comp + drawer, types),
        # Clear filters: cohort selection only - keeps the current panels
        bookmark("bmClearFilters", "Clear filters", [], [], types, data_targets=["cohortSlicer"]),
    ]


# =========================================================================
# 6. WRITE EVERYTHING
# =========================================================================
def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def register_resources() -> None:
    """Dark theme + two background images in report.json."""
    RESOURCES.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(THEME, RESOURCES / THEME.name)
    path = DEFINITION / "report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["themeCollection"]["customTheme"] = {
        "name": THEME.name,
        "reportVersionAtImport": report["themeCollection"]["baseTheme"]["reportVersionAtImport"],
        "type": "RegisteredResources"}
    report["resourcePackages"] = [p for p in report["resourcePackages"] if p["name"] != "RegisteredResources"]
    report["resourcePackages"].append({
        "name": "RegisteredResources", "type": "RegisteredResources",
        "items": [{"name": THEME.name, "path": THEME.name, "type": "CustomTheme"},
                  {"name": BG_OVERVIEW, "path": BG_OVERVIEW, "type": "Image"},
                  {"name": BG_ABOUT, "path": BG_ABOUT, "type": "Image"}]
                 + [{"name": f, "path": f, "type": "Image"} for f in sorted(ICON_FILES)]})
    for f in sorted(ICON_FILES):
        (RESOURCES / f).write_text(icon_svg(f), encoding="utf-8", newline="\n")
    # drop icons / images no longer used (e.g. Desktop's renamed copies)
    keep = {THEME.name, BG_OVERVIEW, BG_ABOUT, *ICON_FILES}
    for f in RESOURCES.iterdir():
        if f.name not in keep and f.suffix in {".png", ".svg"}:
            f.unlink()
    write_json(path, report)
    # remove the UX-01 light theme from the resources if present
    old = RESOURCES / "WorkforceIntelligence.json"
    if old.exists():
        old.unlink()


def write_page(page_id: str, page: dict, visuals: list[dict]) -> None:
    page_dir = DEFINITION / "pages" / page_id
    if (page_dir / "visuals").exists():
        shutil.rmtree(page_dir / "visuals")
    for v in visuals:
        write_json(page_dir / "visuals" / v["name"] / "visual.json", v)
    write_json(page_dir / "page.json", page)


def main() -> None:
    DESIGN.mkdir(parents=True, exist_ok=True)
    (DESIGN / "overview-background.svg").write_text(overview_svg(), encoding="utf-8", newline="\n")
    (DESIGN / "about-background.svg").write_text(about_svg(), encoding="utf-8", newline="\n")

    overview = overview_visuals()
    about = about_visuals()
    write_page(OVERVIEW, page_json(OVERVIEW, "Overview", BG_OVERVIEW, overview_interactions(overview)), overview)
    write_page(ABOUT, page_json(ABOUT, "About", BG_ABOUT), about)
    write_json(DEFINITION / "pages" / "pages.json",
               {"$schema": S_PAGES, "pageOrder": [OVERVIEW, ABOUT], "activePageName": OVERVIEW})

    bm_dir = DEFINITION / "bookmarks"
    if bm_dir.exists():
        shutil.rmtree(bm_dir)
    types = {v["name"]: v["visual"]["visualType"] for v in overview}
    marks = bookmarks(types)
    for b in marks:
        write_json(bm_dir / f"{b['name']}.bookmark.json", b)
    write_json(bm_dir / "bookmarks.json", {"$schema": S_BOOKMARKS, "items": [{"name": b["name"]} for b in marks]})

    register_resources()
    print(f"Overview: {len(overview)} visuals · About: {len(about)} visuals · {len(marks)} bookmarks")
    print("Backgrounds written to powerbi/design/*.svg - render them to PNG before opening Desktop.")


if __name__ == "__main__":
    main()
