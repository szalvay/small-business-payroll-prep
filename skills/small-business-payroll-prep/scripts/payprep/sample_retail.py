"""The retail sample: a made-up three-store outdoor retailer in two states.

`payroll.py sample <dir> --kind retail` builds it on demand. Everything here is fictional:
the business, the people, the rates and the minimum wages (example values only). The same
seed always builds the same stores.

What it exercises: hourly staff on the clock, sales commission by product category with
returns that claw it back and employee purchases excluded, a per-unit protection-plan
spiff, a tiered monthly loyalty sign-up bonus, card tips at a coffee bar, overtime across
two stores of the same company, California daily overtime, double time and the seventh
consecutive day, a raise from the start of a period, a new hire in training, a termination, salaried
store managers split across stores, a coverage stipend and a monthly store bonus on
sales against target and shrink. HR exports are in the ADP Workforce Now layout and the
upload file is an ADP paydata batch.
"""
import datetime as dt
import json
import random
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from .inputs import SPEC
from .sample import write_csv, write_report

D = lambda x: Decimal(str(x))
rng = random.Random(11)

LOCS = {
    "PD": {"id": "PD", "name": "Pearl District", "employer_id": "E1", "city": "Portland", "state": "OR",
           "min_wage": [{"rate": "16.30", "effective_from": "2025-07-01"}, {"rate": "16.80", "effective_from": "2026-07-01"}],
           "pos_labels": ["Harbor & Pine Pearl", "Store 11"], "hris_labels": ["Pearl District Store"], "payroll_code": "110"},
    "BV": {"id": "BV", "name": "Beaverton", "employer_id": "E1", "city": "Beaverton", "state": "OR",
           "min_wage": [{"rate": "16.30", "effective_from": "2025-07-01"}, {"rate": "16.80", "effective_from": "2026-07-01"}],
           "pos_labels": ["Harbor & Pine Beaverton", "Store 12"], "hris_labels": ["Beaverton Store"], "payroll_code": "120"},
    "SM": {"id": "SM", "name": "Midtown", "employer_id": "E2", "city": "Sacramento", "state": "CA",
           "min_wage": [{"rate": "16.50", "effective_from": "2026-01-01"}],
           "pos_labels": ["Harbor & Pine Midtown", "Store 21"], "hris_labels": ["Midtown Sacramento Store"], "payroll_code": "210"},
}

ROLES = [
    {"id": "sales_associate", "label": "Sales Associate", "pay_basis": "hourly", "exempt": False, "hours_worked_source": "clock",
     "service_categories": [], "tips": False, "hris_titles": ["Sales Associate", "Seasonal Sales Associate"]},
    {"id": "key_holder", "label": "Key Holder", "pay_basis": "hourly", "exempt": False, "hours_worked_source": "clock",
     "service_categories": [], "tips": False, "hris_titles": ["Key Holder"]},
    {"id": "stock_associate", "label": "Stock Associate", "pay_basis": "hourly", "exempt": False, "hours_worked_source": "clock",
     "service_categories": [], "tips": False, "hris_titles": ["Stockroom Associate"]},
    {"id": "barista", "label": "Barista", "pay_basis": "hourly", "exempt": False, "hours_worked_source": "clock",
     "service_categories": [], "tips": True, "hris_titles": ["Barista"]},
    {"id": "store_manager", "label": "Store Manager", "pay_basis": "salary", "exempt": True, "service_categories": [],
     "tips": False, "hris_titles": ["Store Manager"]},
]
HOURLY = ["sales_associate", "key_holder", "stock_associate", "barista"]
SELLERS = ["sales_associate", "key_holder"]

TIME_PAY = [{"role": r, "category": c, "basis": "base_rate", "pay_code": "regular"}
            for r in HOURLY for c in ("worked", "training", "meeting")]
TIME_OFF = ([{"role": r, "type": t, "basis": "base_rate", "pay_code": t} for r in HOURLY for t in ("sick", "pto")]
            + [{"role": "store_manager", "type": t, "basis": "base_rate", "pay_code": t} for t in ("sick", "pto")])

INCENTIVES = [
    {"id": "sales_commission", "label": "Sales commission", "source": "sales", "kind": "percent", "frequency": "pay_period",
     "eligible_roles": SELLERS, "pay_code": "commission", "include_in_regular_rate": True,
     "rates": [{"match": "category", "value": "footwear", "rate": "3"}, {"match": "category", "value": "apparel", "rate": "2"},
               {"match": "category", "value": "equipment", "rate": "1"}, {"match": "category", "value": "gift_card", "rate": "0"}],
     "exclude": [{"field": "item_type", "values": ["employee_purchase"]}]},
    {"id": "protection_plan", "label": "Protection plan spiff", "source": "sales", "kind": "per_unit", "frequency": "pay_period",
     "eligible_roles": SELLERS, "pay_code": "spiff", "include_in_regular_rate": True,
     "rates": [{"match": "category", "value": "protection_plan", "rate": "5"}]},
    {"id": "loyalty", "label": "Loyalty sign-up bonus", "source": "sales", "kind": "per_unit", "frequency": "monthly",
     "eligible_roles": SELLERS + ["barista"], "pay_code": "loyalty_bonus", "include_in_regular_rate": True,
     "rates": [{"match": "category", "value": "loyalty_signup"}], "tier_method": "marginal", "tier_scope": "employee",
     "tiers": [{"from": "1", "to": "10", "rate": "1"}, {"from": "11", "rate": "2"}]},
]

PAY_CODES = {
    "regular": ("Regular", "REG", "hours"), "overtime": ("Overtime", "OT", "hours"), "doubletime": ("Double time", "DBL", "hours"),
    "ot_premium": ("Overtime premium", "OTP", "amount"), "salary": ("Salary", "SAL", "amount"),
    "card_tips": ("Credit card tips", "TIP", "amount"), "cash_tips": ("Cash tips (declared)", "CTP", "amount"),
    "sick": ("Sick", "SCK", "hours"), "pto": ("PTO", "PTO", "hours"), "commission": ("Sales commission", "COM", "amount"),
    "spiff": ("Spiff", "SPF", "amount"), "loyalty_bonus": ("Loyalty sign-up bonus", "LYB", "amount"),
    "bonus": ("Store bonus", "BON", "amount"), "stipend": ("Stipend", "STP", "amount"),
    "back_pay": ("Back pay", "BPY", "amount"), "reimbursement": ("Reimbursement", "REI", "amount"),
    "min_wage_makeup": ("Minimum wage make-up", "MWM", "amount"),
    "service_wages": ("Service pay (not used)", "", "none"), "service_per_unit": ("Per-service pay (not used)", "", "none"),
    "service_commission": ("Service commission (not used)", "", "none"),
    "nonproductive_time": ("Non-productive time (not used)", "", "none"), "rest_recovery": ("Rest and recovery (not used)", "", "none"),
}

STAFF = [
    # id, file #, first, last, role, home, rate, hire, term
    ("R101", "000101", "Priya", "Shah", "sales_associate", "PD", "18.00", "2024-05-01", None),
    ("R102", "000102", "Marcus", "Avery", "sales_associate", "PD", "17.50", "2025-03-17", None),
    ("R103", "000103", "Tessa", "Quinn", "key_holder", "PD", "21.00", "2023-09-05", None),
    ("R104", "000104", "Leo", "Park", "barista", "PD", "16.80", "2025-11-03", None),
    ("R105", "000105", "Nina", "Ford", "stock_associate", "PD", "17.25", "2024-02-12", None),
    ("R201", "000201", "Omar", "Haddad", "sales_associate", "BV", "17.75", "2024-08-19", None),
    ("R202", "000202", "Zoe", "Carter", "sales_associate", "BV", "17.25", "2026-10-12", None),
    ("R203", "000203", "Felix", "Grant", "key_holder", "BV", "20.50", "2022-06-01", "2026-10-28"),
    ("R301", "000301", "Ana", "Torres", "sales_associate", "SM", "18.50", "2024-04-22", None),
    ("R302", "000302", "Ravi", "Menon", "key_holder", "SM", "22.00", "2023-01-09", None),
    ("R303", "000303", "Hana", "Sato", "stock_associate", "SM", "17.00", "2025-06-30", None),
    ("M1", "000901", "Elena", "Ruiz", "store_manager", "PD", "64000", "2021-04-05", None),
    ("M2", "000902", "Paul", "Werner", "store_manager", "SM", "68000", "2022-10-17", None),
]
POS_SPELLING = {"R101": "SHAH, PRIYA", "R201": "Haddad, omar"}

PERIODS = [  # biweekly, Monday to Sunday, so no workweek straddles two periods
    (dt.date(2026, 10, 5), dt.date(2026, 10, 18), dt.date(2026, 10, 23), False),
    (dt.date(2026, 10, 19), dt.date(2026, 11, 1), dt.date(2026, 11, 6), True),
]
MONTH = (dt.date(2026, 10, 1), dt.date(2026, 10, 31))


def config():
    return {
        "schema_version": "1.0",
        "company": {"name": "Harbor & Pine Outfitters (sample)", "industry": "retail", "pay_frequency": "biweekly",
                    "workweek_start": "monday", "ot_aggregation": "employer", "min_wage_makeup": "flag", "cash_tips": "report_only",
                    "notes": "Fictional sample business. Rates, minimum wages and payroll codes are example values only."},
        "approval": {},
        "systems": {"hris": "adp_wfn", "payroll": "adp_wfn", "pos": "Example retail POS",
                    "payroll_settings": {"co_code": "HPX", "split_by_location": False},
                    "pos_reports": [
                        {"report": "Sales by associate", "maps_to": "sales", "filters": "pay period; all associates; include returns",
                         "frequency": "pay_period"},
                        {"report": "Loyalty sign-ups by associate", "maps_to": "sales", "filters": "full month on month-end runs",
                         "frequency": "monthly"},
                        {"report": "Tips by employee", "maps_to": "tips", "filters": "pay period; coffee bar", "frequency": "pay_period"},
                        {"report": "Time card detail", "maps_to": "time_entries", "filters": "pay period only", "frequency": "pay_period"},
                        {"report": "Store scorecard", "maps_to": "location_metrics", "filters": "full month", "frequency": "monthly"}]},
        "employers": [{"id": "E1", "legal_name": "Harbor & Pine Oregon LLC"}, {"id": "E2", "legal_name": "Harbor & Pine California LLC"}],
        "locations": list(LOCS.values()),
        "state_rules": {
            "OR": {"weekly_ot_threshold": "40", "daily_ot": None, "seventh_day_ot": False, "piece_rate_nonproductive_separate": False,
                   "confirmed_by_owner": True, "notes": "Sample only."},
            "CA": {"weekly_ot_threshold": "40", "daily_ot": {"threshold": "8", "double_threshold": "12"}, "seventh_day_ot": True,
                   "piece_rate_nonproductive_separate": True, "confirmed_by_owner": True, "notes": "Sample only."}},
        "roles": ROLES, "time_pay": TIME_PAY, "time_off_pay": TIME_OFF, "incentives": INCENTIVES,
        "stipends": [{"id": "two_stores", "employee_id": "M1", "label": "Running two stores", "amount": "150", "location_id": "BV",
                      "effective_from": "2026-09-01", "pay_code": "stipend"}],
        "manager_allocation": [{"employee_id": "M1", "location_id": "PD", "share": "0.6"},
                               {"employee_id": "M1", "location_id": "BV", "share": "0.4"},
                               {"employee_id": "M2", "location_id": "SM", "share": "1"}],
        "bonus_pools": [{"id": "store_bonus", "label": "Store manager bonus", "frequency": "monthly", "pool_per_location": "500",
                         "pay_code": "bonus", "include_in_regular_rate": False,
                         "metrics": [{"id": "to_target", "label": "Sales to target", "numerator": "net_sales",
                                      "denominator": "sales_target", "compare": ">=", "threshold": "1", "weight": "0.6"},
                                     {"id": "shrink", "label": "Shrink rate", "numerator": "shrink_dollars",
                                      "denominator": "net_sales", "compare": "<=", "threshold": "0.015", "weight": "0.4"}],
                         "recipients": [{"location_id": "PD", "employee_id": "M1", "share": "1"},
                                        {"location_id": "BV", "employee_id": "M1", "share": "1"},
                                        {"location_id": "SM", "employee_id": "M2", "share": "1"}]}],
        "employee_overrides": [
            {"employee_id": "R102", "rates": [{"role": "sales_associate", "rate": "18.25", "rate_type": "hourly",
                                               "effective_from": "2026-10-19"}]}],
        "pay_codes": {k: {"label": v[0], "code": v[1], "export_as": v[2]} for k, v in PAY_CODES.items()},
        "checks": {"plausibility": {"min_avg_service_hours": "0.25", "max_avg_service_hours": "4", "max_weekly_hours": "70",
                                    "anomaly_threshold": "0.25"}},
        "intake_notes": [{"id": "start.4", "topic": "Before we start",
                          "question": "What went wrong in past payrolls that you never want to see again?",
                          "answer": "Returns were never taken out of commission, and Sacramento's daily overtime was paid as weekly."}],
    }


def days(start, end):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


# Shift plans: weekday (Mon=0) -> hours, per store
SHIFTS = {
    "R101": {"PD": {0: 8, 1: 8, 3: 8, 4: 8, 5: 8}},
    "R102": {"PD": {1: 7, 2: 7, 4: 7, 5: 8, 6: 6}},
    "R103": {"PD": {0: 8, 2: 8, 3: 8, 4: 8, 6: 7}},
    "R104": {"PD": {0: 6, 1: 6, 2: 6, 5: 7, 6: 7}},
    "R105": {"PD": {0: 8, 1: 8, 2: 8, 3: 8}},
    "R201": {"BV": {0: 8, 1: 8, 2: 8, 4: 8, 5: 7}},
    "R202": {"BV": {1: 6, 3: 6, 5: 8, 6: 6}},
    "R203": {"BV": {0: 8, 2: 8, 3: 8, 4: 8, 5: 8}},
    "R301": {"SM": {0: 8, 1: 8, 2: 8, 4: 8, 5: 8}},
    "R302": {"SM": {0: 8, 1: 8, 3: 8, 4: 8, 6: 8}},
    "R303": {"SM": {1: 8, 2: 8, 3: 8, 4: 8}},
}
CATALOG = {"footwear": [("Trail runner", 140), ("Hiking boot", 189), ("Camp sandal", 65)],
           "apparel": [("Rain shell", 179), ("Fleece pullover", 89), ("Wool socks", 22), ("Base layer", 75)],
           "equipment": [("Day pack", 110), ("Headlamp", 45), ("Two-person tent", 329), ("Trekking poles", 99)]}


def period_data(start, end, monthly):
    staff = {s[0]: s for s in STAFF}
    time_entries, sales, tips, time_off = [], [], [], []
    for emp, plan in SHIFTS.items():
        _, _, first, last, role, home, rate, hire, term = staff[emp]
        name = POS_SPELLING.get(emp, f"{last}, {first}")
        for d in days(start, end):
            if hire and d < dt.date.fromisoformat(hire):
                continue
            if term and d > dt.date.fromisoformat(term):
                continue
            for loc, sched in plan.items():
                h = sched.get(d.weekday())
                # Nina covers two Beaverton shifts in the week of 10/12: 44 hours across two stores
                if emp == "R105" and d in (dt.date(2026, 10, 16), dt.date(2026, 10, 17)):
                    time_entries.append({"employee_id": emp, "location": "BV", "date": d.isoformat(), "category": "worked",
                                         "hours": "8.00" if d.day == 16 else "4.00"})
                # Priya picks up a Sunday in the week of 10/19: 42 hours, with commission in the regular rate
                if emp == "R101" and d == dt.date(2026, 10, 25):
                    h = 2
                # Sacramento: Ana works a 10-hour day and a 13-hour inventory night
                if emp == "R301" and d == dt.date(2026, 10, 10):
                    h = 10
                if emp == "R301" and d == dt.date(2026, 10, 28):
                    h = 13
                # Ravi works seven days in a row in the week of 10/26
                if emp == "R302" and dt.date(2026, 10, 26) <= d <= dt.date(2026, 11, 1):
                    h = sched.get(d.weekday()) or 6
                if not h:
                    continue
                category = "training" if emp == "R202" and d <= dt.date(2026, 10, 15) else "worked"
                time_entries.append({"employee_name": name, "location": LOCS[loc]["pos_labels"][1], "date": d.isoformat(),
                                     "category": category, "hours": f"{h:.2f}"})
                if role in SELLERS and category == "worked":
                    for _ in range(rng.randint(2, 5)):
                        cat = rng.choice(["footwear", "apparel", "apparel", "equipment"])
                        item, price = rng.choice(CATALOG[cat])
                        qty = 2 if item == "Wool socks" and rng.random() < 0.4 else 1
                        sales.append({"employee_name": name, "location": LOCS[loc]["pos_labels"][0], "date": d.isoformat(),
                                      "category": cat, "item": item, "item_type": "sale", "quantity": str(qty),
                                      "amount": f"{price * qty:.2f}"})
                    if rng.random() < 0.3:
                        sales.append({"employee_name": name, "location": LOCS[loc]["pos_labels"][0], "date": d.isoformat(),
                                      "category": "protection_plan", "item": "2-year protection plan", "item_type": "sale",
                                      "quantity": "1", "amount": "24.99"})
                    if rng.random() < 0.2:
                        sales.append({"employee_name": name, "location": LOCS[loc]["pos_labels"][0], "date": d.isoformat(),
                                      "category": "gift_card", "item": "Gift card", "item_type": "sale", "quantity": "1",
                                      "amount": f"{rng.choice([25, 50, 100]):.2f}"})
                if role == "barista" and category == "worked":
                    tips.append({"employee_name": name, "location": LOCS[loc]["pos_labels"][0], "date": d.isoformat(),
                                 "tip_type": "card", "amount": f"{rng.randint(1800, 5200) / 100:.2f}"})
    # a return that claws back commission, and an employee purchase that pays none
    if start == PERIODS[0][0]:
        sales.append({"employee_id": "R201", "location": "BV", "date": "2026-10-14", "category": "footwear", "item": "Hiking boot",
                      "item_type": "return", "quantity": "1", "amount": "189.00", "refund": "Y"})
        sales.append({"employee_id": "R103", "location": "PD", "date": "2026-10-09", "category": "equipment", "item": "Two-person tent",
                      "item_type": "employee_purchase", "quantity": "1", "amount": "246.75"})
    else:
        sales.append({"employee_id": "R301", "location": "SM", "date": "2026-10-27", "category": "apparel", "item": "Rain shell",
                      "item_type": "return", "quantity": "1", "amount": "179.00", "refund": "Y"})
    # loyalty sign-ups for the whole month, paid on the month-end run
    if monthly:
        month_days = [d for d in days(*MONTH)]
        for emp, n in (("R101", 14), ("R102", 6), ("R103", 9), ("R104", 12), ("R201", 8), ("R202", 3), ("R301", 11), ("R302", 5)):
            loc = staff[emp][5]
            hire = dt.date.fromisoformat(staff[emp][7])
            for _ in range(n):
                d = rng.choice([x for x in month_days if x >= hire])
                sales.append({"employee_id": emp, "location": loc, "date": d.isoformat(), "category": "loyalty_signup",
                              "item": "Loyalty program sign-up", "item_type": "signup", "quantity": "1", "amount": "0.00"})
    # a declared cash tip
    tips.append({"employee_id": "R104", "location": "PD", "date": (start + dt.timedelta(days=2)).isoformat(),
                 "tip_type": "cash", "amount": "18.00"})
    # time off
    if start == PERIODS[0][0]:
        time_off += [{"employee_id": "R303", "date": "2026-10-07", "type": "sick", "hours": "8.00"},
                     {"employee_id": "R102", "date": "2026-10-08", "type": "pto", "hours": "7.00"}]
    else:
        time_off += [{"employee_id": "R201", "date": "2026-10-23", "type": "sick", "hours": "8.00"},
                     {"employee_id": "M2", "date": "2026-10-30", "type": "pto", "hours": "8.00"},
                     {"employee_id": "R103", "date": "2026-10-20", "type": "pto", "hours": "8.00"}]
    return sales, tips, time_entries, time_off


def _totals(rows, label_to_id, fields, lo, hi):
    out = defaultdict(lambda: defaultdict(lambda: D(0)))
    for r in rows:
        d = dt.date.fromisoformat(r["date"])
        if not (lo <= d <= hi):
            continue
        loc = label_to_id.get(r.get("location"), r.get("location"))
        sign = -1 if r.get("refund") == "Y" else 1
        for f in fields:
            if r.get(f):
                out[loc][f] += sign * D(r[f])
    return out


def build_retail_sample(dest):
    """Write the retail sample workspace into dest (which must be empty or missing)."""
    global rng
    rng = random.Random(11)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "payroll_config.json").write_text(json.dumps(config(), indent=2) + "\n")
    label_to_id = {}
    for loc in LOCS.values():
        for lab in [loc["id"], *loc["pos_labels"]]:
            label_to_id[lab] = loc["id"]
    roles = {r["id"]: r for r in ROLES}
    for start, end, pay, monthly in PERIODS:
        pdir = dest / "periods" / f"{start}_{end}"
        for sub in ("raw", "inputs", "output"):
            (pdir / sub).mkdir(parents=True, exist_ok=True)
        roster = []
        for eid, file_no, first, last, role, home, rate, hire, term in STAFF:
            gone = term and dt.date.fromisoformat(term) <= end
            roster.append({"Associate ID": eid, "File Number": file_no, "Legal First Name": first, "Legal Last Name": last,
                           "Position Status": "Terminated" if gone else "Active",
                           "Hire Date": dt.date.fromisoformat(hire).strftime("%m/%d/%Y"),
                           "Termination Date": dt.date.fromisoformat(term).strftime("%m/%d/%Y") if term else "",
                           "Location Description": LOCS[home]["hris_labels"][0], "Job Title Description": roles[role]["hris_titles"][0],
                           "Regular Pay Rate Amount": rate, "Regular Pay Rate Description": "Salary" if role == "store_manager" else "Hourly",
                           "Work Contact: Work Email": f"{first.lower()}@example.com"})
        write_csv(pdir / "raw" / "adp_worker_export.csv", list(roster[0].keys()), roster)
        sales, tips, time_entries, time_off = period_data(start, end, monthly)
        write_csv(pdir / "raw" / "adp_time_off.csv", ["Associate ID", "Payroll Name", "Date", "Time Off Policy", "Hours"],
                  [{"Associate ID": r["employee_id"], "Payroll Name": "", "Time Off Policy": {"sick": "Sick Leave", "pto": "Paid Time Off"}[r["type"]],
                    "Date": dt.date.fromisoformat(r["date"]).strftime("%m/%d/%Y"), "Hours": r["hours"]} for r in time_off])
        cols = lambda n: list(SPEC[n])
        write_csv(pdir / "inputs" / "sales.csv", cols("sales"), sales)
        write_csv(pdir / "inputs" / "tips.csv", cols("tips"), tips)
        write_csv(pdir / "inputs" / "time_entries.csv", cols("time_entries"), time_entries)
        adjustments, metrics = [], []
        if monthly:
            adjustments = [
                {"employee_id": "R303", "location": "SM", "pay_code": "back_pay", "description": "Missed 1.5 hours on 10/7 time card",
                 "hours": "1.5", "rate": "17.00", "taxable": "Y", "include_in_regular_rate": "N", "approved_by": "Owner"},
                {"employee_id": "M1", "location": "BV", "pay_code": "reimbursement", "description": "Window cleaning supplies",
                 "amount": "38.20", "taxable": "N", "include_in_regular_rate": "N", "approved_by": "Owner"}]
            for loc, (net, target, shrink) in {"PD": (184200, 175000, 2210), "BV": (121900, 130000, 1340),
                                               "SM": (152400, 150000, 3050)}.items():
                metrics += [{"location": loc, "metric": m, "value": str(v), "window_start": str(MONTH[0]), "window_end": str(MONTH[1])}
                            for m, v in (("net_sales", net), ("sales_target", target), ("shrink_dollars", shrink))]
        write_csv(pdir / "inputs" / "adjustments.csv", cols("adjustments"), adjustments)
        write_csv(pdir / "inputs" / "location_metrics.csv", cols("location_metrics"), metrics)

        period_sales = [r for r in sales if start <= dt.date.fromisoformat(r["date"]) <= end]
        sources = []
        sale_t = _totals(sales, label_to_id, ("amount", "quantity"), start, end)
        time_t = _totals(time_entries, label_to_id, ("hours",), start, end)
        for loc_id, loc in LOCS.items():
            label = loc["pos_labels"][0]
            rows = [dict(r, employee_name=r.get("employee_name") or next(f"{s[3]}, {s[2]}" for s in STAFF if s[0] == r["employee_id"]))
                    for r in period_sales if label_to_id.get(r["location"], r["location"]) == loc_id]
            write_report(pdir / "raw" / f"{loc_id}_sales_by_associate.xlsx", "Sales by Associate", label, start, end,
                         [("Associate", "employee_name"), ("Date", "date"), ("Category", "category"), ("Item", "item"),
                          ("Type", "item_type"), ("Return", "refund"), ("Qty", "quantity"), ("Net Sales", "amount")],
                         rows, "employee_name", ("quantity", "amount"), refund_key="refund")
            sources.append({"file": f"raw/{loc_id}_sales_by_associate.xlsx", "report": "Sales by associate", "location_id": loc_id,
                            "date_from": str(start), "date_to": str(end), "mapped_to": "sales",
                            "totals": {k: str(v) for k, v in sale_t[loc_id].items()}})
            sources.append({"report": "Time card detail", "location_id": loc_id, "date_from": str(start), "date_to": str(end),
                            "mapped_to": "time_entries", "totals": {k: str(v) for k, v in time_t[loc_id].items()}})
        period = {
            "period_start": str(start), "period_end": str(end), "pay_date": str(pay), "include_monthly": monthly,
            "monthly_window": {"start": str(MONTH[0]), "end": str(MONTH[1])} if monthly else None,
            "windows": {}, "attestations": [] if monthly else [
                {"input": "time_off", "location_id": "BV", "statement": "Nobody at Beaverton took time off", "by": "Owner"}],
            "sources": sources, "approved_variances": [], "expected_activity": [],
            "acknowledged_warnings": [],
            "salary_proration": None,
            "notes": "Sample period. Raw ADP exports are in raw/; run hris-import to build roster.csv, pay_rates.csv and time_off.csv.",
        }
        (pdir / "period.json").write_text(json.dumps(period, indent=2) + "\n")
    return dest
