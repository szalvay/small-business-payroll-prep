"""HRIS / payroll connectors driven by editable JSON profiles.

Inbound  (HRIS export -> roster.csv, pay_rates.csv, time_off.csv)
Outbound (earnings lines -> the payroll system's import file)

A profile only describes columns and layouts; no system is hard-coded. Shipped
profiles live in assets/connectors/. A workspace can override or add one by
putting <id>.json in <workspace>/connectors/. Every account is configured a
little differently, so each shipped profile is a starting template: compare it
with the import template you download from your own account before relying on it.
"""
from __future__ import annotations

import csv
import datetime as _dt
import re
from collections import defaultdict
from pathlib import Path

from .util import D, ZERO, Findings, money, norm_name, parse_date, read_json, write_json

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "connectors"


# --------------------------------------------------------------------- profiles
def list_profiles(workspace=None):
    found = {}
    for folder in [ASSETS] + ([Path(workspace) / "connectors"] if workspace else []):
        if folder.exists():
            for p in sorted(folder.glob("*.json")):
                data = read_json(p)
                found[data["id"]] = {"name": data.get("name", data["id"]), "path": str(p), "status": data.get("status", "")}
    return found


def load_profile(profile, workspace=None):
    if str(profile).endswith(".json") and Path(profile).exists():
        return read_json(profile)
    for folder in ([Path(workspace) / "connectors"] if workspace else []) + [ASSETS]:
        p = folder / f"{profile}.json"
        if p.exists():
            return read_json(p)
    raise FileNotFoundError(f"no connector profile '{profile}' (available: {', '.join(list_profiles(workspace))})")


# ----------------------------------------------------------------- read files
def read_table(path):
    """Read CSV or XLSX into (headers, rows). Finds the header row in report-style exports."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        grid = [[("" if v is None else v) for v in row] for row in ws.iter_rows(values_only=True)]
    else:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            grid = [row for row in csv.reader(fh)]
    header_idx = 0
    best = -1
    for i, row in enumerate(grid[:15]):
        filled = sum(1 for v in row if str(v).strip() and not _is_number(v))
        if filled > best:
            best, header_idx = filled, i
    headers = [str(h).strip() for h in grid[header_idx]]
    rows = []
    for row in grid[header_idx + 1:]:
        if not any(str(v).strip() for v in row):
            continue
        rows.append({headers[i]: row[i] for i in range(min(len(headers), len(row))) if headers[i]})
    return headers, rows


def _is_number(v):
    try:
        D(v)
        return True
    except ValueError:
        return False


def _key(text):
    return re.sub(r"[^a-z0-9#]", "", str(text).lower())


def map_columns(headers, aliases, overrides=None):
    """canonical field -> actual header, using alias lists and explicit overrides."""
    index = {_key(h): h for h in headers}
    mapping = {}
    for field, names in aliases.items():
        if overrides and field in overrides:
            if overrides[field] in headers:
                mapping[field] = overrides[field]
            continue
        for name in names:
            if _key(name) in index:
                mapping[field] = index[_key(name)]
                break
    return mapping


# -------------------------------------------------------------------- inbound
PAY_PER = {
    "hour": "hourly", "hr": "hourly", "hourly": "hourly", "h": "hourly",
    "year": "annual", "yr": "annual", "annual": "annual", "annually": "annual", "salary": "annual", "s": "annual",
    "period": "period", "payperiod": "period", "paycheck": "period",
}


def parse_pay(rate_text, pay_type_text="", per_text=""):
    """'$17.00 USD per Hour' -> (17.00, 'hourly'); '$52,000.00/year' -> (52000, 'annual')."""
    text = f"{rate_text}".strip()
    per = ""
    m = re.search(r"(?:per|/)\s*([A-Za-z ]+)$", text)
    if m:
        per = m.group(1).strip().lower().replace(" ", "")
        text = text[:m.start()]
    text = re.sub(r"[A-Za-z]{3}$", "", text.strip()).strip()  # trailing currency code
    rate = D(text) if text else None
    hint = (per or str(per_text or "") or str(pay_type_text or "")).strip().lower().replace(" ", "")
    kind = PAY_PER.get(hint, "")
    if not kind:
        for word, k in PAY_PER.items():
            if len(word) > 2 and word in hint:
                kind = k
                break
    return rate, kind


def import_hris(profile, cfg, period, roster_file=None, time_off_file=None, overrides=None):
    """Write inputs/roster.csv + pay_rates.csv (+ time_off.csv). Returns Findings."""
    f = Findings()
    inbound = profile.get("inbound", {})
    out_dir = period.inputs_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    report = [f"# HRIS import ({profile.get('name')})", ""]

    if roster_file:
        spec = inbound.get("roster") or {}
        headers, rows = read_table(roster_file)
        cols = map_columns(headers, spec.get("columns", {}), (overrides or {}).get("roster"))
        report.append(f"Roster file: `{Path(roster_file).name}` ({len(rows)} rows)")
        report += [f"- {field} <- `{col}`" for field, col in sorted(cols.items())]
        for need in ("employee_id", "first_name", "last_name", "status", "location", "job_title", "pay_rate"):
            if need not in cols:
                f.fail("HRIS_COLUMN", f"roster export: no column for '{need}'. Columns found: {headers}. "
                       f"Add the header to the profile's inbound.roster.columns.{need} list or pass --map {need}=<header>")
        if not f.has_fail:
            status_map = {k.lower(): v for k, v in (spec.get("value_maps", {}).get("status", {})).items()}
            title_to_role = {}
            for role_id, role in cfg.roles.items():
                for t in role.get("hris_titles", []):
                    title_to_role[t.lower()] = role_id
            roster_out, rates_out = [], []
            for r in rows:
                eid = str(r.get(cols["employee_id"], "")).strip()
                if eid.endswith(".0"):
                    eid = eid[:-2]
                if not eid:
                    continue
                status_raw = str(r.get(cols["status"], "")).strip().lower()
                status = status_map.get(status_raw, status_raw if status_raw in ("active", "terminated", "leave") else "")
                if not status:
                    f.fail("HRIS_STATUS", f"employee {eid}: status '{status_raw}' is not mapped (profile value_maps.status)")
                    continue
                title = str(r.get(cols["job_title"], "")).strip()
                role_id = title_to_role.get(title.lower())
                if not role_id:
                    for t, rid in title_to_role.items():
                        if t.startswith("re:") and re.search(t[3:], title, re.I):
                            role_id = rid
                            break
                loc_label = str(r.get(cols["location"], "")).strip()
                loc_id = _location(cfg, loc_label)
                if status == "terminated":
                    term = r.get(cols.get("termination_date")) if cols.get("termination_date") else None
                    term_d = _safe_date(term)
                    if term_d and term_d < period.start - _dt.timedelta(days=62):
                        continue  # long-gone staff stay out of the roster
                if not role_id:
                    f.fail("HRIS_TITLE", f"employee {eid}: job title '{title}' is not mapped to a role "
                           "(add it to that role's hris_titles in the config)")
                    continue
                if not loc_id:
                    f.fail("HRIS_LOCATION", f"employee {eid}: location '{loc_label}' is not mapped "
                           "(add it to that location's hris_labels in the config)")
                    continue
                roster_out.append({
                    "employee_id": eid,
                    "first_name": str(r.get(cols["first_name"], "")).strip(),
                    "last_name": str(r.get(cols["last_name"], "")).strip(),
                    "status": status,
                    "hire_date": _iso(r.get(cols.get("hire_date"))) if cols.get("hire_date") else "",
                    "termination_date": _iso(r.get(cols.get("termination_date"))) if cols.get("termination_date") else "",
                    "home_location": loc_id, "role": role_id, "secondary_role": "",
                    "payroll_id": str(r.get(cols.get("payroll_id"), "")).strip() if cols.get("payroll_id") else "",
                    "pos_names": "", "email": str(r.get(cols.get("email"), "")).strip() if cols.get("email") else "",
                })
                rate, per = parse_pay(r.get(cols["pay_rate"], ""), r.get(cols.get("pay_type")) if cols.get("pay_type") else "",
                                      r.get(cols.get("pay_per")) if cols.get("pay_per") else "")
                basis = cfg.roles[role_id]["pay_basis"]
                rtype = {"piece_service_hour": "service_hour", "piece_per_service": "per_service",
                         "service_revenue_pct": "service_pct", "hourly": "hourly"}.get(basis)
                if basis == "salary":
                    rtype = "salary_period" if per == "period" else "salary_annual"
                if rate is None:
                    f.fail("HRIS_RATE", f"employee {eid}: no pay rate in the export")
                    continue
                if basis == "hourly" and per == "annual":
                    f.warn("HRIS_RATE_KIND", f"employee {eid}: hourly role but the HRIS rate looks annual ({rate})")
                eff = _iso(r.get(cols.get("rate_effective"))) if cols.get("rate_effective") else ""
                eff_d = parse_date(eff) if eff else None
                if eff_d and period.start < eff_d <= period.end:
                    f.warn("HRIS_RATE_MIDPERIOD", f"employee {eid}: rate changed {eff_d} inside the period; add the earlier rate "
                           "as an employee_overrides rate row so days before it are paid correctly")
                rates_out.append({"employee_id": eid, "role": role_id, "rate": str(rate), "rate_type": rtype,
                                  "effective_from": eff if eff_d and eff_d > period.start else ""})
            for o in cfg.data.get("employee_overrides", []):
                for rr in o.get("rates", []):
                    rates_out.append({"employee_id": o["employee_id"], "role": rr["role"], "rate": str(rr["rate"]),
                                      "rate_type": rr["rate_type"], "effective_from": rr.get("effective_from", "")})
            _write_csv(out_dir / "roster.csv", roster_out, ["employee_id", "first_name", "last_name", "status", "hire_date",
                       "termination_date", "home_location", "role", "secondary_role", "payroll_id", "pos_names", "email"])
            _write_csv(out_dir / "pay_rates.csv", rates_out, ["employee_id", "role", "rate", "rate_type", "effective_from"])
            report.append(f"\nWrote {len(roster_out)} employees and {len(rates_out)} rates.")

    if time_off_file:
        spec = inbound.get("time_off") or {}
        headers, rows = read_table(time_off_file)
        cols = map_columns(headers, spec.get("columns", {}), (overrides or {}).get("time_off"))
        report.append(f"\nTime-off file: `{Path(time_off_file).name}` ({len(rows)} rows)")
        report += [f"- {field} <- `{col}`" for field, col in sorted(cols.items())]
        if "employee_id" not in cols and "employee_name" not in cols:
            f.fail("HRIS_COLUMN", f"time-off export: no employee id or name column. Columns found: {headers}")
        if "hours" not in cols or ("date" not in cols and "start_date" not in cols):
            f.fail("HRIS_COLUMN", f"time-off export needs hours and a date (or start/end dates). Columns found: {headers}")
        type_map = {k.lower(): v for k, v in spec.get("type_map", {}).items()}
        out = []
        if not f.has_fail:
            for r in rows:
                raw_type = str(r.get(cols.get("type"), "")).strip().lower()
                kind = type_map.get(raw_type) or next((v for k, v in type_map.items() if k in raw_type), None)
                if not kind:
                    f.fail("HRIS_TIMEOFF_TYPE", f"time-off type '{raw_type}' is not mapped (profile inbound.time_off.type_map)")
                    continue
                hours = D(r.get(cols["hours"]), ZERO)
                emp_id = str(r.get(cols.get("employee_id"), "")).strip().removesuffix(".0") if cols.get("employee_id") else ""
                emp_name = str(r.get(cols.get("employee_name"), "")).strip() if cols.get("employee_name") else ""
                if "date" in cols:
                    days = [_safe_date(r.get(cols["date"]))]
                else:
                    lo, hi = _safe_date(r.get(cols["start_date"])), _safe_date(r.get(cols.get("end_date")) or r.get(cols["start_date"]))
                    days = [lo + _dt.timedelta(days=i) for i in range((hi - lo).days + 1)] if lo and hi else []
                    days = [d for d in days if d.weekday() < 5] or days
                    if len(days) > 1:
                        f.warn("HRIS_TIMEOFF_SPREAD", f"{emp_id or emp_name}: {hours} {kind} hours spread evenly over {len(days)} days; "
                               "use a per-day export if hours differ by day")
                if not days or any(d is None for d in days):
                    f.fail("HRIS_TIMEOFF_DATE", f"{emp_id or emp_name}: unreadable time-off date")
                    continue
                per_day = hours / len(days)
                for d in days:
                    if not (period.start <= d <= period.end):
                        continue
                    out.append({"employee_id": emp_id, "employee_name": "" if emp_id else emp_name, "date": d.isoformat(),
                                "type": kind, "hours": str(per_day.quantize(D("0.01"))), "location": ""})
            _write_csv(out_dir / "time_off.csv", out, ["employee_id", "employee_name", "date", "type", "hours", "location"])
            report.append(f"Wrote {len(out)} time-off rows inside the period.")

    report += ["", "## Findings"] + [f"- **{i['severity']}** {i['message']}" for i in f.items] if f.items else ["", "No findings."]
    (period.dir / "output").mkdir(exist_ok=True)
    (period.dir / "output" / "hris_import_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return f


def _location(cfg, label):
    if not label:
        return None
    key = norm_name(label)
    for loc_id, loc in cfg.locations.items():
        labels = [loc_id, loc.get("name", ""), *loc.get("hris_labels", []), *loc.get("pos_labels", [])]
        if any(norm_name(x) == key for x in labels if x):
            return loc_id
    return None


def _safe_date(value):
    try:
        return parse_date(value)
    except (ValueError, TypeError):
        return None


def _iso(value):
    d = _safe_date(value)
    return d.isoformat() if d else ""


def _write_csv(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------- outbound
def _fmt_date(d, fmt):
    if d is None:
        return ""
    return d.strftime({"mdy": "%m/%d/%Y", "iso": "%Y-%m-%d", "ymd": "%Y%m%d"}.get(fmt, fmt))


def _num(v, places=2):
    if v is None or v == "":
        return ""
    return f"{D(v):.{places}f}"


def aggregate(lines, inputs, cfg, split_by_location=True, include_memo=True):
    """Group earnings lines into export rows: employee x (location) x processor code x rate."""
    groups = defaultdict(lambda: {"hours": ZERO, "amount": ZERO})
    for l in lines:
        if l["kind"] == "memo" and not include_memo:
            continue
        entry = cfg.pay_codes.get(l["pay_code"], {})
        if entry.get("export_as") == "none":
            continue  # paid by the payroll system from its own records (e.g. time off); shown in the workbook only
        key = (l["employee_id"], l["location_id"] if split_by_location else "",
               entry.get("code") or l["pay_code"], entry.get("label") or l["pay_code"],
               entry.get("export_as", "amount"), l["rate"] if entry.get("export_as") == "hours" else None,
               l["pay_code"], l["kind"])
        groups[key]["hours"] += l["hours"] or ZERO
        groups[key]["amount"] += l["amount"]
    out = []
    for (emp_id, loc, code, label, export_as, rate, pay_key, kind), v in groups.items():
        emp = inputs.employees[emp_id]
        loc_cfg = cfg.locations.get(loc) or cfg.locations.get(emp.home_location) or {}
        out.append({
            "employee_id": emp_id, "payroll_id": emp.payroll_id or emp_id,
            "first_name": emp.first, "last_name": emp.last, "name": emp.name,
            "location_id": loc, "location_name": loc_cfg.get("name", ""), "location_code": loc_cfg.get("payroll_code", loc),
            "code": code, "label": label, "export_as": export_as, "pay_key": pay_key, "kind": kind,
            "hours": v["hours"], "rate": rate, "amount": money(v["amount"]),
        })
    out.sort(key=lambda r: (r["last_name"], r["first_name"], r["location_id"], r["code"]))
    return out


def export_payroll(profile, export_id, cfg, period, inputs, lines, settings=None):
    """Write one outbound file. Returns (path, summary dict, Findings)."""
    f = Findings()
    settings = {**(profile.get("defaults") or {}), **(cfg.data.get("systems", {}).get("payroll_settings") or {}), **(settings or {})}
    spec = next((o for o in profile.get("outbound", []) if o["id"] == export_id), None)
    if spec is None:
        raise ValueError(f"profile {profile['id']} has no outbound export '{export_id}'")
    rows = aggregate(lines, inputs, cfg, split_by_location=settings.get("split_by_location", True),
                     include_memo=spec.get("include_memo", True))
    which = spec.get("include", "all")
    if which == "hours":
        rows = [r for r in rows if r["export_as"] == "hours"]
    elif which == "amount":
        rows = [r for r in rows if r["export_as"] == "amount"]
    for need in spec.get("settings_required", []):
        if not settings.get(need):
            f.fail("EXPORT_SETTING", f"{profile['name']} export needs '{need}' (config.systems.payroll_settings.{need})")
    pay_date = period.pay_date or period.end
    ctx = {"period_start": period.start, "period_end": period.end, "pay_date": pay_date,
           "batch_id": settings.get("batch_id") or pay_date.strftime("%y%m%d"), **settings}
    names = _SafeDict({k: v for k, v in ctx.items() if isinstance(v, str)})
    names.update(period_end=period.end.isoformat(), pay_date=pay_date.isoformat(), period_start=period.start.isoformat())
    filename = spec.get("filename", f"{profile['id']}_{export_id}_{{period_end}}.csv").format_map(names)
    _rate_on_file_check(spec, rows, inputs, f)
    out_path = period.output_dir / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if spec["layout"] == "long":
        grid = _long(spec, rows, ctx, settings)
    elif spec["layout"] == "adp_epi":
        grid = _adp(spec, rows, ctx, settings, f)
    else:
        raise ValueError(f"unknown layout {spec['layout']}")
    delim = "\t" if spec.get("delimiter") == "tab" else ","
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=delim)
        if spec.get("include_header", True):
            w.writerow(grid[0])
        w.writerows(grid[1:])
    hours_total = sum((r["hours"] for r in rows if r["export_as"] == "hours"), ZERO)
    amount_total = sum((r["amount"] for r in rows if r["export_as"] == "amount"), ZERO)
    hours_value = sum((r["amount"] for r in rows if r["export_as"] == "hours"), ZERO)
    summary = {"file": str(out_path), "rows": len(grid) - 1, "employees": len({r["employee_id"] for r in rows}),
               "amount_total": amount_total, "hours_total": hours_total, "hours_lines_value": hours_value,
               "grand_total": amount_total + hours_value,
               "note": "Hours lines are paid at the rate your payroll system has on file; confirm those rates match."}
    return out_path, summary, f


class _SafeDict(dict):
    """Unknown {placeholders} in a file name stay visible instead of crashing the export."""

    def __missing__(self, key):
        return f"{{{key}}}"


def _rate_on_file_check(spec, rows, inputs, f):
    """Hours go to the payroll system without a rate (it uses the rate on file). If one person's
    hours were earned at more than one base rate this period, one rate on file cannot pay them right."""
    sends_rate = spec.get("layout") == "long" and spec.get("include_rate", True) and \
        any(field == "rate" for _, field in spec.get("columns", []))
    if sends_rate:
        return
    multiplier = {"overtime": D("1.5"), "doubletime": D("2")}
    bases = defaultdict(set)
    for r in rows:
        if r["export_as"] == "hours" and r["rate"] is not None and r["hours"]:
            bases[r["employee_id"]].add((D(r["rate"]) / multiplier.get(r["pay_key"], D(1))).quantize(D("0.01")))
    for emp_id, found in bases.items():
        if len(found) > 1:
            f.warn("EXPORT_RATE_ON_FILE", f"{inputs.employees[emp_id].name}: hours this period were earned at "
                   f"{len(found)} base rates ({', '.join(str(x) for x in sorted(found))}) but the payroll system pays hours at "
                   "the one rate it has on file. Send the difference as an amount line, or split the hours by rate by hand")


FIELD_GETTERS = {
    "employee_id": lambda r, c: r["employee_id"], "payroll_id": lambda r, c: r["payroll_id"],
    "first_name": lambda r, c: r["first_name"], "last_name": lambda r, c: r["last_name"], "name": lambda r, c: r["name"],
    "location_id": lambda r, c: r["location_id"], "location_name": lambda r, c: r["location_name"],
    "location_code": lambda r, c: r["location_code"], "code": lambda r, c: r["code"], "label": lambda r, c: r["label"],
    "hours": lambda r, c: _num(r["hours"]) if r["export_as"] == "hours" or c.get("hours_on_amount_lines") else "",
    "hours_always": lambda r, c: _num(r["hours"]) if r["hours"] else "",
    "rate": lambda r, c: _num(r["rate"], 4) if r["rate"] is not None and c.get("include_rate", True) else "",
    "amount": lambda r, c: "" if r["export_as"] == "hours" and c.get("blank_amount_for_hours", True) else _num(r["amount"]),
    "det": lambda r, c: "E", "blank": lambda r, c: "",
    "rate_type": lambda r, c: c.get("rate_type_map", {}).get(r["pay_key"], c.get("rate_type_map", {}).get("default", "")),
}


def _long(spec, rows, ctx, settings):
    header = [col[0] for col in spec["columns"]]
    grid = [header]
    opts = {**spec, **settings}
    for r in rows:
        out = []
        for _, field in spec["columns"]:
            if field.startswith("const:"):
                out.append(field[6:])
            elif field.startswith("date:"):
                key, fmt = field[5:].split("|") if "|" in field else (field[5:], "mdy")
                out.append(_fmt_date(ctx.get(key), fmt))
            elif field.startswith("setting:"):
                out.append(str(settings.get(field[8:], "")))
            else:
                out.append(FIELD_GETTERS[field](r, opts))
        grid.append(out)
    return grid


def _adp(spec, rows, ctx, settings, f):
    """ADP paydata batch: one row per employee (per department when split), Reg/OT hours,
    then Hours 3/4 and Earnings 3/4/5 code+amount pairs; overflow continues on another row."""
    hours_slots, earn_slots = spec.get("hours_slots", 2), spec.get("earnings_slots", 3)
    header = ["Co Code", "Batch ID", "File #"]
    if settings.get("split_by_location", True):
        header.append("Temp Dept")
    header += ["Reg Hours", "O/T Hours"]
    for i in range(hours_slots):
        header += [f"Hours {3 + i} Code", f"Hours {3 + i} Amount"]
    for i in range(earn_slots):
        header += [f"Earnings {3 + i} Code", f"Earnings {3 + i} Amount"]
    grid = [header]
    reg_keys = set(spec.get("regular_keys", ["regular"]))
    ot_keys = set(spec.get("overtime_keys", ["overtime"]))
    groups = defaultdict(list)
    for r in rows:
        groups[(r["payroll_id"], r["location_code"] if settings.get("split_by_location", True) else "")].append(r)
    for (file_no, dept), items in groups.items():
        reg = sum((r["hours"] for r in items if r["pay_key"] in reg_keys and r["export_as"] == "hours"), ZERO)
        ot = sum((r["hours"] for r in items if r["pay_key"] in ot_keys and r["export_as"] == "hours"), ZERO)
        hour_pairs = [(r["code"], _num(r["hours"])) for r in items
                      if r["export_as"] == "hours" and r["pay_key"] not in reg_keys | ot_keys and r["hours"]]
        earn_pairs = [(r["code"], _num(r["amount"])) for r in items if r["export_as"] == "amount" and r["amount"]]
        if any(r["export_as"] == "hours" and r["rate"] is not None for r in items):
            f.info("EXPORT_ADP_RATE", f"File # {file_no}: hours are paid at ADP's rate on file; confirm it matches {sorted({str(r['rate']) for r in items if r['rate'] is not None})}")
        first = True
        while first or hour_pairs or earn_pairs:
            row = [settings.get("co_code", ""), ctx["batch_id"], file_no]
            if settings.get("split_by_location", True):
                row.append(dept)
            row += [_num(reg) if first and reg else "", _num(ot) if first and ot else ""]
            for _ in range(hours_slots):
                code, val = hour_pairs.pop(0) if hour_pairs else ("", "")
                row += [code, val]
            for _ in range(earn_slots):
                code, val = earn_pairs.pop(0) if earn_pairs else ("", "")
                row += [code, val]
            grid.append(row)
            first = False
    return grid
