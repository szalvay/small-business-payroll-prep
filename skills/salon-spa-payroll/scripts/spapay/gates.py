"""Pre-calculation gates. A FAIL here stops the run before any pay is computed.

Each gate exists because a real payroll went wrong without it: a missing sick-time
file that silently paid zero sick hours, a report pulled for the wrong location or
dates, an employee terminated before the export who vanished from it, a column
mapped one position off that turned service hours into zeros.
"""
from __future__ import annotations

from collections import defaultdict

from .util import D, ZERO, Findings, week_start

SOURCE_TOTAL_FIELDS = {
    "services": ("service_hours", "quantity", "revenue"),
    "addons": ("quantity",),
    "sales": ("amount", "quantity"),
    "tips": ("amount",),
    "time_entries": ("hours",),
    "time_off": ("hours",),
}


def active_windows(cfg, period):
    """Date windows (by source file) that incentives and bonus pools pay on this run."""
    windows = defaultdict(list)
    for inc in cfg.incentives:
        freq = inc.get("frequency", "pay_period")
        if freq == "monthly" and not period.include_monthly:
            continue
        win = period.window_for(inc["id"], freq)
        if win:
            windows[inc["source"]].append((inc["id"], win))
    return windows


def run_gates(cfg, period, inputs):
    f = Findings()
    emps = inputs.employees
    rows = inputs.rows

    # --- which inputs this run needs -------------------------------------
    roles_in_use = set()
    for emp in emps.values():
        if emp.status == "terminated" and emp.termination_date and emp.termination_date < period.start:
            continue
        roles_in_use.update(emp.roles())
    bases = {cfg.roles[r]["pay_basis"] for r in roles_in_use if r in cfg.roles}
    sources_needed = {"time_entries": any(
        cfg.roles[r].get("pay_basis") != "salary" and cfg.roles[r].get("hours_worked_source", "clock") == "clock"
        for r in roles_in_use if r in cfg.roles)}
    sources_needed["services"] = any(b.startswith("piece") or b == "service_revenue_pct" for b in bases)
    sources_needed["tips"] = any(cfg.roles[r].get("tips") for r in roles_in_use if r in cfg.roles)
    sources_needed["time_off"] = True
    windows = active_windows(cfg, period)
    sources_needed["addons"] = bool(windows.get("addons"))
    sources_needed["sales"] = bool(windows.get("sales"))
    bonus_active = [bp for bp in cfg.bonus_pools
                    if bp.get("frequency", "monthly") == "pay_period" or period.include_monthly]
    sources_needed["location_metrics"] = bool(bonus_active)

    for name, needed in sources_needed.items():
        if not needed:
            continue
        if name == "time_off":
            for loc_id in cfg.locations:
                has_rows = any(r["loc"] == loc_id for r in rows.get("time_off", []))
                if not has_rows and not period.attested_none("time_off", loc_id):
                    f.fail("GATE_TIMEOFF_MISSING",
                           f"no sick/PTO rows for location {loc_id} and no attestation that nobody took time off. "
                           "A missing time-off export pays zero sick hours and every check still passes; "
                           "add the rows or an attestation in period.json")
            continue
        if name not in inputs.present and not period.attested_none(name):
            f.fail("GATE_INPUT_MISSING",
                   f"inputs/{name}.csv is missing or empty but this run needs it; add it, or attest in period.json that there is none this period")

    # --- dates ------------------------------------------------------------
    for name in ("time_entries", "tips", "time_off"):
        for r in rows.get(name, []):
            if not (period.start <= r["date"] <= period.end):
                f.fail("GATE_DATE", f"{name}.csv line {r['_line']}: {r['date']} is outside the pay period "
                       f"{period.start}..{period.end}; hours and tips are paid only for days in the period")
    for name in ("services", "addons", "sales"):
        wins = [w for _, w in windows.get(name, [])] + [(period.start, period.end)]
        for r in rows.get(name, []):
            if not any(lo <= r["date"] <= hi for lo, hi in wins):
                f.fail("GATE_DATE", f"{name}.csv line {r['_line']}: {r['date']} is outside the pay period and every active pay window")
    for r in rows.get("adjustments", []):
        if r.get("amount") is None and (r.get("hours") is None or r.get("rate") is None):
            f.fail("GATE_ADJ", f"adjustments.csv line {r['_line']}: give an amount, or hours and rate")
        if (r.get("pay_code") or "") not in cfg.pay_codes:
            f.fail("GATE_ADJ", f"adjustments.csv line {r['_line']}: pay_code '{r.get('pay_code')}' has no processor code in the config")

    # --- employment status vs activity ----------------------------------
    activity = defaultdict(list)
    for name in ("time_entries", "services", "addons", "sales", "tips", "time_off"):
        for r in rows.get(name, []):
            activity[r["emp"]].append((name, r))
    for emp_id, acts in activity.items():
        emp = emps[emp_id]
        for name, r in acts:
            if emp.termination_date and r["date"] > emp.termination_date:
                f.fail("GATE_TERMED", f"{emp.name}: {name} on {r['date']} is after their termination date {emp.termination_date}")
                break
            if emp.hire_date and r["date"] < emp.hire_date:
                f.fail("GATE_PREHIRE", f"{emp.name}: {name} on {r['date']} is before their hire date {emp.hire_date}")
                break
        if emp.status == "terminated" and emp.termination_date and emp.termination_date < period.start:
            in_period = [r for n, r in acts if period.start <= r["date"] <= period.end]
            if in_period:
                f.fail("GATE_TERMED_PRIOR", f"{emp.name} was terminated {emp.termination_date}, before this period, "
                       "but appears in this period's data. POS reports keep terminated staff; confirm they were already paid out")
        if emp.status == "leave":
            f.warn("GATE_LEAVE", f"{emp.name} is on leave but has activity this period; confirm the status")

    for emp in emps.values():
        if emp.termination_date and period.start <= emp.termination_date <= period.end:
            f.info("GATE_FINAL_PAY", f"{emp.name} left on {emp.termination_date}. Final-pay deadlines vary by state and can be "
                   "sooner than this payday; confirm the final check was (or will be) issued on time")
        if emp.status != "active":
            continue
        if any(cfg.roles.get(r, {}).get("pay_basis") == "salary" for r in emp.roles()):
            continue
        if emp.hire_date and emp.hire_date > period.end:
            continue
        if emp_id_has_none(emp.id, activity):
            f.warn("GATE_NO_ACTIVITY", f"{emp.name} is active but has no hours, services or time off this period. "
                   "If they worked, they may be missing from an export (POS filters drop people terminated before the pull)")

    # --- report provenance and report totals ------------------------------
    if not period.sources:
        f.warn("GATE_NO_SOURCES", "period.json lists no source reports; the mapped CSVs cannot be checked against "
               "each report's own totals")
    for src in period.sources:
        label = src.get("file") or src.get("report") or "source"
        loc = src.get("location_id")
        if loc and loc not in cfg.locations:
            f.fail("GATE_SOURCE_LOC", f"source {label}: location_id '{loc}' is not configured")
            continue
        mapped = src.get("mapped_to")
        lo, hi = src.get("date_from"), src.get("date_to")
        if lo and hi:
            from .util import parse_date
            lo, hi = parse_date(lo), parse_date(hi)
            win = None
            if src.get("window"):
                win = period.windows.get(src["window"]) or (period.monthly_window if src["window"] == "monthly" else None)
            expected = win or (period.start, period.end)
            if (lo, hi) != expected:
                f.fail("GATE_SOURCE_DATES", f"source {label} covers {lo}..{hi} but should cover {expected[0]}..{expected[1]}; "
                       "re-export for the right dates (a full-week export on a boundary week re-pays days already paid)")
        for metric, stated in (src.get("totals") or {}).items():
            if mapped not in SOURCE_TOTAL_FIELDS or metric not in SOURCE_TOTAL_FIELDS[mapped]:
                f.warn("GATE_SOURCE_METRIC", f"source {label}: total '{metric}' for '{mapped}' is not checkable")
                continue
            got = ZERO
            for r in rows.get(mapped, []):
                if loc and r["loc"] != loc:
                    continue
                if lo and hi and not (lo <= r["date"] <= hi):
                    continue
                got += D(r.get(metric), ZERO)
            if abs(got - D(stated)) > D("0.01"):
                f.fail("GATE_SOURCE_TOTAL", f"source {label}: the report says {metric} = {D(stated)}, the mapped "
                       f"{mapped}.csv rows add to {got}. Something was dropped, doubled or mis-mapped")

    # --- expected activity ---------------------------------------------
    for exp in period.expected_activity:
        name = exp.get("input", "time_entries")
        hits = [r for r in rows.get(name, []) if r["emp"] == exp.get("employee_id")]
        if exp.get("category"):
            hits = [r for r in hits if r.get("category") == exp["category"]]
        total = sum((D(r.get("hours") or r.get("quantity") or r.get("amount"), ZERO) for r in hits), ZERO)
        if total < D(exp.get("minimum", "0.01")):
            f.fail("GATE_EXPECTED", f"expected {exp.get('category') or name} for {exp.get('employee_id')} "
                   f"({exp.get('reason', 'owner instruction')}) is not in the data yet")

    # --- plausibility -------------------------------------------------------
    plaus = cfg.checks.get("plausibility", {})
    min_avg = D(plaus.get("min_avg_service_hours", "0.25"))
    max_avg = D(plaus.get("max_avg_service_hours", "4"))
    max_week = D(plaus.get("max_weekly_hours", "70"))
    for loc_id in cfg.locations:
        svc = [r for r in rows.get("services", []) if r["loc"] == loc_id and period.start <= r["date"] <= period.end]
        qty = sum((r["quantity"] for r in svc), ZERO)
        hours = sum((r["service_hours"] for r in svc), ZERO)
        if svc and hours == ZERO:
            f.fail("GATE_ZERO_SVC_HOURS", f"location {loc_id}: {len(svc)} service rows but zero service hours. "
                   "The service-hours column was probably mapped from the wrong report column")
        elif qty > ZERO:
            avg = hours / qty
            if avg < min_avg or avg > max_avg:
                f.warn("GATE_SVC_AVG", f"location {loc_id}: average {avg:.2f} service hours per service is implausible; "
                       "check that quantity and service hours were not swapped")
    weekly = defaultdict(lambda: ZERO)
    for r in rows.get("time_entries", []):
        weekly[(r["emp"], week_start(r["date"], cfg.workweek_start))] += r["hours"]
    for (emp_id, wk), total in weekly.items():
        if total > max_week:
            f.warn("GATE_LONG_WEEK", f"{emps[emp_id].name}: {total} hours recorded in the week of {wk}; check for a duplicated export")
    # Identical service/add-on/sale lines are normal (two of the same add-on in a day);
    # identical tip or time rows almost always mean a report was mapped twice.
    seen = {}
    for name in ("tips", "time_entries"):
        for r in rows.get(name, []):
            key = (name, r["emp"], r["loc"], r["date"], r.get("category"), r.get("amount"), r.get("hours"), r.get("tip_type"))
            if key in seen:
                f.warn("GATE_DUP_ROW", f"{name}.csv lines {seen[key]} and {r['_line']} are identical; a doubled export pays twice")
            else:
                seen[key] = r["_line"]
    return f


def emp_id_has_none(emp_id, activity):
    return not activity.get(emp_id)
