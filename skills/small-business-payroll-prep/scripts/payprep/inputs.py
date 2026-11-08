"""Canonical input files: specs, loading, typing and employee/location resolution.

Every POS, HRIS or time clock is different. Their exports are mapped (by Claude,
or by an HRIS connector profile) into these few plain CSV files, and the engine
only ever reads these. One row = one fact. Nothing is aggregated by hand.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .util import D, ZERO, Findings, norm_name, name_variants, parse_date

YES = {"y", "yes", "true", "1", "x"}

# column -> (type, required). Types: str, date, dec, bool
SPEC = {
    "roster": {
        "employee_id": ("str", True), "first_name": ("str", True), "last_name": ("str", True),
        "status": ("str", True), "hire_date": ("date", False), "termination_date": ("date", False),
        "home_location": ("str", True), "role": ("str", True), "secondary_role": ("str", False),
        "payroll_id": ("str", False), "pos_names": ("str", False), "email": ("str", False),
    },
    "pay_rates": {
        "employee_id": ("str", True), "role": ("str", True), "rate": ("dec", True),
        "rate_type": ("str", True), "effective_from": ("date", False),
    },
    "time_entries": {
        "employee_id": ("str", False), "employee_name": ("str", False), "location": ("str", True),
        "date": ("date", True), "category": ("str", True), "hours": ("dec", True),
        "role": ("str", False), "note": ("str", False),
    },
    "services": {
        "employee_id": ("str", False), "employee_name": ("str", False), "location": ("str", True),
        "date": ("date", True), "service_code": ("str", False), "service_name": ("str", False),
        "category": ("str", True), "quantity": ("dec", True), "service_hours": ("dec", True),
        "revenue": ("dec", False), "refund": ("bool", False),
    },
    "addons": {
        "employee_id": ("str", False), "employee_name": ("str", False), "location": ("str", True),
        "date": ("date", True), "addon_code": ("str", True), "addon_name": ("str", False),
        "quantity": ("dec", True), "customer_price": ("dec", False), "refund": ("bool", False),
    },
    "sales": {
        "employee_id": ("str", False), "employee_name": ("str", False), "location": ("str", True),
        "date": ("date", True), "category": ("str", True), "item": ("str", False),
        "item_type": ("str", False), "quantity": ("dec", True), "amount": ("dec", True),
        "refund": ("bool", False),
    },
    "tips": {
        "employee_id": ("str", False), "employee_name": ("str", False), "location": ("str", True),
        "date": ("date", True), "tip_type": ("str", True), "amount": ("dec", True),
    },
    "time_off": {
        "employee_id": ("str", False), "employee_name": ("str", False), "date": ("date", True),
        "type": ("str", True), "hours": ("dec", True), "location": ("str", False),
    },
    "adjustments": {
        "employee_id": ("str", False), "employee_name": ("str", False), "location": ("str", True),
        "pay_code": ("str", True), "description": ("str", True), "hours": ("dec", False),
        "rate": ("dec", False), "amount": ("dec", False), "taxable": ("bool", False),
        "include_in_regular_rate": ("bool", False), "approved_by": ("str", True),
    },
    "location_metrics": {
        "location": ("str", True), "metric": ("str", True), "value": ("dec", True),
        "window_start": ("date", False), "window_end": ("date", False),
    },
}

DESCRIPTIONS = {
    "roster": "Everyone who might be paid this period (from your HR system).",
    "pay_rates": "Each person's rate for each role; add a row with effective_from for a mid-period change.",
    "time_entries": "Clocked or recorded time, one row per person per day per kind of time.",
    "services": "Every service performed, one row per service line, from the POS service detail report.",
    "addons": "Every add-on/enhancement performed, one row per line, from the POS add-on report.",
    "sales": "Retail, membership, gift card and package sales credited to a person.",
    "tips": "Card tips (and declared cash tips) per person per day.",
    "time_off": "Sick, PTO and holiday hours taken, one row per person per day.",
    "adjustments": "One-off pay approved by the owner: bonuses, back pay, reimbursements.",
    "location_metrics": "Location scorecard numbers used by manager bonus pools.",
}

PERSON_FILES = ("time_entries", "services", "addons", "sales", "tips", "time_off", "adjustments")
VALID_STATUS = {"active", "terminated", "leave"}
VALID_RATE_TYPES = {"hourly", "service_hour", "per_service", "service_pct", "salary_annual", "salary_period"}
VALID_TIP_TYPES = {"card", "cash"}


@dataclass
class Employee:
    id: str
    first: str
    last: str
    status: str
    home_location: str
    role: str
    secondary_role: str = ""
    hire_date: object = None
    termination_date: object = None
    payroll_id: str = ""
    pos_names: list = field(default_factory=list)
    email: str = ""

    @property
    def name(self):
        return f"{self.last}, {self.first}"

    def roles(self):
        return [r for r in (self.role, self.secondary_role) if r]


@dataclass
class InputSet:
    employees: dict
    rates: dict          # (emp, role) -> [(effective_from or None, rate, rate_type)]
    rows: dict           # file name -> list of typed rows
    present: set         # which files were provided
    files: dict          # file name -> path

    def rate(self, emp_id, role_id, on_date):
        options = self.rates.get((emp_id, role_id)) or []
        best = None
        for eff, rate, rtype in options:
            if eff is None or eff <= on_date:
                if best is None or (eff is not None and (best[0] is None or eff > best[0])):
                    best = (eff, rate, rtype)
        return (best[1], best[2]) if best else (None, None)


def write_templates(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, cols in SPEC.items():
        path = directory / f"{name}.csv"
        if not path.exists():
            with open(path, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(list(cols))
    return directory


def _read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        rows = []
        for i, raw in enumerate(reader, start=2):
            clean = {(k or "").strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
            if not any(v for v in clean.values() if v not in (None, "")):
                continue
            rows.append((i, clean))
    return headers, rows


def _typed(name, line, raw, findings, path):
    out = {"_file": name, "_line": line}
    for col, (ctype, required) in SPEC[name].items():
        value = raw.get(col, "")
        if value in (None, ""):
            if required:
                findings.fail("IN_REQUIRED", f"{path.name} line {line}: '{col}' is required", file=name, line=line)
            out[col] = None if (ctype != "bool" or col == "taxable") else False
            continue
        try:
            if ctype == "date":
                out[col] = parse_date(value, col)
            elif ctype == "dec":
                out[col] = D(value)
            elif ctype == "bool":
                out[col] = str(value).strip().lower() in YES
            else:
                out[col] = str(value).strip()
        except ValueError as exc:
            findings.fail("IN_TYPE", f"{path.name} line {line}: {exc}", file=name, line=line)
            out[col] = None
    return out


class Resolver:
    """Maps names / ids / labels in input files to roster employees and config locations."""

    def __init__(self, employees, cfg):
        self.employees = employees
        self.by_name = {}
        self.ambiguous = set()
        for emp in employees.values():
            names = {emp.name, f"{emp.first} {emp.last}", *emp.pos_names}
            override = cfg.overrides.get(emp.id) or {}
            names.update(override.get("pos_names", []))
            for n in names:
                for v in name_variants(n):
                    if v in self.by_name and self.by_name[v] != emp.id:
                        self.ambiguous.add(v)
                    self.by_name[v] = emp.id
        self.loc_by_label = {}
        for loc_id, loc in cfg.locations.items():
            for label in [loc_id, loc.get("name", ""), *loc.get("pos_labels", []), *loc.get("hris_labels", [])]:
                if label:
                    self.loc_by_label[norm_name(label)] = loc_id
                    self.loc_by_label[str(label).strip().lower()] = loc_id

    def employee(self, emp_id, emp_name):
        if emp_id and emp_id in self.employees:
            return emp_id, None
        if emp_name:
            variants = name_variants(emp_name)
            hits = {self.by_name[v] for v in variants if v in self.by_name}
            if any(v in self.ambiguous for v in variants) or len(hits) > 1:
                return None, f"name '{emp_name}' matches more than one employee; use employee_id"
            if hits:
                return hits.pop(), None
            return None, f"'{emp_name}' is not on the roster" + self._suggest(emp_name)
        if emp_id:
            return None, f"employee_id '{emp_id}' is not on the roster"
        return None, "row has neither employee_id nor employee_name"

    def _suggest(self, name):
        target = norm_name(name)
        last = target.split(",")[0] if "," in target else target[-6:]
        close = [e.name for e in self.employees.values() if last and last[:4] in norm_name(e.last)]
        if close:
            return f" (close: {', '.join(sorted(close)[:3])}; add the POS spelling to that person's pos_names)"
        return " (add them to the roster, or add this spelling to someone's pos_names)"

    def location(self, label):
        if label is None:
            return None
        key = str(label).strip()
        return self.loc_by_label.get(key.lower()) or self.loc_by_label.get(norm_name(key))


def load_inputs(period, cfg):
    findings = Findings()
    inputs_dir = period.inputs_dir
    files, raw_rows, present = {}, {}, set()
    for name in SPEC:
        path = inputs_dir / f"{name}.csv"
        if not path.exists():
            continue
        headers, rows = _read_csv(path)
        missing = [c for c, (_, req) in SPEC[name].items() if req and c not in headers]
        if name in PERSON_FILES and "employee_id" not in headers and "employee_name" not in headers:
            missing.append("employee_id or employee_name")
        if missing:
            findings.fail("IN_HEADERS", f"{path.name}: missing column(s) {missing}", file=name)
            continue
        unknown = [h for h in headers if h and h not in SPEC[name]]
        if unknown:
            findings.warn("IN_EXTRA_COLS", f"{path.name}: ignoring unknown column(s) {unknown}", file=name)
        files[name] = path
        if rows:
            present.add(name)
        raw_rows[name] = [_typed(name, line, raw, findings, path) for line, raw in rows]

    # roster
    employees = {}
    for row in raw_rows.get("roster", []):
        eid = row.get("employee_id")
        if not eid:
            continue
        if eid in employees:
            findings.fail("IN_ROSTER_DUP", f"roster.csv line {row['_line']}: employee_id {eid} appears twice")
            continue
        status = (row.get("status") or "").lower()
        if status not in VALID_STATUS:
            findings.fail("IN_ROSTER_STATUS", f"roster.csv line {row['_line']}: status must be one of {sorted(VALID_STATUS)}")
        override = cfg.overrides.get(eid) or {}
        emp = Employee(
            id=eid, first=row.get("first_name") or "", last=row.get("last_name") or "", status=status,
            home_location=row.get("home_location") or "", role=row.get("role") or "",
            secondary_role=override.get("secondary_role") or row.get("secondary_role") or "",
            hire_date=row.get("hire_date"), termination_date=row.get("termination_date"),
            payroll_id=override.get("payroll_id") or row.get("payroll_id") or "",
            pos_names=[n.strip() for n in (row.get("pos_names") or "").split(";") if n.strip()],
            email=row.get("email") or "",
        )
        if override.get("home_location"):
            emp.home_location = override["home_location"]
        employees[eid] = emp
    if "roster" not in present:
        findings.fail("IN_NO_ROSTER", "inputs/roster.csv is missing or empty; it is the list of who can be paid")

    resolver = Resolver(employees, cfg)
    for emp in employees.values():
        loc = resolver.location(emp.home_location)
        if not loc:
            findings.fail("IN_ROSTER_LOC", f"roster: {emp.name} home_location '{emp.home_location}' is not a configured location")
        else:
            emp.home_location = loc
        for role_id in emp.roles():
            if role_id not in cfg.roles:
                findings.fail("IN_ROSTER_ROLE", f"roster: {emp.name} role '{role_id}' is not a configured role")

    # pay rates
    rates = {}
    for row in raw_rows.get("pay_rates", []):
        eid, role_id = row.get("employee_id"), row.get("role")
        if eid not in employees:
            findings.fail("IN_RATE_EMP", f"pay_rates.csv line {row['_line']}: employee_id {eid} is not on the roster")
            continue
        rtype = (row.get("rate_type") or "").lower()
        if rtype not in VALID_RATE_TYPES:
            findings.fail("IN_RATE_TYPE", f"pay_rates.csv line {row['_line']}: rate_type must be one of {sorted(VALID_RATE_TYPES)}")
        rates.setdefault((eid, role_id), []).append((row.get("effective_from"), row.get("rate"), rtype))
    for emp in employees.values():
        if emp.status == "terminated" and emp.termination_date and emp.termination_date < period.start:
            continue
        for role_id in emp.roles():
            if (emp.id, role_id) not in rates:
                findings.fail("IN_RATE_MISSING", f"pay_rates: no rate for {emp.name} as {role_id}")
        for (eid, role_id), opts in rates.items():
            if eid == emp.id:
                changes = [eff for eff, _, _ in opts if eff and period.start < eff <= period.end]
                for eff in changes:
                    findings.info("IN_RATE_CHANGE", f"{emp.name} ({role_id}) rate changes on {eff}; days before are paid at the earlier rate")

    # person/location rows
    rows = {}
    for name in PERSON_FILES + ("location_metrics",):
        typed = []
        for row in raw_rows.get(name, []):
            if name != "location_metrics":
                eid, err = resolver.employee(row.get("employee_id"), row.get("employee_name"))
                if err:
                    findings.fail("IN_PERSON", f"{name}.csv line {row['_line']}: {err}", file=name, line=row["_line"])
                    continue
                row["emp"] = eid
            loc_label = row.get("location")
            if name == "time_off" and not loc_label:
                row["loc"] = employees[row["emp"]].home_location
            else:
                loc = resolver.location(loc_label)
                if not loc:
                    findings.fail("IN_LOCATION", f"{name}.csv line {row['_line']}: location '{loc_label}' is not configured", file=name, line=row["_line"])
                    continue
                row["loc"] = loc
            _normalize(name, row, findings, cfg)
            typed.append(row)
        rows[name] = typed

    return InputSet(employees=employees, rates=rates, rows=rows, present=present, files=files), findings


def _normalize(name, row, findings, cfg):
    """Lower-case enums and make refunds negative."""
    where = f"{name}.csv line {row['_line']}"
    if name == "time_entries":
        row["category"] = (row.get("category") or "").lower()
        from .config import TIME_CATEGORIES
        if row["category"] not in TIME_CATEGORIES:
            findings.fail("IN_CATEGORY", f"{where}: category '{row['category']}' must be one of {sorted(TIME_CATEGORIES)}")
        if row.get("hours") is not None and row["hours"] < ZERO:
            findings.fail("IN_NEGATIVE", f"{where}: negative hours; fix the source instead")
        if row.get("role") and row["role"] not in cfg.roles:
            findings.fail("IN_ROLE", f"{where}: unknown role '{row['role']}'")
    elif name == "time_off":
        row["type"] = (row.get("type") or "").lower()
        if row["type"] == "vacation":
            row["type"] = "pto"
        from .config import TIME_OFF_TYPES
        if row["type"] not in TIME_OFF_TYPES:
            findings.fail("IN_TIMEOFF_TYPE", f"{where}: type '{row['type']}' must be one of {sorted(TIME_OFF_TYPES)}")
    elif name == "tips":
        row["tip_type"] = (row.get("tip_type") or "").lower()
        if row["tip_type"] not in VALID_TIP_TYPES:
            findings.fail("IN_TIP_TYPE", f"{where}: tip_type must be 'card' or 'cash'")
    elif name in ("services", "addons", "sales"):
        if name in ("services", "sales"):
            row["category"] = (row.get("category") or "").lower()
        if name == "sales" and row.get("item_type"):
            row["item_type"] = row["item_type"].lower()
        if row.get("refund"):
            for col in ("quantity", "service_hours", "revenue", "amount"):
                if row.get(col) is not None and row[col] > ZERO:
                    row[col] = -row[col]
