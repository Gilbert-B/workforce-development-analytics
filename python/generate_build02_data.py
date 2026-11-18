"""Generate the Build 02 synthetic data: watch-list, coaching, certification, readiness.

Everything produced is fictional. Inputs:
  * the committed Build 01 CSVs (data/synthetic/), which are only READ;
  * config/build02_synthetic.toml (thresholds and probabilities).
Output: six CSVs plus generation_manifest.json in data/synthetic/build02/.

The idea worth understanding: decisions only use what was RECORDED by then.
Every business decision (open a watch-list case, close it, sit an exam,
approve or defer readiness) happens at a date and time. The generator only
lets that decision see Build 01 records whose recorded_at is on or before
that moment. A review on Monday 10:00 can't see Friday's scores if they were
only entered on Monday afternoon. That is how "no look-ahead" is guaranteed.

As in Build 01, the whole story is simulated first (the "truth", which
ignores the as-of date). Then we observe it as of a date, keeping only the
records entered by then. An earlier as-of date therefore always gives a
subset of a later one.

Usage:
    python python/generate_build02_data.py
    python python/generate_build02_data.py --as-of-date 2026-10-01
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_synthetic_data import (  # noqa: E402  (shared Build 01 helpers)
    add_business_days, sha256, sha256_ignoring_line_endings, write_csv,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "build02_synthetic.toml"
DEFAULT_BUILD01 = REPO_ROOT / "data" / "synthetic"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "synthetic" / "build02"
GENERATOR_VERSION = "build02-1.0"

TABLES = ["certification_type", "watchlist_case", "watchlist_case_event",
          "coaching_action", "certification_attempt", "readiness_review"]

# Controlled vocabularies (no free text anywhere).
ACTION_FOR_REASON = {
    "LOW_ATTENDANCE": "Attendance follow-up",
    "LOW_COMPETENCY": "Skills practice",
    "DECLINING_SCORES": "1:1 coaching",
    "MANUAL_REFERRAL": "Supervisor check-in",
}
ACTION_TYPES = ["1:1 coaching", "Attendance follow-up", "Skills practice", "Supervisor check-in"]
STAFF_ROLE = {"1:1 coaching": "Coach", "Attendance follow-up": "Programme coordinator",
              "Skills practice": "Trainer", "Supervisor check-in": "Team supervisor"}
NOTE_CODE = {"1:1 coaching": "NOTE-COACH-GOALS", "Attendance follow-up": "NOTE-ATT-PLAN",
             "Skills practice": "NOTE-PRACTICE-SET", "Supervisor check-in": "NOTE-SUPERVISOR-REVIEW"}


def ts(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute))


def stream(seed: int, name: str, key: str) -> random.Random:
    """An independent random stream per (purpose, record). Seeding with a
    string is stable across Python versions and operating systems, and it
    means one trainee's results never depend on how many others came first."""
    return random.Random(f"{seed}|{name}|{key}")


def uniform_int(rng: random.Random, low: int, high: int) -> int:
    return low + int(rng.random() * (high - low + 1))


# --------------------------------------------------------------------------
# Build 01 inputs, with "what was known at time t" helpers
# --------------------------------------------------------------------------

def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_build01(folder: Path) -> dict[str, list[dict]]:
    names = ["data_snapshot", "cohort", "competency", "enrolment",
             "enrolment_status_event", "scheduled_session", "attendance", "assessment"]
    return {n: read_csv(folder / f"{n}.csv") for n in names}


class Build01:
    """Build 01 records, indexed for 'known by time t' questions."""

    def __init__(self, t: dict[str, list[dict]]):
        self.as_of = date.fromisoformat(t["data_snapshot"][0]["as_of_date"])
        self.cohorts = {c["cohort_id"]: c for c in t["cohort"]}
        self.n_competencies = len(t["competency"])
        self.enrolments = sorted(t["enrolment"], key=lambda e: e["enrolment_id"])
        self.events = defaultdict(dict)   # enrolment -> event_type -> (effective date, recorded datetime)
        for ev in t["enrolment_status_event"]:
            self.events[ev["enrolment_id"]][ev["event_type"]] = (
                date.fromisoformat(ev["effective_date"]), datetime.fromisoformat(ev["recorded_at"]))
        week_of = {s["session_id"]: int(s["programme_week"]) for s in t["scheduled_session"]}
        self.attendance = defaultdict(list)   # enrolment -> [(week, status, recorded)]
        for a in t["attendance"]:
            self.attendance[a["enrolment_id"]].append(
                (week_of[a["session_id"]], a["attendance_status"], datetime.fromisoformat(a["recorded_at"])))
        self.scores = defaultdict(list)       # enrolment -> [(week, score, recorded)]
        for a in t["assessment"]:
            self.scores[a["enrolment_id"]].append(
                (int(a["programme_week"]), int(a["score"]), datetime.fromisoformat(a["recorded_at"])))

    def event_known(self, enrolment_id: str, kind: str, when: datetime):
        """(effective, recorded) if the event was recorded by `when`, else None."""
        ev = self.events[enrolment_id].get(kind)
        return ev if ev and ev[1] <= when else None

    def ended_known(self, enrolment_id: str, when: datetime) -> bool:
        return any(self.event_known(enrolment_id, k, when) for k in ("withdrawn", "completed", "cancelled"))

    def week_average(self, enrolment_id: str, week: int, when: datetime) -> float | None:
        """Average of the week's scores known by `when`, only if EVERY
        competency was scored (a partly known week is not evidence)."""
        known = [s for w, s, rec in self.scores[enrolment_id] if w == week and rec <= when]
        return mean(known) if len(known) == self.n_competencies else None

    def latest_full_week(self, enrolment_id: str, when: datetime) -> tuple[int, float] | None:
        weeks = sorted({w for w, _, rec in self.scores[enrolment_id] if rec <= when}, reverse=True)
        for w in weeks:
            avg = self.week_average(enrolment_id, w, when)
            if avg is not None:
                return w, avg
        return None

    def recorded_attendance_rate(self, enrolment_id: str, weeks: set[int], when: datetime):
        """(present / recorded, recorded count). Unrecorded marks are simply
        absent from Build 01's attendance table, so they never count as Absent."""
        marks = [st for w, st, rec in self.attendance[enrolment_id] if w in weeks and rec <= when]
        return (sum(m == "Present" for m in marks) / len(marks) if marks else None), len(marks)


# --------------------------------------------------------------------------
# The simulated truth
# --------------------------------------------------------------------------

@dataclass
class Case:
    case_id: str
    enrolment_id: str
    opened: date
    opened_recorded: datetime
    reason: str
    severity: str
    trigger_week: int | None
    source_type: str
    closed: date | None = None
    closed_recorded: datetime | None = None
    closure_reason: str | None = None
    actions: list = field(default_factory=list)


def review_signals(b1: Build01, cfg: dict, enrolment_id: str, cohort_id: str, week: int,
                   when: datetime, cohort_avg_cache: dict) -> list[str]:
    """The reasons a reviewer would look at this trainee at `when`."""
    signals = []
    window = set(range(week - cfg["attendance_window_weeks"] + 1, week + 1))
    rate, n = b1.recorded_attendance_rate(enrolment_id, window, when)
    if n >= cfg["attendance_min_recorded_sessions"] and rate < cfg["low_recorded_attendance_rate"]:
        signals.append("LOW_ATTENDANCE")
    latest = b1.latest_full_week(enrolment_id, when)
    if latest:
        w, avg = latest
        key = (cohort_id, w, when)
        if key not in cohort_avg_cache:   # same-week cohort average: a COMPARABLE score
            peers = [b1.week_average(e["enrolment_id"], w, when)
                     for e in b1.enrolments if e["cohort_id"] == cohort_id]
            peers = [p for p in peers if p is not None]
            cohort_avg_cache[key] = mean(peers) if peers else None
        cohort_avg = cohort_avg_cache[key]
        if cohort_avg is not None and avg <= cohort_avg - cfg["low_score_gap_vs_cohort"]:
            signals.append("LOW_COMPETENCY")
        prev = b1.week_average(enrolment_id, w - 1, when)
        if prev is not None and prev - avg >= cfg["declining_score_drop"]:
            signals.append("DECLINING_SCORES")
    return signals


def simulate_watchlist(b1: Build01, config: dict, seed: int) -> list[Case]:
    cfg = config["watchlist"]
    cases: list[Case] = []
    cache: dict = {}
    for e in b1.enrolments:
        eid, num = e["enrolment_id"], e["enrolment_id"].split("-")[1]
        start = date.fromisoformat(b1.cohorts[e["cohort_id"]]["start_date"])
        rng = stream(seed, "watchlist", eid)
        episode, open_case, clear_reviews = 0, None, 0
        for week in range(cfg["first_review_after_week"], cfg["last_review_after_week"] + 1):
            review_day = start + timedelta(weeks=week)          # Monday after week `week`
            when = at(review_day, cfg["review_hour"])
            draws = [rng.random() for _ in range(3)]            # fixed number per review
            started = b1.event_known(eid, "started", when)
            if not started:
                continue
            if open_case and close_for_end_event(b1, open_case, when, rng_draw=draws[2]):
                cases.append(open_case)
                open_case = None
            if b1.ended_known(eid, when):
                break                                           # no reviews once an exit is recorded
            signals = review_signals(b1, cfg, eid, e["cohort_id"], week, when, cache)
            if open_case:
                clear_reviews = clear_reviews + 1 if not signals else 0
                if clear_reviews >= cfg["clear_reviews_to_close"]:
                    open_case.closed = review_day
                    open_case.closed_recorded = recorded_after(review_day, draws[2], cfg, 16)
                    open_case.closure_reason = ("Administrative" if open_case.source_type == "Manual referral"
                                                else "Improved")
                    cases.append(open_case)
                    open_case = None
                continue
            manual = not signals and draws[1] < cfg["manual_referral_probability"]
            if (signals and draws[0] < cfg["open_case_probability"]) or manual:
                episode += 1
                open_case = Case(
                    case_id=f"WLC-{num}-{episode}", enrolment_id=eid, opened=review_day,
                    opened_recorded=recorded_after(review_day, draws[2], cfg, 11),
                    reason=signals[0] if signals else "MANUAL_REFERRAL",
                    severity="Low" if manual else ("High" if len(signals) >= 2 else "Medium"),
                    trigger_week=None if manual else week,
                    source_type="Manual referral" if manual else "Observed signal")
                clear_reviews = 0
        if open_case:   # still open after the last review: closes when the exit is recorded (if ever)
            close_for_end_event(b1, open_case, datetime.max, rng_draw=rng.random())
            cases.append(open_case)
    for case in cases:
        case.actions = simulate_actions(b1, config, seed, case)
    return cases


def recorded_after(day: date, draw: float, cfg: dict, hour: int) -> datetime:
    lag = int(draw * (cfg["max_recording_delay_days"] + 1))
    return at(add_business_days(day, lag) if lag else day, hour)


def close_for_end_event(b1: Build01, case: Case, when: datetime, rng_draw: float) -> bool:
    """Close the case administratively once a withdrawal or completion is
    RECORDED. These closures are not coaching outcomes."""
    for kind, reason in (("withdrawn", "Withdrawn"), ("completed", "Programme ended")):
        ev = b1.event_known(case.enrolment_id, kind, when)
        if ev:
            effective, recorded = ev
            case.closed = max(effective, case.opened)
            closed_rec = at(add_business_days(recorded.date(), int(rng_draw * 2)), 17)
            case.closed_recorded = max(closed_rec, case.opened_recorded + timedelta(hours=1))
            case.closure_reason = reason
            return True
    return False


def simulate_actions(b1: Build01, config: dict, seed: int, case: Case) -> list[dict]:
    """Completed coaching actions, only while the case is open AND the
    trainee is still in training. Actions never decide when a case closes,
    so the data can't 'prove' that coaching works."""
    cfg = config["coaching"]
    rng = stream(seed, "coaching", case.case_id)
    if rng.random() < cfg["no_action_probability"]:
        return []
    events = b1.events[case.enrolment_id]
    last_day = date.max
    if case.closed:
        last_day = case.closed
    if "withdrawn" in events:
        last_day = min(last_day, events["withdrawn"][0] - timedelta(days=1))
    if "completed" in events:
        last_day = min(last_day, events["completed"][0])
    actions = []
    day = add_business_days(case.opened_recorded.date(),
                            uniform_int(rng, cfg["first_action_min_days"], cfg["first_action_max_days"]))
    for k in range(1, cfg["max_actions_per_case"] + 1):
        if day > last_day:
            break
        kind = ACTION_FOR_REASON[case.reason] if k == 1 else ACTION_TYPES[int(rng.random() * 4)]
        lag = int(rng.random() * 3)
        actions.append({
            "coaching_action_id": f"CA-{case.case_id[4:]}-{k}",
            "watchlist_case_id": case.case_id,
            "action_date": day,
            "recorded_at": at(add_business_days(day, lag) if lag else day, 17, 30),
            "action_type": kind,
            "staff_role": STAFF_ROLE[kind],
            "followup_recommended": 1 if rng.random() < cfg["followup_recommended_probability"] else 0,
            "action_note_code": NOTE_CODE[kind],
        })
        day = add_business_days(day, uniform_int(rng, cfg["next_action_min_days"], cfg["next_action_max_days"]))
    return actions


def simulate_certification(b1: Build01, config: dict, seed: int) -> list[dict]:
    cfg = config["certification"]
    attempts = []
    for e in b1.enrolments:
        eid, num = e["enrolment_id"], e["enrolment_id"].split("-")[1]
        completed = b1.events[eid].get("completed")
        if not completed:
            continue                           # active, withdrawn or cancelled: no attempts
        effective, recorded = completed
        rng = stream(seed, "certification", eid)
        if rng.random() < cfg["no_attempt_probability"]:
            continue
        # The exam can only be booked once completion is on record, and it is
        # always on a later day than the completion date (never the same day).
        earliest = max(effective, recorded.date())
        for ctype in cfg["types"]:
            crng = stream(seed, "certification", f"{eid}|{ctype['certification_code']}")
            if crng.random() < cfg["skip_probability"]:
                continue
            day = add_business_days(earliest, uniform_int(crng, cfg["first_attempt_min_days"],
                                                          cfg["first_attempt_max_days"]))
            # Exam performance reflects the latest fully assessed training week known that day.
            latest = b1.latest_full_week(eid, at(day, 9))
            base = latest[1] if latest else 55.0
            score = base + cfg["score_offset"] + crng.gauss(0, cfg["score_sd"])
            for attempt in range(1, ctype["max_attempts"] + 1):
                points = int(round(min(100, max(0, score))))
                passed = points >= ctype["pass_mark"]
                lag = int(crng.random() * 3)
                attempts.append({
                    "certification_attempt_id": f"CAT-{num}-{ctype['certification_code']}-{attempt}",
                    "enrolment_id": eid,
                    "certification_id": ctype["certification_id"],
                    "attempt_number": attempt,
                    "attempt_date": day,
                    "recorded_at": at(add_business_days(day, lag) if lag else day, 15),
                    "score": points,
                    "result": "Passed" if passed else "Failed",
                    "policy_version": config["run"]["policy_version"],
                })
                if passed or crng.random() >= cfg["retake_probability"]:
                    break
                day = add_business_days(day, uniform_int(crng, cfg["retake_min_days"], cfg["retake_max_days"]))
                score = score + crng.gauss(cfg["retake_gain_mean"], cfg["retake_gain_sd"])
    return attempts


def simulate_readiness(b1: Build01, config: dict, seed: int, attempts: list[dict]) -> list[dict]:
    cfg = config["readiness"]
    types = config["certification"]["types"]
    mandatory = [t["certification_id"] for t in types if t["mandatory_for_readiness"]]
    max_attempts = {t["certification_id"]: t["max_attempts"] for t in types}
    by_enrolment = defaultdict(list)
    for a in attempts:
        by_enrolment[a["enrolment_id"]].append(a)

    reviews = []
    for e in b1.enrolments:
        eid, num = e["enrolment_id"], e["enrolment_id"].split("-")[1]
        completed = b1.events[eid].get("completed")
        if not completed:
            continue
        rng = stream(seed, "readiness", eid)
        if rng.random() < cfg["unreviewed_probability"]:
            continue                                 # completed, not (yet) reviewed: NOT a failure
        day = add_business_days(completed[0], uniform_int(rng, cfg["first_review_min_days"],
                                                          cfg["first_review_max_days"]))
        for review_number in range(1, cfg["max_reviews"] + 1):
            when = at(day, cfg["review_hour"])
            # Evidence as known at the review: records entered by then only.
            completion_ok = b1.event_known(eid, "completed", when) is not None
            known = [a for a in by_enrolment[eid] if a["recorded_at"] <= when]
            passed = {a["certification_id"] for a in known if a["result"] == "Passed"}
            cert_ok = all(c in passed for c in mandatory)
            exhausted = any(c not in passed and sum(a["certification_id"] == c for a in known) >= max_attempts[c]
                            for c in mandatory)
            latest = b1.latest_full_week(eid, when)
            score = round(latest[1], 1) if latest else None
            competency_ok = score is not None and score >= cfg["competency_threshold"]
            draw = rng.random()
            signoff = completion_ok and cert_ok and competency_ok and draw < cfg["signoff_probability"]
            if signoff:
                decision, reason = "Approved", "ALL_GATES_MET_SIGNED_OFF"
            elif not cert_ok:
                decision, reason = "Deferred", "CERTIFICATION_NOT_MET" if exhausted else "CERTIFICATION_PENDING"
            elif score is None:
                decision, reason = "Deferred", "INSUFFICIENT_COMPETENCY_EVIDENCE"
            elif not competency_ok:
                decision, reason = "Deferred", "COMPETENCY_BELOW_THRESHOLD"
            else:
                decision, reason = "Deferred", "SIGNOFF_PENDING"
            lag = int(rng.random() * 2)
            reviews.append({
                "readiness_review_id": f"RDR-{num}-{review_number}",
                "enrolment_id": eid,
                "review_number": review_number,
                "review_date": day,
                "recorded_at": at(add_business_days(day, lag) if lag else day, 16),
                "decision": decision,
                "decision_reason_code": reason,
                "reviewer_role": "Operations manager",
                "policy_version": config["run"]["policy_version"],
                "completion_gate_passed": int(completion_ok),
                "certification_gate_passed": int(cert_ok),
                "competency_gate_passed": int(competency_ok),
                "review_competency_score": score,
                "signoff_recorded": int(signoff),
            })
            # Only re-review when something can still change.
            if decision == "Approved" or reason not in ("CERTIFICATION_PENDING", "SIGNOFF_PENDING"):
                break
            day = add_business_days(day, uniform_int(rng, cfg["re_review_min_days"], cfg["re_review_max_days"]))
    return reviews


# --------------------------------------------------------------------------
# Observe as of a date, validate, write
# --------------------------------------------------------------------------

def observe(cases: list[Case], attempts: list[dict], reviews: list[dict],
            config: dict, as_of: date) -> dict[str, list[dict]]:
    """Keep records that were entered by the end of the as-of date."""
    cutoff = at(as_of, 23, 59)
    policy = config["run"]["policy_version"]
    t = {name: [] for name in TABLES}
    for c in config["certification"]["types"]:
        t["certification_type"].append({
            "certification_id": c["certification_id"], "certification_code": c["certification_code"],
            "certification_name": c["certification_name"],
            "mandatory_for_readiness": int(c["mandatory_for_readiness"]),
            "pass_mark": c["pass_mark"], "max_attempts": c["max_attempts"], "policy_version": policy})
    for case in sorted(cases, key=lambda c: c.case_id):
        if case.opened_recorded > cutoff:
            continue
        t["watchlist_case"].append({
            "watchlist_case_id": case.case_id, "enrolment_id": case.enrolment_id,
            "opened_effective_date": case.opened, "opened_recorded_at": case.opened_recorded,
            "primary_reason_code": case.reason, "severity": case.severity,
            "trigger_programme_week": case.trigger_week, "source_type": case.source_type,
            "policy_version": policy})
        t["watchlist_case_event"].append({
            "watchlist_event_id": f"WLE-{case.case_id[4:]}-O", "watchlist_case_id": case.case_id,
            "event_type": "Opened", "effective_date": case.opened, "recorded_at": case.opened_recorded,
            "closure_reason": None, "recorded_by_role": "Training lead"})
        if case.closed and case.closed_recorded <= cutoff:
            t["watchlist_case_event"].append({
                "watchlist_event_id": f"WLE-{case.case_id[4:]}-C", "watchlist_case_id": case.case_id,
                "event_type": "Closed", "effective_date": case.closed, "recorded_at": case.closed_recorded,
                "closure_reason": case.closure_reason, "recorded_by_role": "Programme coordinator"})
        t["coaching_action"] += [a for a in case.actions if a["recorded_at"] <= cutoff]
    t["certification_attempt"] = sorted((a for a in attempts if a["recorded_at"] <= cutoff),
                                        key=lambda a: a["certification_attempt_id"])
    t["readiness_review"] = sorted((r for r in reviews if r["recorded_at"] <= cutoff),
                                   key=lambda r: r["readiness_review_id"])
    t["coaching_action"].sort(key=lambda a: a["coaching_action_id"])
    return t


def _cell(value):
    if value is None:
        return ""                        # empty CSV field = SQL NULL
    if isinstance(value, datetime):
        return ts(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def validate(t: dict[str, list[dict]], b1: Build01, config: dict, as_of: date) -> list[str]:
    """Business-rule checks on the generated tables (the SQL validation
    queries repeat them independently in the database). Returns problems."""
    problems = []
    def D(v) -> date:   # accepts date, datetime or the CSV text form
        if isinstance(v, datetime):
            return v.date()
        return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])
    enrolments = {e["enrolment_id"] for e in b1.enrolments}
    cases = {c["watchlist_case_id"]: c for c in t["watchlist_case"]}
    types = {c["certification_id"]: c for c in t["certification_type"]}

    for name, key in [("watchlist_case", "watchlist_case_id"), ("watchlist_case_event", "watchlist_event_id"),
                      ("coaching_action", "coaching_action_id"), ("certification_attempt", "certification_attempt_id"),
                      ("readiness_review", "readiness_review_id")]:
        ids = [r[key] for r in t[name]]
        if len(ids) != len(set(ids)):
            problems.append(f"{name}: duplicate {key}")
    for name in ("watchlist_case", "certification_attempt", "readiness_review"):
        problems += [f"{name}: unknown enrolment {r['enrolment_id']}" for r in t[name]
                     if r["enrolment_id"] not in enrolments]

    # Dates: nothing after the snapshot, recorded never before effective.
    for name, eff_col in [("watchlist_case", "opened_effective_date"), ("watchlist_case_event", "effective_date"),
                          ("coaching_action", "action_date"), ("certification_attempt", "attempt_date"),
                          ("readiness_review", "review_date")]:
        rec_col = "opened_recorded_at" if name == "watchlist_case" else "recorded_at"
        for r in t[name]:
            if D(r[eff_col]) > as_of or D(r[rec_col]) > as_of:
                problems.append(f"{name}: dated after the snapshot")
            if D(r[rec_col]) < D(r[eff_col]):
                problems.append(f"{name}: recorded before it happened")

    # Watch-list lifecycle: one Opened, at most one Closed, close >= open, no overlap.
    ev_by_case = defaultdict(dict)
    for ev in t["watchlist_case_event"]:
        if ev["watchlist_case_id"] not in cases:
            problems.append("event for unknown case")
            continue
        if ev["event_type"] in ev_by_case[ev["watchlist_case_id"]]:
            problems.append(f"case {ev['watchlist_case_id']}: two {ev['event_type']} events")
        ev_by_case[ev["watchlist_case_id"]][ev["event_type"]] = ev
        if (ev["event_type"] == "Closed") != (ev["closure_reason"] is not None):
            problems.append("closure_reason must be set on Closed events only")
    periods = defaultdict(list)
    for cid, c in cases.items():
        evs = ev_by_case.get(cid, {})
        if "Opened" not in evs:
            problems.append(f"case {cid}: no Opened event")
            continue
        close = D(evs["Closed"]["effective_date"]) if "Closed" in evs else None
        if close and close < D(c["opened_effective_date"]):
            problems.append(f"case {cid}: closed before opened")
        periods[c["enrolment_id"]].append((D(c["opened_effective_date"]), close))
    for eid, ps in periods.items():
        ps.sort(key=lambda period: period[0])          # by opening date (close may be None)
        for (o1, c1), (o2, _) in zip(ps, ps[1:]):
            if c1 is None or o2 <= c1:
                problems.append(f"enrolment {eid}: overlapping watch-list cases")

    # Coaching: inside its case's open period.
    for a in t["coaching_action"]:
        c = cases.get(a["watchlist_case_id"])
        if not c:
            problems.append("action for unknown case")
            continue
        closed = ev_by_case[c["watchlist_case_id"]].get("Closed")
        if D(a["action_date"]) < D(c["opened_effective_date"]) or (
                closed and D(a["action_date"]) > D(closed["effective_date"])):
            problems.append(f"action {a['coaching_action_id']} outside its case")

    # Certification: completed only, strictly after completion, ordered, max attempts, result = pass mark.
    pairs = defaultdict(list)
    for a in t["certification_attempt"]:
        ctype = types.get(a["certification_id"])
        done = b1.events[a["enrolment_id"]].get("completed")
        if not ctype or not done:
            problems.append(f"attempt {a['certification_attempt_id']}: no completion or unknown certification")
            continue
        if D(a["attempt_date"]) <= done[0]:
            problems.append(f"attempt {a['certification_attempt_id']}: not after completion")
        if int(a["attempt_number"]) > int(ctype["max_attempts"]):
            problems.append(f"attempt {a['certification_attempt_id']}: over max attempts")
        if (int(a["score"]) >= int(ctype["pass_mark"])) != (a["result"] == "Passed"):
            problems.append(f"attempt {a['certification_attempt_id']}: result does not match pass mark")
        pairs[(a["enrolment_id"], a["certification_id"])].append(a)
    for attempts in pairs.values():
        attempts.sort(key=lambda a: int(a["attempt_number"]))
        if [int(a["attempt_number"]) for a in attempts] != list(range(1, len(attempts) + 1)):
            problems.append("attempt numbers have gaps")
        for prev, nxt in zip(attempts, attempts[1:]):
            if D(nxt["attempt_date"]) <= D(prev["attempt_date"]) or prev["result"] == "Passed":
                problems.append("retake not after a failed earlier attempt")

    # Readiness: after completion, Approved only with every gate + sign-off, numbered in date order.
    by_enrolment = defaultdict(list)
    for r in t["readiness_review"]:
        done = b1.events[r["enrolment_id"]].get("completed")
        if not done or D(r["review_date"]) <= done[0]:
            problems.append(f"review {r['readiness_review_id']}: not after completion")
        gates = all(int(r[g]) == 1 for g in ("completion_gate_passed", "certification_gate_passed",
                                              "competency_gate_passed", "signoff_recorded"))
        if r["decision"] == "Approved" and not gates:
            problems.append(f"review {r['readiness_review_id']}: Approved without all evidence and sign-off")
        by_enrolment[r["enrolment_id"]].append(r)
    for rs in by_enrolment.values():
        rs.sort(key=lambda r: int(r["review_number"]))
        if [int(r["review_number"]) for r in rs] != list(range(1, len(rs) + 1)):
            problems.append("review numbers have gaps")
        if any(D(b["review_date"]) <= D(a["review_date"]) for a, b in zip(rs, rs[1:])):
            problems.append("reviews not in date order")
    return problems


def load_config(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def build_tables(config: dict, b1: Build01, as_of: date) -> dict[str, list[dict]]:
    """Simulate the truth, then observe it as of `as_of` (no files written)."""
    if as_of > b1.as_of:
        raise ValueError(f"as-of date {as_of} is after the Build 01 snapshot {b1.as_of}")
    seed = config["run"]["seed"]
    cases = simulate_watchlist(b1, config, seed)
    attempts = simulate_certification(b1, config, seed)
    reviews = simulate_readiness(b1, config, seed, attempts)
    return observe(cases, attempts, reviews, config, as_of)


def generate(config_path: Path = DEFAULT_CONFIG, build01_dir: Path = DEFAULT_BUILD01,
             output_dir: Path = DEFAULT_OUTPUT, as_of: date | None = None,
             build01_tables: dict | None = None) -> dict:
    """Run the whole Build 02 generation. Returns the manifest."""
    config = load_config(config_path)
    b1 = Build01(build01_tables or read_build01(build01_dir))
    as_of = as_of or b1.as_of
    seed = config["run"]["seed"]
    tables = build_tables(config, b1, as_of)
    problems = validate(tables, b1, config, as_of)
    if problems:
        raise ValueError("Generated data breaks business rules:\n  " + "\n  ".join(problems[:20]))

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "as_of_date": as_of.isoformat(),
        "policy_version": config["run"]["policy_version"],
        "config_sha256": sha256_ignoring_line_endings(config_path),
        "build01_manifest_sha256": (sha256_ignoring_line_endings(build01_dir / "generation_manifest.json")
                                    if build01_tables is None else "in-memory"),
        "files": {},
    }
    for name in TABLES:
        path = output_dir / f"{name}.csv"
        write_csv(path, [{k: _cell(v) for k, v in row.items()} for row in tables[name]])
        manifest["files"][path.name] = {"rows": len(tables[name]), "sha256": sha256(path)}
    (output_dir / "generation_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--build01-dir", type=Path, default=DEFAULT_BUILD01)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--as-of-date", type=date.fromisoformat,
                        help="earlier as-of date (default: Build 01's snapshot date)")
    args = parser.parse_args()
    manifest = generate(args.config, args.build01_dir, args.output_dir, args.as_of_date)
    print(f"Build 02 synthetic data written to {args.output_dir}")
    print(f"  seed={manifest['seed']}  as_of_date={manifest['as_of_date']}  policy={manifest['policy_version']}")
    for name, info in manifest["files"].items():
        print(f"  {name:<28} {info['rows']:>5} rows  sha256={info['sha256'][:12]}")


if __name__ == "__main__":
    main()
