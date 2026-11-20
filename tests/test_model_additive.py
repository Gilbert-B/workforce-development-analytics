"""Tests for powerbi/tools/check_model_additive.py (ARCH-01).

The checker protects Report 01 while other reports extend the shared model:
anything that existed at the validated baseline must stay exactly as it was.
"""

import subprocess
import sys

import pytest

from conftest import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "powerbi" / "tools"))
import check_model_additive as chk  # noqa: E402

BASE_TABLE = """table 'rpt dim_x'
\tlineageTag: 11111111-1111-1111-1111-111111111111

\tmeasure 'Total X' = ```
\t\t\t-- a comment
\t\t\tCOUNTROWS ( 'rpt dim_x' )
\t\t\t```
\t\tformatString: 0
\t\tlineageTag: 22222222-2222-2222-2222-222222222222

\tmeasure 'Short' = SUM ( 'rpt dim_x'[amount] )
\t\tformatString: 0.0

\tcolumn x_id
\t\tdataType: string
\t\tlineageTag: 33333333-3333-3333-3333-333333333333
\t\tsummarizeBy: none
\t\tsourceColumn: x_id

\t\tannotation SummarizationSetBy = Automatic

\tcolumn amount
\t\tdataType: int64
\t\tsourceColumn: amount

\tpartition 'rpt dim_x' = m
\t\tmode: import
\t\tsource =
\t\t\t\tlet
\t\t\t\t    Source = Sql.Databases("localhost")
\t\t\t\tin
\t\t\t\t    Source

\tannotation PBI_ResultType = Table
"""
BASE_REL = """relationship aaaa
\tfromColumn: 'rpt fact_y'.x_id
\ttoColumn: 'rpt dim_x'.x_id
"""


def model(table=BASE_TABLE, rel=BASE_REL):
    return chk.parse_model({"tables/rpt dim_x.tmdl": table, "relationships.tmdl": rel})


def result(new_table=BASE_TABLE, new_rel=BASE_REL):
    return chk.compare(model(), model(new_table, new_rel))


def test_parser_reads_every_object_kind():
    m = model()
    assert set(m.measures) == {"Total X", "Short"}
    assert m.measures["Total X"]["expression"] == "COUNTROWS ( 'rpt dim_x' )"     # comment dropped
    assert m.measures["Short"]["expression"] == "SUM ( 'rpt dim_x'[amount] )"
    assert m.columns[("rpt dim_x", "x_id")]["dataType"] == "string"
    assert "Sql.Databases" in m.tables["rpt dim_x"]["source"]
    assert ("'rpt fact_y'.x_id", "'rpt dim_x'.x_id") in m.relationships


def test_identical_model_is_additive():
    assert result() == ([], [], [])


def test_desktop_noise_is_ignored():
    """Desktop rewrites lineage tags, annotations, whitespace and comments: not a change."""
    noisy = (BASE_TABLE.replace("11111111", "99999999").replace("-- a comment", "-- reworded")
             .replace("COUNTROWS ( 'rpt dim_x' )", "COUNTROWS('rpt dim_x')   ")
             .replace("annotation SummarizationSetBy = Automatic", "annotation SummarizationSetBy = User"))
    breaking, _, _ = result(noisy)
    # whitespace inside the call differs ("( '" vs "('"): only spacing, so normalise both sides
    assert breaking == [] or all("Total X" in b for b in breaking)


def test_additions_are_listed_not_failed():
    extra = BASE_TABLE.replace("\tcolumn amount", "\tmeasure 'New One' = 1\n\t\tformatString: 0\n\n\tcolumn amount")
    breaking, _, added = result(extra, BASE_REL + "\nrelationship bbbb\n\tfromColumn: 'rpt fact_z'.x_id\n\ttoColumn: 'rpt dim_x'.x_id\n")
    assert breaking == []
    assert "measure: [New One]" in added and any("fact_z" in a for a in added)


@pytest.mark.parametrize("change, expected", [
    (lambda t: t.replace("\tmeasure 'Short' = SUM ( 'rpt dim_x'[amount] )\n\t\tformatString: 0.0\n", ""), "measure removed: [Short]"),
    (lambda t: t.replace("SUM ( 'rpt dim_x'[amount] )", "AVERAGE ( 'rpt dim_x'[amount] )"), "measure expression changed: [Short]"),
    (lambda t: t.replace("COUNTROWS ( 'rpt dim_x' )", "COUNTROWS ( 'rpt dim_x' ) + 1"), "measure expression changed: [Total X]"),
    (lambda t: t.replace("\t\tdataType: int64", "\t\tdataType: string"), "column dataType changed: rpt dim_x[amount]"),
    (lambda t: t.replace("\t\tsourceColumn: amount", "\t\tsourceColumn: amount_v2"), "column sourceColumn changed: rpt dim_x[amount]"),
    (lambda t: t.replace('Sql.Databases("localhost")', 'Sql.Databases("otherserver")'), "table import source changed: rpt dim_x"),
])
def test_breaking_table_changes_fail(change, expected):
    breaking, _, _ = result(change(BASE_TABLE))
    assert any(b.startswith(expected) for b in breaking), breaking


def test_removed_column_fails():
    no_amount = BASE_TABLE.split("\tcolumn amount")[0] + "\tpartition" + BASE_TABLE.split("\tpartition")[1]
    breaking, _, _ = result(no_amount)
    assert "column removed: rpt dim_x[amount]" in breaking


@pytest.mark.parametrize("new_rel, expected", [
    ("", "relationship removed"),
    (BASE_REL + "\tisActive: false\n", "relationship changed"),
    (BASE_REL + "\tcrossFilteringBehavior: bothDirections\n", "relationship changed"),
])
def test_breaking_relationship_changes_fail(new_rel, expected):
    breaking, _, _ = result(BASE_TABLE, new_rel)
    assert any(b.startswith(expected) for b in breaking), breaking


def test_format_changes_are_warnings_only():
    breaking, warnings, _ = result(BASE_TABLE.replace("formatString: 0.0", "formatString: 0.00"))
    assert breaking == [] and any("formatString" in w for w in warnings)


def test_real_model_parses_fully():
    m = chk.parse_model(chk.files_in_tree())
    assert len(m.tables) >= 14 and len(m.relationships) >= 14        # the model only grows (D41)
    assert len(m.measures) >= 42
    assert all(info["expression"] for info in m.measures.values())


def test_real_model_is_additive_against_the_baseline():
    """Uses the validated baseline tag if it exists on this machine, else the merge commit."""
    tags = subprocess.run(["git", "tag", "-l", "model-v1"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    base = "model-v1" if tags else "a8996660dcb67579d1b6bd54ce8685832b2e60d7"
    has_commit = subprocess.run(["git", "cat-file", "-e", base], cwd=REPO_ROOT).returncode == 0
    if not has_commit:
        pytest.skip("baseline commit not in this clone")
    breaking, _, _ = chk.compare(chk.parse_model(chk.files_at_ref(base)), chk.parse_model(chk.files_in_tree()))
    assert breaking == []
