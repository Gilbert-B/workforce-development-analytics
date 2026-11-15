"""Tests for the synthetic data generator (no database needed).

Grouped by what they prove:
  reproducibility, keys & references, lifecycle rules,
  nothing-from-the-future, and the intended synthetic patterns.
"""

from collections import defaultdict
from datetime import date, timedelta

import pytest

from conftest import CONFIG, REPO_ROOT, gen, read_tables

PRIMARY_KEYS = {
    "cohort": ["cohort_id"],
    "employee": ["employee_id"],
    "competency": ["competency_id"],
    "enrolment": ["enrolment_id"],
    "enrolment_status_event": ["status_event_id"],
    "scheduled_session": ["session_id"],
    "attendance": ["enrolment_id", "session_id"],
    "assessment": ["assessment_id"],
}
# Business keys that must also be unique (the grain of the table).
GRAIN_KEYS = {
    "enrolment": ["employee_id", "cohort_id"],
    "enrolment_status_event": ["enrolment_id", "event_type"],
    "scheduled_session": ["cohort_id", "session_date"],
    "assessment": ["enrolment_id", "competency_id", "programme_week", "attempt_number"],
}
FOREIGN_KEYS = [  # (child table, column, parent table, parent column)
    ("enrolment", "employee_id", "employee", "employee_id"),
    ("enrolment", "cohort_id", "cohort", "cohort_id"),
    ("enrolment_status_event", "enrolment_id", "enrolment", "enrolment_id"),
    ("scheduled_session", "cohort_id", "cohort", "cohort_id"),
    ("attendance", "enrolment_id", "enrolment", "enrolment_id"),
    ("attendance", "session_id", "scheduled_session", "session_id"),
    ("assessment", "enrolment_id", "enrolment", "enrolment_id"),
    ("assessment", "competency_id", "competency", "competency_id"),
]


def events_by_enrolment(dataset):
    out = defaultdict(dict)
    for ev in dataset["enrolment_status_event"]:
        out[ev["enrolment_id"]][ev["event_type"]] = date.fromisoformat(ev["effective_date"])
    return out


def status_as_of(events: dict, day: date) -> str | None:
    """Python version of Rule 2 / rpt.fn_enrolment_status_as_of."""
    def on_or_before(kind):
        return kind in events and events[kind] <= day
    if on_or_before("cancelled"):
        return "Cancelled before start"
    if on_or_before("withdrawn"):
        return "Withdrawn"
    if on_or_before("completed"):
        return "Completed"
    if on_or_before("started"):
        return "Active"
    if on_or_before("enrolled"):
        return "Enrolled (not started)"
    return None


# ---------------------------------------------------------------- reproducibility

def test_same_seed_and_date_give_identical_files(tmp_path):
    m1 = gen.generate(CONFIG, tmp_path / "run1")
    m2 = gen.generate(CONFIG, tmp_path / "run2")
    assert m1["files"] == m2["files"]          # same row counts AND same sha256 per file


def test_different_seed_gives_different_data(tmp_path):
    m1 = gen.generate(CONFIG, tmp_path / "a")
    m2 = gen.generate(CONFIG, tmp_path / "b", seed=999)
    assert m1["files"]["assessment.csv"]["sha256"] != m2["files"]["assessment.csv"]["sha256"]


def test_committed_csvs_match_the_generator(generated_dir):
    """data/synthetic/ in Git must be exactly what the generator produces."""
    committed = (REPO_ROOT / "data" / "synthetic" / "generation_manifest.json").read_text()
    regenerated = (generated_dir / "generation_manifest.json").read_text()
    assert committed == regenerated, "Re-run python/generate_synthetic_data.py and commit the result"


def test_earlier_as_of_date_is_a_subset_of_later(tmp_path, as_of):
    """Prefix property: moving the as-of date back only removes rows,
    never changes them. Proves the generator has no future leakage."""
    gen.generate(CONFIG, tmp_path / "early", as_of=as_of - timedelta(days=45))
    gen.generate(CONFIG, tmp_path / "late")
    early = read_tables(tmp_path / "early")
    late = read_tables(tmp_path / "late")
    for table in PRIMARY_KEYS:
        late_rows = {tuple(sorted(r.items())) for r in late[table]}
        early_rows = {tuple(sorted(r.items())) for r in early[table]}
        assert early_rows <= late_rows, f"{table}: an earlier snapshot contains a row the later one doesn't"
    assert len(early["assessment"]) < len(late["assessment"])


# ---------------------------------------------------------------- volumes

def test_at_least_three_cohorts_with_60_to_75_starters(dataset):
    assert len(dataset["cohort"]) >= 3
    starters = defaultdict(int)
    cohort_of = {e["enrolment_id"]: e["cohort_id"] for e in dataset["enrolment"]}
    for ev in dataset["enrolment_status_event"]:
        if ev["event_type"] == "started":
            starters[cohort_of[ev["enrolment_id"]]] += 1
    assert len(starters) >= 3
    for cohort_id, n in starters.items():
        assert 60 <= n <= 75, f"{cohort_id} has {n} starters"


# ---------------------------------------------------------------- keys and references

@pytest.mark.parametrize("table", sorted(PRIMARY_KEYS))
def test_primary_keys_are_unique(dataset, table):
    keys = [tuple(r[c] for c in PRIMARY_KEYS[table]) for r in dataset[table]]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("table", sorted(GRAIN_KEYS))
def test_business_grain_is_unique(dataset, table):
    keys = [tuple(r[c] for c in GRAIN_KEYS[table]) for r in dataset[table]]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("child,col,parent,pcol", FOREIGN_KEYS)
def test_no_orphaned_foreign_keys(dataset, child, col, parent, pcol):
    parents = {r[pcol] for r in dataset[parent]}
    orphans = [r[col] for r in dataset[child] if r[col] not in parents]
    assert not orphans, f"{child}.{col} values missing from {parent}: {orphans[:5]}"


def test_attendance_session_belongs_to_enrolment_cohort(dataset):
    cohort_of_enrolment = {e["enrolment_id"]: e["cohort_id"] for e in dataset["enrolment"]}
    cohort_of_session = {s["session_id"]: s["cohort_id"] for s in dataset["scheduled_session"]}
    for a in dataset["attendance"]:
        assert cohort_of_enrolment[a["enrolment_id"]] == cohort_of_session[a["session_id"]]


def test_repeat_enrolment_keeps_employee_but_gets_new_enrolment(dataset):
    per_employee = defaultdict(list)
    for e in dataset["enrolment"]:
        per_employee[e["employee_id"]].append(e)
    repeats = {emp: rows for emp, rows in per_employee.items() if len(rows) > 1}
    assert len(repeats) == 2
    events = events_by_enrolment(dataset)
    for rows in repeats.values():
        first, second = sorted(rows, key=lambda r: r["enrolled_date"])
        assert "withdrawn" in events[first["enrolment_id"]]          # left the first cohort
        assert first["enrolment_id"] != second["enrolment_id"]


# ---------------------------------------------------------------- lifecycle rules

def test_status_events_are_in_a_valid_order(dataset):
    for enrolment_id, ev in events_by_enrolment(dataset).items():
        assert "enrolled" in ev, enrolment_id
        assert not ("cancelled" in ev and "started" in ev), enrolment_id
        end_events = [k for k in ("cancelled", "withdrawn", "completed") if k in ev]
        assert len(end_events) <= 1, enrolment_id
        if "started" in ev:
            assert ev["started"] >= ev["enrolled"]
        for end in ("withdrawn", "completed"):
            if end in ev:
                assert "started" in ev and ev[end] >= ev["started"], enrolment_id


def test_recorded_timestamp_never_before_effective_date(dataset):
    for ev in dataset["enrolment_status_event"]:
        assert ev["recorded_at"][:10] >= ev["effective_date"]


def test_completion_is_explicit_and_only_at_programme_end(dataset):
    end_date = {c["cohort_id"]: c["planned_end_date"] for c in dataset["cohort"]}
    cohort_of = {e["enrolment_id"]: e["cohort_id"] for e in dataset["enrolment"]}
    completions = [ev for ev in dataset["enrolment_status_event"] if ev["event_type"] == "completed"]
    assert completions
    for ev in completions:
        assert ev["effective_date"] == end_date[cohort_of[ev["enrolment_id"]]]


def test_status_as_of_ignores_later_events(dataset):
    """An enrolment that withdrew later is still Active on an earlier date."""
    events = events_by_enrolment(dataset)
    withdrawn = [(eid, ev) for eid, ev in events.items() if "withdrawn" in ev]
    assert withdrawn
    for eid, ev in withdrawn:
        assert status_as_of(ev, ev["withdrawn"] - timedelta(days=1)) == "Active"
        assert status_as_of(ev, ev["withdrawn"]) == "Withdrawn"
        assert status_as_of(ev, ev["started"] - timedelta(days=1)) == "Enrolled (not started)"


# ---------------------------------------------------------------- nothing from the future

def test_no_record_is_dated_after_the_as_of_date(dataset, as_of):
    limit = as_of.isoformat()
    session_date = {s["session_id"]: s["session_date"] for s in dataset["scheduled_session"]}
    for ev in dataset["enrolment_status_event"]:
        assert ev["effective_date"] <= limit and ev["recorded_at"][:10] <= limit
    for a in dataset["attendance"]:
        assert session_date[a["session_id"]] <= limit and a["recorded_at"][:10] <= limit
    for a in dataset["assessment"]:
        assert a["assessment_date"] <= limit and a["recorded_at"][:10] <= limit


def test_unfinished_cohort_has_no_future_assessments_or_completions(dataset, as_of):
    unfinished = [c for c in dataset["cohort"] if c["planned_end_date"] > as_of.isoformat()]
    assert unfinished, "the config should include at least one cohort still in progress"
    cohort_of = {e["enrolment_id"]: e["cohort_id"] for e in dataset["enrolment"]}
    for c in unfinished:
        # Last week whose Friday assessment date has passed
        fridays = [s for s in dataset["scheduled_session"]
                   if s["cohort_id"] == c["cohort_id"] and s["session_day"] == "5"
                   and s["session_date"] <= as_of.isoformat()]
        last_week = max((int(s["programme_week"]) for s in fridays), default=0)
        weeks = {int(a["programme_week"]) for a in dataset["assessment"]
                 if cohort_of[a["enrolment_id"]] == c["cohort_id"]}
        assert weeks and max(weeks) <= last_week
        assert not any(ev["event_type"] == "completed" and cohort_of[ev["enrolment_id"]] == c["cohort_id"]
                       for ev in dataset["enrolment_status_event"])


# ---------------------------------------------------------------- attendance semantics

def test_attendance_only_present_or_absent_and_only_while_enrolled(dataset):
    events = events_by_enrolment(dataset)
    session_date = {s["session_id"]: date.fromisoformat(s["session_date"]) for s in dataset["scheduled_session"]}
    for a in dataset["attendance"]:
        assert a["attendance_status"] in {"Present", "Absent"}   # never a fake 'Absent' for missing data
        ev = events[a["enrolment_id"]]
        day = session_date[a["session_id"]]
        assert "started" in ev and day >= ev["started"]
        assert "withdrawn" not in ev or day < ev["withdrawn"]


def test_some_eligible_attendance_is_unrecorded(dataset, as_of):
    """Missing marks must exist (to test 'unknown' handling) and be absent
    from the file, not recoded as 'Absent'."""
    events = events_by_enrolment(dataset)
    recorded = {(a["enrolment_id"], a["session_id"]) for a in dataset["attendance"]}
    eligible = set()
    for s in dataset["scheduled_session"]:
        day = date.fromisoformat(s["session_date"])
        if day > as_of:
            continue
        for e in dataset["enrolment"]:
            ev = events[e["enrolment_id"]]
            if (e["cohort_id"] == s["cohort_id"] and "started" in ev and day >= ev["started"]
                    and ("withdrawn" not in ev or day < ev["withdrawn"])):
                eligible.add((e["enrolment_id"], s["session_id"]))
    unrecorded = eligible - recorded
    assert recorded <= eligible
    assert 0.01 < len(unrecorded) / len(eligible) < 0.15


# ---------------------------------------------------------------- intended synthetic patterns

def _cohort_week_average(dataset, cohort_id, week):
    cohort_of = {e["enrolment_id"]: e["cohort_id"] for e in dataset["enrolment"]}
    scores = [int(a["score"]) for a in dataset["assessment"]
              if cohort_of[a["enrolment_id"]] == cohort_id and int(a["programme_week"]) == week]
    return sum(scores) / len(scores)


def test_cohort_2_improves_faster_than_cohort_1(dataset):
    gain_1 = _cohort_week_average(dataset, "COH-2026-01", 8) - _cohort_week_average(dataset, "COH-2026-01", 1)
    gain_2 = _cohort_week_average(dataset, "COH-2026-02", 8) - _cohort_week_average(dataset, "COH-2026-02", 1)
    assert gain_2 > gain_1 + 3


def test_scores_improve_on_average_in_every_cohort(dataset, as_of):
    for c in dataset["cohort"]:
        weeks = sorted({int(a["programme_week"]) for a in dataset["assessment"]
                        if a["enrolment_id"] in {e["enrolment_id"] for e in dataset["enrolment"]
                                                  if e["cohort_id"] == c["cohort_id"]}})
        assert _cohort_week_average(dataset, c["cohort_id"], weeks[-1]) > \
               _cohort_week_average(dataset, c["cohort_id"], weeks[0])


def test_some_trainees_show_declining_attendance(dataset):
    week_of = {s["session_id"]: int(s["programme_week"]) for s in dataset["scheduled_session"]}
    by_enrolment = defaultdict(lambda: defaultdict(list))
    for a in dataset["attendance"]:
        by_enrolment[a["enrolment_id"]][week_of[a["session_id"]]].append(a["attendance_status"] == "Present")
    decliners = 0
    for weeks in by_enrolment.values():
        ordered = sorted(weeks)
        if len(ordered) < 4:
            continue
        early = [x for w in ordered[:2] for x in weeks[w]]
        late = [x for w in ordered[-2:] for x in weeks[w]]
        if sum(early) / len(early) - sum(late) / len(late) >= 0.3:
            decliners += 1
    assert decliners >= 3


def test_there_are_several_explicit_withdrawals(dataset):
    withdrawals = [ev for ev in dataset["enrolment_status_event"] if ev["event_type"] == "withdrawn"]
    assert len(withdrawals) >= 5


def test_pre_start_cancellations_are_not_starters(dataset):
    events = events_by_enrolment(dataset)
    cancelled = [ev for ev in events.values() if "cancelled" in ev]
    assert cancelled and all("started" not in ev for ev in cancelled)
