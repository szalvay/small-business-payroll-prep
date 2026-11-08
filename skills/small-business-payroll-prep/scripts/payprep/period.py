"""Pay periods, the workspace layout, and the cross-period hours history.

Workspace layout:
    <workspace>/payroll_config.json
    <workspace>/PAY_RULES_BOOK.md
    <workspace>/history/weeks.json          (hours/OT per workweek, written by each run)
    <workspace>/periods/<start>_<end>/period.json
                                    /raw/      POS + HRIS exports exactly as downloaded
                                    /inputs/   canonical CSVs the engine reads
                                    /output/   workbook, processor file(s), summary, evidence
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from .util import D, ZERO, parse_date, read_json, write_json, workweeks

CONFIG_NAME = "payroll_config.json"


def find_workspace(start: Path) -> Path:
    start = Path(start).resolve()
    for candidate in [start, *start.parents]:
        if (candidate / CONFIG_NAME).exists():
            return candidate
    raise FileNotFoundError(f"no {CONFIG_NAME} found at or above {start}")


class Period:
    def __init__(self, period_dir):
        self.dir = Path(period_dir).resolve()
        self.data = read_json(self.dir / "period.json")
        d = self.data
        self.start = parse_date(d["period_start"])
        self.end = parse_date(d["period_end"])
        if self.end < self.start:
            raise ValueError("period_end is before period_start")
        self.pay_date = parse_date(d.get("pay_date")) if d.get("pay_date") else None
        self.id = f"{self.start.isoformat()}_{self.end.isoformat()}"
        self.include_monthly = bool(d.get("include_monthly"))
        mw = d.get("monthly_window") or {}
        self.monthly_window = (
            (parse_date(mw["start"]), parse_date(mw["end"])) if mw.get("start") and mw.get("end") else None
        )
        self.windows = {
            key: (parse_date(v["start"]), parse_date(v["end"]))
            for key, v in (d.get("windows") or {}).items()
        }
        self.attestations = d.get("attestations", [])
        self.sources = d.get("sources", [])
        self.approved_variances = d.get("approved_variances", [])
        self.expected_activity = d.get("expected_activity", [])
        self.acknowledged = d.get("acknowledged_warnings", [])
        self.salary_proration = D(d.get("salary_proration")) if d.get("salary_proration") not in (None, "") else None
        self.notes = d.get("notes", "")
        self.inputs_dir = self.dir / "inputs"
        self.output_dir = self.dir / "output"
        self.raw_dir = self.dir / "raw"

    def days(self):
        day = self.start
        while day <= self.end:
            yield day
            day += _dt.timedelta(days=1)

    def window_for(self, key, frequency):
        """Date window an incentive/bonus pays on. Explicit window > monthly > pay period."""
        if key in self.windows:
            return self.windows[key]
        if frequency == "monthly":
            return self.monthly_window
        return (self.start, self.end)

    def attested_none(self, input_name, location_id=None):
        for a in self.attestations:
            if a.get("input") != input_name:
                continue
            if a.get("location_id") in (None, "", "*") or a.get("location_id") == location_id:
                return a
        return None


def new_period(workspace, start, end, pay_date=None, include_monthly=False, monthly_window=None):
    workspace = Path(workspace)
    start, end = parse_date(start), parse_date(end)
    pid = f"{start.isoformat()}_{end.isoformat()}"
    pdir = workspace / "periods" / pid
    for sub in ("raw", "inputs", "output"):
        (pdir / sub).mkdir(parents=True, exist_ok=True)
    if not (pdir / "period.json").exists():
        data = {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "pay_date": parse_date(pay_date).isoformat() if pay_date else None,
            "include_monthly": bool(include_monthly),
            "monthly_window": monthly_window,
            "windows": {},
            "attestations": [],
            "sources": [],
            "approved_variances": [],
            "expected_activity": [],
            "acknowledged_warnings": [],
            "salary_proration": None,
            "notes": "",
        }
        write_json(pdir / "period.json", data)
    return pdir


# --- history -----------------------------------------------------------------

class History:
    """Per-day hours and per-week overtime already paid, across pay periods.

    Needed because pay periods and workweeks do not line up: a workweek that
    straddles two pay periods owes overtime on its combined hours (the boundary
    week), and monthly commissions paid later raise the regular rate of weeks
    that were already paid.
    """

    def __init__(self, workspace):
        self.path = Path(workspace) / "history" / "weeks.json"
        if self.path.exists():
            self.data = read_json(self.path)
        else:
            self.data = {"days": {}, "weeks": {}}

    @staticmethod
    def _dkey(emp, employer, day):
        return f"{emp}|{employer}|{day.isoformat()}"

    @staticmethod
    def _wkey(emp, employer, week):
        return f"{emp}|{employer}|{week.isoformat()}"

    def day(self, emp, employer, day, exclude_period=None):
        rec = self.data["days"].get(self._dkey(emp, employer, day))
        if not rec or rec.get("period") == exclude_period:
            return None
        return rec

    def paid_for_week(self, emp, employer, week, exclude_period):
        recs = self.data["weeks"].get(self._wkey(emp, employer, week), {})
        total = {"ot": ZERO, "dt": ZERO, "premium": ZERO, "makeup": ZERO}
        for pid, rec in recs.items():
            if pid == exclude_period:
                continue
            for k in total:
                total[k] += D(rec.get(k), ZERO)
        return total

    def week_record(self, emp, employer, week, exclude_period=None):
        """Combined record for a week across periods other than exclude_period."""
        recs = self.data["weeks"].get(self._wkey(emp, employer, week), {})
        return {pid: rec for pid, rec in recs.items() if pid != exclude_period}

    def has_any(self):
        return bool(self.data["days"])

    def periods(self):
        """(start, end) of every period that has written history in this workspace."""
        ids = {rec.get("period") for rec in self.data["days"].values()}
        for weeks in self.data["weeks"].values():
            ids.update(weeks)
        out = []
        for pid in ids:
            try:
                lo, hi = (parse_date(x) for x in str(pid).split("_"))
                out.append((lo, hi))
            except (ValueError, TypeError):
                continue
        return sorted(out)

    def record(self, period_id, day_rows, week_rows):
        # drop prior entries written by this same period (idempotent re-runs)
        self.data["days"] = {k: v for k, v in self.data["days"].items() if v.get("period") != period_id}
        for weeks in self.data["weeks"].values():
            weeks.pop(period_id, None)
        for (emp, employer, day), rec in day_rows.items():
            self.data["days"][self._dkey(emp, employer, day)] = {**rec, "period": period_id}
        for (emp, employer, week), rec in week_rows.items():
            self.data["weeks"].setdefault(self._wkey(emp, employer, week), {})[period_id] = rec
        write_json(self.path, self.data)


def boundary_weeks(period, workweek_start):
    """Workweeks that start before the period (their earlier days were paid last period)."""
    return [w for w in workweeks(period.start, period.end, workweek_start) if w < period.start]
