"""Load and validate the company payroll configuration (payroll_config.json).

The config is the owner's pay rules in machine form. It is produced by the intake
(interview or intake workbook) and signed off through the Pay Rules Book.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .util import D, Findings, parse_date, read_json, ZERO

SCHEMA_VERSION = "1.0"

PAY_BASES = {"piece_service_hour", "piece_per_service", "service_revenue_pct", "hourly", "salary"}
HOURS_SOURCES = {"clock", "services_plus_time"}
RATE_BASES = {"min_wage", "base_rate", "fixed", "regular_rate", "unpaid"}
TIME_CATEGORIES = {"worked", "lobby", "training", "trainee", "trainer", "meeting", "cleaning",
                   "travel", "waiting", "rest_recovery", "other"}
TIME_OFF_TYPES = {"sick", "pto", "vacation", "holiday", "bereavement", "jury_duty", "unpaid"}
INCENTIVE_SOURCES = {"addons", "services", "sales"}
INCENTIVE_KINDS = {"per_unit", "percent"}
MATCH_TYPES = {"code_prefix", "code", "category", "item_contains", "any"}
FREQUENCIES = {"pay_period", "monthly"}
PAY_FREQUENCIES = {"weekly": 52, "biweekly": 26, "semi_monthly": 24, "monthly": 12}
EXPORT_AS = {"hours", "amount", "none"}

# Pay keys the engine itself produces. Each must have an entry in config.pay_codes
# when it is used. Keys from time_pay / time_off_pay / incentives / stipends /
# bonus pools / adjustments are added to this set at validation time.
ENGINE_PAY_KEYS = {
    "service_wages": "Pay for service time (piece rate per service hour)",
    "service_per_unit": "Pay per service performed",
    "service_commission": "Percent of service revenue",
    "regular": "Regular hourly hours",
    "overtime": "Overtime hours (1.5x)",
    "doubletime": "Double-time hours (2x)",
    "ot_premium": "Overtime premium (half-time on the regular rate)",
    "card_tips": "Credit card tips",
    "cash_tips": "Cash tips (declared)",
    "salary": "Salary",
    "min_wage_makeup": "Minimum wage make-up pay",
    "nonproductive_time": "Separately paid non-productive time",
    "rest_recovery": "Rest and recovery period pay",
}


class Config:
    """Thin wrapper with lookups over the raw config dict."""

    def __init__(self, data: dict, path: Path | None = None):
        self.data = data
        self.path = Path(path) if path else None
        self.company = data.get("company", {})
        self.workweek_start = self.company.get("workweek_start", "sunday").lower()
        self.locations = {loc["id"]: loc for loc in data.get("locations", [])}
        self.employers = {e["id"]: e for e in data.get("employers", [])}
        self.roles = {r["id"]: r for r in data.get("roles", [])}
        self.state_rules = data.get("state_rules", {})
        self.pay_codes = data.get("pay_codes", {})
        self.incentives = data.get("incentives", [])
        self.bonus_pools = data.get("bonus_pools", [])
        self.stipends = data.get("stipends", [])
        self.overrides = {o["employee_id"]: o for o in data.get("employee_overrides", [])}
        self.checks = data.get("checks", {})
        self._time_pay = {}
        for row in data.get("time_pay", []):
            self._time_pay[(row["role"], row["category"])] = row
        self._time_off_pay = {}
        for row in data.get("time_off_pay", []):
            self._time_off_pay[(row["role"], row["type"])] = row

    # --- lookups -----------------------------------------------------------
    def role(self, role_id):
        return self.roles.get(role_id)

    def location(self, loc_id):
        return self.locations.get(loc_id)

    def employer_of(self, loc_id):
        loc = self.locations.get(loc_id) or {}
        if self.company.get("ot_aggregation", "employer") == "location":
            return f"loc:{loc_id}"
        return loc.get("employer_id", "default")

    def state_rule(self, loc_id, key, default=None):
        loc = self.locations.get(loc_id) or {}
        rules = self.state_rules.get(loc.get("state", ""), {})
        value = rules.get(key, default)
        return default if value is None else value

    def min_wage(self, loc_id, on_date):
        loc = self.locations.get(loc_id)
        if not loc:
            raise KeyError(f"unknown location {loc_id}")
        best = None
        for entry in loc.get("min_wage", []):
            eff = parse_date(entry.get("effective_from")) if entry.get("effective_from") else None
            if eff is None or eff <= on_date:
                if best is None or (eff and (best[0] is None or eff > best[0])):
                    best = (eff, D(entry["rate"]))
        if best is None:
            raise KeyError(f"no minimum wage for location {loc_id} on {on_date}")
        return best[1]

    def time_pay(self, role_id, category):
        return self._time_pay.get((role_id, category)) or self._time_pay.get(("*", category))

    def time_off_pay(self, role_id, kind):
        return self._time_off_pay.get((role_id, kind)) or self._time_off_pay.get(("*", kind))

    def pay_code_label(self, key):
        entry = self.pay_codes.get(key) or {}
        return entry.get("label") or key

    def periods_per_year(self):
        return PAY_FREQUENCIES.get(self.company.get("pay_frequency", "semi_monthly"), 24)

    def fingerprint(self):
        """Stable hash of the rules (excluding the approval block) for sign-off."""
        rules = {k: v for k, v in self.data.items() if k != "approval"}
        blob = json.dumps(rules, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()[:16]

    @property
    def approved(self):
        appr = self.data.get("approval") or {}
        return bool(appr.get("approved_by")) and appr.get("rules_fingerprint") == self.fingerprint()


def load_config(path) -> Config:
    path = Path(path)
    return Config(read_json(path), path)


def used_pay_keys(cfg: Config):
    keys = set()
    for row in cfg.data.get("time_pay", []):
        keys.add(row.get("pay_code") or row["category"])
    for row in cfg.data.get("time_off_pay", []):
        keys.add(row.get("pay_code") or row["type"])
    for inc in cfg.incentives:
        keys.add(inc.get("pay_code") or inc["id"])
    for st in cfg.stipends:
        keys.add(st.get("pay_code") or "stipend")
    for bp in cfg.bonus_pools:
        keys.add(bp.get("pay_code") or "bonus")
    return keys


def validate_config(cfg: Config) -> Findings:
    """Structural and logical checks. FAIL = cannot run payroll on these rules."""
    f = Findings()
    data = cfg.data
    if str(data.get("schema_version", "")) != SCHEMA_VERSION:
        f.warn("CFG_SCHEMA", f"schema_version is {data.get('schema_version')!r}; this engine expects {SCHEMA_VERSION}")

    comp = cfg.company
    if not comp.get("name"):
        f.fail("CFG_COMPANY", "company.name is missing")
    if comp.get("pay_frequency") not in PAY_FREQUENCIES:
        f.fail("CFG_FREQ", f"company.pay_frequency must be one of {sorted(PAY_FREQUENCIES)}")
    if cfg.workweek_start not in {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}:
        f.fail("CFG_WORKWEEK", "company.workweek_start must be a day name, e.g. 'sunday'")
    if comp.get("min_wage_makeup", "flag") not in {"flag", "auto"}:
        f.fail("CFG_MAKEUP", "company.min_wage_makeup must be 'flag' or 'auto'")

    if not cfg.employers:
        f.fail("CFG_EMPLOYER", "at least one employer (legal entity) is required")
    if not cfg.locations:
        f.fail("CFG_LOCATION", "at least one location is required")
    for loc_id, loc in cfg.locations.items():
        if loc.get("employer_id") not in cfg.employers:
            f.fail("CFG_LOC_EMPLOYER", f"location {loc_id}: employer_id {loc.get('employer_id')!r} is not a listed employer")
        if not loc.get("state"):
            f.fail("CFG_LOC_STATE", f"location {loc_id}: state is missing")
        elif loc["state"] not in cfg.state_rules:
            f.fail("CFG_STATE_RULES", f"location {loc_id}: no state_rules entry for {loc['state']}")
        if not loc.get("min_wage"):
            f.fail("CFG_MIN_WAGE", f"location {loc_id}: min_wage list is empty")
        for entry in loc.get("min_wage", []):
            try:
                if D(entry.get("rate")) is None or D(entry.get("rate")) <= ZERO:
                    raise ValueError
                if entry.get("effective_from"):
                    parse_date(entry["effective_from"])
            except ValueError:
                f.fail("CFG_MIN_WAGE", f"location {loc_id}: bad min_wage entry {entry}")

    for state, rules in cfg.state_rules.items():
        if not rules.get("confirmed_by_owner"):
            f.warn("CFG_STATE_UNCONFIRMED", f"state_rules[{state}] not confirmed by the owner (confirm with your payroll provider or counsel)")
        if D(rules.get("weekly_ot_threshold", 40)) is None:
            f.fail("CFG_STATE_OT", f"state_rules[{state}].weekly_ot_threshold must be a number")
        daily = rules.get("daily_ot")
        if daily and (D(daily.get("threshold")) is None):
            f.fail("CFG_STATE_DAILY", f"state_rules[{state}].daily_ot.threshold must be a number")

    if not cfg.roles:
        f.fail("CFG_ROLES", "at least one role is required")
    for role_id, role in cfg.roles.items():
        if role.get("pay_basis") not in PAY_BASES:
            f.fail("CFG_ROLE_BASIS", f"role {role_id}: pay_basis must be one of {sorted(PAY_BASES)}")
        if role.get("pay_basis") != "salary" and role.get("hours_worked_source", "clock") not in HOURS_SOURCES:
            f.fail("CFG_ROLE_HOURS", f"role {role_id}: hours_worked_source must be one of {sorted(HOURS_SOURCES)}")
        if role.get("pay_basis") == "salary" and not role.get("exempt"):
            f.warn("CFG_ROLE_SALARY", f"role {role_id}: salaried but not marked exempt; non-exempt salaried overtime is not calculated, so record their hours as hourly instead")
        if role.get("pay_basis", "").startswith("piece") and not role.get("service_categories"):
            f.warn("CFG_ROLE_CATS", f"role {role_id}: no service_categories; every service category will count for this role")

    for row in data.get("time_pay", []):
        if row.get("role") != "*" and row.get("role") not in cfg.roles:
            f.fail("CFG_TIMEPAY_ROLE", f"time_pay: unknown role {row.get('role')!r}")
        if row.get("category") not in TIME_CATEGORIES:
            f.fail("CFG_TIMEPAY_CAT", f"time_pay: unknown category {row.get('category')!r}; use one of {sorted(TIME_CATEGORIES)}")
        _check_basis(f, "time_pay", row)
    for row in data.get("time_off_pay", []):
        if row.get("role") != "*" and row.get("role") not in cfg.roles:
            f.fail("CFG_TIMEOFF_ROLE", f"time_off_pay: unknown role {row.get('role')!r}")
        if row.get("type") not in TIME_OFF_TYPES:
            f.fail("CFG_TIMEOFF_TYPE", f"time_off_pay: unknown type {row.get('type')!r}")
        _check_basis(f, "time_off_pay", row)

    ids = set()
    for inc in cfg.incentives:
        iid = inc.get("id")
        if not iid or iid in ids:
            f.fail("CFG_INC_ID", f"incentive id missing or duplicated: {iid!r}")
        ids.add(iid)
        if inc.get("source") not in INCENTIVE_SOURCES:
            f.fail("CFG_INC_SOURCE", f"incentive {iid}: source must be one of {sorted(INCENTIVE_SOURCES)}")
        if inc.get("kind") not in INCENTIVE_KINDS:
            f.fail("CFG_INC_KIND", f"incentive {iid}: kind must be one of {sorted(INCENTIVE_KINDS)}")
        if inc.get("frequency", "pay_period") not in FREQUENCIES:
            f.fail("CFG_INC_FREQ", f"incentive {iid}: frequency must be one of {sorted(FREQUENCIES)}")
        for role_id in inc.get("eligible_roles", []):
            if role_id not in cfg.roles:
                f.fail("CFG_INC_ROLE", f"incentive {iid}: unknown eligible role {role_id!r}")
        if inc.get("kind") == "percent" and inc.get("source") == "addons":
            f.fail("CFG_INC_KIND", f"incentive {iid}: add-ons carry no sale amount; use kind 'per_unit'")
        if not inc.get("rates"):
            f.fail("CFG_INC_RATES", f"incentive {iid}: needs at least one rates entry (what it pays on)")
        for rate in inc.get("rates", []):
            if rate.get("match") not in MATCH_TYPES:
                f.fail("CFG_INC_MATCH", f"incentive {iid}: match must be one of {sorted(MATCH_TYPES)}")
            if not inc.get("tiers") and D(rate.get("rate")) is None:
                f.fail("CFG_INC_RATE", f"incentive {iid}: rate missing for match {rate.get('value')!r}")
            elif inc.get("kind") == "percent" and D(rate.get("rate")) is not None and not (ZERO <= D(rate.get("rate")) <= 100):
                f.fail("CFG_INC_PCT", f"incentive {iid}: percent rate {rate.get('rate')} must be between 0 and 100 (10 means 10%)")
            elif inc.get("kind") == "percent" and D(rate.get("rate")) is not None and ZERO < D(rate.get("rate")) < 1:
                f.warn("CFG_INC_PCT_SMALL", f"incentive {iid}: percent rate {rate.get('rate')} means {rate.get('rate')}% "
                       "(less than one percent). If you meant {:.0f}%, write {:.0f}".format(D(rate.get('rate')) * 100, D(rate.get('rate')) * 100))
        if inc.get("tiers"):
            if inc.get("tier_method", "marginal") not in {"marginal", "highest"}:
                f.fail("CFG_INC_TIER", f"incentive {iid}: tier_method must be 'marginal' or 'highest'")
            for tier in inc["tiers"]:
                if D(tier.get("from")) is None or D(tier.get("rate")) is None:
                    f.fail("CFG_INC_TIER", f"incentive {iid}: each tier needs 'from' and 'rate'")
        if inc.get("credit", "seller") == "location":
            if not inc.get("recipients"):
                f.fail("CFG_INC_RECIP", f"incentive {iid}: credit=location needs recipients")

    for bp in cfg.bonus_pools:
        if D(bp.get("pool_per_location")) is None:
            f.fail("CFG_BONUS_POOL", f"bonus pool {bp.get('id')}: pool_per_location must be a number")
        weights = sum((D(m.get("weight"), ZERO) for m in bp.get("metrics", [])), ZERO)
        if bp.get("metrics") and weights > 1:
            f.fail("CFG_BONUS_WEIGHT", f"bonus pool {bp.get('id')}: metric weights add to {weights} (> 1)")
        for r in bp.get("recipients", []):
            if r.get("location_id") not in cfg.locations:
                f.fail("CFG_BONUS_LOC", f"bonus pool {bp.get('id')}: unknown location {r.get('location_id')!r}")

    for st in cfg.stipends:
        if D(st.get("amount")) is None:
            f.fail("CFG_STIPEND", f"stipend {st.get('id')}: amount must be a number")
        if st.get("location_id") and st["location_id"] not in cfg.locations:
            f.fail("CFG_STIPEND", f"stipend {st.get('id')}: unknown location {st['location_id']!r}")

    shares = {}
    for row in data.get("manager_allocation", []):
        if row.get("location_id") not in cfg.locations:
            f.fail("CFG_ALLOC", f"manager_allocation: unknown location {row.get('location_id')!r}")
        shares[row.get("employee_id")] = shares.get(row.get("employee_id"), ZERO) + D(row.get("share"), ZERO)
    for emp, total in shares.items():
        if abs(total - 1) > D("0.0001"):
            f.fail("CFG_ALLOC", f"manager_allocation for {emp} adds to {total} (must be 1.0)")

    for o in data.get("employee_overrides", []):
        if o.get("secondary_role") and o["secondary_role"] not in cfg.roles:
            f.fail("CFG_OVERRIDE", f"employee_overrides {o.get('employee_id')}: unknown secondary_role {o['secondary_role']!r}")

    needed = used_pay_keys(cfg)
    for key in sorted(needed | set(cfg.pay_codes)):
        entry = cfg.pay_codes.get(key)
        if entry is None:
            f.fail("CFG_PAYCODE", f"pay_codes: no processor pay code for {key!r}")
        elif entry.get("export_as", "amount") not in EXPORT_AS:
            f.fail("CFG_PAYCODE", f"pay_codes[{key}].export_as must be 'hours', 'amount' or 'none'")
    for key in ENGINE_PAY_KEYS:
        if key not in cfg.pay_codes:
            f.info("CFG_PAYCODE_ENGINE", f"pay_codes has no entry for engine pay type {key!r}; a run that produces it will stop and ask")

    if not cfg.approved:
        appr = data.get("approval") or {}
        if appr.get("approved_by"):
            f.warn("CFG_APPROVAL_STALE", "rules changed since the owner signed the Pay Rules Book; re-render and re-approve")
        else:
            f.warn("CFG_NOT_APPROVED", "the owner has not signed off the Pay Rules Book yet")
    return f


def _check_basis(f, section, row):
    basis = row.get("basis")
    if basis not in RATE_BASES:
        f.fail("CFG_BASIS", f"{section} {row.get('role')}/{row.get('category') or row.get('type')}: basis must be one of {sorted(RATE_BASES)}")
    if basis == "fixed" and D(row.get("fixed_rate")) is None:
        f.fail("CFG_BASIS", f"{section} {row.get('role')}/{row.get('category') or row.get('type')}: basis 'fixed' needs fixed_rate")
