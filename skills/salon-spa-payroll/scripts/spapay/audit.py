"""Independent audit: recompute every employee's pay a second way and compare.

This module deliberately shares no calculation code with calc.py. It re-reads
the same canonical rows and the same rules, but walks them employee by employee
with its own lookups, tiers and rounding. Checks that compare a workbook to
itself miss the errors that matter; a second, separate computation does not.

Overtime: the audit recomputes weekly overtime hours on its own for every
workweek it can see in full. Daily-overtime states, boundary weeks and regular-
rate uplifts are verified through the identity that straight time for all hours
plus half-time premium must equal what the engine paid (the "two methods agree"
check).
"""
from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP

from .util import D, ZERO, money, week_start

OT_CODES = {"regular", "overtime", "doubletime", "ot_premium", "min_wage_makeup"}


def _rate(rates, emp, role, day):
    best_eff, best = None, None
    for eff, rate, _ in rates.get((emp, role), []):
        if eff is None or eff <= day:
            if best is None or (eff is not None and (best_eff is None or eff > best_eff)):
                best_eff, best = eff, rate
    return best


def _pct(rate):
    """Percent rates are always written as percents: 10 means 10%, 1 means 1%, 0.5 means 0.5%."""
    return D(rate) / 100


def _code(text):
    return (text or "").split(":")[0].strip().upper()


def audit(cfg, period, inputs, result):
    emps, rates, rows = inputs.employees, inputs.rates, inputs.rows
    expected = defaultdict(lambda: ZERO)          # (emp, pay_code) -> $
    hourly_week = defaultdict(lambda: ZERO)       # (emp, week) -> hours at base rate (hourly roles)
    hourly_pay = defaultdict(lambda: ZERO)        # emp -> straight $ at base rate
    notes = []

    def role_of_service(emp, category):
        for r in emp.roles():
            if category in (cfg.roles.get(r, {}).get("service_categories") or []):
                return r
        return emp.role

    def exempt(emp):
        role = cfg.roles.get(emp.role, {})
        return bool(role.get("exempt")) or role.get("pay_basis") == "salary"

    for r in rows.get("services", []):
        if not (period.start <= r["date"] <= period.end):
            continue
        emp = emps[r["emp"]]
        role = role_of_service(emp, r["category"])
        basis = cfg.roles.get(role, {}).get("pay_basis")
        rate = _rate(rates, emp.id, role, r["date"])
        if rate is None:
            continue
        if basis == "piece_service_hour":
            expected[(emp.id, "service_wages")] += r["service_hours"] * rate
        elif basis == "piece_per_service":
            expected[(emp.id, "service_per_unit")] += r["quantity"] * rate
        elif basis == "service_revenue_pct" and r.get("revenue") is not None:
            expected[(emp.id, "service_commission")] += r["revenue"] * _pct(rate)

    clocked_days = {(r["emp"], r["date"]) for r in rows.get("time_entries", []) if r["category"] == "worked"}
    for r in rows.get("time_entries", []):
        emp = emps[r["emp"]]
        if exempt(emp):
            continue
        role = r.get("role") or emp.role
        basis_kind = cfg.roles.get(role, {}).get("pay_basis")
        rule = cfg.time_pay(role, r["category"])
        if rule is None and basis_kind == "hourly":
            rule = {"basis": "base_rate", "pay_code": "regular"}
        if rule is None or rule["basis"] in ("unpaid", "regular_rate"):
            continue
        if rule["basis"] == "min_wage":
            rate = cfg.min_wage(r["loc"], r["date"])
        elif rule["basis"] == "fixed":
            rate = D(rule["fixed_rate"])
        else:
            rate = _rate(rates, emp.id, role, r["date"]) or ZERO
        if basis_kind == "hourly" and rule["basis"] == "base_rate":
            hourly_week[(emp.id, week_start(r["date"], cfg.workweek_start))] += r["hours"]
            hourly_pay[emp.id] += r["hours"] * rate
            expected[(emp.id, "regular")] += r["hours"] * rate
        else:
            expected[(emp.id, rule.get("pay_code") or r["category"])] += r["hours"] * rate

    for r in rows.get("tips", []):
        code = "card_tips" if r["tip_type"] == "card" else "cash_tips"
        expected[(r["emp"], code)] += r["amount"]

    for r in rows.get("time_off", []):
        emp = emps[r["emp"]]
        rule = cfg.time_off_pay(emp.role, r["type"])
        if not rule or rule["basis"] in ("unpaid", "regular_rate"):
            continue
        if exempt(emp) and rule["basis"] == "base_rate":
            continue
        if rule["basis"] == "min_wage":
            rate = cfg.min_wage(r["loc"], r["date"])
        elif rule["basis"] == "fixed":
            rate = D(rule["fixed_rate"])
        else:
            rate = _rate(rates, emp.id, emp.role, r["date"]) or ZERO
        expected[(emp.id, rule.get("pay_code") or r["type"])] += r["hours"] * rate

    for r in rows.get("adjustments", []):
        amt = r["amount"] if r.get("amount") is not None else (r.get("hours") or ZERO) * (r.get("rate") or ZERO)
        expected[(r["emp"], r["pay_code"])] += amt

    # incentives, recomputed from scratch
    for inc in cfg.incentives:
        freq = inc.get("frequency", "pay_period")
        if freq == "monthly" and not period.include_monthly:
            continue
        lo, hi = period.window_for(inc["id"], freq) or (None, None)
        if lo is None:
            continue
        per_emp = defaultdict(lambda: ZERO)
        per_loc = defaultdict(lambda: ZERO)
        flat_pay = defaultdict(lambda: ZERO)
        for r in rows.get(inc["source"], []):
            if not (lo <= r["date"] <= hi):
                continue
            skip = False
            for ex in inc.get("exclude", []):
                if str(r.get(ex["field"]) or "").lower() in [str(v).lower() for v in ex.get("values", [])]:
                    skip = True
            if skip:
                continue
            code = _code(r.get("addon_code") or r.get("service_code") or r.get("item"))
            blob = f"{r.get('addon_name') or ''} {r.get('service_name') or ''} {r.get('item') or ''}".lower()
            hit = None
            for e in inc["rates"]:
                v = str(e.get("value", "")).strip()
                ok = (e["match"] == "any" or (e["match"] == "code_prefix" and code.startswith(v.upper()))
                      or (e["match"] == "code" and code == v.upper())
                      or (e["match"] == "category" and (r.get("category") or "") == v.lower())
                      or (e["match"] == "item_contains" and v.lower() in blob))
                if ok:
                    hit = e
                    break
            if hit is None or (hit.get("only_employees") and r["emp"] not in hit["only_employees"]):
                continue
            base = (r.get("quantity") or ZERO) if inc["kind"] == "per_unit" else \
                ((r.get("amount") if inc["source"] == "sales" else r.get("revenue")) or ZERO)
            if inc.get("credit", "seller") == "location":
                per_loc[r["loc"]] += base
                continue
            emp = emps[r["emp"]]
            elig_roles, elig_emps = inc.get("eligible_roles") or [], inc.get("eligible_employees") or []
            if (elig_roles or elig_emps) and not (emp.id in elig_emps or set(emp.roles()) & set(elig_roles)):
                continue
            scope = (emp.id, r["loc"]) if inc.get("tier_scope", "employee_location") == "employee_location" else (emp.id, None)
            per_emp[scope] += base
            if not inc.get("tiers"):
                rate = D(hit["rate"])
                flat_pay[scope] += base * (rate if inc["kind"] == "per_unit" else _pct(rate))
        code_key = inc.get("pay_code") or inc["id"]
        if inc.get("credit", "seller") == "location":
            for loc, base in per_loc.items():
                pay = _tier_pay(inc, base) if inc.get("tiers") else base * _first_rate(inc)
                for rec in inc.get("recipients", []):
                    if rec["location_id"] == loc:
                        expected[(rec["employee_id"], code_key)] += pay * D(rec.get("share", 1))
        elif inc.get("tiers"):
            for (emp_id, _), base in per_emp.items():
                expected[(emp_id, code_key)] += _tier_pay(inc, base) if base > 0 else ZERO
        else:
            for (emp_id, _), pay in flat_pay.items():
                expected[(emp_id, code_key)] += pay if pay > 0 else ZERO

    # salaries and stipends
    days = (period.end - period.start).days + 1
    for emp in emps.values():
        if cfg.roles.get(emp.role, {}).get("pay_basis") != "salary":
            continue
        if (emp.termination_date and emp.termination_date < period.start) or (emp.hire_date and emp.hire_date > period.end):
            continue
        opts = rates.get((emp.id, emp.role), [])
        if not opts:
            continue
        eff, rate, rtype = sorted(opts, key=lambda o: (o[0] is not None, o[0] or period.end))[-1]
        per = rate / cfg.periods_per_year() if rtype == "salary_annual" else rate
        if period.salary_proration is not None:
            factor = period.salary_proration
        else:
            first = max(period.start, emp.hire_date) if emp.hire_date else period.start
            last = min(period.end, emp.termination_date) if emp.termination_date else period.end
            factor = D((last - first).days + 1) / D(days)
        expected[(emp.id, "salary")] += per * factor
    from .util import parse_date
    for st in cfg.stipends:
        eff = parse_date(st.get("effective_from")) if st.get("effective_from") else None
        thru = parse_date(st.get("effective_through")) if st.get("effective_through") else None
        if (eff and eff > period.end) or (thru and thru < period.start):
            continue
        expected[(st["employee_id"], st.get("pay_code") or "stipend")] += D(st["amount"])

    # bonus pools
    metrics = defaultdict(dict)
    for r in rows.get("location_metrics", []):
        metrics[(r["loc"], r.get("window_start"), r.get("window_end"))][r["metric"]] = r["value"]
    for bp in cfg.bonus_pools:
        freq = bp.get("frequency", "monthly")
        if freq == "monthly" and not period.include_monthly:
            continue
        win = period.window_for(bp["id"], freq)
        for rec in bp.get("recipients", []):
            loc = rec["location_id"]
            vals = metrics.get((loc, win[0], win[1]) if win else None) or metrics.get((loc, None, None))
            if not vals:
                continue
            earned = ZERO
            for m in bp.get("metrics", []):
                num, den = vals.get(m["numerator"]), (vals.get(m["denominator"]) if m.get("denominator") else D(1))
                if num is None or den is None:
                    earned = None
                    break
                value = num / den if den else ZERO
                op, thr = m.get("compare", ">="), D(m["threshold"])
                if (op == ">=" and value >= thr) or (op == ">" and value > thr) or (op == "<=" and value <= thr) or (op == "<" and value < thr):
                    earned += D(m["weight"])
            if earned is not None:
                expected[(rec["employee_id"], bp.get("pay_code") or "bonus")] += D(bp["pool_per_location"]) * earned * D(rec.get("share", 1))

    # compare everything except the overtime family
    paid = defaultdict(lambda: ZERO)
    for l in result.lines:
        paid[(l["employee_id"], l["pay_code"])] += l["amount"]
    rr_codes = {l["pay_code"] for l in result.lines if l["rule"] in ("R-REGULAR-RATE", "R-TIME-REGULAR-RATE")}
    mismatches = []
    keys = (set(expected) | set(paid))
    for key in sorted(keys):
        emp_id, code = key
        if code in OT_CODES or code in rr_codes or code == "nonproductive_time":
            continue
        exp_amt, got = money(expected.get(key, ZERO)), paid.get(key, ZERO)
        if abs(exp_amt - got) > D("0.02"):  # line-level rounding can differ by a cent per line
            mismatches.append({"employee_id": emp_id, "employee": emps[emp_id].name if emp_id in emps else emp_id,
                               "pay_code": code, "engine": got, "audit": exp_amt, "difference": got - exp_amt})

    # overtime family: straight time for every hour + premium must agree both ways
    ot_rows = []
    week_by_emp = defaultdict(list)
    for w in result.weeks:
        week_by_emp[w["employee_id"]].append(w)
    for emp_id in sorted({l["employee_id"] for l in result.lines if l["pay_code"] in OT_CODES} | set(hourly_pay)):
        engine_total = sum((paid.get((emp_id, c), ZERO) for c in OT_CODES), ZERO)
        straight = money(hourly_pay.get(emp_id, ZERO))
        premium = sum((w["premium_now"] for w in week_by_emp.get(emp_id, [])), ZERO)
        makeup = sum((w["makeup_now"] for w in week_by_emp.get(emp_id, [])), ZERO)
        trueup = sum((l["amount"] for l in result.lines if l["employee_id"] == emp_id and l["rule"] == "R-OT-TRUEUP"), ZERO)
        independent = straight + money(premium) + money(makeup) + trueup
        # independent weekly OT hours where the whole week is in this period and no daily rule applies
        for w in week_by_emp.get(emp_id, []):
            if w["prior_hours"] == 0:
                loc_states = {cfg.locations[l]["state"] for l in cfg.locations}
                if not any(cfg.state_rules.get(s, {}).get("daily_ot") for s in loc_states):
                    thr = D(next(iter(cfg.state_rules.values())).get("weekly_ot_threshold", 40)) if cfg.state_rules else D(40)
                    own_ot = max(ZERO, w["total_hours"] - thr)
                    if abs(own_ot - w["ot_hours"]) > D("0.01"):
                        mismatches.append({"employee_id": emp_id, "employee": emps[emp_id].name, "pay_code": f"OT hours week {w['week_start']}",
                                           "engine": w["ot_hours"], "audit": own_ot, "difference": w["ot_hours"] - own_ot})
        diff = engine_total - independent
        ot_rows.append({"employee_id": emp_id, "employee": emps[emp_id].name, "engine": engine_total,
                        "straight_plus_premium": independent, "difference": diff})
        if abs(diff) > D("0.05"):
            mismatches.append({"employee_id": emp_id, "employee": emps[emp_id].name, "pay_code": "hourly + overtime family",
                               "engine": engine_total, "audit": independent, "difference": diff})
    return {"mismatches": mismatches, "ot_equivalence": ot_rows, "notes": notes,
            "status": "PASS" if not mismatches else "FAIL"}


def _tiers(inc):
    out = []
    for t in sorted(inc["tiers"], key=lambda t: D(t["from"])):
        rate = D(t["rate"])
        out.append((D(t["from"]), D(t["to"]) if t.get("to") not in (None, "") else None,
                    rate if inc["kind"] == "per_unit" else _pct(rate)))
    return out


def _tier_pay(inc, base):
    if base <= 0:
        return ZERO
    tiers = _tiers(inc)
    if inc.get("tier_method", "marginal") == "highest":
        best = ZERO
        for lo, _, rate in tiers:
            if base >= lo:
                best = rate
        return base * best
    total = ZERO
    for lo, hi, rate in tiers:
        start = lo - 1 if inc["kind"] == "per_unit" else lo
        end = base if hi is None else min(hi, base)
        if end > start:
            total += (end - start) * rate
    return total


def _first_rate(inc):
    rate = D(inc["rates"][0].get("rate"), ZERO)
    return rate if inc["kind"] == "per_unit" else _pct(rate)
