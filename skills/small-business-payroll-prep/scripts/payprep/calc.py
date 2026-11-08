"""The pay engine: turns canonical inputs + the owner's rules into earnings lines.

Order of work (each step only reads what earlier steps produced):
  1. service pay (piece rate per service hour / per service / % of revenue)
  2. time pay (hourly work, lobby, training, trainer ...) and hours worked per day
  3. tips, time off, adjustments
  4. incentives (add-on spiffs, retail, memberships, gift cards ...) with tiers and windows
  5. salaries, stipends, manager bonus pools
  6. overtime per workweek (boundary weeks across pay periods, daily rules, regular
     rate including commissions), minimum-wage floor, regular-rate time pay
  7. overtime true-up for monthly incentives paid after the weeks they were earned
Everything is computed in Decimal and rounded to cents once per line.
"""
from __future__ import annotations

import datetime as _dt
from collections import defaultdict
from dataclasses import dataclass, field

from .util import CENT, D, ZERO, Findings, fmt_money, money, parse_date, week_start
from .gates import active_windows

HALF = D("0.5")
ONE_HALF = D("1.5")
TWO = D("2")
RATE_TYPE_FOR_BASIS = {
    "piece_service_hour": {"service_hour"},
    "piece_per_service": {"per_service"},
    "service_revenue_pct": {"service_pct"},
    "hourly": {"hourly"},
    "salary": {"salary_annual", "salary_period"},
}


@dataclass
class Result:
    lines: list = field(default_factory=list)
    weeks: list = field(default_factory=list)
    findings: Findings = field(default_factory=Findings)
    incentive_notes: list = field(default_factory=list)  # source rows no incentive paid, grouped
    history_days: dict = field(default_factory=dict)
    history_weeks: dict = field(default_factory=dict)
    paid_inputs: dict = field(default_factory=dict)    # what the engine consumed, for checks


def _pct(rate):
    """Percent rates are always written as percents: 10 means 10%, 1 means 1%, 0.5 means 0.5%."""
    return D(rate) / 100


def _units(n):
    n = D(n).normalize()
    return f"{n} unit" if n == 1 else f"{n} units"


def _norm_code(code):
    return (code or "").split(":")[0].strip().upper()


class Engine:
    def __init__(self, cfg, period, inputs, history):
        self.cfg, self.period, self.inputs, self.history = cfg, period, inputs, history
        self.r = Result()
        self.f = self.r.findings
        self.emps = inputs.employees
        self.rows = inputs.rows
        self._acc = defaultdict(lambda: {"hours": ZERO, "amount": ZERO, "dates": set(), "detail": set()})
        # day level tracking for overtime / min wage (non-exempt only)
        self.day_hours = defaultdict(lambda: defaultdict(lambda: ZERO))     # (emp, employer, date) -> loc -> hours
        self.day_straight = defaultdict(lambda: ZERO)                     # (emp, employer, date) -> $
        self.day_minreq = defaultdict(lambda: ZERO)                       # (emp, employer, date) -> $ required
        self.hourly = defaultdict(lambda: {"hours": ZERO, "amount": ZERO})  # (emp, loc, role, week, rate) -> base-rate hourly
        self.deferred_rr = []                                             # time paid at the regular rate
        self.monthly_rr = []                                              # (emp, loc, inc_id, amount, window)
        self.period_rr = defaultdict(lambda: ZERO)                        # emp -> pay-period $ in the regular rate
        self.service_day = defaultdict(lambda: ZERO)                      # (emp, date) -> service hours

    # ------------------------------------------------------------------ utils
    def employer(self, loc):
        return self.cfg.employer_of(loc)

    def exempt(self, emp_id):
        emp = self.emps[emp_id]
        role = self.cfg.roles.get(emp.role, {})
        return bool(role.get("exempt")) or role.get("pay_basis") == "salary"

    def rate(self, emp_id, role_id, day):
        rate, rtype = self.inputs.rate(emp_id, role_id, day)
        if rate is None:
            self.f.fail("CALC_NO_RATE", f"{self.emps[emp_id].name}: no {role_id} rate effective on {day}")
            return ZERO
        basis = self.cfg.roles.get(role_id, {}).get("pay_basis")
        if basis in RATE_TYPE_FOR_BASIS and rtype not in RATE_TYPE_FOR_BASIS[basis]:
            self.f.fail("CALC_RATE_TYPE", f"{self.emps[emp_id].name}: {role_id} is paid {basis} but the rate type is {rtype}")
        return rate

    def acc(self, emp, loc, role, pay_code, amount, hours=None, rate=None, day=None, rule="", detail="",
            in_rr=False, kind="earning"):
        key = (emp, loc, role, pay_code, rate, kind, rule, in_rr)
        a = self._acc[key]
        a["amount"] += amount
        if hours is not None:
            a["hours"] += hours
        if day:
            a["dates"].add(day)
        if detail:
            a["detail"].add(detail)

    def add_hours(self, emp, loc, day, hours, straight):
        if self.exempt(emp):
            return
        key = (emp, self.employer(loc), day)
        self.day_hours[key][loc] += hours
        self.day_straight[key] += straight
        self.day_minreq[key] += hours * self.cfg.min_wage(loc, day)

    def in_period(self, day):
        return self.period.start <= day <= self.period.end

    # --------------------------------------------------------------- 1 services
    def services(self):
        consumed = defaultdict(lambda: ZERO)
        for r in self.rows.get("services", []):
            if not self.in_period(r["date"]):
                continue
            emp = self.emps[r["emp"]]
            role_id = self._role_for_category(emp, r["category"], r)
            role = self.cfg.roles.get(role_id, {})
            basis = role.get("pay_basis")
            consumed[(r["loc"], "service_hours")] += r["service_hours"]
            amount = ZERO
            if basis == "piece_service_hour":
                rate = self.rate(emp.id, role_id, r["date"])
                amount = r["service_hours"] * rate
                self.acc(emp.id, r["loc"], role_id, "service_wages", amount, r["service_hours"], rate, r["date"],
                         rule="R-SVC-HOUR", in_rr=True)
                consumed[(r["loc"], "paid_service_hours")] += r["service_hours"]
            elif basis == "piece_per_service":
                rate = self.rate(emp.id, role_id, r["date"])
                amount = r["quantity"] * rate
                self.acc(emp.id, r["loc"], role_id, "service_per_unit", amount, r["service_hours"], rate, r["date"],
                         rule="R-SVC-UNIT", in_rr=True, detail=f"{r['quantity']} services")
                consumed[(r["loc"], "paid_service_hours")] += r["service_hours"]
            elif basis == "service_revenue_pct":
                rate = self.rate(emp.id, role_id, r["date"])
                if r.get("revenue") is None:
                    self.f.fail("CALC_NO_REVENUE", f"services.csv line {r['_line']}: {emp.name} is paid on service revenue but the row has no revenue")
                    continue
                amount = r["revenue"] * _pct(rate)
                self.acc(emp.id, r["loc"], role_id, "service_commission", amount, r["service_hours"], _pct(rate), r["date"],
                         rule="R-SVC-PCT", in_rr=True)
                consumed[(r["loc"], "paid_service_hours")] += r["service_hours"]
            self.service_day[(emp.id, r["date"])] += r["service_hours"]
            if role.get("hours_worked_source") == "services_plus_time" and basis != "salary":
                self.add_hours(emp.id, r["loc"], r["date"], r["service_hours"], amount)
            elif amount:
                # clock-based piece workers: hours come from the clock, earnings still count
                self.day_straight[(emp.id, self.employer(r["loc"]), r["date"])] += amount if not self.exempt(emp.id) else ZERO
        self.r.paid_inputs["services"] = dict(consumed)

    def _role_for_category(self, emp, category, row):
        roles = emp.roles()
        for role_id in roles:
            cats = self.cfg.roles.get(role_id, {}).get("service_categories") or []
            if category in cats:
                return role_id
        primary = self.cfg.roles.get(emp.role, {})
        if primary.get("service_categories"):
            self.f.warn("CALC_SVC_CATEGORY", f"services.csv line {row['_line']}: {emp.name} performed a '{category}' service, "
                        f"which is not a category of their role(s) {roles}; paid as {emp.role}")
        return emp.role

    # ------------------------------------------------------------------ 2 time
    def time(self):
        by_day = defaultdict(list)
        for r in self.rows.get("time_entries", []):
            by_day[(r["emp"], r["date"])].append(r)
        consumed = defaultdict(lambda: ZERO)
        for (emp_id, day), rows in by_day.items():
            emp = self.emps[emp_id]
            if self.exempt(emp_id):
                self.f.info("CALC_EXEMPT_TIME", f"{emp.name}: time entries on {day} ignored (exempt / salaried)")
                continue
            worked_rows = [r for r in rows if r["category"] == "worked"]
            for r in rows:
                role_id = r.get("role") or emp.role
                role = self.cfg.roles.get(role_id, {})
                basis_kind = role.get("pay_basis")
                consumed[(r["loc"], "hours")] += r["hours"]
                rule = self.cfg.time_pay(role_id, r["category"])
                piece_clock = basis_kind != "hourly" and role.get("hours_worked_source") == "clock"
                if rule is None:
                    if basis_kind == "hourly":
                        rule = {"basis": "base_rate", "pay_code": "regular"}
                    elif piece_clock and r["category"] == "worked":
                        rule = {"basis": "unpaid", "pay_code": "worked"}  # clocked shift; pay comes from services
                    else:
                        self.f.fail("CALC_NO_TIME_RULE", f"{emp.name}: no pay rule for '{r['category']}' time as {role_id} "
                                    "(add a time_pay rule in the config)")
                        continue
                counts_as_hours = True
                if piece_clock and r["category"] != "worked" and worked_rows:
                    counts_as_hours = False  # break-out inside the clocked shift
                pay, rate = self._time_pay_amount(emp_id, role_id, r, rule)
                pay_code = rule.get("pay_code") or r["category"]
                if rule["basis"] == "regular_rate":
                    if counts_as_hours:
                        self.add_hours(emp_id, r["loc"], day, r["hours"], ZERO)
                    self.deferred_rr.append((emp_id, r["loc"], role_id, day, r["hours"], pay_code, counts_as_hours))
                    continue
                if basis_kind == "hourly" and rule["basis"] == "base_rate":
                    wk = week_start(day, self.cfg.workweek_start)
                    b = self.hourly[(emp_id, r["loc"], role_id, wk, rate)]
                    b["hours"] += r["hours"]
                    b["amount"] += pay
                elif rule["basis"] != "unpaid":
                    self.acc(emp_id, r["loc"], role_id, pay_code, pay, r["hours"], rate, day,
                             rule=f"R-TIME-{r['category'].upper()}", in_rr=True)
                    consumed[(r["loc"], "paid_hours")] += r["hours"]
                if counts_as_hours:
                    self.add_hours(emp_id, r["loc"], day, r["hours"], pay)
                elif pay:
                    self.day_straight[(emp_id, self.employer(r["loc"]), day)] += pay
            self._ca_nonproductive(emp, day, rows, worked_rows)
        # piece workers paid on the clock but with no time rows that day still worked their service hours
        for (emp_id, day), svc_hours in self.service_day.items():
            emp = self.emps[emp_id]
            role = self.cfg.roles.get(emp.role, {})
            if role.get("hours_worked_source") == "clock" and role.get("pay_basis") != "hourly" and not self.exempt(emp_id):
                if (emp_id, day) not in by_day and svc_hours > 0:
                    self.f.warn("CALC_NO_CLOCK", f"{emp.name}: {svc_hours} service hours on {day} but no clocked time; "
                                "counted the service hours as hours worked")
                    loc = next((r["loc"] for r in self.rows.get("services", []) if r["emp"] == emp_id and r["date"] == day), emp.home_location)
                    key = (emp_id, self.employer(loc), day)
                    self.day_hours[key][loc] += svc_hours
                    self.day_minreq[key] += svc_hours * self.cfg.min_wage(loc, day)
        self.r.paid_inputs["time_entries"] = dict(consumed)

    def _time_pay_amount(self, emp_id, role_id, r, rule):
        basis = rule["basis"]
        if basis == "min_wage":
            rate = self.cfg.min_wage(r["loc"], r["date"])
        elif basis == "base_rate":
            rate = self.rate(emp_id, role_id, r["date"])
        elif basis == "fixed":
            rate = D(rule["fixed_rate"])
        else:
            return ZERO, None
        return r["hours"] * rate, rate

    def _ca_nonproductive(self, emp, day, rows, worked_rows):
        """States that require piece-rate workers to be paid separately for
        non-productive time (e.g. waiting between clients) get it at minimum wage."""
        role = self.cfg.roles.get(emp.role, {})
        if role.get("pay_basis") not in ("piece_service_hour", "piece_per_service", "service_revenue_pct"):
            return
        if not worked_rows:
            return
        loc = worked_rows[0]["loc"]
        if not self.cfg.state_rule(loc, "piece_rate_nonproductive_separate", False):
            return
        worked = sum((r["hours"] for r in worked_rows), ZERO)
        breakouts = sum((r["hours"] for r in rows if r["category"] != "worked"), ZERO)
        other = worked - self.service_day.get((emp.id, day), ZERO) - breakouts
        if other > ZERO:
            rate = self.cfg.min_wage(loc, day)
            self.acc(emp.id, loc, emp.role, "nonproductive_time", other * rate, other, rate, day,
                     rule="R-STATE-NONPRODUCTIVE", in_rr=True)
            self.day_straight[(emp.id, self.employer(loc), day)] += other * rate

    # --------------------------------------------------- 3 tips, time off, adj
    def tips(self):
        consumed = defaultdict(lambda: ZERO)
        cash_mode = self.cfg.company.get("cash_tips", "report_only")
        for r in self.rows.get("tips", []):
            emp = self.emps[r["emp"]]
            consumed[(r["loc"], r["tip_type"])] += r["amount"]
            if not any(self.cfg.roles.get(x, {}).get("tips") for x in emp.roles()):
                self.f.warn("CALC_TIPS_ROLE", f"{emp.name} received tips but their role is not set up for tips; passed through anyway")
            if r["tip_type"] == "card":
                self.acc(emp.id, r["loc"], emp.role, "card_tips", r["amount"], day=r["date"], rule="R-TIPS")
            else:
                kind = "memo" if cash_mode == "report_only" else "earning"
                self.acc(emp.id, r["loc"], emp.role, "cash_tips", r["amount"], day=r["date"], rule="R-TIPS", kind=kind)
        self.r.paid_inputs["tips"] = dict(consumed)

    def time_off(self):
        consumed = defaultdict(lambda: ZERO)
        for r in self.rows.get("time_off", []):
            emp = self.emps[r["emp"]]
            consumed[(r["loc"], r["type"])] += r["hours"]
            rule = self.cfg.time_off_pay(emp.role, r["type"])
            if rule is None:
                self.f.fail("CALC_NO_TIMEOFF_RULE", f"{emp.name}: no pay rule for '{r['type']}' as {emp.role}")
                continue
            if rule["basis"] == "unpaid":
                continue
            if rule["basis"] == "regular_rate":
                self.deferred_rr.append((emp.id, r["loc"], emp.role, r["date"], r["hours"], rule.get("pay_code") or r["type"], None))
                continue
            if self.exempt(emp.id) and rule["basis"] == "base_rate":
                self.f.info("CALC_EXEMPT_TIMEOFF", f"{emp.name}: {r['hours']} {r['type']} hours recorded; salary covers them")
                continue
            pay, rate = self._time_pay_amount(emp.id, emp.role, r, rule)
            self.acc(emp.id, r["loc"], emp.role, rule.get("pay_code") or r["type"], pay, r["hours"], rate, r["date"],
                     rule=f"R-TIMEOFF-{r['type'].upper()}")
        self.r.paid_inputs["time_off"] = dict(consumed)

    def adjustments(self):
        consumed = defaultdict(lambda: ZERO)
        for r in self.rows.get("adjustments", []):
            emp = self.emps[r["emp"]]
            amount = r["amount"] if r.get("amount") is not None else (r["hours"] or ZERO) * (r["rate"] or ZERO)
            consumed[(r["loc"], "amount")] += amount
            in_rr = bool(r.get("include_in_regular_rate"))
            kind = "nontaxable" if r.get("taxable") is False else "earning"
            self.acc(emp.id, r["loc"], emp.role, r["pay_code"], amount, r.get("hours"), r.get("rate"),
                     rule="R-ADJ", detail=f"{r['description']} (approved by {r['approved_by']})", in_rr=in_rr, kind=kind)
            if in_rr:
                self.period_rr[emp.id] += amount
        self.r.paid_inputs["adjustments"] = dict(consumed)

    # ------------------------------------------------------------ 4 incentives
    def incentives(self):
        windows = active_windows(self.cfg, self.period)
        consumed = defaultdict(lambda: ZERO)
        # What happened to every source row across all incentives:
        # 3 paid, 2 matched but not payable to this seller, 1 excluded by a rule, 0 matched no rate at all.
        row_state = {}

        def mark(source, r, state, reason, subject):
            key = (source, r["_line"])
            if key not in row_state or state > row_state[key][0]:
                row_state[key] = (state, reason, subject, r)

        for inc in self.cfg.incentives:
            freq = inc.get("frequency", "pay_period")
            if freq == "monthly" and not self.period.include_monthly:
                continue
            win = self.period.window_for(inc["id"], freq)
            if win is None:
                self.f.fail("CALC_NO_WINDOW", f"incentive {inc['id']} is monthly but period.json has no monthly_window")
                continue
            lo, hi = win
            outside = defaultdict(lambda: [ZERO, ZERO])  # matched rows in the pay period but outside this window
            base = defaultdict(lambda: ZERO)        # scope key -> units or $
            by_loc = defaultdict(lambda: ZERO)      # (scope key, loc) -> base share
            direct = defaultdict(lambda: ZERO)      # (emp, loc) -> $ when no tiers
            loc_base = defaultdict(lambda: ZERO)    # credit=location
            for r in self.rows.get(inc["source"], []):
                in_window = lo <= r["date"] <= hi
                emp = self.emps[r["emp"]]
                code = _norm_code(r.get("addon_code") or r.get("service_code") or r.get("category") or r.get("item"))
                rate_entry = None if self._excluded(inc, r) else self._match(inc, r)
                qty = r.get("quantity") or ZERO
                value = qty if inc["kind"] == "per_unit" else (r.get("amount") if inc["source"] == "sales" else r.get("revenue")) or ZERO
                if not in_window:
                    if rate_entry is not None and self.in_period(r["date"]):
                        o = outside[r["date"]]
                        o[0] += qty
                        o[1] += value
                    continue
                if self._excluded(inc, r):
                    mark(inc["source"], r, 1, f"excluded by {inc['id']} rule", code)
                    continue
                if rate_entry is None:
                    mark(inc["source"], r, 0, "no rate in any incentive", code)
                    continue
                if rate_entry.get("only_employees") and emp.id not in rate_entry["only_employees"]:
                    mark(inc["source"], r, 2, f"{inc['id']}: {code} pays only {', '.join(rate_entry['only_employees'])}", emp.name)
                    continue
                if inc.get("credit", "seller") != "location" and not self._eligible(inc, emp):
                    mark(inc["source"], r, 2, f"{inc['id']}: seller's role is not eligible", emp.name)
                    continue
                mark(inc["source"], r, 3, inc["id"], code)
                consumed[(inc["id"], r["loc"])] += value
                if inc.get("credit", "seller") == "location":
                    loc_base[r["loc"]] += value
                    continue
                scope = (emp.id, r["loc"]) if inc.get("tier_scope", "employee_location") == "employee_location" else (emp.id,)
                base[scope] += value
                by_loc[(scope, r["loc"])] += value
                if not inc.get("tiers"):
                    rate = D(rate_entry["rate"])
                    direct[(emp.id, r["loc"])] += value * (rate if inc["kind"] == "per_unit" else _pct(rate))
            if outside:
                days = sorted(outside)
                units = sum((v[0] for v in outside.values()), ZERO)
                amount = sum((v[1] for v in outside.values()), ZERO)
                what = _units(units) if inc["kind"] == "per_unit" else f"{fmt_money(amount)} in sales"
                when = str(days[0]) if days[0] == days[-1] else f"{days[0]}..{days[-1]}"
                self.f.warn("INC_OUTSIDE_WINDOW", f"{inc['id']}: {what} on {when} fall inside this pay period "
                            f"but outside the {inc['id']} window {lo}..{hi}, so they were not paid. Confirm that is intended, "
                            "or widen the window in period.json")
            in_rr = inc.get("include_in_regular_rate", True)
            pay_code = inc.get("pay_code") or inc["id"]
            rule = f"R-INC-{inc['id'].upper()}"
            outputs = []
            if inc.get("credit", "seller") == "location":
                for loc, total in loc_base.items():
                    payout = self._tiered(inc, total) if inc.get("tiers") else total * self._flat_rate(inc)
                    recs = [rec for rec in inc.get("recipients", []) if rec.get("location_id") == loc]
                    if not recs:
                        self.f.warn("INC_NO_RECIPIENT", f"{inc['id']}: {loc} earned {money(payout)} but no recipient is set for {loc}")
                    for rec in recs:
                        share = D(rec.get("share", 1))
                        outputs.append((rec["employee_id"], loc, payout * share, f"{share:.0%} of {loc} base {total.normalize()}"))
            elif inc.get("tiers"):
                for scope, total in base.items():
                    payout = self._tiered(inc, total)
                    if total < ZERO:
                        self.f.warn("CALC_NEG_BASE", f"incentive {inc['id']}: refunds exceed sales for {self.emps[scope[0]].name}; nothing clawed back")
                        payout = ZERO
                    locs = [(loc, v) for (s, loc), v in by_loc.items() if s == scope]
                    parts = allocate(payout, [v for _, v in locs]) if total > 0 else [ZERO] * len(locs)
                    for (loc, _), part in zip(locs, parts):
                        outputs.append((scope[0], loc, part, self._tier_detail(inc, total)))
            else:
                for (emp_id, loc), amount in direct.items():
                    if amount < ZERO:
                        self.f.warn("CALC_NEG_BASE", f"incentive {inc['id']}: refunds exceed sales for {self.emps[emp_id].name} at {loc}; nothing clawed back")
                        amount = ZERO
                    outputs.append((emp_id, loc, amount, ""))
            for emp_id, loc, amount, detail in outputs:
                if emp_id not in self.emps:
                    self.f.fail("CALC_INC_RECIP", f"incentive {inc['id']}: recipient {emp_id} is not on the roster")
                    continue
                role_id = self._role_for_incentive(inc, self.emps[emp_id])
                self.acc(emp_id, loc, role_id, pay_code, amount, rule=rule, detail=detail, in_rr=in_rr)
                if in_rr and not self.exempt(emp_id):
                    if freq == "monthly" or (lo, hi) != (self.period.start, self.period.end):
                        self.monthly_rr.append((emp_id, loc, inc["id"], amount, (lo, hi)))
                    else:
                        self.period_rr[emp_id] += amount
        self.r.paid_inputs["incentives"] = dict(consumed)
        self._incentive_notes(row_state)

    def _incentive_notes(self, row_state):
        """Report every source row that no incentive paid, grouped, so nothing is dropped silently."""
        groups = defaultdict(lambda: [ZERO, ZERO, set()])
        for (source, _), (state, reason, subject, r) in row_state.items():
            if state == 3:
                continue
            if state == 0 and source == "services":
                continue  # most services carry no incentive; that is normal
            g = groups[(source, state, reason, subject)]
            g[0] += r.get("quantity") or ZERO
            g[1] += (r.get("amount") if source == "sales" else r.get("revenue")) or ZERO
            g[2].add(self.emps[r["emp"]].name)
        unmapped_level = (self.cfg.checks.get("unmapped_addons") or "warn").lower()
        for (source, state, reason, subject), (units, amount, people) in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], str(kv[0][3]))):
            self.r.incentive_notes.append({"source": source, "state": state, "reason": reason, "subject": subject,
                                           "units": units, "amount": amount, "people": sorted(people)})
            if state == 0 and source == "addons":
                msg = (f"add-on code {subject} ({_units(units)} by {', '.join(sorted(people))}) has no rate in any "
                       "incentive, so it paid $0. Add it to a rate list (rate 0 confirms it pays nothing)")
                (self.f.warn if unmapped_level == "warn" else self.f.info)("INC_ADDON_UNMAPPED", msg)
            elif state == 0 and source == "sales":
                self.f.info("INC_SALES_UNMAPPED", f"sales category/item {subject} ({fmt_money(amount)}) is not paid by any incentive")
            elif state == 2:
                what = fmt_money(amount) if amount else _units(units)
                self.f.info("INC_NOT_ELIGIBLE", f"{reason}: {subject} ({what}) paid $0")

    def _excluded(self, inc, r):
        for ex in inc.get("exclude", []):
            value = str(r.get(ex.get("field"), "") or "").lower()
            if value in {str(v).lower() for v in ex.get("values", [])}:
                return True
        return False

    def _match(self, inc, r):
        code = _norm_code(r.get("addon_code") or r.get("service_code") or r.get("item"))
        text = f"{r.get('addon_name') or ''} {r.get('service_name') or ''} {r.get('item') or ''}".lower()
        for entry in inc.get("rates", []):
            m, v = entry.get("match"), str(entry.get("value", "")).strip()
            if m == "any":
                return entry
            if m == "code_prefix" and code.startswith(v.upper()):
                return entry
            if m == "code" and code == v.upper():
                return entry
            if m == "category" and (r.get("category") or "") == v.lower():
                return entry
            if m == "item_contains" and v.lower() in text:
                return entry
        return None

    def _eligible(self, inc, emp):
        if emp.id in inc.get("eligible_employees", []):
            return True
        roles = inc.get("eligible_roles") or []
        if not roles and not inc.get("eligible_employees"):
            return True
        return any(r in roles for r in emp.roles())

    def _role_for_incentive(self, inc, emp):
        for r in emp.roles():
            if r in (inc.get("eligible_roles") or []):
                return r
        return emp.role

    def _flat_rate(self, inc):
        entry = inc["rates"][0]
        rate = D(entry.get("rate"), ZERO)
        return rate if inc["kind"] == "per_unit" else _pct(rate)

    def _tiers(self, inc):
        tiers = sorted(inc["tiers"], key=lambda t: D(t["from"]))
        out = []
        for t in tiers:
            rate = D(t["rate"])
            out.append((D(t["from"]), D(t["to"]) if t.get("to") not in (None, "") else None,
                        rate if inc["kind"] == "per_unit" else _pct(rate)))
        return out

    def _tiered(self, inc, total):
        if total <= ZERO:
            return ZERO
        tiers = self._tiers(inc)
        if inc.get("tier_method", "marginal") == "highest":
            rate = ZERO
            for lo, _, r in tiers:
                if total >= lo:
                    rate = r
            return total * rate
        payout = ZERO
        unit_based = inc["kind"] == "per_unit"
        for lo, hi, rate in tiers:
            floor = lo - 1 if unit_based else lo
            top = hi if hi is not None else total
            span = min(total, top) - floor
            if span > 0:
                payout += span * rate
        return payout

    def _tier_detail(self, inc, total):
        if inc["kind"] != "per_unit":
            return f"base {money(total)}"
        parts = []
        for lo, hi, rate in self._tiers(inc):
            top = hi if hi is not None else total
            span = min(total, top) - (lo - 1)
            if span > 0:
                parts.append(f"{span.normalize()} x {money(rate)}")
        return f"{total.normalize()} units: " + " + ".join(parts)

    # ------------------------------------------------------ 5 salary / pools
    def salaries(self):
        p = self.period
        days_in_period = (p.end - p.start).days + 1
        alloc = defaultdict(list)
        for row in self.cfg.data.get("manager_allocation", []):
            alloc[row["employee_id"]].append((row["location_id"], D(row["share"])))
        for emp in self.emps.values():
            role = self.cfg.roles.get(emp.role, {})
            if role.get("pay_basis") != "salary":
                continue
            if emp.termination_date and emp.termination_date < p.start:
                continue
            if emp.hire_date and emp.hire_date > p.end:
                continue
            rate, rtype = self.inputs.rate(emp.id, emp.role, p.end)
            if rate is None:
                self.f.fail("CALC_NO_SALARY", f"{emp.name}: no salary rate")
                continue
            per_period = rate / self.cfg.periods_per_year() if rtype == "salary_annual" else rate
            factor = p.salary_proration
            if factor is None:
                first = max(p.start, emp.hire_date) if emp.hire_date else p.start
                last = min(p.end, emp.termination_date) if emp.termination_date else p.end
                factor = D((last - first).days + 1) / D(days_in_period)
            amount = per_period * factor
            detail = f"{money(per_period)} per period" + (f" x {factor:.4f}" if factor != 1 else "")
            shares = alloc.get(emp.id) or [(emp.home_location, D(1))]
            for (loc, share), part in zip(shares, allocate(amount, [s for _, s in shares])):
                self.acc(emp.id, loc, emp.role, "salary", part, rule="R-SALARY",
                         detail=detail + (f", {share:.0%} to {loc}" if len(shares) > 1 else ""))
        for st in self.cfg.stipends:
            eff = parse_date(st.get("effective_from")) if st.get("effective_from") else None
            thru = parse_date(st.get("effective_through")) if st.get("effective_through") else None
            if (eff and eff > p.end) or (thru and thru < p.start):
                continue
            emp = self.emps.get(st["employee_id"])
            if not emp:
                self.f.fail("CALC_STIPEND", f"stipend {st.get('id')}: {st['employee_id']} is not on the roster")
                continue
            if (eff and eff > p.start) or (thru and thru < p.end):
                self.f.warn("CALC_STIPEND_PARTIAL", f"stipend {st.get('id')} for {emp.name} starts or ends inside this period; paid in full")
            self.acc(emp.id, st.get("location_id") or emp.home_location, emp.role, st.get("pay_code") or "stipend",
                     D(st["amount"]), rule="R-STIPEND", detail=st.get("label", ""))

    def bonus_pools(self):
        metrics = defaultdict(dict)
        for r in self.rows.get("location_metrics", []):
            metrics[(r["loc"], r.get("window_start"), r.get("window_end"))][r["metric"]] = r["value"]
        for bp in self.cfg.bonus_pools:
            freq = bp.get("frequency", "monthly")
            if freq == "monthly" and not self.period.include_monthly:
                continue
            win = self.period.window_for(bp["id"], freq)
            locs = sorted({r["location_id"] for r in bp.get("recipients", [])})
            for loc in locs:
                vals = metrics.get((loc, win[0], win[1]) if win else None) or metrics.get((loc, None, None))
                if vals is None:
                    self.f.fail("CALC_NO_METRICS", f"bonus pool {bp['id']}: no location_metrics for {loc} covering {win}")
                    continue
                earned, details, ok = ZERO, [], True
                for m in bp.get("metrics", []):
                    num = vals.get(m["numerator"])
                    den = vals.get(m["denominator"]) if m.get("denominator") else D(1)
                    if num is None or den is None:
                        self.f.fail("CALC_NO_METRICS", f"bonus pool {bp['id']}: metric '{m['numerator']}' or '{m.get('denominator')}' missing for {loc}")
                        ok = False
                        break
                    value = num / den if den else ZERO
                    passed = _compare(value, m.get("compare", ">="), D(m["threshold"]))
                    details.append(f"{m.get('label', m['id'])} {value:.4f} {'PASS' if passed else 'FAIL'} vs {m['threshold']}")
                    if passed:
                        earned += D(m["weight"])
                if not ok:
                    continue
                payout = D(bp["pool_per_location"]) * earned
                for rec in bp["recipients"]:
                    if rec["location_id"] != loc:
                        continue
                    emp = self.emps.get(rec["employee_id"])
                    if not emp:
                        self.f.fail("CALC_BONUS_RECIP", f"bonus pool {bp['id']}: {rec['employee_id']} is not on the roster")
                        continue
                    amount = payout * D(rec.get("share", 1))
                    in_rr = bp.get("include_in_regular_rate", False)
                    if not self.exempt(emp.id) and not in_rr:
                        self.f.warn("CALC_BONUS_RR", f"{emp.name} is non-exempt; a non-discretionary bonus belongs in the regular rate (set include_in_regular_rate)")
                    self.acc(emp.id, loc, emp.role, bp.get("pay_code") or "bonus", amount, rule=f"R-POOL-{bp['id'].upper()}",
                             detail="; ".join(details), in_rr=in_rr)
                    if in_rr and not self.exempt(emp.id):
                        self.monthly_rr.append((emp.id, loc, bp["id"], amount, win))

    # ------------------------------------------------------- 6 overtime etc.
    def overtime(self):
        p, cfg = self.period, self.cfg
        # spread pay-period regular-rate earnings (incentives, bonuses) over the hours worked this period
        hours_by_emp = defaultdict(lambda: ZERO)
        for (emp, employer, day), locs in self.day_hours.items():
            hours_by_emp[emp] += sum(locs.values(), ZERO)
        for emp, extra in self.period_rr.items():
            total = hours_by_emp.get(emp, ZERO)
            if total <= 0:
                continue
            for (e, employer, day), locs in self.day_hours.items():
                if e == emp:
                    self.day_straight[(e, employer, day)] += extra * sum(locs.values(), ZERO) / total

        weeks = defaultdict(set)
        for (emp, employer, day) in self.day_hours:
            weeks[(emp, employer, week_start(day, cfg.workweek_start))].add(day)
        for (emp_id, employer, wk), days in sorted(weeks.items()):
            self._week(emp_id, employer, wk)

    def _week(self, emp_id, employer, wk):
        cfg, p = self.cfg, self.period
        emp = self.emps[emp_id]
        dates = [wk + _dt.timedelta(days=i) for i in range(7)]
        per_day, prior_hours, prior_straight, prior_minreq, current_hours = {}, ZERO, ZERO, ZERO, ZERO
        loc_hours = defaultdict(lambda: ZERO)
        for day in dates:
            if p.start <= day <= p.end:
                locs = self.day_hours.get((emp_id, employer, day))
                h = sum(locs.values(), ZERO) if locs else ZERO
                for loc, v in (locs or {}).items():
                    loc_hours[loc] += v
                current_hours += h
            else:
                rec = self.history.day(emp_id, employer, day, exclude_period=p.id)
                h = D(rec["hours"]) if rec else ZERO
                if rec:
                    prior_hours += h
                    prior_straight += D(rec.get("straight"), ZERO)
                    prior_minreq += D(rec.get("minreq"), ZERO)
            if h:
                per_day[day] = h
        if current_hours <= 0:
            return
        main_loc = max(loc_hours, key=loc_hours.get)
        states = {cfg.locations[l]["state"] for l in loc_hours}
        if len(states) > 1:
            self.f.warn("CALC_MULTI_STATE_WEEK", f"{emp.name}: week of {wk} spans states {sorted(states)}; overtime uses {cfg.locations[main_loc]['state']} rules")
        threshold = D(cfg.state_rule(main_loc, "weekly_ot_threshold", 40))
        daily = cfg.state_rule(main_loc, "daily_ot")
        seventh = cfg.state_rule(main_loc, "seventh_day_ot", False)

        ot = dt = ZERO
        regular_total = ZERO
        worked_days = [d for d in dates if per_day.get(d)]
        for i, day in enumerate(dates):
            h = per_day.get(day, ZERO)
            if not h:
                continue
            if daily:
                d_thr = D(daily.get("threshold", 8))
                d_dbl = D(daily["double_threshold"]) if daily.get("double_threshold") else None
                if seventh and len(worked_days) == 7 and day == dates[6]:
                    day_ot = min(h, d_thr)
                    day_dt = max(ZERO, h - d_thr)
                else:
                    day_dt = max(ZERO, h - d_dbl) if d_dbl else ZERO
                    day_ot = max(ZERO, min(h, d_dbl or h) - d_thr)
                ot += day_ot
                dt += day_dt
                regular_total += h - day_ot - day_dt
            else:
                regular_total += h
        ot += max(ZERO, regular_total - threshold)
        total_hours = prior_hours + current_hours

        # straight-time earnings in the week, before regular-rate time pay
        current_straight = sum((self.day_straight.get((emp_id, employer, d), ZERO) for d in dates if p.start <= d <= p.end), ZERO)
        current_minreq = sum((self.day_minreq.get((emp_id, employer, d), ZERO) for d in dates if p.start <= d <= p.end), ZERO)
        # time paid at the regular rate (e.g. paid rest periods for piece-rate workers)
        rr_time_hours = ZERO
        for item in self.deferred_rr:
            e, loc, role_id, day, hours, pay_code, counts = item
            if e == emp_id and counts is not None and wk <= day <= dates[-1] and cfg.employer_of(loc) == employer:
                rr_time_hours += hours
        straight = prior_straight + current_straight
        base_hours = total_hours - rr_time_hours
        avg_rate = straight / base_hours if base_hours > 0 else ZERO
        for item in list(self.deferred_rr):
            e, loc, role_id, day, hours, pay_code, counts = item
            if e == emp_id and counts is not None and wk <= day <= dates[-1] and cfg.employer_of(loc) == employer:
                rate = max(avg_rate, cfg.min_wage(loc, day))
                self.acc(emp_id, loc, role_id, pay_code, hours * rate, hours, rate.quantize(D("0.0001")), day,
                         rule="R-TIME-REGULAR-RATE", in_rr=True)
                straight += hours * rate
                current_straight += hours * rate
                self.day_straight[(emp_id, employer, day)] += hours * rate
                self.deferred_rr.remove(item)

        prior_paid = self.history.paid_for_week(emp_id, employer, wk, exclude_period=p.id)

        # minimum-wage floor for the workweek
        minreq = prior_minreq + current_minreq
        shortfall = minreq - straight
        makeup_owed = shortfall - prior_paid["makeup"]
        makeup_paid = ZERO
        if makeup_owed > D("0.005"):
            if cfg.company.get("min_wage_makeup", "flag") == "auto":
                makeup_paid = makeup_owed
                self._split(emp_id, loc_hours, current_hours, "min_wage_makeup", makeup_paid, rule="R-MINWAGE",
                            detail=f"week of {wk}: earned {money(straight)} for {total_hours} hrs, minimum {money(minreq)}", in_rr=True)
                straight += makeup_paid
                self.f.warn("CALC_MINWAGE_MAKEUP", f"{emp.name}: added {money(makeup_paid)} minimum-wage make-up for the week of {wk}")
            else:
                self.f.fail("CALC_MINWAGE_SHORT", f"{emp.name}: week of {wk} earned {money(straight)} for {total_hours} hours; "
                            f"the minimum is {money(minreq)} (short {money(makeup_owed)}). Decide: add an adjustment, or set "
                            "company.min_wage_makeup to 'auto'")

        rr = straight / total_hours if total_hours > 0 else ZERO
        premium_due = HALF * rr * ot + rr * dt
        ot_owed = max(ZERO, ot - prior_paid["ot"])
        dt_owed = max(ZERO, dt - prior_paid["dt"])
        premium_owed = premium_due - prior_paid["premium"]

        # hourly employees get OT as hours; anything the hours don't cover is a premium amount
        premium_paid = ZERO
        hourly_keys = [k for k in self.hourly if k[0] == emp_id and k[3] == wk and cfg.employer_of(k[1]) == employer]
        hourly_hours = sum((self.hourly[k]["hours"] for k in hourly_keys), ZERO)
        ot_lines = dt_lines = ZERO
        if hourly_hours > 0 and (ot_owed > 0 or dt_owed > 0):
            dt_lines = min(dt_owed, hourly_hours)
            ot_lines = min(ot_owed, hourly_hours - dt_lines)
            for k in hourly_keys:
                b = self.hourly[k]
                share = b["hours"] / hourly_hours
                base = b["amount"] / b["hours"] if b["hours"] else ZERO
                o, d = ot_lines * share, dt_lines * share
                b["hours"] -= o + d
                b["amount"] -= (o + d) * base
                if o:
                    self.acc(emp_id, k[1], k[2], "overtime", o * base * ONE_HALF, o, (base * ONE_HALF).quantize(D("0.0001")),
                             rule="R-OT", detail=f"week of {wk}")
                if d:
                    self.acc(emp_id, k[1], k[2], "doubletime", d * base * TWO, d, (base * TWO).quantize(D("0.0001")),
                             rule="R-OT", detail=f"week of {wk}")
                premium_paid += HALF * base * o + base * d
        extra = premium_owed - premium_paid
        if extra > D("0.005"):
            label = "regular-rate overtime premium" if hourly_hours > 0 else "overtime premium"
            self._split(emp_id, loc_hours, current_hours, "ot_premium", extra, rule="R-OT",
                        detail=f"week of {wk}: {ot} OT / {dt} DT hrs at regular rate {rr:.4f} ({label})")
            premium_paid += extra
        elif extra < -D("0.005") and hourly_hours > 0:
            self.f.info("CALC_OT_OVERPAID", f"{emp.name}: week of {wk} overtime at 1.5x base exceeds the regular-rate premium by {money(-extra)} (allowed)")

        self.r.weeks.append({
            "employee_id": emp_id, "employee": emp.name, "employer": employer, "week_start": wk,
            "prior_hours": prior_hours, "current_hours": current_hours, "total_hours": total_hours,
            "ot_hours": ot, "dt_hours": dt, "regular_rate": rr, "straight_earnings": straight,
            "premium_due": premium_due, "paid_before": prior_paid["premium"], "premium_now": premium_paid,
            "min_wage_required": minreq, "makeup_now": makeup_paid,
        })
        self.r.history_weeks[(emp_id, employer, wk)] = {
            "hours": str(current_hours), "ot": str(ot_owed), "dt": str(dt_owed),
            "premium": str(premium_paid), "makeup": str(makeup_paid),
        }

    def _split(self, emp_id, loc_hours, total, pay_code, amount, rule, detail, in_rr=False):
        emp = self.emps[emp_id]
        items = sorted(loc_hours.items(), key=lambda kv: -kv[1])
        remaining = money(amount)
        for i, (loc, h) in enumerate(items):
            part = remaining if i == len(items) - 1 else money(amount * h / total)
            remaining -= part
            self.acc(emp_id, loc, emp.role, pay_code, part, rule=rule, detail=detail, in_rr=in_rr)

    # --------------------------------------- 7 OT true-up for later incentives
    def monthly_trueup(self):
        cfg, p = self.cfg, self.period
        if not self.monthly_rr:
            return
        current_week = {(w["employee_id"], w["employer"], w["week_start"]): w for w in self.r.weeks}
        for emp_id, loc, source_id, amount, (lo, hi) in self.monthly_rr:
            emp = self.emps[emp_id]
            day_hours = {}
            missing = []
            day = lo
            while day <= hi:
                for employer in {cfg.employer_of(l) for l in cfg.locations}:
                    if p.start <= day <= p.end:
                        locs = self.day_hours.get((emp_id, employer, day))
                        h = sum(locs.values(), ZERO) if locs else ZERO
                    else:
                        rec = self.history.day(emp_id, employer, day, exclude_period=p.id)
                        h = D(rec["hours"]) if rec else ZERO
                        if rec is None and employer == cfg.employer_of(loc) and not self.history.has_any():
                            missing.append(day)
                    if h:
                        day_hours[(employer, day)] = h
                day += _dt.timedelta(days=1)
            total = sum(day_hours.values(), ZERO)
            if total <= 0:
                continue
            per_hour = amount / total
            trueup = ZERO
            by_week = defaultdict(lambda: ZERO)
            for (employer, day), h in day_hours.items():
                by_week[(employer, week_start(day, cfg.workweek_start))] += h
            for (employer, wk), h_in_window in by_week.items():
                cur = current_week.get((emp_id, employer, wk))
                if cur:
                    week_total, ot, dt = cur["total_hours"], cur["ot_hours"], cur["dt_hours"]
                else:
                    recs = self.history.week_record(emp_id, employer, wk, exclude_period=p.id)
                    if not recs:
                        continue
                    week_total = sum((D(r.get("hours"), ZERO) for r in recs.values()), ZERO)
                    ot = sum((D(r.get("ot"), ZERO) for r in recs.values()), ZERO)
                    dt = sum((D(r.get("dt"), ZERO) for r in recs.values()), ZERO)
                if (ot <= 0 and dt <= 0) or week_total <= 0:
                    continue
                uplift = per_hour * h_in_window / week_total
                trueup += HALF * uplift * ot + uplift * dt
            if missing and not self.history.has_any():
                self.f.warn("CALC_TRUEUP_HISTORY", f"{emp.name}: {source_id} covers {lo}..{hi} but there is no hours history "
                            "from earlier runs; any overtime in those weeks needs a manual regular-rate true-up")
            if trueup > D("0.005"):
                self.acc(emp_id, loc, emp.role, "ot_premium", trueup, rule="R-OT-TRUEUP",
                         detail=f"overtime true-up: {source_id} raises the regular rate of weeks in {lo}..{hi}")

    # ------------------------------------------------------- time off at RR
    def leftover_regular_rate(self):
        """Time off paid at the employee's regular rate for this period (average hourly earnings)."""
        for item in self.deferred_rr:
            emp_id, loc, role_id, day, hours, pay_code, counts = item
            straight = sum((v for (e, _, d), v in self.day_straight.items() if e == emp_id), ZERO)
            worked = sum((sum(l.values(), ZERO) for (e, _, d), l in self.day_hours.items() if e == emp_id), ZERO)
            if worked > 0:
                rate = straight / worked
            else:
                rate = self.cfg.min_wage(loc, day)
                self.f.warn("CALC_RR_NO_HOURS", f"{self.emps[emp_id].name}: no hours worked this period; {pay_code} paid at minimum wage")
            self.acc(emp_id, loc, role_id, pay_code, hours * rate, hours, rate.quantize(D("0.0001")), day,
                     rule="R-REGULAR-RATE")
        self.deferred_rr = []

    # ----------------------------------------------------------------- run
    def finalize(self):
        for (emp, loc, role, pay_code, rate, kind, rule, in_rr), a in self._acc.items():
            if pay_code == "regular":
                continue
            self._emit(emp, loc, role, pay_code, a, rate, kind, rule, in_rr)
        regular = defaultdict(lambda: {"hours": ZERO, "amount": ZERO})
        for (emp, loc, role, wk, rate), b in self.hourly.items():
            regular[(emp, loc, role, rate)]["hours"] += b["hours"]
            regular[(emp, loc, role, rate)]["amount"] += b["amount"]
        for (emp, loc, role, rate), b in regular.items():
            if b["hours"] == 0 and b["amount"] == 0:
                continue
            self._emit(emp, loc, role, "regular", {"hours": b["hours"], "amount": b["amount"], "dates": set(), "detail": set()},
                       rate, "earning", "R-HOURLY", True)
        for (emp, employer, day), locs in self.day_hours.items():
            self.r.history_days[(emp, employer, day)] = {
                "hours": str(sum(locs.values(), ZERO)),
                "straight": str(self.day_straight.get((emp, employer, day), ZERO)),
                "minreq": str(self.day_minreq.get((emp, employer, day), ZERO)),
            }
        missing_codes = sorted({l["pay_code"] for l in self.r.lines if l["pay_code"] not in self.cfg.pay_codes})
        for code in missing_codes:
            self.f.fail("CALC_PAYCODE", f"pay type '{code}' was produced but has no processor pay code in the config")
        self.r.lines.sort(key=lambda l: (l["location_id"], self.emps[l["employee_id"]].name, l["pay_code"]))

    def _emit(self, emp, loc, role, pay_code, a, rate, kind, rule, in_rr):
        amount = money(a["amount"])
        if amount == 0 and not a["hours"]:
            return
        entry = self.cfg.pay_codes.get(pay_code, {})
        self.r.lines.append({
            "employee_id": emp, "employee": self.emps[emp].name, "location_id": loc, "role": role,
            "pay_code": pay_code, "label": entry.get("label", pay_code), "processor_code": entry.get("code", ""),
            "export_as": entry.get("export_as", "amount"),
            "hours": a["hours"].quantize(CENT) if a["hours"] else None,
            "rate": rate, "amount": amount, "kind": kind, "rule": rule, "in_regular_rate": in_rr,
            "detail": "; ".join(sorted(a["detail"]))[:500],
        })

    def run(self):
        self.services()
        self.time()
        self.tips()
        self.time_off()
        self.adjustments()
        self.incentives()
        self.salaries()
        self.bonus_pools()
        self.overtime()
        self.monthly_trueup()
        self.leftover_regular_rate()
        self.finalize()
        return self.r


def allocate(total, weights):
    """Split a dollar total by weights into cents that add back to the rounded total."""
    total = money(total)
    weights = [D(w) for w in weights]
    wsum = sum(weights, ZERO)
    if not weights:
        return []
    if wsum == 0:
        return [total] + [ZERO] * (len(weights) - 1)
    parts = [money(total * w / wsum) for w in weights]
    parts[-1] = total - sum(parts[:-1], ZERO)
    return parts


def _compare(value, op, threshold):
    return {
        ">=": value >= threshold, ">": value > threshold,
        "<=": value <= threshold, "<": value < threshold,
    }.get(op, value >= threshold)


def calculate(cfg, period, inputs, history):
    return Engine(cfg, period, inputs, history).run()
