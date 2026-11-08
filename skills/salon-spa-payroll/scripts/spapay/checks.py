"""Reconciliation checks after the calculation: every input total must land in pay.

Each check recounts an input file directly (not from the engine's own tallies)
and compares it to what the earnings lines paid. A variance is a FAIL unless the
owner approved it in period.json -> approved_variances.
"""
from __future__ import annotations

from collections import defaultdict

from .util import D, ZERO

TOL = D("0.01")


def _approved(period, check, loc):
    for av in period.approved_variances:
        if av.get("check") == check and av.get("location_id") in (None, "", "*", loc):
            return av
    return None


def run_checks(cfg, period, inputs, result):
    rows, lines, emps = inputs.rows, result.lines, inputs.employees
    checks = []

    def add(check, loc, input_total, paid_total, note=""):
        variance = (paid_total - input_total).quantize(D("0.01"))
        status = "PASS" if abs(variance) <= TOL else "FAIL"
        av = None
        if status == "FAIL":
            av = _approved(period, check, loc)
            if av and abs(variance) <= D(av.get("max_variance", "0")):
                status = "PASS*"
                note = (note + "; " if note else "") + f"approved variance: {av.get('reason', '')} ({av.get('approved_by', '')})"
        checks.append({"check": check, "location_id": loc, "input_total": input_total, "paid_total": paid_total,
                       "variance": variance, "status": status, "note": note})

    def exempt(emp_id):
        role = cfg.roles.get(emps[emp_id].role, {})
        return bool(role.get("exempt")) or role.get("pay_basis") == "salary"

    def piece_roles(emp_id):
        return {r for r in emps[emp_id].roles()
                if cfg.roles.get(r, {}).get("pay_basis") in ("piece_service_hour", "piece_per_service", "service_revenue_pct")}

    by_loc_lines = defaultdict(list)
    for l in lines:
        by_loc_lines[l["location_id"]].append(l)

    for loc in cfg.locations:
        L = by_loc_lines.get(loc, [])
        in_period = lambda r: period.start <= r["date"] <= period.end

        # 1. service hours of piece-rate staff -> paid service hours
        svc_in = sum((r["service_hours"] for r in rows.get("services", [])
                      if r["loc"] == loc and in_period(r) and piece_roles(r["emp"])), ZERO)
        svc_paid = sum((l["hours"] or ZERO for l in L
                        if l["pay_code"] in ("service_wages", "service_per_unit", "service_commission")), ZERO)
        if svc_in or svc_paid:
            add("Service hours paid", loc, svc_in, svc_paid)

        # 2. tips
        for tip_type, code in (("card", "card_tips"), ("cash", "cash_tips")):
            t_in = sum((r["amount"] for r in rows.get("tips", []) if r["loc"] == loc and r["tip_type"] == tip_type), ZERO)
            t_paid = sum((l["amount"] for l in L if l["pay_code"] == code), ZERO)
            if t_in or t_paid:
                add(f"{tip_type.title()} tips passed through", loc, t_in, t_paid)

        # 3. time entries (paid kinds of time) -> hours on time/hourly lines
        time_codes = {"regular", "overtime", "doubletime", "nonproductive_time"}
        expected = ZERO
        for r in rows.get("time_entries", []):
            if r["loc"] != loc or exempt(r["emp"]):
                continue
            role_id = r.get("role") or emps[r["emp"]].role
            rule = cfg.time_pay(role_id, r["category"])
            basis_kind = cfg.roles.get(role_id, {}).get("pay_basis")
            if rule is None and basis_kind == "hourly":
                rule = {"basis": "base_rate", "pay_code": "regular"}
            if rule is None or rule.get("basis") == "unpaid":
                continue
            time_codes.add(rule.get("pay_code") or r["category"])
            expected += r["hours"]
        paid = sum((l["hours"] or ZERO for l in L if l["pay_code"] in time_codes
                    and l["pay_code"] != "nonproductive_time" and l["rule"] != "R-OT-TRUEUP"
                    and not l["rule"].startswith("R-TIMEOFF")), ZERO)
        if expected or paid:
            add("Paid time hours (regular + OT + paid non-service time)", loc, expected, paid)

        # 4. time off hours -> time-off lines
        to_expected = ZERO
        to_codes = set()
        for r in rows.get("time_off", []):
            if r["loc"] != loc:
                continue
            rule = cfg.time_off_pay(emps[r["emp"]].role, r["type"])
            if not rule or rule.get("basis") == "unpaid":
                continue
            if exempt(r["emp"]) and rule.get("basis") == "base_rate":
                continue
            to_codes.add(rule.get("pay_code") or r["type"])
            to_expected += r["hours"]
        to_paid = sum((l["hours"] or ZERO for l in L if l["rule"].startswith("R-TIMEOFF") or
                       (l["rule"] == "R-REGULAR-RATE" and l["pay_code"] in to_codes)), ZERO)
        if to_expected or to_paid:
            add("Time-off hours paid", loc, to_expected, to_paid)

        # 5. adjustments
        adj_in = sum((r["amount"] if r.get("amount") is not None else (r.get("hours") or ZERO) * (r.get("rate") or ZERO)
                      for r in rows.get("adjustments", []) if r["loc"] == loc), ZERO)
        adj_paid = sum((l["amount"] for l in L if l["rule"] == "R-ADJ"), ZERO)
        if adj_in or adj_paid:
            add("Approved adjustments", loc, adj_in.quantize(D("0.01")), adj_paid)

    # 6. every line maps to a processor code
    unmapped = sorted({l["pay_code"] for l in lines if not (cfg.pay_codes.get(l["pay_code"]) or {}).get("code")})
    checks.append({"check": "Every pay type has a processor code", "location_id": "*", "input_total": D(len(lines)),
                   "paid_total": D(len(lines) - sum(1 for l in lines if l["pay_code"] in unmapped)),
                   "variance": D(len([l for l in lines if l["pay_code"] in unmapped])),
                   "status": "FAIL" if unmapped else "PASS",
                   "note": ("missing: " + ", ".join(unmapped)) if unmapped else ""})

    return checks


def headcount(cfg, inputs, lines):
    seen = defaultdict(set)
    for l in lines:
        seen[(l["location_id"], l["role"])].add(l["employee_id"])
    return {k: len(v) for k, v in seen.items()}
