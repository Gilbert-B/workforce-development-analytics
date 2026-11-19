"""Tests for the Build 02 generator (no database needed).

Grouped by what they prove:
  reproducibility and Build 01 protection, no look-ahead, business rules,
  negative tests (broken data IS caught), policy from config, storylines.
"""

import copy
import csv
import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean

import pytest

from conftest import REPO_ROOT, read_tables

import generate_build02_data as b02  # noqa: E402  (conftest puts python/ on sys.path)

BUILD01_DIR = REPO_ROOT / "data" / "synthetic"
BUILD02_DIR = BUILD01_DIR / "build02"
CONFIG02 = REPO_ROOT / "config" / "build02_synthetic.toml"


@pytest.fixture(scope="module")
def b1():
    return b02.Build01(b02.read_build01(BUILD01_DIR))


@pytest.fixture(scope="module")
def config02():
    return b02.load_config(CONFIG02)


@pytest.fixture(scope="module")
def tables(b1, config02):
    """The default Build 02 tables, as Python values (dates, None...)."""
    return b02.build_tables(config02, b1, b1.as_of)


@pytest.fixture(scope="module")
def cohort_of():
    with open(BUILD01_DIR / "enrolment.csv", newline="", encoding="utf-8") as f:
        return {r["enrolment_id"]: r["cohort_id"] for r in csv.DictReader(f)}


def truncate_build01(raw: dict, cutoff: datetime) -> dict:
    """Build 01 exactly as it stood at `cutoff`: only records entered by then."""
    out = copy.deepcopy(raw)
    for name in ("enrolment_status_event", "attendance", "assessment"):
        out[name] = [r for r in out[name] if datetime.fromisoformat(r["recorded_at"]) <= cutoff]
    out["data_snapshot"] = [{**out["data_snapshot"][0], "as_of_date": cutoff.date().isoformat()}]
    return out


# ---------------------------------------------------------------- reproducibility

def test_same_inputs_give_identical_files(tmp_path):
    m1 = b02.generate(output_dir=tmp_path / "run1")
    m2 = b02.generate(output_dir=tmp_path / "run2")
    assert m1["files"] == m2["files"]


def test_committed_build02_csvs_match_the_generator(tmp_path):
    """data/synthetic/build02/ in Git must be exactly what the generator produces."""
    b02.generate(output_dir=tmp_path)
    committed = (BUILD02_DIR / "generation_manifest.json").read_text(encoding="utf-8")
    assert committed == (tmp_path / "generation_manifest.json").read_text(encoding="utf-8"), \
        "Re-run python/generate_build02_data.py and commit the result"


def test_build01_files_are_never_modified(tmp_path):
    def fingerprint():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in BUILD01_DIR.glob("*.*")}
    before = fingerprint()
    b02.generate(output_dir=tmp_path)
    assert fingerprint() == before


def test_as_of_comes_from_build01_and_cannot_be_later(b1, config02):
    assert b1.as_of == date(2026, 11, 2)
    with pytest.raises(ValueError):
        b02.build_tables(config02, b1, b1.as_of + timedelta(days=1))


def test_build02_csvs_are_ascii_with_lf_endings():
    for path in BUILD02_DIR.glob("*.csv"):
        raw = path.read_bytes()
        raw.decode("ascii")                       # raises if not plain ASCII
        assert b"\r\n" not in raw, path.name


def test_manifest_is_the_same_with_windows_line_endings(tmp_path):
    crlf = tmp_path / "config_crlf.toml"
    crlf.write_bytes(CONFIG02.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert (b02.generate(CONFIG02, output_dir=tmp_path / "lf")["config_sha256"]
            == b02.generate(crlf, output_dir=tmp_path / "crlf")["config_sha256"])


# ---------------------------------------------------------------- no look-ahead

def test_earlier_as_of_date_is_a_subset_of_later(b1, config02, tables):
    """Moving the as-of date back only removes rows, never changes them."""
    early = b02.build_tables(config02, b1, date(2026, 8, 14))
    for name in b02.TABLES:
        late_rows = {tuple(sorted(map(str, r.items()))) for r in tables[name]}
        early_rows = {tuple(sorted(map(str, r.items()))) for r in early[name]}
        assert early_rows <= late_rows, name
    assert len(early["readiness_review"]) < len(tables["readiness_review"])


@pytest.mark.parametrize("cutoff", ["2026-06-10", "2026-08-20", "2026-10-12"])
def test_decisions_only_use_records_entered_by_then(config02, cutoff):
    """Generate Build 02 from Build 01 as it looked at `cutoff`, and from the
    full Build 01 observed at the same date. Case openings, exam attempts and
    readiness decisions must be identical: nothing recorded later was used."""
    raw = b02.read_build01(BUILD01_DIR)
    day = date.fromisoformat(cutoff)
    full = b02.build_tables(config02, b02.Build01(raw), day)
    partial = b02.build_tables(config02, b02.Build01(truncate_build01(raw, datetime.combine(day, datetime.max.time()))), day)
    for name in ("watchlist_case", "certification_attempt", "readiness_review"):
        assert full[name] == partial[name], name


# ---------------------------------------------------------------- business rules

def test_generated_data_passes_every_rule(tables, b1, config02):
    assert b02.validate(tables, b1, config02, b1.as_of) == []


def test_two_mandatory_fictional_certifications(tables):
    names = {c["certification_name"] for c in tables["certification_type"] if c["mandatory_for_readiness"]}
    assert names == {"Payments Exception Handling", "Operational Controls & Reconciliation"}
    assert {(c["pass_mark"], c["max_attempts"], c["policy_version"]) for c in tables["certification_type"]} \
        == {(70, 2, "B02-R1")}


def test_policy_version_on_every_record(tables):
    for name in ("watchlist_case", "certification_attempt", "readiness_review"):
        assert {r["policy_version"] for r in tables[name]} == {"B02-R1"}, name


def test_only_completed_enrolments_have_attempts_and_reviews(tables, b1):
    for name in ("certification_attempt", "readiness_review"):
        for r in tables[name]:
            assert "completed" in b1.events[r["enrolment_id"]], r


def test_unfinished_cohort_3_has_no_attempts_or_reviews_but_has_open_cases(tables, cohort_of):
    assert not [r for r in tables["certification_attempt"] if cohort_of[r["enrolment_id"]] == "COH-2026-03"]
    assert not [r for r in tables["readiness_review"] if cohort_of[r["enrolment_id"]] == "COH-2026-03"]
    closed = {e["watchlist_case_id"] for e in tables["watchlist_case_event"] if e["event_type"] == "Closed"}
    open_c3 = [c for c in tables["watchlist_case"]
               if c["watchlist_case_id"] not in closed and cohort_of[c["enrolment_id"]] == "COH-2026-03"]
    assert open_c3


def test_finished_cohorts_have_no_open_cases(tables, cohort_of):
    closed = {e["watchlist_case_id"] for e in tables["watchlist_case_event"] if e["event_type"] == "Closed"}
    still_open = [c for c in tables["watchlist_case"] if c["watchlist_case_id"] not in closed]
    assert {cohort_of[c["enrolment_id"]] for c in still_open} == {"COH-2026-03"}


def test_missing_attendance_is_never_counted_as_absent(b1):
    """The signal rate ignores unrecorded marks: an enrolment whose only
    known marks are Present has a rate of 1.0, whatever is unrecorded."""
    eid = "ENR-00001"
    marks = [m for m in b1.attendance[eid] if m[0] in {1, 2}]
    rate, n = b1.recorded_attendance_rate(eid, {1, 2}, datetime.max)
    assert n == len(marks)
    assert rate == sum(m[1] == "Present" for m in marks) / n


def test_readiness_score_needs_every_competency(b1):
    """A week with only some competencies known is not evidence."""
    eid = "ENR-00001"
    week8 = [s for s in b1.scores[eid] if s[0] == 8]
    if week8:
        first_recorded = min(s[2] for s in week8)
        partial = b02.Build01.__new__(b02.Build01)
        partial.__dict__ = {**b1.__dict__, "scores": {eid: [s for s in b1.scores[eid] if s[0] != 8] + week8[:2]}}
        assert partial.week_average(eid, 8, first_recorded + timedelta(days=30)) is None


# ---------------------------------------------------------------- negative tests: broken data is caught

def broken(tables, name, index, **changes):
    t = copy.deepcopy(tables)
    t[name][index].update(changes)
    return t


def first(tables, name, **match):
    return next(i for i, r in enumerate(tables[name]) if all(r[k] == v for k, v in match.items()))


def problems_for(t, b1, config02):
    return " | ".join(b02.validate(t, b1, config02, b1.as_of))


def test_rejects_overlapping_cases(tables, b1, config02):
    t = copy.deepcopy(tables)
    case = t["watchlist_case"][0]
    clone = {**case, "watchlist_case_id": "WLC-TEST-9", "opened_effective_date": case["opened_effective_date"]}
    t["watchlist_case"].append(clone)
    t["watchlist_case_event"].append({"watchlist_event_id": "WLE-TEST-9-O", "watchlist_case_id": "WLC-TEST-9",
                                      "event_type": "Opened", "effective_date": clone["opened_effective_date"],
                                      "recorded_at": clone["opened_recorded_at"], "closure_reason": None,
                                      "recorded_by_role": "Training lead"})
    assert "overlapping" in problems_for(t, b1, config02)


def test_rejects_action_before_case_opened(tables, b1, config02):
    a = tables["coaching_action"][0]
    case = next(c for c in tables["watchlist_case"] if c["watchlist_case_id"] == a["watchlist_case_id"])
    day = case["opened_effective_date"] - timedelta(days=3)
    t = broken(tables, "coaching_action", 0, action_date=day, recorded_at=datetime.combine(day, datetime.min.time()))
    assert "outside its case" in problems_for(t, b1, config02)


def test_rejects_closure_before_opening(tables, b1, config02):
    i = first(tables, "watchlist_case_event", event_type="Closed")
    t = broken(tables, "watchlist_case_event", i, effective_date=date(2026, 1, 1))
    assert "closed before opened" in problems_for(t, b1, config02)


def test_rejects_attempt_on_completion_day(tables, b1, config02):
    a = tables["certification_attempt"][0]
    done = b1.events[a["enrolment_id"]]["completed"][0]
    t = broken(tables, "certification_attempt", 0, attempt_date=done)
    assert "not after completion" in problems_for(t, b1, config02)


def test_rejects_duplicate_attempt(tables, b1, config02):
    t = copy.deepcopy(tables)
    t["certification_attempt"].append(dict(t["certification_attempt"][0]))
    p = problems_for(t, b1, config02)
    assert "duplicate certification_attempt_id" in p


def test_rejects_too_many_attempts(tables, b1, config02):
    t = broken(tables, "certification_attempt", 0, attempt_number=3)
    assert "over max attempts" in problems_for(t, b1, config02)


def test_rejects_result_that_disagrees_with_pass_mark(tables, b1, config02):
    i = first(tables, "certification_attempt", result="Failed")
    t = broken(tables, "certification_attempt", i, result="Passed")
    assert "does not match pass mark" in problems_for(t, b1, config02)


def test_rejects_attempt_for_active_enrolment(tables, b1, config02):
    t = broken(tables, "certification_attempt", 0, enrolment_id="ENR-00143")   # Cohort 3, in progress
    assert "no completion" in problems_for(t, b1, config02)


def test_rejects_approval_without_signoff(tables, b1, config02):
    i = first(tables, "readiness_review", decision="Approved")
    t = broken(tables, "readiness_review", i, signoff_recorded=0)
    assert "Approved without all evidence" in problems_for(t, b1, config02)


def test_rejects_approval_without_certification(tables, b1, config02):
    i = first(tables, "readiness_review", decision="Approved")
    t = broken(tables, "readiness_review", i, certification_gate_passed=0)
    assert "Approved without all evidence" in problems_for(t, b1, config02)


def test_rejects_future_dated_records(tables, b1, config02):
    future = b1.as_of + timedelta(days=1)
    t = broken(tables, "readiness_review", 0, review_date=future,
               recorded_at=datetime.combine(future, datetime.min.time()))
    assert "after the snapshot" in problems_for(t, b1, config02)


# ---------------------------------------------------------------- policy comes from config

def test_pass_mark_comes_from_config(b1, config02):
    stricter = copy.deepcopy(config02)
    for c in stricter["certification"]["types"]:
        c["pass_mark"] = 80
    t = b02.build_tables(stricter, b1, b1.as_of)
    assert b02.validate(t, b1, stricter, b1.as_of) == []
    assert all((a["score"] >= 80) == (a["result"] == "Passed") for a in t["certification_attempt"])


def test_competency_threshold_comes_from_config(b1, config02):
    stricter = copy.deepcopy(config02)
    stricter["readiness"]["competency_threshold"] = 75.0
    t = b02.build_tables(stricter, b1, b1.as_of)
    for r in t["readiness_review"]:
        if r["review_competency_score"] is not None:
            assert bool(r["competency_gate_passed"]) == (r["review_competency_score"] >= 75.0)
    assert any(r["decision_reason_code"] == "COMPETENCY_BELOW_THRESHOLD" for r in t["readiness_review"])


# ---------------------------------------------------------------- required storylines

def gap_change_after_coaching(tables, b1, cohort_of):
    """For actioned cases: change in (trainee - cohort) week average from the
    trigger week to two weeks later. Descriptive: association only."""
    week = defaultdict(list)
    cohort = defaultdict(list)
    for eid, rows in b1.scores.items():
        for w, s, _ in rows:
            week[(eid, w)].append(s)
            cohort[(cohort_of[eid], w)].append(s)
    actioned = {a["watchlist_case_id"] for a in tables["coaching_action"]}
    out = {}
    for c in tables["watchlist_case"]:
        w, eid = c["trigger_programme_week"], c["enrolment_id"]
        if c["watchlist_case_id"] in actioned and w and (eid, w) in week and (eid, w + 2) in week:
            k = cohort_of[eid]
            out[c["watchlist_case_id"]] = ((mean(week[(eid, w + 2)]) - mean(cohort[(k, w + 2)]))
                                           - (mean(week[(eid, w)]) - mean(cohort[(k, w)])))
    return out


def test_story_coaching_followed_by_improvement_and_by_none(tables, b1, cohort_of):
    changes = gap_change_after_coaching(tables, b1, cohort_of)
    assert any(v >= 2 for v in changes.values()), "no coached trainee closed the gap to the cohort"
    assert any(v <= -2 for v in changes.values()), "every coached trainee improved: interventions look universal"


def test_story_case_lifecycles(tables):
    closures = {e["closure_reason"] for e in tables["watchlist_case_event"] if e["event_type"] == "Closed"}
    assert {"Improved", "Withdrawn", "Programme ended"} <= closures
    actioned = {a["watchlist_case_id"] for a in tables["coaching_action"]}
    assert any(c["watchlist_case_id"] not in actioned for c in tables["watchlist_case"]), "no unactioned case"
    per_enrolment = defaultdict(int)
    for c in tables["watchlist_case"]:
        per_enrolment[c["enrolment_id"]] += 1
    assert max(per_enrolment.values()) >= 2, "no enrolment with two (non-overlapping) episodes"


def test_story_certification_outcomes(tables, b1):
    pairs = defaultdict(list)
    for a in tables["certification_attempt"]:
        pairs[(a["enrolment_id"], a["certification_id"])].append(a["result"])
    outcomes = {tuple(v) for v in pairs.values()}
    assert ("Failed", "Passed") in outcomes            # retake then pass
    assert ("Failed", "Failed") in outcomes            # failed every allowed attempt
    assert ("Passed",) in outcomes
    completed = {e for e, ev in b1.events.items() if "completed" in ev}
    attempted = {a["enrolment_id"] for a in tables["certification_attempt"]}
    assert completed - attempted, "every completer attempted: no 'not attempted' example"


def test_story_readiness_outcomes(tables, b1):
    by_enrolment = defaultdict(list)
    for r in sorted(tables["readiness_review"], key=lambda r: r["review_number"]):
        by_enrolment[r["enrolment_id"]].append(r["decision"])
    completed = {e for e, ev in b1.events.items() if "completed" in ev}
    assert completed - set(by_enrolment), "no completed-but-unreviewed enrolment"
    assert any(v[-1] == "Deferred" for v in by_enrolment.values())
    assert any(v[-1] == "Approved" and "Deferred" in v[:-1] for v in by_enrolment.values())


def test_story_repeat_employee_records_stay_on_their_own_enrolment(tables):
    """EMP-00025 is ENR-00025 (Cohort 1, withdrew) and ENR-00143 (Cohort 3).
    The Cohort 1 case belongs to ENR-00025 only."""
    cases = [c for c in tables["watchlist_case"] if c["enrolment_id"] in ("ENR-00025", "ENR-00143")]
    assert cases and {c["enrolment_id"] for c in cases} == {"ENR-00025"}


def test_trace_enrolment_has_all_three_storylines(tables):
    """ENR-00044 is the walkthrough's trace example; keep it meaningful."""
    eid = "ENR-00044"
    assert any(c["enrolment_id"] == eid for c in tables["watchlist_case"])
    assert any(a["watchlist_case_id"].startswith("WLC-00044") for a in tables["coaching_action"])
    assert any(a["enrolment_id"] == eid and a["attempt_number"] == 2 and a["result"] == "Passed"
               for a in tables["certification_attempt"])
    decisions = [r["decision"] for r in sorted(tables["readiness_review"], key=lambda r: r["review_number"])
                 if r["enrolment_id"] == eid]
    assert decisions == ["Deferred", "Approved"]


def test_no_personal_free_text(tables):
    """Only controlled codes: no names, comments or emails in Build 02."""
    assert {a["action_note_code"] for a in tables["coaching_action"]} <= set(b02.NOTE_CODE.values())
    for name in b02.TABLES:
        for row in tables[name]:
            for value in row.values():
                assert "@" not in str(value)


def test_committed_files_load_back_with_the_expected_rows():
    committed = read_tables(BUILD02_DIR)
    assert set(committed) == set(b02.TABLES)
    assert all(committed[n] for n in b02.TABLES)


# ---------------------------------------------------------------- audit outputs (signals, evidence, data quality)

def test_audit_files_are_written_and_in_the_manifest(tmp_path):
    m = b02.generate(output_dir=tmp_path)
    for filename in b02.AUDIT_FILES.values():
        assert (tmp_path / "audit" / filename).exists()
        assert f"audit/{filename}" in m["files"]


def test_audit_case_ids_match_the_case_table(tables):
    """Every case in the table appears once as 'case opened' in the audit, and
    the audit never names a case the dataset doesn't contain (no look-ahead)."""
    audit = tables["audit_review_signals"]
    opened = [r["watchlist_case_id"] for r in audit if r["review_outcome"].endswith(": case opened")]
    assert sorted(opened) == sorted(c["watchlist_case_id"] for c in tables["watchlist_case"])
    known = {c["watchlist_case_id"] for c in tables["watchlist_case"]}
    assert {r["watchlist_case_id"] for r in audit if r["watchlist_case_id"]} <= known
    closed = {e["watchlist_case_id"]: e["closure_reason"] for e in tables["watchlist_case_event"]
              if e["event_type"] == "Closed"}
    for r in audit:
        if r["case_closed_reason"]:
            assert closed[r["watchlist_case_id"]] == r["case_closed_reason"]


def test_audit_signals_follow_the_evidence_and_config(tables, config02):
    cfg = config02["watchlist"]
    for r in tables["audit_review_signals"]:
        low_att = (r["recorded_sessions"] >= cfg["attendance_min_recorded_sessions"]
                   and r["recorded_attendance_rate"] < cfg["low_recorded_attendance_rate"])
        assert r["signal_low_attendance"] == int(low_att), r
        if r["gap_vs_cohort"] is not None and abs(r["gap_vs_cohort"] + cfg["low_score_gap_vs_cohort"]) > 0.01:
            assert r["signal_low_competency"] == int(r["gap_vs_cohort"] <= -cfg["low_score_gap_vs_cohort"]), r
        if r["latest_full_week"] is None:
            assert r["signal_low_competency"] == r["signal_declining_scores"] == 0
        assert r["signal_count"] == r["signal_low_attendance"] + r["signal_low_competency"] + r["signal_declining_scores"]


def test_missing_attendance_is_a_data_quality_flag_not_an_absence(tables, config02):
    threshold = config02["watchlist"]["unrecorded_review_min_sessions"]
    flagged = 0
    for r in tables["audit_review_signals"]:
        assert r["unrecorded_sessions"] == r["eligible_sessions"] - r["recorded_sessions"] >= 0
        if r["recorded_sessions"]:
            # the rate uses recorded marks only: unrecorded never lowers it
            assert abs(r["recorded_attendance_rate"] - r["present_sessions"] / r["recorded_sessions"]) < 1e-4
        assert (r["attendance_dq_flag"] == "VERIFY_UNRECORDED_MARKS") == (r["unrecorded_sessions"] >= threshold)
        flagged += r["attendance_dq_flag"] != "OK"
    assert flagged > 0


def test_readiness_evidence_populations_reconcile(tables, b1):
    rows = tables["audit_readiness_evidence"]
    completed = [e for e, ev in b1.events.items() if "completed" in ev]
    assert len(rows) == len(completed) == 127
    reviewed = {r["enrolment_id"] for r in tables["readiness_review"]}
    attempted = {a["enrolment_id"] for a in tables["certification_attempt"]}
    for r in rows:
        assert (r["readiness_population"] == "Not reviewed") == (r["enrolment_id"] not in reviewed)
        assert (r["certification_population"] == "Not attempted") == (r["enrolment_id"] not in attempted)
    pops = {p: sum(r["readiness_population"] == p for r in rows) for p in ("Approved", "Deferred", "Not reviewed")}
    assert sum(pops.values()) == 127 and all(pops.values())
