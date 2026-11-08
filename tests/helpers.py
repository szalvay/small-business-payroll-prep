"""Tiny workspace builder for the engine tests. Everything here is made up."""
import copy
import csv
import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "small-business-payroll-prep"
sys.path.insert(0, str(SKILL / "scripts"))

from payprep.config import Config  # noqa: E402
from payprep.inputs import SPEC  # noqa: E402
from payprep.run import run_period  # noqa: E402

PAY_CODES = {k: {"label": k, "code": k.upper(), "export_as": "hours" if k in ("regular", "overtime", "doubletime") else "amount"}
             for k in ("service_wages", "service_per_unit", "service_commission", "regular", "overtime", "doubletime",
                       "ot_premium", "card_tips", "cash_tips", "salary", "min_wage_makeup", "nonproductive_time",
                       "rest_recovery", "lobby", "training", "sick", "pto", "enhancements", "retail_commission",
                       "membership_commission", "gc_commission", "bonus", "stipend", "back_pay", "mgr_override")}

BASE = {
    "schema_version": "1.0",
    "company": {"name": "Test Spa", "pay_frequency": "semi_monthly", "workweek_start": "sunday",
                "ot_aggregation": "employer", "min_wage_makeup": "flag", "cash_tips": "report_only"},
    "approval": {},
    "systems": {"payroll": "generic"},
    "employers": [{"id": "E1", "legal_name": "Test Spa LLC"}],
    "locations": [
        {"id": "A", "name": "Alpha", "employer_id": "E1", "state": "OR",
         "min_wage": [{"rate": "15.00", "effective_from": "2026-01-01"}], "pos_labels": ["Alpha Spa"]},
        {"id": "B", "name": "Beta", "employer_id": "E1", "state": "OR",
         "min_wage": [{"rate": "15.00", "effective_from": "2026-01-01"}], "pos_labels": ["Beta Spa"]},
    ],
    "state_rules": {"OR": {"weekly_ot_threshold": "40", "daily_ot": None, "confirmed_by_owner": True},
                    "CA": {"weekly_ot_threshold": "40", "daily_ot": {"threshold": "8", "double_threshold": "12"},
                           "seventh_day_ot": True, "confirmed_by_owner": True}},
    "roles": [
        {"id": "lmt", "label": "LMT", "pay_basis": "piece_service_hour", "hours_worked_source": "services_plus_time",
         "service_categories": ["massage"], "tips": True},
        {"id": "esty", "label": "Esthetician", "pay_basis": "piece_service_hour", "hours_worked_source": "services_plus_time",
         "service_categories": ["facial"], "tips": True},
        {"id": "fd", "label": "Front desk", "pay_basis": "hourly", "hours_worked_source": "clock", "tips": False},
        {"id": "mgr", "label": "Manager", "pay_basis": "salary", "exempt": True},
    ],
    "time_pay": [{"role": "lmt", "category": "lobby", "basis": "min_wage", "pay_code": "lobby"},
                 {"role": "lmt", "category": "training", "basis": "min_wage", "pay_code": "training"}],
    "time_off_pay": [{"role": "*", "type": "sick", "basis": "min_wage", "pay_code": "sick"},
                     {"role": "fd", "type": "sick", "basis": "base_rate", "pay_code": "sick"}],
    "incentives": [],
    "stipends": [], "bonus_pools": [], "manager_allocation": [], "employee_overrides": [],
    "pay_codes": PAY_CODES,
    "checks": {},
}


def roster_row(emp_id, first, last, role, loc="A", status="active", hire="2020-01-01", term="", secondary="", pos_names=""):
    return {"employee_id": emp_id, "first_name": first, "last_name": last, "status": status, "hire_date": hire,
            "termination_date": term, "home_location": loc, "role": role, "secondary_role": secondary, "pos_names": pos_names}


class Workspace:
    def __init__(self, config_changes=None, approve=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = copy.deepcopy(BASE)
        for key, value in (config_changes or {}).items():
            self.cfg[key] = value
        self.approve = approve
        self.save_config()

    def save_config(self):
        if self.approve:
            self.cfg["approval"] = {}
            self.cfg["approval"] = {"approved_by": "Tester", "approved_on": "2026-01-01",
                                    "rules_fingerprint": Config(self.cfg).fingerprint()}
        (self.root / "payroll_config.json").write_text(json.dumps(self.cfg, indent=2))

    def period(self, start, end, roster, rates, files=None, **period_fields):
        pdir = self.root / "periods" / f"{start}_{end}"
        (pdir / "inputs").mkdir(parents=True, exist_ok=True)
        data = {"period_start": start, "period_end": end, "pay_date": end, "include_monthly": False,
                "monthly_window": None, "windows": {}, "attestations": [], "sources": [], "approved_variances": [],
                "expected_activity": [], "salary_proration": None,
                "acknowledged_warnings": [{"code": "GATE_NO_SOURCES", "by": "Tester", "note": "unit test"},
                                          {"code": "GATE_HISTORY_GAP", "by": "Tester", "note": "unit test"}]}
        files = dict(files or {})
        if "time_off" not in files and not period_fields.get("keep_time_off_gate"):
            data["attestations"].append({"input": "time_off", "location_id": "*", "statement": "none", "by": "Tester"})
        for name in ("tips", "time_entries", "services", "addons", "sales"):
            if name not in files:
                data["attestations"].append({"input": name, "statement": "none this period", "by": "Tester"})
        period_fields.pop("keep_time_off_gate", None)
        data.update(period_fields)
        (pdir / "period.json").write_text(json.dumps(data, indent=2))
        self._csv(pdir / "inputs" / "roster.csv", "roster", roster)
        self._csv(pdir / "inputs" / "pay_rates.csv", "pay_rates",
                  [{"employee_id": e, "role": r, "rate": str(rate), "rate_type": t, "effective_from": eff}
                   for e, r, rate, t, eff in rates])
        for name, rows in files.items():
            self._csv(pdir / "inputs" / f"{name}.csv", name, rows)
        return pdir

    @staticmethod
    def _csv(path, name, rows):
        cols = list(SPEC[name])
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in cols})

    def run(self, pdir, **kw):
        return run_period(pdir, **kw)

    def close(self):
        self.tmp.cleanup()


def total(out, emp_id=None, pay_code=None, field="amount"):
    s = Decimal("0")
    for l in out["result"].lines:
        if (emp_id is None or l["employee_id"] == emp_id) and (pay_code is None or l["pay_code"] == pay_code):
            s += (l[field] or Decimal("0"))
    return s


def codes(findings, severity=None):
    return {i["code"] for i in findings.items if severity is None or i["severity"] == severity}


def svc(emp, day, hours, cat="massage", code="MS60", loc="A", qty=None, revenue="100", refund=""):
    """One service line; quantity defaults to one service per hour so averages look real."""
    if qty is None:
        qty = str(max(1, round(float(hours))))
    return {"employee_id": emp, "location": loc, "date": day, "service_code": code, "category": cat,
            "quantity": qty, "service_hours": str(hours), "revenue": revenue, "refund": refund}


def clock(emp, day, hours, loc="A", category="worked"):
    return {"employee_id": emp, "location": loc, "date": day, "category": category, "hours": str(hours)}
