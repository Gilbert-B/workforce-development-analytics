"""Add the Report 02 and Report 03 tables, relationships and measures to the SHARED model (TMDL).

WHY A GENERATOR
    Hand-writing TMDL for ~200 columns is error-prone. This script reads each
    view's columns straight from SQL Server (sys.columns), so the model always
    matches the SQL contract, and it writes the measures from one readable list.
    Report 01's tables, relationships and measures are never touched: only the
    tables listed in OWNED are (re)written, and only relationships that touch an
    owned table are replaced. `check_model_additive.py` proves it.

USAGE (repository root, Power BI Desktop CLOSED, database loaded)
    python powerbi/tools/build_model.py --server localhost
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))
import load_to_sql as db  # noqa: E402

MODEL = REPO / "powerbi" / "workforcedevelopmentanalytics.SemanticModel" / "definition"
NS = uuid.UUID("6b1f9c2e-6c0a-4b4e-9d61-3f0f6f1c2a10")      # fixed namespace -> stable lineage tags

# ---------------------------------------------------------------- tables this script owns
# view -> {"sort": {column: sort_by_column}, "hidden": [...]}
OWNED = {
    # Report 02 (Build 03)
    "dim_agent": {},
    "dim_ops_queue": {},
    "fact_payment_case": {"sort": {"tenure_band": "tenure_band_order"}, "hidden": ["tenure_band_order"]},
    "fact_qa_review": {"sort": {"tenure_band": "tenure_band_order"}, "hidden": ["tenure_band_order"]},
    "fact_qa_check": {"sort": {"tenure_band": "tenure_band_order"}, "hidden": ["tenure_band_order"]},
    "fact_agent_day": {"sort": {"tenure_band": "tenure_band_order"}, "hidden": ["tenure_band_order"]},
    # Report 03 (Build 04)
    "dim_graduate": {"sort": {"competency_band": "competency_band_order", "proficiency_status": "proficiency_status_order"},
                     "hidden": ["competency_band_order", "proficiency_status_order"]},
    "fact_outcome_window": {"sort": {"window_label": "window_order"}, "hidden": ["window_order"]},
}

# (many table, many column) -> (one table, one column); all single-direction, active
RELATIONSHIPS = [
    ("fact_payment_case", "agent_id", "dim_agent", "agent_id"),
    ("fact_qa_review", "agent_id", "dim_agent", "agent_id"),
    ("fact_qa_check", "agent_id", "dim_agent", "agent_id"),
    ("fact_agent_day", "agent_id", "dim_agent", "agent_id"),
    ("fact_payment_case", "queue_id", "dim_ops_queue", "queue_id"),
    ("fact_qa_review", "queue_id", "dim_ops_queue", "queue_id"),
    ("fact_qa_check", "queue_id", "dim_ops_queue", "queue_id"),
    ("fact_payment_case", "received_date", "dim_date", "date"),
    ("fact_qa_review", "reviewed_date", "dim_date", "date"),
    ("fact_qa_check", "reviewed_date", "dim_date", "date"),
    ("fact_agent_day", "work_date", "dim_date", "date"),
    # Build 04: training attributes filter the outcome windows and the case-level facts
    ("fact_outcome_window", "agent_id", "dim_graduate", "agent_id"),
    ("fact_payment_case", "agent_id", "dim_graduate", "agent_id"),
    ("fact_agent_day", "agent_id", "dim_graduate", "agent_id"),
]

PC, QA, QC, AG, AD, GR, OW = ("'rpt fact_payment_case'", "'rpt fact_qa_review'", "'rpt fact_qa_check'",
                              "'rpt dim_agent'", "'rpt fact_agent_day'", "'rpt dim_graduate'", "'rpt fact_outcome_window'")
# tenured benchmark: drop every agent-side filter (agent, graduate attributes, tenure band), keep the rest
BENCH = (f"REMOVEFILTERS ( 'rpt dim_agent' ), REMOVEFILTERS ( 'rpt dim_graduate' ),\n"
         f"    REMOVEFILTERS ( {{t}}[tenure_band], {{t}}[tenure_band_order] ),\n"
         f"    {{t}}[tenure_band] = \"Tenured\"")

# home view -> [(name, DAX, formatString, displayFolder)]
MEASURES = {
    "fact_payment_case": [
        ("Cases Received", f"COALESCE ( COUNTROWS ( {PC} ), 0 )", "#,0", "Operations"),
        ("Cases Resolved", f"COALESCE ( CALCULATE ( COUNTROWS ( {PC} ), KEEPFILTERS ( {PC}[is_open] = 0 ) ), 0 )",
         "#,0", "Operations"),
        ("Open Cases (Snapshot)", f"COALESCE ( CALCULATE ( COUNTROWS ( {PC} ), KEEPFILTERS ( {PC}[is_open] = 1 ) ), 0 )",
         "#,0", "Operations"),
        ("Overdue Open Cases (Snapshot)",
         f"COALESCE ( CALCULATE ( COUNTROWS ( {PC} ), KEEPFILTERS ( {PC}[is_overdue_open] = 1 ) ), 0 )",
         "#,0", "Operations"),
        ("SLA Met %",
         f"-- sla_met is blank for open cases; COUNT skips blanks, so the denominator is resolved cases only\n"
         f"DIVIDE ( SUM ( {PC}[sla_met] ), COUNT ( {PC}[sla_met] ) )", "0.0%", "Operations"),
        ("SLA Met % (Tenured Benchmark)",
         f"-- tenured agents' SLA met % in the same queue / date / priority context\n"
         f"CALCULATE ( [SLA Met %],\n    {BENCH.format(t=PC)} )", "0.0%", "Operations"),
        ("SLA Gap vs Tenured (pts)", "([SLA Met %] - [SLA Met % (Tenured Benchmark)]) * 100", "+0.0;-0.0;0.0",
         "Operations"),
        ("First-Time-Right %", f"DIVIDE ( SUM ( {PC}[first_time_right] ), [Cases Resolved] )", "0.0%", "Operations"),
        ("First-Time-Right % (Tenured Benchmark)",
         f"CALCULATE ( [First-Time-Right %],\n    {BENCH.format(t=PC)} )", "0.0%", "Operations"),
        ("Reworked Cases", f"COALESCE ( CALCULATE ( COUNTROWS ( {PC} ), KEEPFILTERS ( {PC}[has_rework] = 1 ) ), 0 )",
         "#,0", "Operations"),
        ("Avg Resolution Hours", f"AVERAGE ( {PC}[final_resolution_hours] )", "0.0", "Operations"),
        ("Median Resolution Hours", f"MEDIAN ( {PC}[final_resolution_hours] )", "0.0", "Operations"),
        ("QA Sample Rate %",
         f"-- share of RESOLVED cases picked for QA (both sides dated by received date)\n"
         f"DIVIDE ( CALCULATE ( COUNTROWS ( {PC} ), KEEPFILTERS ( {PC}[qa_sampled] = 1 ) ), [Cases Resolved] )",
         "0.0%", "Quality"),
    ],
    "fact_qa_review": [
        ("QA Reviews", f"COALESCE ( COUNTROWS ( {QA} ), 0 )", "#,0", "Quality"),
        ("QA Pass %", f"DIVIDE ( SUM ( {QA}[passed] ), COUNTROWS ( {QA} ) )", "0.0%", "Quality"),
        ("QA Pass % (Tenured Benchmark)", f"CALCULATE ( [QA Pass %],\n    {BENCH.format(t=QA)} )", "0.0%", "Quality"),
        ("Avg QA Score", f"AVERAGE ( {QA}[score] )", "0.0", "Quality"),
        ("QA Critical Error %", f"DIVIDE ( SUM ( {QA}[has_critical_error] ), COUNTROWS ( {QA} ) )", "0.0%", "Quality"),
    ],
    "fact_qa_check": [
        ("Checklist Item Fail %",
         f"DIVIDE ( CALCULATE ( COUNTROWS ( {QC} ), KEEPFILTERS ( {QC}[passed] = 0 ) ), COUNTROWS ( {QC} ) )",
         "0.00%", "Quality"),
    ],
    "dim_agent": [
        ("Active Agents (Snapshot)",
         f"COALESCE ( CALCULATE ( COUNTROWS ( {AG} ), KEEPFILTERS ( {AG}[is_active_at_snapshot] = 1 ) ), 0 )",
         "#,0", "Agents"),
        ("Graduate Agents (Snapshot)",
         f"COALESCE ( CALCULATE ( COUNTROWS ( {AG} ), KEEPFILTERS ( {AG}[is_active_at_snapshot] = 1 ),\n"
         f"                       KEEPFILTERS ( {AG}[agent_type] = \"Graduate\" ) ), 0 )", "#,0", "Agents"),
        ("Agents Exited", f"COALESCE ( CALCULATE ( COUNTROWS ( {AG} ), KEEPFILTERS ( NOT ISBLANK ( {AG}[exit_date] ) ) ), 0 )",
         "#,0", "Agents"),
        ("Agent Title",
         f"-- Agent 360 header: one agent in context, else a prompt\n"
         f"IF ( HASONEVALUE ( {AG}[agent_id] ),\n"
         f"    SELECTEDVALUE ( {AG}[agent_name] ) & \"  ·  \" & SELECTEDVALUE ( {AG}[agent_id] ),\n"
         f"    \"Drill through from any agent to open their profile\" )", None, "Agents"),
        ("Agent Profile Label",
         f"IF ( HASONEVALUE ( {AG}[agent_id] ),\n"
         f"    VAR T = SELECTEDVALUE ( {AG}[agent_type] )\n"
         f"    VAR Started = FORMAT ( SELECTEDVALUE ( {AG}[start_date] ), \"d mmm yyyy\" )\n"
         f"    VAR ExitDate = SELECTEDVALUE ( {AG}[exit_date] )\n"
         f"    RETURN\n"
         f"        T & \" agent · \" & SELECTEDVALUE ( {AG}[team_name] ) & \" · \" & SELECTEDVALUE ( {AG}[primary_queue_name] )\n"
         f"        & \" · started \" & Started\n"
         f"        & IF ( T = \"Graduate\", \" · cohort \" & SELECTEDVALUE ( {AG}[cohort_id] ), \"\" )\n"
         f"        & IF ( ISBLANK ( ExitDate ), \"\", \" · left \" & FORMAT ( ExitDate, \"d mmm yyyy\" ) ),\n"
         f"    \"\" )", None, "Agents"),
    ],
    "dim_graduate": [
        ("Graduates Deployed", f"COALESCE ( COUNTROWS ( {GR} ), 0 )", "#,0", "Outcomes"),
        ("90-Day Retention %",
         f"-- graduates still employed at day 90 / graduates who have reached day 90 (observed periods only)\n"
         f"DIVIDE ( SUM ( {GR}[retained_90_days] ), COUNT ( {GR}[retained_90_days] ) )", "0.0%", "Outcomes"),
        ("Graduates Left Before Day 90",
         f"COALESCE ( CALCULATE ( COUNTROWS ( {GR} ), KEEPFILTERS ( {GR}[retained_90_days] = 0 ) ), 0 )", "#,0", "Outcomes"),
        ("Proficient by Day 90 %",
         f"-- of graduates still employed at day 90: reached the proficiency standard in any window\n"
         f"DIVIDE (\n"
         f"    CALCULATE ( COUNTROWS ( {GR} ), KEEPFILTERS ( {GR}[retained_90_days] = 1 ),\n"
         f"                KEEPFILTERS ( NOT ISBLANK ( {GR}[days_to_proficiency] ) ) ),\n"
         f"    CALCULATE ( COUNTROWS ( {GR} ), KEEPFILTERS ( {GR}[retained_90_days] = 1 ) ) )", "0.0%", "Outcomes"),
        ("Proficient by Day 30 %",
         f"DIVIDE (\n"
         f"    CALCULATE ( COUNTROWS ( {GR} ), KEEPFILTERS ( {GR}[days_to_proficiency] = 30 ) ),\n"
         f"    CALCULATE ( COUNTROWS ( {GR} ), KEEPFILTERS ( {GR}[proficiency_status] <> \"Too early to tell\" ) ) )",
         "0.0%", "Outcomes"),
        ("Avg Days to Proficiency",
         f"-- proficient graduates only; measured in 30-day windows, so 30 / 60 / 90\n"
         f"AVERAGE ( {GR}[days_to_proficiency] )", "0", "Outcomes"),
        ("Avg Final Competency", f"AVERAGE ( {GR}[final_competency_score] )", "0.0", "Outcomes"),
        ("Certified First Attempt %",
         f"DIVIDE ( CALCULATE ( COUNTROWS ( {GR} ), KEEPFILTERS ( {GR}[certified_first_attempt] = \"Yes\" ) ),\n"
         f"         COUNTROWS ( {GR} ) )", "0.0%", "Outcomes"),
        ("Graduate Title",
         f"IF ( HASONEVALUE ( {GR}[agent_id] ),\n"
         f"    SELECTEDVALUE ( {GR}[graduate_name] ) & \"  ·  \" & SELECTEDVALUE ( {GR}[cohort_name] ),\n"
         f"    \"Drill through from any graduate to open their journey\" )", None, "Outcomes"),
        ("Graduate Journey Label",
         f"IF ( HASONEVALUE ( {GR}[agent_id] ),\n"
         f"    \"Final competency \" & FORMAT ( SELECTEDVALUE ( {GR}[final_competency_score] ), \"0.0\" )\n"
         f"    & \" (\" & SELECTEDVALUE ( {GR}[competency_band] ) & \")\"\n"
         f"    & \" · certified first attempt: \" & SELECTEDVALUE ( {GR}[certified_first_attempt] )\n"
         f"    & \" · watch list: \" & SELECTEDVALUE ( {GR}[watchlisted_in_training] )\n"
         f"    & \" · deployed \" & FORMAT ( SELECTEDVALUE ( {GR}[deployment_date] ), \"d mmm yyyy\" )\n"
         f"    & \" · \" & SELECTEDVALUE ( {GR}[proficiency_status] ),\n"
         f"    \"\" )", None, "Outcomes"),
    ],
    "fact_outcome_window": [
        ("Complete Windows", f"COALESCE ( SUM ( {OW}[is_complete] ), 0 )", "#,0", "Outcomes"),
        ("Window SLA Met %",
         f"-- complete windows only: metrics of incomplete windows are blank by design\n"
         f"DIVIDE ( SUM ( {OW}[sla_met_cases] ), SUM ( {OW}[cases_resolved] ) )", "0.0%", "Outcomes"),
        ("Window First-Time-Right %", f"DIVIDE ( SUM ( {OW}[first_time_right_cases] ), SUM ( {OW}[cases_resolved] ) )",
         "0.0%", "Outcomes"),
        ("Window QA Pass %", f"DIVIDE ( SUM ( {OW}[qa_passed] ), SUM ( {OW}[qa_reviews] ) )", "0.0%", "Outcomes"),
        ("Window Resolved per Agent-Day", f"DIVIDE ( SUM ( {OW}[resolved_on_agent_days] ), SUM ( {OW}[agent_days] ) )",
         "0.00", "Outcomes"),
        ("Window Proficient %", f"DIVIDE ( SUM ( {OW}[is_proficient] ), COUNT ( {OW}[is_proficient] ) )", "0.0%", "Outcomes"),
        ("Window SLA Gap vs Tenured (pts)", "([Window SLA Met %] - [SLA Met % (Tenured Benchmark)]) * 100",
         "+0.0;-0.0;0.0", "Outcomes"),
        ("Window FTR Gap vs Tenured (pts)",
         "([Window First-Time-Right %] - [First-Time-Right % (Tenured Benchmark)]) * 100", "+0.0;-0.0;0.0", "Outcomes"),
    ],
    "fact_agent_day": [
        ("Agent-Days Worked", f"COALESCE ( COUNTROWS ( {AD} ), 0 )", "#,0", "Agents"),
        ("Resolved per Agent-Day", f"DIVIDE ( SUM ( {AD}[cases_resolved] ), COUNTROWS ( {AD} ) )", "0.00", "Agents"),
    ],
}

SQL_TYPES = {  # SQL Server type -> (TMDL dataType, formatString, date-only?)
    "varchar": ("string", None, False), "nvarchar": ("string", None, False), "char": ("string", None, False),
    "nchar": ("string", None, False),
    "int": ("int64", "0", False), "bigint": ("int64", "0", False), "smallint": ("int64", "0", False),
    "tinyint": ("int64", "0", False),
    "bit": ("boolean", None, False),
    "date": ("dateTime", "Long Date", True), "datetime2": ("dateTime", "General Date", False),
    "datetime": ("dateTime", "General Date", False),
    "decimal": ("double", "0.00", False), "numeric": ("double", "0.00", False), "float": ("double", "0.00", False),
}


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NS, "|".join(parts)))


def q(name: str) -> str:
    """TMDL name quoting: plain if simple, else single quotes."""
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else "'" + name.replace("'", "''") + "'"


def view_columns(conn, view: str) -> list[tuple[str, str]]:
    rows = conn.cursor().execute(
        "SELECT c.name, t.name FROM sys.columns AS c JOIN sys.types AS t ON t.user_type_id = c.user_type_id "
        "WHERE c.object_id = OBJECT_ID(?) ORDER BY c.column_id", f"rpt.{view}").fetchall()
    if not rows:
        raise SystemExit(f"rpt.{view} not found: load the database first")
    return [(r[0], r[1]) for r in rows]


def table_tmdl(view: str, columns, spec: dict) -> str:
    name = f"rpt {view}"
    out = [f"table {q(name)}", f"\tlineageTag: {tag(name)}", ""]
    for m_name, dax, fmt, folder in MEASURES.get(view, []):
        lines = dax.splitlines()
        if len(lines) == 1:
            out.append(f"\tmeasure {q(m_name)} = {dax}")
        else:
            out.append(f"\tmeasure {q(m_name)} = ```")
            out += [f"\t\t\t{line}" for line in lines]
            out.append("\t\t\t```")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out.append(f"\t\tdisplayFolder: {folder}")
        out.append(f"\t\tlineageTag: {tag(name, 'measure', m_name)}")
        out.append("")
    for col, sql_type in columns:
        dtype, fmt, date_only = SQL_TYPES[sql_type]
        if col.endswith("_month"):
            fmt = "mmm yyyy"                         # month-start dates: axis shows "Aug 2026"
        out.append(f"\tcolumn {q(col)}")
        out.append(f"\t\tdataType: {dtype}")
        if col in spec.get("hidden", []):
            out.append("\t\tisHidden")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out.append(f"\t\tlineageTag: {tag(name, 'column', col)}")
        out.append("\t\tsummarizeBy: none")
        out.append(f"\t\tsourceColumn: {col}")
        if col in spec.get("sort", {}):
            out.append(f"\t\tsortByColumn: {spec['sort'][col]}")
        out.append("")
        out.append("\t\tannotation SummarizationSetBy = Automatic")
        if date_only:
            out.append("")
            out.append("\t\tannotation UnderlyingDateTimeDataType = Date")
        out.append("")
    step = f"rpt_{view}"
    out += [f"\tpartition {q(name)} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
            '\t\t\t\t    Source = Sql.Databases("localhost"),',
            '\t\t\t\t    WorkforceDevAnalytics = Source{[Name="WorkforceDevAnalytics"]}[Data],',
            f'\t\t\t\t    {step} = WorkforceDevAnalytics{{[Schema="rpt",Item="{view}"]}}[Data]',
            "\t\t\t\tin", f"\t\t\t\t    {step}", "", "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(out)


def write_relationships() -> None:
    path = MODEL / "relationships.tmdl"
    text = path.read_text(encoding="utf-8")
    owned = {f"'rpt {v}'" for v in OWNED}
    blocks = [b for b in re.split(r"\n(?=relationship )", text.strip()) if b.strip()]
    keep = [b for b in blocks if not any(o + "." in b for o in owned)]
    new = []
    for m_tab, m_col, o_tab, o_col in RELATIONSHIPS:
        new.append(f"relationship {tag('rel', m_tab, m_col, o_tab, o_col)}\n"
                   f"\tfromColumn: 'rpt {m_tab}'.{m_col}\n\ttoColumn: 'rpt {o_tab}'.{o_col}")
    path.write_text("\n\n".join(keep + new) + "\n\n", encoding="utf-8", newline="\n")


def write_model_refs() -> None:
    path = MODEL / "model.tmdl"
    text = path.read_text(encoding="utf-8")
    for v in OWNED:
        ref = f"ref table 'rpt {v}'"
        if ref not in text:
            text = _insert_ref(text, ref)
        m = re.search(r"annotation PBI_QueryOrder = (\[.*\])", text)
        order = json.loads(m.group(1))
        if f"rpt {v}" not in order:
            order.append(f"rpt {v}")
            text = text.replace(m.group(1), "[" + ",".join(f'"{o}"' for o in order) + "]")
    path.write_text(text, encoding="utf-8", newline="\n")


def _insert_ref(text: str, ref: str) -> str:
    """Add a 'ref table' line after the last existing one."""
    last = list(re.finditer(r"^ref table [^\n]+$", text, flags=re.M))[-1]
    return text[:last.end()] + "\n" + ref + text[last.end():]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", default=os.environ.get("WDA_SQL_SERVER"))
    args = parser.parse_args()
    if not args.server:
        parser.error("give --server or set WDA_SQL_SERVER")
    conn = db.connect(args.server, db.DATABASE)
    for view, spec in OWNED.items():
        cols = view_columns(conn, view)
        (MODEL / "tables" / f"rpt {view}.tmdl").write_text(table_tmdl(view, cols, spec), encoding="utf-8", newline="\n")
        print(f"  rpt {view:<22} {len(cols):>3} columns  {len(MEASURES.get(view, [])):>2} measures")
    write_relationships()
    write_model_refs()
    print(f"Model updated: {len(OWNED)} tables, {len(RELATIONSHIPS)} relationships, "
          f"{sum(len(m) for m in MEASURES.values())} measures (Report 01 objects untouched)")


if __name__ == "__main__":
    main()
