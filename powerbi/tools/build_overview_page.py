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
COHORTS_P = "c3a1e7b2d9f04c6e8a21"         # UX-03 pages
SKILLS_P = "d4b2f8c3e0a15d7f9b32"
ATTEND_P = "e5c3a9d4f1b26e8a0c43"
TRAINEE_P = "f6d4b0e5a2c37f9b1d54"         # drill-through (hidden in view mode)
COACH_P = "a8d1f4c7e2b95a3d6c17"           # BI-02 pages
READY_P = "b9e2a5d8f3c06b4e7d28"
BACKGROUNDS: list[str] = []                # filled as page backgrounds are written
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
    ("cohorts", "Cohorts", 216, COHORTS_P),
    ("skills", "Skills", 290, SKILLS_P),
    ("attendance", "Attendance", 364, ATTEND_P),
    ("coaching", "Coaching", 438, COACH_P),       # BI-02
    ("readiness", "Readiness", 512, READY_P),     # BI-02
    ("trainee", "Trainee 360", 586, None),   # reached by drill-through only, never a nav link
    ("about", "About", 1016, ABOUT),
]

# Model names exactly as in Power BI
ENROL, ATTEND, COMPET, COHORT, WEEK, SNAP = (
    "rpt dim_enrolment", "rpt fact_attendance", "rpt dim_competency",
    "rpt dim_cohort", "rpt dim_programme_week", "rpt dim_snapshot")
# BI-02 (Build 02 views)
WLC, WLE, COACH, CERT, CATT, RREV = (
    "rpt fact_watchlist_case", "rpt fact_watchlist_event", "rpt fact_coaching_action",
    "rpt dim_certification", "rpt fact_certification_attempt", "rpt fact_readiness_review")

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
    "coaching": '<path d="M4 5h16v10H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
    "readiness": '<path d="M12 3 4 6v6c0 4.5 3.4 8.2 8 9 4.6-.8 8-4.5 8-9V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
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


def svg_base(active: str, height: int = H) -> list[str]:
    """Canvas, grid texture and navigation rail shared by every page."""
    H = height                     # noqa: N806  (a taller page, e.g. Trainee 360)
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


def count_proj(table: str, column: str, label: str) -> dict:
    """Power BI's built-in 'Count of <column>' (an implicit aggregation, not a DAX measure)."""
    return {"field": {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Entity": table}},
                                                                 "Property": column}}, "Function": 5}},
            "queryRef": f"Count({table}.{column})", "nativeQueryRef": f"Count of {column}", "displayName": label}


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
        tone = GOLD if on else ("#6F7D90" if page or key == "trainee" else "#3E4A5C")
        out.append(container(f"navIcon_{key}", 35, cy - 13, 26, 26, z, image(icon_file(key, tone)))); z += 1
        lines = [[(label, {"fontFamily": "Segoe UI Semibold" if on else "Segoe UI", "fontSize": "7pt", "color": tone})]]
        if page is None:
            sub = "drill-through" if key == "trainee" else "planned"
            lines.append([(sub, {"fontFamily": "Segoe UI", "fontSize": "6pt", "color": "#3E4A5C"})])
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
    add("snapshotLabel", 1186, 38, 296, 44, {
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
        },
        # same sync group on every page: the cohort selection follows you between pages
        "syncGroup": {"groupName": "CohortSelection", "fieldChanges": True, "filterChanges": True}})

    # KPI cards: icon + label + number + context line (frame is in the background)
    for i, (vid, table, name, label, context, icon, accent) in enumerate(KPIS):
        x = X0 + i * (KPI_W + KPI_GAP)
        add(f"{vid}Icon", x + 33, KPI_Y + 31, 22, 22, image(icon_file(icon, accent)))
        add(f"{vid}Label", x + 70, KPI_Y + 28, KPI_W - 80, 30, textbox([[(label,
            {"fontFamily": "Segoe UI Semibold", "fontSize": "9pt", "color": MUTED})]]))
        if vid in CONTEXT_MEASURE:          # data-driven context line
            ctable, cmeasure = CONTEXT_MEASURE[vid]
            add(f"{vid}Context", x + 4, KPI_Y + 126, KPI_W - 8, 44, {   # cards need ~40px+ or text is clipped
                "visualType": "card",
                "query": {"queryState": {"Values": {"projections": [proj("Measure", ctable, cmeasure)]}}},
                "objects": {"labels": props(fontFamily=FONT["regular"], fontSize=9, color=colour("#8FA0B4")),
                            "categoryLabels": props(show=False)}})
        else:                               # static description
            add(f"{vid}Context", x + 10, KPI_Y + 134, KPI_W - 20, 30, textbox([[(context,
                {"fontFamily": "Segoe UI", "fontSize": "10pt", "color": "#8FA0B4"})]], "center"))
        if vid in BAR_MEASURE:              # SVG progress bar drawn by a measure
            btable, bmeasure = BAR_MEASURE[vid]
            add(f"{vid}Bar", x + 24, KPI_Y + 128, KPI_W - 48, 8, image_from_measure(btable, bmeasure))
        add(vid, x + 14, KPI_Y + 56, KPI_W - 28, 70, {
            "visualType": "card",
            "query": {"queryState": {"Values": {"projections": [proj("Measure", table, name)]}}},
            "objects": {"labels": props(fontFamily=FONT["bold"], fontSize=30, color=colour(CREAM)),
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
            # one projection only: a field may appear once per visual with one display name.
            # Data labels show the % share; the default tooltip shows the session count.
            "Y": {"projections": [proj("Measure", ATTEND, "Eligible Attendance Sessions", "Sessions")]}},
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
    add("currentWeekMarker", rx + 14, ry + 72, 320, 48, {
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
    add("chartTrend", rx + 20, ry + 120, rw - 40, PANEL_H - 140, {
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
    add("chartHeatmap", rx + 20, ry + 126, rw - 40, PANEL_H - 146, {
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
def page_json(page_id: str, display: str, background: str, interactions=None, *, extra: dict | None = None) -> dict:
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
    page.update(extra or {})
    return page


def overview_interactions(visuals: list[dict]) -> list[dict]:
    """Chart clicks must not filter the KPI numbers (only the slicer does)."""
    kpis = [k[0] for k in KPIS]
    kpis += [f"{k}Context" for k in CONTEXT_MEASURE] + [f"{k}Bar" for k in BAR_MEASURE]
    charts = ["chartStatus", "chartAttendance", "chartTrend", "chartHeatmap"]
    return [{"source": c, "target": k, "type": "NoFilter"} for c in charts for k in kpis]


def bookmark(name: str, display: str, show: list[str], hide: list[str], types: dict,
             data_targets: list[str] | None = None, page: str = OVERVIEW) -> dict:
    """Display-only bookmark that changes visibility of the listed visuals only."""
    targets = show + hide + (data_targets or [])
    containers = {n: {"singleVisual": {"visualType": types[n]}} for n in show}
    containers.update({n: {"singleVisual": {"visualType": types[n], "display": {"mode": "hidden"}}} for n in hide})
    for n in data_targets or []:
        containers[n] = {"singleVisual": {"visualType": types[n]}, "filters": {"byExpr": []}}
    return {"$schema": S_BOOKMARK, "displayName": display, "name": name,
            "options": {"targetVisualNames": targets, "applyOnlyToTargetVisuals": True,
                        **({"suppressDisplay": True} if data_targets else {"suppressData": True})},
            "explorationState": {"version": "1.3", "activeSection": page,
                                 "sections": {page: {"visualContainers": containers}}}}


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
                  *[{"name": b, "path": b, "type": "Image"} for b in BACKGROUNDS]]
                 + [{"name": f, "path": f, "type": "Image"} for f in sorted(ICON_FILES)]})
    for f in sorted(ICON_FILES):
        (RESOURCES / f).write_text(icon_svg(f), encoding="utf-8", newline="\n")
    # drop icons / images no longer used (e.g. Desktop's renamed copies)
    keep = {THEME.name, *BACKGROUNDS, *ICON_FILES}
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


# =========================================================================
# 7. UX-03 PAGES: Cohort Intelligence, Competency & Skills, Attendance &
#    Participation, Trainee 360 (drill-through). Existing measures only, plus
#    the approved [Withdrawal Rate (Snapshot)].
# =========================================================================
SPAN = XR - X0                         # 1744: content width
COL_L = 860                            # left column width (two-column rows)
COL_R = SPAN - COL_L - 16              # 868
X_R = X0 + COL_L + 16                  # 1012: right column x
COHORT_COLOURS = (("2026 Cohort 1", SKY), ("2026 Cohort 2", TEAL), ("2026 Cohort 3", GOLD))
STATUS_SERIES = (("Active Trainees (Snapshot)", "Active", GOLD),
                 ("Completed Trainees (Snapshot)", "Completed (to date)", TEAL),
                 ("Withdrawn Trainees (Snapshot)", "Withdrawn", CORAL))
ATT_STATUS = (("Present", TEAL), ("Absent", CORAL), ("Unrecorded", SLATE))
UX03_SLICERS: dict[str, tuple[str, list[str]]] = {}     # page id -> (key, slicer names) for Clear filters


def page_svg(active: str, frames=(), tiles=(), tracks=(), back=False, height: int = H) -> str:
    """Background for a UX-03 page: shared rail + header pill/button + panel frames."""
    out = svg_base(active, height)
    out.append('<rect x="1152" y="40" width="336" height="40" rx="20" fill="#FFFFFF" fill-opacity=".04" stroke="#FFFFFF" stroke-opacity=".09"/>')
    out.append(f'<circle cx="1174" cy="60" r="4" fill="{TEAL}"/><circle cx="1174" cy="60" r="8" fill="{TEAL}" fill-opacity=".25"/>')
    out.append('<rect x="1764" y="40" width="116" height="40" rx="12" fill="#FFFFFF" fill-opacity=".03" stroke="#FFFFFF" stroke-opacity=".09"/>')
    for x, y, w, h in tracks:
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h//2}" fill="#000000" fill-opacity=".25" stroke="#FFFFFF" stroke-opacity=".09"/>')
    for f in frames:
        out.append(svg_frame(*f))
    for x, y, accent in tiles:
        out.append(f'<rect x="{x}" y="{y}" width="40" height="40" rx="12" fill="{accent}" fill-opacity=".14"/>')
    out.append('</svg>')
    return "\n".join(out)


def text(size, colour_, weight="Segoe UI"):
    return {"fontFamily": weight, "fontSize": f"{size}pt", "color": colour_}


def header(page_id: str, key: str, eyebrow: str, title: str, *, week_slicer=False, back=False,
           note: str = "Cohorts compared by programme week, not calendar date") -> list[dict]:
    """Eyebrow, title, snapshot label, Clear filters (or Back), cohort and week selectors."""
    v = [container("headerEyebrow", X0 - 6, 34, 900, 30, 1000, textbox([[(eyebrow, text(10, GOLD, "Segoe UI Semibold"))]])),
         container("headerTitle", X0 - 6, 58, 1000, 64, 1001, textbox([[(title, {"fontFamily": "Segoe UI Bold",
                                                                                 "fontSize": "30pt", "color": CREAM})]])),
         container("snapshotLabel", 1186, 38, 296, 44, 1002, {
             "visualType": "card",
             "query": {"queryState": {"Values": {"projections": [proj("Measure", SNAP, "Snapshot Label")]}}},
             "objects": {"labels": props(fontSize=10, color=colour("#C9D2DE"), fontFamily=FONT["regular"]),
                         "categoryLabels": props(show=False)}})]
    if back:
        v.append(container("btnBack", 1764, 40, 116, 40, 1003, button(
            "←  Back", link={"type": "Back"}, fg="#C9D2DE", hover_alpha=90, size=10, tooltip="Back to the page you came from")))
        return v
    slicers = ["cohortSlicer"]
    v.append(container("btnClearFilters", 1764, 40, 116, 40, 1003, button(
        "✕  Clear filters", link=bookmark_link(f"bmClearFilters_{key}"), fg="#C9D2DE", hover_alpha=90, size=10,
        tooltip="Clear the cohort and week selections on this page")))
    v.append(container("cohortSlicer", X0 + 8, 124, 524, 44, 1004, {
        "visualType": "slicer",
        "query": {"queryState": {"Values": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]}}},
        "objects": {"data": props(mode="Basic"), "general": props(orientation=1),
                    "selection": props(selectAllCheckboxEnabled=False, singleSelect=False),
                    "header": props(show=False),
                    "items": props(fontColor=colour("#D8DEE6"), background=colour("#0B1D33"), outlineStyle=0, textSize=11)},
        "syncGroup": {"groupName": "CohortSelection", "fieldChanges": True, "filterChanges": True}}))
    note_x = 692
    if week_slicer:
        slicers.append("weekSlicer")
        v.append(container("weekLabel", 690, 130, 130, 32, 1005, textbox([[("Programme week", text(10, "#8FA0B4"))]])))
        v.append(container("weekSlicer", 820, 124, 180, 44, 1006, {
            "visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [proj("Column", WEEK, "week_label", "Programme week")]}}},
            "objects": {"data": props(mode="Dropdown"), "header": props(show=False),
                        "selection": props(selectAllCheckboxEnabled=True, singleSelect=False),
                        "items": props(fontColor=colour("#D8DEE6"), background=colour("#0B1D33"), textSize=11)},
            "syncGroup": {"groupName": "WeekSelection", "fieldChanges": True, "filterChanges": True}}))
    else:   # no room beside a week selector; there the "Programme week" label makes the same point
        v.append(container("cohortNote", note_x - 6, 132, 1150 - note_x, 30, 1007, textbox([[(
            note, text(10, "#7F8EA2"))]])))
    UX03_SLICERS[page_id] = (key, slicers)
    return v


def panel_title(name: str, x: int, y: int, w: int, title: str, subtitle: str, z: int) -> dict:
    return container(name, x + 16, y + 14, w - 32, 60, z, textbox([[(title, text(13, CREAM, "Segoe UI Semibold"))],
                                                                     [(subtitle, text(9, "#8FA0B4"))]]))


def body(x, y, w, h):
    """Content area inside a panel frame, below its title."""
    return x + 14, y + 74, w - 28, h - 86


def number_card(measure_table: str, measure: str, label: str | None = None, size=30) -> dict:
    return {"visualType": "card",
            "query": {"queryState": {"Values": {"projections": [proj("Measure", measure_table, measure, label)]}}},
            "objects": {"labels": props(fontFamily=FONT["bold"], fontSize=size, color=colour(CREAM)),
                        "categoryLabels": props(show=False)}}


def number_filter(name: str, table: str, column: str, value: int) -> dict:
    """Visual filter: <table>[<column>] = whole number (e.g. has_action = 0)."""
    return {"name": name, "field": field("Column", table, column), "type": "Categorical", "howCreated": "User",
            "filter": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                       "Where": [{"Condition": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                           "Values": [[{"Literal": {"Value": f"{value}L"}}]]}}}]}}


def category_filter(name: str, table: str, column: str, value: str) -> dict:
    """Visual/page filter: <table>[<column>] = value (no DAX needed)."""
    return {"name": name, "field": field("Column", table, column), "type": "Categorical", "howCreated": "User",
            "filter": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                       "Where": [{"Condition": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                           "Values": [[{"Literal": {"Value": f"'{value}'"}}]]}}}]}}


def kpi_tile(prefix: str, x: int, y: int, w: int, h: int, z: int, label: str, table: str, measure: str,
             context: str, icon: str, accent: str, visual_filter: dict | None = None) -> list[dict]:
    """Icon + label + number + context line (frame and icon tile are in the background)."""
    num = container(prefix, x + 14, y + 54, w - 28, 66, z + 2, number_card(table, measure))
    if visual_filter:
        num["filterConfig"] = {"filters": [visual_filter]}
    return [container(f"{prefix}Icon", x + 33, y + 31, 22, 22, z, image(icon_file(icon, accent))),
            container(f"{prefix}Label", x + 70, y + 28, w - 80, 30, z + 1,
                      textbox([[(label, text(9, MUTED, "Segoe UI Semibold"))]])),
            num,
            container(f"{prefix}Context", x + 10, y + h - 40, w - 20, 30, z + 3,
                      textbox([[(context, text(10, "#8FA0B4"))]], "center"))]


def heatmap(row_table, row_col, row_label, col_table, col_col, col_label, m_table, measure, m_label,
            low="#0B2A3E", high="#3FC1B0") -> dict:
    return {"visualType": "pivotTable",
            "query": {"queryState": {
                "Rows": {"projections": [proj("Column", row_table, row_col, row_label)]},
                "Columns": {"projections": [proj("Column", col_table, col_col, col_label)]},
                "Values": {"projections": [proj("Measure", m_table, measure, m_label)]}}},
            "objects": {
                "values": [{"properties": {
                    "backColor": {"solid": {"color": {"expr": {"FillRule": {
                        "Input": field("Measure", m_table, measure),
                        "FillRule": {"linearGradient2": {
                            "min": {"color": {"Literal": {"Value": f"'{low}'"}}},
                            "max": {"color": {"Literal": {"Value": f"'{high}'"}}},
                            "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'noColor'"}}}}}}}}}},
                    "fontColorPrimary": colour(CREAM), "fontSize": literal(10)},
                    "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"{m_table}.{measure}"}}],
                "subTotals": props(rowSubtotals=False, columnSubtotals=False),
                "columnHeaders": props(fontSize=9, fontColor=colour("#8FA0B4")),
                "rowHeaders": props(fontSize=10, fontColor=colour("#D8DEE6")),
                "grid": props(gridVertical=True, gridVerticalColor=colour(NAVY), gridVerticalWeight=3,
                              gridHorizontal=True, gridHorizontalColor=colour(NAVY), gridHorizontalWeight=3,
                              rowPadding=12)}}


def by_week_sort() -> dict:
    return {"sort": [{"field": field("Column", WEEK, "programme_week"), "direction": "Ascending"}]}


def by_cohort_sort() -> dict:
    return {"sort": [{"field": field("Column", COHORT, "cohort_name"), "direction": "Ascending"}]}


def cohort_colour_points() -> list[dict]:
    return [{"properties": {"fill": colour(c)}, "selector": value_selector(COHORT, "cohort_name", n)} for n, c in COHORT_COLOURS]


def status_colour_points() -> list[dict]:
    return [{"properties": {"fill": colour(c)}, "selector": value_selector(ATTEND, "attendance_status", s)} for s, c in ATT_STATUS]


def axis_objects(x_title: str | None = None, categorical=False) -> dict:
    cat = props(showAxisTitle=bool(x_title), **({"titleText": x_title} if x_title else {}),
                **({"axisType": "Categorical"} if categorical else {}))
    return {"categoryAxis": cat, "valueAxis": props(showAxisTitle=False)}


# ------------------------------------------------------------- A. Cohort Intelligence
def cohort_page() -> dict:
    pid, key = COHORTS_P, "cohorts"
    v = header(pid, key, "COHORT INTELLIGENCE · STATUS AT THE DATA SNAPSHOT", "Cohort Intelligence")
    z = 1100
    score = (X0, 196, SPAN, 272)
    third = (SPAN - 32) // 3                         # 570
    status = (X0, 484, third, 300)
    attend = (X0 + third + 16, 484, third, 300)
    trend = (X0 + 2 * (third + 16), 484, SPAN - 2 * (third + 16), 300)
    roster = (X0, 800, SPAN, 240)

    v.append(panel_title("scoreTitle", *score[:3], "Cohort scorecard",
                         "Snapshot status per cohort. Completed is to date for in-progress cohorts, not a final outcome. "
                         "Starters = Active + Completed + Withdrawn.", z)); z += 1
    cols = [proj("Column", COHORT, "cohort_name", "Cohort"), proj("Column", COHORT, "delivery_mode", "Delivery"),
            proj("Column", COHORT, "schedule_status", "Programme status"), proj("Column", COHORT, "weeks_started", "Weeks started"),
            proj("Measure", ENROL, "Total Enrolments", "Enrolments"), proj("Measure", ENROL, "Cancelled Before Start", "Cancelled before start"),
            proj("Measure", ENROL, "Starting Headcount", "Starters"), proj("Measure", ENROL, "Active Trainees (Snapshot)", "Active"),
            proj("Measure", ENROL, "Completed Trainees (Snapshot)", "Completed (to date)"),
            proj("Measure", ENROL, "Withdrawn Trainees (Snapshot)", "Withdrawn"),
            proj("Measure", ENROL, "Withdrawal Rate (Snapshot)", "Withdrawal rate"),
            proj("Measure", ATTEND, "Recorded Attendance Rate", "Recorded attendance"),
            proj("Measure", ATTEND, "Attendance Recording Rate", "Recording rate")]
    v.append(container("scorecard", *body(*score), z, {
        "visualType": "tableEx", "query": {"queryState": {"Values": {"projections": cols}}, "sortDefinition": by_cohort_sort()},
        "objects": {"total": props(totals=True), "columnHeaders": props(wordWrap=True)}})); z += 1

    v.append(panel_title("statusTitle", *status[:3], "Lifecycle status (share of starters)",
                         "Pre-start cancellations excluded", z)); z += 1
    v.append(container("statusMix", *body(*status), z, {
        "visualType": "hundredPercentStackedBarChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]},
                                 "Y": {"projections": [proj("Measure", ENROL, m, l) for m, l, _ in STATUS_SERIES]}},
                  "sortDefinition": by_cohort_sort()},
        "objects": {"dataPoint": [{"properties": {"fill": colour(c)}, "selector": {"metadata": f"{ENROL}.{m}"}} for m, _, c in STATUS_SERIES],
                    "labels": props(show=True, color=colour("#06111F"), fontSize=9, labelPrecision=0),
                    **axis_objects()}})); z += 1

    v.append(panel_title("attendTitle", *attend[:3], "Attendance: rate vs recording completeness",
                         "Recorded rate = Present ÷ (Present + Absent); recording rate = recorded ÷ eligible", z)); z += 1
    v.append(container("attendCompare", *body(*attend), z, {
        "visualType": "clusteredBarChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]},
                                 "Y": {"projections": [proj("Measure", ATTEND, "Recorded Attendance Rate", "Recorded attendance"),
                                                       proj("Measure", ATTEND, "Attendance Recording Rate", "Recording rate")]}},
                  "sortDefinition": by_cohort_sort()},
        "objects": {"dataPoint": [{"properties": {"fill": colour(TEAL)}, "selector": {"metadata": f"{ATTEND}.Recorded Attendance Rate"}},
                                  {"properties": {"fill": colour(GOLD)}, "selector": {"metadata": f"{ATTEND}.Attendance Recording Rate"}}],
                    "labels": props(show=True, color=colour(CREAM), fontSize=9, labelPrecision=1),
                    **axis_objects()}})); z += 1

    v.append(panel_title("trendTitle", *trend[:3], "Competency by programme week",
                         "Same-week comparison; in-progress cohorts stop at their latest assessed week", z)); z += 1
    v.append(container("cohortTrend", *body(*trend), z, {
        "visualType": "lineChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", WEEK, "programme_week", "Programme week")]},
                                 "Y": {"projections": [proj("Measure", COMPET, "Average Competency Score", "Average score")]},
                                 "Series": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]}},
                  "sortDefinition": by_week_sort()},
        "objects": {"dataPoint": cohort_colour_points(), "lineStyles": props(strokeWidth=3, showMarker=True),
                    **axis_objects("Programme week", categorical=True)}})); z += 1

    v.append(panel_title("rosterTitle", *roster[:3], "Enrolments",
                         "One row per enrolment (a person can enrol more than once). Right-click a row → Drill through → Trainee 360.", z)); z += 1
    v.append(container("enrolmentRoster", *body(*roster), z, {
        "visualType": "tableEx",
        "query": {"queryState": {"Values": {"projections": [
            proj("Column", ENROL, "enrolment_id", "Enrolment"), proj("Column", ENROL, "employee_name", "Trainee (synthetic)"),
            proj("Column", ENROL, "employee_id", "Employee"), proj("Column", COHORT, "cohort_name", "Cohort"),
            proj("Column", ENROL, "status_as_of_snapshot", "Status at snapshot"), proj("Column", ENROL, "start_date", "Start date")]}},
            "sortDefinition": {"sort": [{"field": field("Column", ENROL, "enrolment_id"), "direction": "Ascending"}]}}})); z += 1

    v += nav_decor(key, 100) + nav_buttons(pid, 3000)
    svg = page_svg(key, frames=[score, status, attend, trend, roster], tracks=[(X0, 120, 540, 52)])
    return {"id": pid, "key": key, "display": "Cohort Intelligence", "svg": svg, "visuals": v}


# ------------------------------------------------------------- B. Competency & Skills Development
def skills_page() -> dict:
    pid, key = SKILLS_P, "skills"
    v = header(pid, key, "COMPETENCY & SKILLS DEVELOPMENT", "Competency & Skills Development", week_slicer=True)
    z = 1100
    trend = (X0, 196, COL_L, 420)
    heat = (X_R, 196, COL_R, 420)
    compare = (X0, 632, COL_L, 408)
    sample = (X_R, 632, COL_R, 408)
    v.append(panel_title("trendTitle", *trend[:3], "Average score by programme week, per competency",
                         "Cohort means: a change can partly reflect which trainees were assessed that week", z)); z += 1
    v.append(container("skillTrend", *body(*trend), z, {
        "visualType": "lineChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", WEEK, "programme_week", "Programme week")]},
                                 "Y": {"projections": [proj("Measure", COMPET, "Average Competency Score", "Average score")]},
                                 "Series": {"projections": [proj("Column", COMPET, "competency_name", "Competency")]}},
                  "sortDefinition": by_week_sort()},
        "objects": {"lineStyles": props(strokeWidth=3, showMarker=True), **axis_objects("Programme week", categorical=True)}})); z += 1
    v.append(panel_title("heatTitle", *heat[:3], "Competency × programme week",
                         "Average score; darker = lower, brighter = higher; blank = not yet assessed", z)); z += 1
    v.append(container("skillHeatmap", *body(*heat), z, heatmap(COMPET, "competency_name", "Competency", WEEK, "week_label",
                                                                "Week", COMPET, "Average Competency Score", "Average score"))); z += 1
    v.append(panel_title("compareTitle", *compare[:3], "Competency comparison across cohorts",
                         "Pick ONE programme week above for a like-for-like comparison", z)); z += 1
    # which week(s) the comparison is showing (text measure, filtered by the week selector)
    v.append(container("compareWeeks", compare[0] + compare[2] - 390, compare[1] + 12, 374, 44, z, {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [proj("Measure", WEEK, "Selected Weeks Label")]}}},
        "objects": {"labels": props(fontFamily=FONT["semibold"], fontSize=10, color=colour(GOLD)),
                    "categoryLabels": props(show=False)}})); z += 1
    v.append(container("skillCompare", *body(*compare), z, {
        "visualType": "clusteredBarChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", COMPET, "competency_name", "Competency")]},
                                 "Series": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]},
                                 "Y": {"projections": [proj("Measure", COMPET, "Average Competency Score", "Average score")]}},
                  "sortDefinition": {"sort": [{"field": field("Column", COMPET, "competency_name"), "direction": "Ascending"}]}},
        "objects": {"dataPoint": cohort_colour_points(), "labels": props(show=True, color=colour(CREAM), fontSize=9, labelPrecision=1),
                    **axis_objects()}})); z += 1
    v.append(panel_title("sampleTitle", *sample[:3], "Sample size: assessed trainees per week",
                         "Distinct enrolments assessed; Cohort 3 has no Week 7-8 results yet", z)); z += 1
    v.append(container("skillSample", *body(*sample), z, {
        "visualType": "clusteredColumnChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", WEEK, "programme_week", "Programme week")]},
                                 "Series": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]},
                                 "Y": {"projections": [proj("Measure", COMPET, "Assessed Trainees", "Assessed trainees")]}},
                  "sortDefinition": by_week_sort()},
        "objects": {"dataPoint": cohort_colour_points(), "labels": props(show=True, color=colour(CREAM), fontSize=8),
                    **axis_objects("Programme week", categorical=True)}})); z += 1
    # D26: paired change strip. Same trainees, consecutive weeks: removes the "who was assessed" effect
    paired = (X_R, 120, COL_R, 52)
    v.append(container("pairedLabel", paired[0] + 18, 124, 600, 44, z, textbox([
        [("PAIRED WEEK-OVER-WEEK CHANGE", text(9, GOLD, "Segoe UI Semibold"))],
        [("Same trainees vs their previous week · follows the cohort and week selectors · score points",
          text(9, "#8FA0B4"))]]))); z += 1
    v.append(container("pairedValue", paired[0] + paired[2] - 196, 122, 180, 48, z, {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [proj("Measure", COMPET, "Paired WoW Competency Change")]}}},
        "objects": {"labels": props(fontFamily=FONT["bold"], fontSize=18, color=colour(TEAL)),
                    "categoryLabels": props(show=False)}})); z += 1
    v += nav_decor(key, 100) + nav_buttons(pid, 3000)
    # the week selector only drives the like-for-like comparison panel and the paired-change strip
    interactions = [{"source": "weekSlicer", "target": t, "type": "NoFilter"} for t in ("skillTrend", "skillHeatmap", "skillSample")]
    svg = page_svg(key, frames=[trend, heat, compare, sample],
                   tracks=[(X0, 120, 540, 52), (812, 120, 196, 52), paired])
    return {"id": pid, "key": key, "display": "Competency & Skills", "svg": svg, "visuals": v, "interactions": interactions}


# ------------------------------------------------------------- C. Attendance & Participation
def attendance_page() -> dict:
    pid, key = ATTEND_P, "attendance"
    v = header(pid, key, "ATTENDANCE & PARTICIPATION · ENROLMENT-SESSION GRAIN", "Attendance & Participation", week_slicer=True)
    z = 1100
    kw = (SPAN - 3 * 16) // 4                         # 424
    tiles = []
    cards = [("kpiEligible", "ELIGIBLE ENROLMENT-SESSIONS", ATTEND, "Eligible Attendance Sessions",
              "One per enrolment per scheduled session", "attendance", TEAL, None),
             ("kpiUnrecorded", "UNRECORDED ENROLMENT-SESSIONS", ATTEND, "Eligible Attendance Sessions",
              "No mark recorded (not counted as absent)", "doc", SLATE,
              category_filter("onlyUnrecorded", ATTEND, "attendance_status", "Unrecorded")),
             ("kpiRecordedRate", "RECORDED ATTENDANCE RATE", ATTEND, "Recorded Attendance Rate",
              "Present ÷ (Present + Absent)", "check", TEAL, None),
             ("kpiRecordingRate", "ATTENDANCE RECORDING RATE", ATTEND, "Attendance Recording Rate",
              "Recorded ÷ eligible enrolment-sessions", "doc", GOLD, None)]
    frames = []
    for i, (prefix, label, table, measure, context, icon, accent, vf) in enumerate(cards):
        x = X0 + i * (kw + 16)
        frames.append((x, 196, kw, 150)); tiles.append((x + 24, 196 + 22, accent))
        v += kpi_tile(prefix, x, 196, kw, 150, z, label, table, measure, context, icon, accent, vf); z += 4
    mix = (X0, 362, COL_L, 330)
    weekly = (X_R, 362, COL_R, 330)
    heat = (X0, 708, COL_L, 332)
    counts = (X_R, 708, COL_R, 332)
    v.append(panel_title("mixTitle", *mix[:3], "Attendance composition by cohort",
                         "Share of eligible enrolment-sessions; hover for counts", z)); z += 1
    v.append(container("attendMix", *body(*mix), z, {
        "visualType": "hundredPercentStackedBarChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]},
                                 "Series": {"projections": [proj("Column", ATTEND, "attendance_status", "Attendance")]},
                                 "Y": {"projections": [proj("Measure", ATTEND, "Eligible Attendance Sessions", "Sessions")]}},
                  "sortDefinition": by_cohort_sort()},
        "objects": {"dataPoint": status_colour_points(), "labels": props(show=True, color=colour("#06111F"), fontSize=9, labelPrecision=1),
                    **axis_objects()}})); z += 1
    v.append(panel_title("weeklyTitle", *weekly[:3], "Rates by programme week",
                         "Ratios of summed counts, never averages of percentages", z)); z += 1
    v.append(container("attendWeekly", *body(*weekly), z, {
        "visualType": "lineChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", WEEK, "programme_week", "Programme week")]},
                                 "Y": {"projections": [proj("Measure", ATTEND, "Recorded Attendance Rate", "Recorded attendance"),
                                                       proj("Measure", ATTEND, "Attendance Recording Rate", "Recording rate")]}},
                  "sortDefinition": by_week_sort()},
        "objects": {"dataPoint": [{"properties": {"fill": colour(TEAL)}, "selector": {"metadata": f"{ATTEND}.Recorded Attendance Rate"}},
                                  {"properties": {"fill": colour(GOLD)}, "selector": {"metadata": f"{ATTEND}.Attendance Recording Rate"}}],
                    "lineStyles": props(strokeWidth=3, showMarker=True), **axis_objects("Programme week", categorical=True)}})); z += 1
    v.append(panel_title("heatTitle", *heat[:3], "Recorded attendance rate: cohort × week",
                         "Where are attendance gaps concentrated?", z)); z += 1
    v.append(container("attendHeatmap", *body(*heat), z, heatmap(COHORT, "cohort_name", "Cohort", WEEK, "week_label", "Week",
                                                                ATTEND, "Recorded Attendance Rate", "Recorded attendance",
                                                                low="#5A2E2A", high="#3FC1B0"))); z += 1
    v.append(panel_title("countsTitle", *counts[:3], "Enrolment-sessions per week by attendance mark",
                         "Counts, including unrecorded marks", z)); z += 1
    v.append(container("attendCounts", *body(*counts), z, {
        "visualType": "columnChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", WEEK, "programme_week", "Programme week")]},
                                 "Series": {"projections": [proj("Column", ATTEND, "attendance_status", "Attendance")]},
                                 "Y": {"projections": [proj("Measure", ATTEND, "Eligible Attendance Sessions", "Sessions")]}},
                  "sortDefinition": by_week_sort()},
        "objects": {"dataPoint": status_colour_points(), **axis_objects("Programme week", categorical=True)}})); z += 1
    v += nav_decor(key, 100) + nav_buttons(pid, 3000)
    svg = page_svg(key, frames=frames + [mix, weekly, heat, counts], tiles=tiles,
                   tracks=[(X0, 120, 540, 52), (812, 120, 196, 52)])
    return {"id": pid, "key": key, "display": "Attendance & Participation", "svg": svg, "visuals": v}


# ------------------------------------------------------------- D. Trainee 360 (drill-through)
def trainee_page() -> dict:
    pid, key = TRAINEE_P, "trainee"
    v = header(pid, key, "TRAINEE 360 · TRAINING · ONE ENROLMENT", "Trainee 360 — Training", back=True)
    z = 1100
    ident = (X0, 130, SPAN, 120)
    kw = (SPAN - 2 * 16) // 3                         # 570
    cards = [("kpiRecorded", "RECORDED ATTENDANCE RATE", ATTEND, "Recorded Attendance Rate", "Present ÷ (Present + Absent)", "check", TEAL),
             ("kpiRecording", "ATTENDANCE RECORDING RATE", ATTEND, "Attendance Recording Rate", "Recorded ÷ eligible sessions", "doc", GOLD),
             ("kpiScore", "AVERAGE COMPETENCY SCORE", COMPET, "Average Competency Score", "All assessed weeks, 0-100", "star", TEAL)]
    frames, tiles = [ident], []
    v.append(container("identity", *body(ident[0], ident[1] - 60, ident[2], ident[3] + 50), z, {
        "visualType": "multiRowCard",
        "query": {"queryState": {"Values": {"projections": [
            proj("Column", ENROL, "employee_name", "Trainee (synthetic)"), proj("Column", ENROL, "enrolment_id", "Enrolment"),
            proj("Column", ENROL, "employee_id", "Employee"), proj("Column", COHORT, "cohort_name", "Cohort"),
            proj("Column", ENROL, "status_as_of_snapshot", "Status at snapshot"), proj("Column", ENROL, "start_date", "Start date")]}}}}))
    z += 1
    for i, (prefix, label, table, measure, context, icon, accent) in enumerate(cards):
        x = X0 + i * (kw + 16)
        frames.append((x, 266, kw, 150)); tiles.append((x + 24, 266 + 22, accent))
        v += kpi_tile(prefix, x, 266, kw, 150, z, label, table, measure, context, icon, accent); z += 4
    att = (X0, 432, COL_L, 608)
    comp = (X_R, 432, COL_R, 300)
    bench = (X_R, 748, COL_R, 292)                    # D26: cohort same-week benchmark
    v.append(panel_title("attTitle", *att[:3], "Attendance by programme week",
                         "This enrolment's sessions by mark; unrecorded is not absent", z)); z += 1
    v.append(container("traineeAttendance", *body(*att), z, {
        "visualType": "columnChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", WEEK, "programme_week", "Programme week")]},
                                 "Series": {"projections": [proj("Column", ATTEND, "attendance_status", "Attendance")]},
                                 "Y": {"projections": [proj("Measure", ATTEND, "Eligible Attendance Sessions", "Sessions")]}},
                  "sortDefinition": by_week_sort()},
        "objects": {"dataPoint": status_colour_points(), **axis_objects("Programme week", categorical=True)}})); z += 1
    v.append(panel_title("compTitle", *comp[:3], "Competency progression",
                         "This enrolment, one line per competency", z)); z += 1
    v.append(container("traineeCompetency", *body(*comp), z, {
        "visualType": "lineChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", WEEK, "programme_week", "Programme week")]},
                                 "Y": {"projections": [proj("Measure", COMPET, "Average Competency Score", "Score")]},
                                 "Series": {"projections": [proj("Column", COMPET, "competency_name", "Competency")]}},
                  "sortDefinition": by_week_sort()},
        "objects": {"lineStyles": props(strokeWidth=3, showMarker=True), **axis_objects("Programme week", categorical=True)}})); z += 1
    v.append(panel_title("benchTitle", *bench[:3], "This trainee vs cohort, same programme week",
                         "Average across competencies · cohort line = all trainees in the same cohort that week", z)); z += 1
    v.append(container("traineeBenchmark", *body(*bench), z, {
        "visualType": "lineChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", WEEK, "programme_week", "Programme week")]},
                                 "Y": {"projections": [proj("Measure", COMPET, "Average Competency Score", "This trainee"),
                                                       proj("Measure", COMPET, "Cohort Same-Week Average", "Cohort, same week")]}},
                  "sortDefinition": by_week_sort()},
        "objects": {"dataPoint": [{"properties": {"fill": colour(TEAL)}, "selector": {"metadata": f"{COMPET}.Average Competency Score"}},
                                  {"properties": {"fill": colour(GOLD)}, "selector": {"metadata": f"{COMPET}.Cohort Same-Week Average"}}],
                    "lineStyles": props(strokeWidth=3, showMarker=True), **axis_objects("Programme week", categorical=True)}})); z += 1
    # ---- BI-02 extension: coaching, certification and readiness history of THIS enrolment
    status = (X0, 1056, SPAN, 96)
    cases = (X0, 1168, COL_L, 300)
    actions = (X_R, 1168, COL_R, 300)
    attempts = (X0, 1484, COL_L, 300)
    reviews = (X_R, 1484, COL_R, 300)
    v.append(container("readinessStatusLabel", status[0] + 24, status[1] + 14, 330, 30, z,
                       textbox([[("READINESS STATUS · AT THE SNAPSHOT", text(9, GOLD, "Segoe UI Semibold"))]]))); z += 1
    v.append(container("readinessStatusValue", status[0] + 14, status[1] + 40, 900, 48, z, {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [proj("Measure", RREV, "Readiness Status Label")]}}},
        "objects": {"labels": props(fontFamily=FONT["semibold"], fontSize=16, color=colour(CREAM)),
                    "categoryLabels": props(show=False)}})); z += 1
    v.append(container("readinessStatusNote", status[0] + 940, status[1] + 30, status[2] - 960, 52, z,
                       textbox([[("Readiness is a dated management decision, not deployment. A trainee still in training "
                                  "is \u201cnot yet eligible\u201d; a completer without a review is \u201cnot reviewed\u201d. Neither is a failure.",
                                  text(10, "#8FA0B4"))]]))); z += 1
    for frame, name, title, sub, cols, sort_col in [
        (cases, "traineeCases", "Watch-list episodes",
         "Support cases for this enrolment · empty = never watch-listed",
         [proj("Column", WLC, "watchlist_case_id", "Case"), proj("Column", WLC, "opened_effective_date", "Opened"),
          proj("Column", WLC, "primary_reason", "Reason"), proj("Column", WLC, "severity", "Severity"),
          proj("Column", WLC, "case_status_as_of_snapshot", "Status (snapshot)"),
          proj("Column", WLC, "closure_reason", "Closure reason"), proj("Column", WLC, "action_count", "Actions")],
         (WLC, "opened_effective_date")),
        (actions, "traineeActions", "Coaching actions",
         "Completed, dated actions · association only, not proof of effect",
         [proj("Column", COACH, "action_date", "Date"), proj("Column", COACH, "action_type", "Action"),
          proj("Column", COACH, "staff_role", "By (role)"), proj("Column", COACH, "days_since_case_opened", "Days after opening"),
          proj("Column", COACH, "watchlist_case_id", "Case")],
         (COACH, "action_date")),
        (attempts, "traineeAttempts", "Certification attempts",
         "Fictional internal certifications · empty = no attempt yet (not a failure)",
         [proj("Column", CERT, "certification_name", "Certification"), proj("Column", CATT, "attempt_number", "Attempt"),
          proj("Column", CATT, "attempt_date", "Date"), proj("Column", CATT, "score", "Score"),
          proj("Column", CATT, "pass_mark", "Pass mark"), proj("Column", CATT, "result", "Result")],
         (CATT, "attempt_date")),
        (reviews, "traineeReviews", "Readiness reviews (timeline)",
         "Evidence as it stood at each review · the latest review is in force",
         [proj("Column", RREV, "review_number", "Review"), proj("Column", RREV, "review_date", "Date"),
          proj("Column", RREV, "decision", "Decision"), proj("Column", RREV, "decision_reason_code", "Reason"),
          proj("Column", RREV, "certification_gate_passed", "Certified"),
          proj("Column", RREV, "competency_gate_passed", "Competency gate"),
          proj("Column", RREV, "review_competency_score", "Score"), proj("Column", RREV, "signoff_recorded", "Signed off"),
          proj("Column", RREV, "is_latest_review", "Latest")],
         (RREV, "review_number")),
    ]:
        v.append(panel_title(f"{name}Title", *frame[:3], title, sub, z)); z += 1
        v.append(container(name, *body(*frame), z, {
            "visualType": "tableEx",
            "query": {"queryState": {"Values": {"projections": cols}},
                      "sortDefinition": {"sort": [{"field": field("Column", *sort_col), "direction": "Ascending"}]}},
            "objects": {"columnHeaders": props(wordWrap=True)}})); z += 1
    v += nav_decor(key, 100) + nav_buttons(pid, 3000)
    enrol_field = field("Column", ENROL, "enrolment_id")
    extra = {"type": "Drillthrough", "visibility": "HiddenInViewMode",
             "pageBinding": {"name": "trainee360Binding", "type": "Drillthrough",
                             "parameters": [{"name": "trainee360Enrolment", "boundFilter": "drillEnrolment", "fieldExpr": enrol_field}]},
             "filterConfig": {"filters": [{"name": "drillEnrolment", "field": enrol_field, "type": "Categorical",
                                           "howCreated": "Drillthrough"}]}}
    extra.update({"height": TRAINEE_H, "displayOption": "FitToWidth"})     # taller page: scroll down
    svg = page_svg(key, frames=frames + [att, comp, bench, status, cases, actions, attempts, reviews],
                   tiles=tiles, height=TRAINEE_H)
    return {"id": pid, "key": key, "display": "Trainee 360 — Training", "svg": svg, "visuals": v, "extra": extra}


TRAINEE_H = 1824     # Trainee 360 grew downwards in BI-02 (1080 + coaching/certification/readiness rows)


def kpi_row(prefixes: list[tuple], y: int, h: int, z: int, gap: int = 16) -> tuple[list, list, list, int]:
    """A row of equal KPI tiles across the content width. Returns visuals, frames, icon tiles, z."""
    n = len(prefixes)
    w = (SPAN - (n - 1) * gap) // n
    v, frames, tiles = [], [], []
    for i, (prefix, label, table, measure, context, icon, accent) in enumerate(prefixes):
        x = X0 + i * (w + gap)
        frames.append((x, y, w, h)); tiles.append((x + 24, y + 22, accent))
        v += kpi_tile(prefix, x, y, w, h, z, label, table, measure, context, icon, accent); z += 4
    return v, frames, tiles, z


def no_filter_on(sources: list[str], targets: list[str]) -> list[dict]:
    """Chart clicks highlight other charts but never change the KPI numbers."""
    return [{"source": s, "target": t, "type": "NoFilter"} for s in sources for t in targets]


SEVERITY_COLOURS = (("High", CORAL), ("Medium", GOLD), ("Low", SLATE))


# ------------------------------------------------------------- E. Coaching & Watch List (BI-02)
def coaching_page() -> dict:
    pid, key = COACH_P, "coaching"
    v = header(pid, key, "COACHING & WATCH LIST · SNAPSHOT 2 NOV 2026 UNLESS LABELLED", "Coaching & Watch List",
               note="Descriptive only: no causal claim · unrecorded attendance \u2260 absent")
    z = 1100
    kpis = [("kpiOpenWatch", "OPEN WATCH-LIST ENROLMENTS", WLC, "Open Watch-list Enrolments (Snapshot)",
             "Distinct enrolments, open at the snapshot", "users", GOLD),
            ("kpiWatchRate", "WATCH-LIST RATE (SNAPSHOT)", WLC, "Watch-list Rate (Snapshot)",
             "Open active \u00f7 active trainees", "play", GOLD),
            ("kpiCases", "WATCH-LIST CASES", WLC, "Watch-list Cases", "Episodes, not people \u00b7 to date", "doc", TEAL),
            ("kpiCoverage", "COACHING COVERAGE", WLC, "Coaching Coverage", "Cases with an action \u00f7 all cases", "check", TEAL),
            ("kpiUnactioned", "UNACTIONED CASES", WLC, "Unactioned Watch-list Cases", "No completed action \u00b7 see table", "info", CORAL)]
    kv, frames, tiles, z = kpi_row(kpis, 196, 150, z)
    v += kv
    third = (SPAN - 32) // 3                          # 570
    reason = (X0, 362, third, 330)
    moves = (X0 + third + 16, 362, SPAN - third - 16, 330)
    types = (X0, 708, third, 332)
    first = (X0 + third + 16, 708, third, 332)
    unact = (X0 + 2 * (third + 16), 708, SPAN - 2 * (third + 16), 332)

    v.append(panel_title("reasonTitle", *reason[:3], "Cases by primary reason and severity",
                         "Cases (episodes) to date \u00b7 a signal is a reason to look, not a prediction", z)); z += 1
    v.append(container("chartReason", *body(*reason), z, {
        "visualType": "barChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", WLC, "primary_reason", "Reason")]},
                                 "Series": {"projections": [proj("Column", WLC, "severity", "Severity")]},
                                 "Y": {"projections": [proj("Measure", WLC, "Watch-list Cases", "Cases")]}}},
        "objects": {"dataPoint": [{"properties": {"fill": colour(c)}, "selector": value_selector(WLC, "severity", s)}
                                  for s, c in SEVERITY_COLOURS],
                    "labels": props(show=True, color=colour("#06111F"), fontSize=9), **axis_objects()}})); z += 1
    v.append(panel_title("movesTitle", *moves[:3], "Watch-list movement by effective date",
                         "Opened and Closed events (count of event rows) \u00b7 an event trend, NOT a snapshot measure", z)); z += 1
    v.append(container("chartMoves", *body(*moves), z, {
        "visualType": "columnChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", WLE, "effective_date", "Effective date")]},
                                 "Series": {"projections": [proj("Column", WLE, "event_type", "Event")]},
                                 "Y": {"projections": [count_proj(WLE, "watchlist_event_id", "Events")]}},
                  "sortDefinition": {"sort": [{"field": field("Column", WLE, "effective_date"), "direction": "Ascending"}]}},
        "objects": {"dataPoint": [{"properties": {"fill": colour(GOLD)}, "selector": value_selector(WLE, "event_type", "Opened")},
                                  {"properties": {"fill": colour(TEAL)}, "selector": value_selector(WLE, "event_type", "Closed")}],
                    **axis_objects()}})); z += 1
    v.append(panel_title("typesTitle", *types[:3], "Coaching actions by type",
                         "Count of completed actions (rows) \u00b7 a case can have several", z)); z += 1
    v.append(container("chartActionTypes", *body(*types), z, {
        "visualType": "clusteredBarChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", COACH, "action_type", "Action")]},
                                 "Y": {"projections": [count_proj(COACH, "coaching_action_id", "Actions")]}}},
        "objects": {"dataPoint": props(fill=colour(TEAL)),
                    "labels": props(show=True, color=colour(CREAM), fontSize=9), **axis_objects()}})); z += 1
    v.append(panel_title("firstTitle", *first[:3], "Days from opening to first action",
                         "Actioned cases only; cases with no action are in the table, never counted as 0 days", z)); z += 1
    v.append(container("chartFirstAction", *body(*first), z, {
        "visualType": "columnChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", WLC, "days_to_first_action", "Days to first action")]},
                                 "Y": {"projections": [proj("Measure", WLC, "Watch-list Cases", "Cases")]}},
                  "sortDefinition": {"sort": [{"field": field("Column", WLC, "days_to_first_action"), "direction": "Ascending"}]}},
        "objects": {"dataPoint": props(fill=colour(GOLD)),
                    "labels": props(show=True, color=colour("#06111F"), fontSize=9),
                    **axis_objects("Days", categorical=True)},
    })); z += 1
    v[-1]["filterConfig"] = {"filters": [number_filter("onlyActioned", WLC, "has_action", 1)]}
    v.append(panel_title("unactTitle", *unact[:3], "Unactioned cases: age, state and closure",
                         "has_action = 0 \u00b7 right-click a row \u2192 Drill through \u2192 Trainee 360", z)); z += 1
    v.append(container("tableUnactioned", *body(*unact), z, {
        "visualType": "tableEx",
        "query": {"queryState": {"Values": {"projections": [
            proj("Column", ENROL, "enrolment_id", "Enrolment"), proj("Column", WLC, "watchlist_case_id", "Case"),
            proj("Column", COHORT, "cohort_name", "Cohort"), proj("Column", WLC, "days_open", "Days open"),
            proj("Column", WLC, "case_status_as_of_snapshot", "State"), proj("Column", WLC, "closure_reason", "Closure")]}},
            "sortDefinition": {"sort": [{"field": field("Column", WLC, "days_open"), "direction": "Descending"}]}},
        "objects": {"columnHeaders": props(wordWrap=True)}})); z += 1
    v[-1]["filterConfig"] = {"filters": [number_filter("onlyUnactioned", WLC, "has_action", 0)]}

    v += nav_decor(key, 100) + nav_buttons(pid, 3000)
    charts = ["chartReason", "chartMoves", "chartActionTypes", "chartFirstAction", "tableUnactioned"]
    svg = page_svg(key, frames=frames + [reason, moves, types, first, unact], tiles=tiles, tracks=[(X0, 120, 540, 52)])
    return {"id": pid, "key": key, "display": "Coaching & Watch List", "svg": svg, "visuals": v,
            "interactions": no_filter_on(charts, [k[0] for k in kpis])}


# ------------------------------------------------------------- F. Certification & Readiness (BI-02)
def readiness_page() -> dict:
    pid, key = READY_P, "readiness"
    v = header(pid, key, "CERTIFICATION & READINESS · COMPLETED ENROLMENTS · SNAPSHOT 2 NOV 2026", "Certification & Readiness",
               note="Readiness \u2260 deployment \u00b7 fictional internal certifications")
    z = 1100
    kpis = [("kpiAttempts", "ATTEMPTS", CATT, "Certification Attempts", "Attempt rows, incl. retakes", "doc", TEAL),
            ("kpiCandidatePass", "CANDIDATE PASS RATE", CATT, "Certification Candidate Pass Rate",
             "Passed pairs \u00f7 attempted pairs", "check", TEAL),
            ("kpiFirstPass", "FIRST-ATTEMPT PASS", CATT, "First-Attempt Pass Rate", "Attempt 1 passed \u00f7 attempt 1", "star", TEAL),
            ("kpiMandatoryMet", "BOTH MANDATORY MET", CATT, "Mandatory Certifications Met", "Completed enrolments", "cap", TEAL),
            ("kpiApproved", "APPROVED (SNAPSHOT)", RREV, "Ready / Approved (Snapshot)", "Latest review = Approved", "readiness", GOLD),
            ("kpiApprovalRate", "APPROVAL RATE", RREV, "Readiness Approval Rate", "Approved \u00f7 reviewed", "check", GOLD),
            ("kpiReadyCoverage", "READINESS COVERAGE", RREV, "Readiness Coverage", "Approved \u00f7 all completed", "users", GOLD)]
    kv, frames, tiles, z = kpi_row(kpis, 196, 150, z, gap=12)
    v += kv
    third = (SPAN - 32) // 3
    certs = (X0, 362, third, 330)
    tries = (X0 + third + 16, 362, third, 330)
    pops = (X0 + 2 * (third + 16), 362, SPAN - 2 * (third + 16), 330)
    decision = (X0, 708, third, 332)
    reasons = (X0 + third + 16, 708, third, 332)
    table = (X0 + 2 * (third + 16), 708, SPAN - 2 * (third + 16), 332)

    v.append(panel_title("certsTitle", *certs[:3], "Candidate pass rate by certification",
                         "Pairs that passed on any attempt \u00f7 pairs attempted; not-attempted excluded", z)); z += 1
    v.append(container("chartCertPass", *body(*certs), z, {
        "visualType": "clusteredBarChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", CERT, "certification_name", "Certification")]},
                                 "Series": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]},
                                 "Y": {"projections": [proj("Measure", CATT, "Certification Candidate Pass Rate", "Candidate pass rate")]}}},
        "objects": {"dataPoint": cohort_colour_points(),
                    "labels": props(show=True, color=colour(CREAM), fontSize=9, labelPrecision=1), **axis_objects()}})); z += 1
    v.append(panel_title("triesTitle", *tries[:3], "Attempts by attempt number and result",
                         "Attempts, not people \u00b7 attempt 2 = retake (maximum 2)", z)); z += 1
    v.append(container("chartAttempts", *body(*tries), z, {
        "visualType": "clusteredColumnChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", CATT, "attempt_number", "Attempt")]},
                                 "Series": {"projections": [proj("Column", CATT, "result", "Result")]},
                                 "Y": {"projections": [proj("Measure", CATT, "Certification Attempts", "Attempts")]}},
                  "sortDefinition": {"sort": [{"field": field("Column", CATT, "attempt_number"), "direction": "Ascending"}]}},
        "objects": {"dataPoint": [{"properties": {"fill": colour(TEAL)}, "selector": value_selector(CATT, "result", "Passed")},
                                  {"properties": {"fill": colour(CORAL)}, "selector": value_selector(CATT, "result", "Failed")}],
                    "labels": props(show=True, color=colour(CREAM), fontSize=9), **axis_objects("Attempt", categorical=True)}})); z += 1
    v.append(panel_title("popsTitle", *pops[:3], "Populations outside the rates",
                         "Different populations: never add these together", z)); z += 1
    v.append(container("cardPopulations", *body(*pops), z, {
        "visualType": "multiRowCard",
        "query": {"queryState": {"Values": {"projections": [
            proj("Measure", CATT, "Completers With No Certification Attempt", "Completers with no certification attempt"),
            proj("Measure", CATT, "Unattempted Certification Opportunities", "Mandatory certifications not attempted (completer \u00d7 certification)"),
            proj("Measure", RREV, "Unreviewed Completers", "Completers not yet reviewed (not deferred, not failed)"),
            proj("Measure", WLC, "Unactioned Watch-list Cases", "Watch-list cases with no completed action")]}}}})); z += 1
    v.append(panel_title("decisionTitle", *decision[:3], "Latest readiness decision by cohort",
                         "Latest review per enrolment (count of latest reviews) \u00b7 unreviewed completers are in the table", z)); z += 1
    v.append(container("chartDecision", *body(*decision), z, {
        "visualType": "barChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", COHORT, "cohort_name", "Cohort")]},
                                 "Series": {"projections": [proj("Column", RREV, "decision", "Decision")]},
                                 "Y": {"projections": [count_proj(RREV, "readiness_review_id", "Enrolments")]}},
                  "sortDefinition": by_cohort_sort()},
        "objects": {"dataPoint": [{"properties": {"fill": colour(TEAL)}, "selector": value_selector(RREV, "decision", "Approved")},
                                  {"properties": {"fill": colour(GOLD)}, "selector": value_selector(RREV, "decision", "Deferred")}],
                    "labels": props(show=True, color=colour("#06111F"), fontSize=9), **axis_objects()}})); z += 1
    v[-1]["filterConfig"] = {"filters": [number_filter("onlyLatest", RREV, "is_latest_review", 1)]}
    v.append(panel_title("reasonsTitle", *reasons[:3], "Why deferred (latest review)",
                         "Deferred enrolments by reason \u00b7 evidence gates as they stood at that review", z)); z += 1
    v.append(container("chartDeferral", *body(*reasons), z, {
        "visualType": "clusteredBarChart",
        "query": {"queryState": {"Category": {"projections": [proj("Column", RREV, "decision_reason_code", "Reason")]},
                                 "Y": {"projections": [count_proj(RREV, "readiness_review_id", "Enrolments")]}}},
        "objects": {"dataPoint": props(fill=colour(GOLD)),
                    "labels": props(show=True, color=colour(CREAM), fontSize=9), **axis_objects()}})); z += 1
    v[-1]["filterConfig"] = {"filters": [number_filter("onlyLatestR", RREV, "is_latest_review", 1),
                                         category_filter("onlyDeferred", RREV, "decision", "Deferred")]}
    v.append(panel_title("readyTableTitle", *table[:3], "Readiness by cohort: approval rate vs coverage",
                         "Approval rate \u00f7 reviewed completers; coverage \u00f7 ALL completers. Blank = no completers.", z)); z += 1
    v.append(container("tableReadiness", *body(*table), z, {
        "visualType": "tableEx",
        "query": {"queryState": {"Values": {"projections": [
            proj("Column", COHORT, "cohort_name", "Cohort"),
            proj("Measure", RREV, "Reviewed for Readiness", "Reviewed"),
            proj("Measure", RREV, "Unreviewed Completers", "Not reviewed"),
            proj("Measure", RREV, "Ready / Approved (Snapshot)", "Approved"),
            proj("Measure", RREV, "Readiness Approval Rate", "Approval rate"),
            proj("Measure", RREV, "Readiness Coverage", "Coverage")]}},
            "sortDefinition": by_cohort_sort()},
        "objects": {"total": props(totals=True), "columnHeaders": props(wordWrap=True)}})); z += 1

    v += nav_decor(key, 100) + nav_buttons(pid, 3000)
    charts = ["chartCertPass", "chartAttempts", "chartDecision", "chartDeferral", "tableReadiness"]
    svg = page_svg(key, frames=frames + [certs, tries, pops, decision, reasons, table], tiles=tiles,
                   tracks=[(X0, 120, 540, 52)])
    return {"id": pid, "key": key, "display": "Certification & Readiness", "svg": svg, "visuals": v,
            "interactions": no_filter_on(charts, [k[0] for k in kpis] + ["cardPopulations"])}


def ux03_pages() -> list[dict]:
    return [cohort_page(), skills_page(), attendance_page(), coaching_page(), readiness_page(), trainee_page()]


def ux03_bookmarks() -> list[dict]:
    """One 'Clear filters' bookmark per UX-03 page: clears that page's slicers only."""
    out = []
    for pid, (key, slicers) in UX03_SLICERS.items():
        out.append(bookmark(f"bmClearFilters_{key}", f"Clear filters · {key}", [], [],
                            {n: "slicer" for n in slicers}, data_targets=slicers, page=pid))
    return out


def main() -> None:
    DESIGN.mkdir(parents=True, exist_ok=True)
    def background(name: str, svg: str) -> str:
        (DESIGN / f"{name}-background.svg").write_text(svg, encoding="utf-8", newline="\n")
        BACKGROUNDS.append(f"{name}-background.png")
        return f"{name}-background.png"

    pages = {}   # page id -> (page.json, visuals)
    overview = overview_visuals()
    pages[OVERVIEW] = (page_json(OVERVIEW, "Overview", background("overview", overview_svg()),
                                 overview_interactions(overview)), overview)
    for spec in ux03_pages():                      # Cohort Intelligence, Skills, Attendance, Trainee 360
        pages[spec["id"]] = (page_json(spec["id"], spec["display"], background(spec["key"], spec["svg"]),
                                       spec.get("interactions"), extra=spec.get("extra")), spec["visuals"])
    about = about_visuals()
    pages[ABOUT] = (page_json(ABOUT, "About", background("about", about_svg())), about)
    for pid, (pj, vis) in pages.items():
        write_page(pid, pj, vis)
    write_json(DEFINITION / "pages" / "pages.json",
               {"$schema": S_PAGES, "pageOrder": list(pages), "activePageName": OVERVIEW})

    bm_dir = DEFINITION / "bookmarks"
    if bm_dir.exists():
        shutil.rmtree(bm_dir)
    types = {v["name"]: v["visual"]["visualType"] for v in overview}
    marks = bookmarks(types) + ux03_bookmarks()
    for b in marks:
        write_json(bm_dir / f"{b['name']}.bookmark.json", b)
    write_json(bm_dir / "bookmarks.json", {"$schema": S_BOOKMARKS, "items": [{"name": b["name"]} for b in marks]})

    register_resources()
    for pid, (pj, vis) in pages.items():
        print(f"  {pj['displayName']:<34} {len(vis):>3} visuals")
    print(f"{len(marks)} bookmarks · backgrounds in powerbi/design/*.svg - render them to PNG before opening Desktop.")


if __name__ == "__main__":
    main()
