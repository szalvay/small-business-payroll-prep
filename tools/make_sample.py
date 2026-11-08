#!/usr/bin/env python3
"""Build the sample workspace: a made-up three-location spa with every tricky case.

Everything here is fictional: the business, the people, the rates and the minimum
wages (example values only). Re-run after changing the engine's input format:
    python3 tools/make_sample.py
"""
import csv
import datetime as dt
import json
import random
import shutil
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "salon-spa-payroll"
DEST = SKILL / "assets" / "sample_workspace"
sys.path.insert(0, str(SKILL / "scripts"))

rng = random.Random(7)
D = lambda x: Decimal(str(x))

LOCS = {
    "DT": {"id": "DT", "name": "Downtown", "employer_id": "E1", "city": "Portland", "state": "OR",
           "min_wage": [{"rate": "16.30", "effective_from": "2025-07-01"}, {"rate": "16.80", "effective_from": "2026-07-01"}],
           "pos_labels": ["Willowbrook Downtown", "0101"], "hris_labels": ["Downtown Portland"], "payroll_code": "100"},
    "EC": {"id": "EC", "name": "Eastside", "employer_id": "E1", "city": "Salem", "state": "OR",
           "min_wage": [{"rate": "15.05", "effective_from": "2025-07-01"}, {"rate": "15.55", "effective_from": "2026-07-01"}],
           "pos_labels": ["Willowbrook Eastside", "0102"], "hris_labels": ["Eastside Salem"], "payroll_code": "200"},
    "VA": {"id": "VA", "name": "Riverside", "employer_id": "E2", "city": "Vancouver", "state": "WA",
           "min_wage": [{"rate": "17.13", "effective_from": "2026-01-01"}],
           "pos_labels": ["Willowbrook Riverside", "0201"], "hris_labels": ["Riverside Vancouver"], "payroll_code": "300"},
}

ROLES = [
    {"id": "massage_therapist", "label": "Massage Therapist", "pay_basis": "piece_service_hour", "exempt": False,
     "hours_worked_source": "services_plus_time", "service_categories": ["massage"], "tips": True,
     "hris_titles": ["Massage Therapist", "Licensed Massage Therapist"]},
    {"id": "stretch_therapist", "label": "Stretch Therapist", "pay_basis": "piece_service_hour", "exempt": False,
     "hours_worked_source": "services_plus_time", "service_categories": ["stretch"], "tips": True, "hris_titles": ["Stretch Therapist"]},
    {"id": "esthetician", "label": "Esthetician", "pay_basis": "piece_service_hour", "exempt": False,
     "hours_worked_source": "services_plus_time", "service_categories": ["facial"], "tips": True, "hris_titles": ["Esthetician"]},
    {"id": "front_desk", "label": "Front Desk", "pay_basis": "hourly", "exempt": False, "hours_worked_source": "clock",
     "service_categories": [], "tips": False, "hris_titles": ["Front Desk Associate", "Front Desk"]},
    {"id": "manager", "label": "Location Manager", "pay_basis": "salary", "exempt": True, "service_categories": [],
     "tips": False, "hris_titles": ["Location Manager", "General Manager"]},
]

PIECE = ["massage_therapist", "stretch_therapist", "esthetician"]
TIME_PAY = ([{"role": r, "category": c, "basis": "min_wage", "pay_code": c if c != "trainee" else "training"}
             for r in PIECE for c in ("lobby", "training", "trainee", "meeting")]
            + [{"role": r, "category": "trainer", "basis": "base_rate", "pay_code": "training"} for r in PIECE]
            + [{"role": "front_desk", "category": c, "basis": "base_rate", "pay_code": "regular"} for c in ("worked", "training", "meeting")])
TIME_OFF = ([{"role": r, "type": "sick", "basis": "min_wage", "pay_code": "sick"} for r in PIECE]
            + [{"role": "front_desk", "type": "sick", "basis": "base_rate", "pay_code": "sick"},
               {"role": "front_desk", "type": "pto", "basis": "base_rate", "pay_code": "pto"},
               {"role": "manager", "type": "pto", "basis": "base_rate", "pay_code": "pto"},
               {"role": "manager", "type": "sick", "basis": "base_rate", "pay_code": "sick"}])

INCENTIVES = [
    {"id": "addon_spiff", "label": "Add-on spiffs", "source": "addons", "kind": "per_unit", "frequency": "pay_period",
     "eligible_roles": ["massage_therapist", "stretch_therapist"], "pay_code": "enhancements", "include_in_regular_rate": True,
     "rates": [{"match": "code_prefix", "value": "CBD", "rate": "10"}, {"match": "code_prefix", "value": "CUP", "rate": "5"},
               {"match": "code_prefix", "value": "RTR", "rate": "2"},
               {"match": "code", "value": "KTAPE", "rate": "2", "only_employees": ["E104"]},
               {"match": "code", "value": "HOTSTONE", "rate": "0"}]},
    {"id": "esty_enhancement", "label": "Skin care enhancements", "source": "addons", "kind": "per_unit", "frequency": "pay_period",
     "eligible_roles": ["esthetician"], "pay_code": "enhancements", "include_in_regular_rate": True,
     "rates": [{"match": "code_prefix", "value": "SKN", "rate": "1"}]},
    {"id": "esty_advanced", "label": "Advanced facials", "source": "services", "kind": "per_unit", "frequency": "pay_period",
     "eligible_roles": ["esthetician"], "pay_code": "advanced_service", "include_in_regular_rate": True,
     "rates": [{"match": "code_prefix", "value": "ADV", "rate": "10"}]},
    {"id": "retail", "label": "Retail commission", "source": "sales", "kind": "percent", "frequency": "monthly",
     "eligible_roles": ["esthetician"], "pay_code": "retail_commission", "include_in_regular_rate": True,
     "rates": [{"match": "category", "value": "retail", "rate": "10"}]},
    {"id": "memberships", "label": "Membership commission", "source": "sales", "kind": "per_unit", "frequency": "monthly",
     "eligible_roles": ["front_desk"], "pay_code": "membership_commission", "include_in_regular_rate": True,
     "rates": [{"match": "category", "value": "membership"}], "tier_method": "marginal", "tier_scope": "employee_location",
     "tiers": [{"from": "1", "to": "5", "rate": "10"}, {"from": "6", "rate": "15"}],
     "exclude": [{"field": "item_type", "values": ["renewal", "transfer"]}]},
    {"id": "gift_cards", "label": "Gift card commission", "source": "sales", "kind": "percent", "frequency": "pay_period",
     "eligible_roles": ["front_desk"], "pay_code": "gc_commission", "include_in_regular_rate": True,
     "rates": [{"match": "category", "value": "gift_card", "rate": "3"}]},
    {"id": "mgr_gc_override", "label": "Manager gift card override", "source": "sales", "kind": "percent", "frequency": "pay_period",
     "credit": "location", "pay_code": "mgr_override", "include_in_regular_rate": False,
     "rates": [{"match": "category", "value": "gift_card", "rate": "1"}],
     "recipients": [{"location_id": "DT", "employee_id": "M1", "share": "1"}, {"location_id": "EC", "employee_id": "M1", "share": "1"},
                    {"location_id": "VA", "employee_id": "M2", "share": "1"}]},
]

PAY_CODES = {
    "service_wages": ("Service pay", "Commission", "amount"), "service_per_unit": ("Per-service pay", "Commission", "amount"),
    "service_commission": ("Service commission", "Commission", "amount"), "regular": ("Regular", "Regular", "hours"),
    "overtime": ("Overtime", "Overtime", "hours"), "doubletime": ("Double time", "Double Time", "hours"),
    "ot_premium": ("Overtime premium", "OT Premium", "amount"), "card_tips": ("Credit card tips", "Credit Card Tips", "amount"),
    "cash_tips": ("Cash tips", "Cash Tips", "amount"), "salary": ("Salary", "Salary", "amount"),
    "min_wage_makeup": ("Minimum wage make-up", "Min Wage Makeup", "amount"),
    "nonproductive_time": ("Non-productive time", "Nonproductive", "amount"), "rest_recovery": ("Rest and recovery", "Rest Recovery", "amount"),
    "lobby": ("Lobby", "Lobby", "amount"), "training": ("Training", "Training", "amount"), "meeting": ("Meetings", "Meeting", "amount"),
    "sick": ("Sick", "Sick", "amount"), "pto": ("PTO", "PTO", "amount"), "enhancements": ("Enhancements", "Enhancements", "amount"),
    "advanced_service": ("Advanced service", "Advance Service Commission", "amount"),
    "retail_commission": ("Retail commission", "Product Sales Commission", "amount"),
    "membership_commission": ("Membership commission", "Commission", "amount"), "gc_commission": ("Gift card commission", "GC Comm", "amount"),
    "mgr_override": ("Manager GC override", "GC Override", "amount"), "bonus": ("Bonus", "Bonus", "amount"),
    "stipend": ("Stipend", "Stipend", "amount"), "back_pay": ("Back pay", "Back Pay", "amount"),
    "reimbursement": ("Reimbursement", "Reimbursement", "amount"),
}

STAFF = [
    # id, first, last, role, home, rate, hire, term
    ("E101", "Ava", "Thornton", "massage_therapist", "DT", "26.00", "2024-03-01", None),
    ("E102", "Ben", "Castillo", "massage_therapist", "DT", "24.00", "2023-06-12", None),
    ("E103", "Chloe", "Nguyen", "esthetician", "DT", "24.00", "2025-01-15", None),
    ("E104", "Dev", "Patel", "stretch_therapist", "DT", "22.00", "2025-05-02", None),
    ("E105", "Ella", "Brooks", "front_desk", "DT", "17.50", "2024-09-09", None),
    ("E106", "Finn", "Murphy", "front_desk", "DT", "18.00", "2025-02-20", None),
    ("E107", "Sam", "Rivera", "massage_therapist", "DT", "25.00", "2023-11-01", None),
    ("E201", "Grace", "Kim", "massage_therapist", "EC", "23.00", "2025-08-18", None),
    ("E202", "Hugo", "Silva", "esthetician", "EC", "22.00", "2024-04-04", None),
    ("E203", "Iris", "Lane", "front_desk", "EC", "16.50", "2025-03-03", "2026-10-28"),
    ("E204", "Jon", "Ortiz", "massage_therapist", "EC", "23.00", "2026-10-20", None),
    ("E301", "Theo", "Alvarez", "massage_therapist", "VA", "27.00", "2024-07-07", None),
    ("E302", "Lena", "Fischer", "front_desk", "VA", "18.50", "2025-10-01", None),
    ("E303", "Maya", "Okafor", "esthetician", "VA", "25.00", "2024-12-01", None),
    ("M1", "Nora", "Bennett", "manager", "DT", "58000", "2022-01-10", None),
    ("M2", "Owen", "Marsh", "manager", "VA", "54000", "2023-02-01", None),
]
POS_SPELLING = {"E101": "AVA: Thornton, Ava", "E201": "Kim, grace", "E302": "FISCHER, LENA"}


def config():
    return {
        "schema_version": "1.0",
        "company": {"name": "Willowbrook Spa Co. (sample)", "pay_frequency": "semi_monthly", "workweek_start": "sunday",
                    "ot_aggregation": "employer", "min_wage_makeup": "flag", "cash_tips": "report_only",
                    "notes": "Fictional sample business. Rates and minimum wages are example values only."},
        "approval": {},
        "systems": {"hris": "bamboohr", "payroll": "bamboohr", "pos": "Example POS",
                    "payroll_settings": {"split_by_location": False},
                    "pos_reports": [
                        {"report": "Service detail by provider", "maps_to": "services", "filters": "pay period; all providers", "frequency": "pay_period"},
                        {"report": "Add-ons by provider", "maps_to": "addons", "filters": "pay period; sorted by provider", "frequency": "pay_period"},
                        {"report": "Tips by provider", "maps_to": "tips", "filters": "pay period", "frequency": "pay_period"},
                        {"report": "Time clock detail", "maps_to": "time_entries", "filters": "pay period only, never full boundary weeks", "frequency": "pay_period"},
                        {"report": "Sales by employee", "maps_to": "sales", "filters": "gift cards each period; full month on month-end runs", "frequency": "pay_period"},
                        {"report": "Location scorecard", "maps_to": "location_metrics", "filters": "full month", "frequency": "monthly"}]},
        "employers": [{"id": "E1", "legal_name": "Willowbrook Spa Oregon LLC"}, {"id": "E2", "legal_name": "Willowbrook Spa Washington LLC"}],
        "locations": list(LOCS.values()),
        "state_rules": {
            "OR": {"weekly_ot_threshold": "40", "daily_ot": None, "seventh_day_ot": False, "piece_rate_nonproductive_separate": False,
                   "confirmed_by_owner": True, "notes": "Sample only."},
            "WA": {"weekly_ot_threshold": "40", "daily_ot": None, "seventh_day_ot": False, "piece_rate_nonproductive_separate": False,
                   "confirmed_by_owner": True, "notes": "Sample only."}},
        "roles": ROLES, "time_pay": TIME_PAY, "time_off_pay": TIME_OFF, "incentives": INCENTIVES,
        "stipends": [{"id": "cover_ec", "employee_id": "M1", "label": "Covering Eastside", "amount": "250", "location_id": "EC",
                      "effective_from": "2026-09-01", "pay_code": "stipend"}],
        "manager_allocation": [{"employee_id": "M1", "location_id": "DT", "share": "0.5"},
                               {"employee_id": "M1", "location_id": "EC", "share": "0.5"},
                               {"employee_id": "M2", "location_id": "VA", "share": "1"}],
        "bonus_pools": [{"id": "mgr_bonus", "label": "Manager scorecard bonus", "frequency": "monthly", "pool_per_location": "600",
                         "pay_code": "bonus", "include_in_regular_rate": False,
                         "metrics": [{"id": "close_rate", "label": "Membership close rate", "numerator": "memberships_sold",
                                      "denominator": "service_guests", "compare": ">=", "threshold": "0.14", "weight": "0.5"},
                                     {"id": "rebook_rate", "label": "Rebook rate", "numerator": "rebooked_guests",
                                      "denominator": "service_guests", "compare": ">=", "threshold": "0.30", "weight": "0.5"}],
                         "recipients": [{"location_id": "DT", "employee_id": "M1", "share": "1"},
                                        {"location_id": "EC", "employee_id": "M1", "share": "1"},
                                        {"location_id": "VA", "employee_id": "M2", "share": "1"}]}],
        "employee_overrides": [
            {"employee_id": "E107", "secondary_role": "esthetician", "pos_names": ["Rivera, Sammy"],
             "rates": [{"role": "esthetician", "rate": "23.00", "rate_type": "service_hour", "effective_from": ""}]},
            {"employee_id": "E201", "rates": [{"role": "massage_therapist", "rate": "24.00", "rate_type": "service_hour",
                                               "effective_from": "2026-10-24"}]}],
        "pay_codes": {k: {"label": v[0], "code": v[1], "export_as": v[2]} for k, v in PAY_CODES.items()},
        "checks": {"plausibility": {"min_avg_service_hours": "0.25", "max_avg_service_hours": "4", "max_weekly_hours": "70",
                                    "anomaly_threshold": "0.25"}},
        "intake_notes": [{"id": "start.2", "topic": "Before we start", "question": "What went wrong in past payrolls that you never want to see again?",
                          "answer": "A missing sick-time export once paid nobody's sick hours."}],
    }


def write_csv(path, cols, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


def days(start, end):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


MASSAGE = [("MS60", "Massage 60", 1.0, 99), ("MS90", "Massage 90", 1.5, 139), ("MS30", "Massage 30", 0.5, 59)]
STRETCH = [("ST30", "Stretch 30", 0.5, 49), ("ST60", "Stretch 60", 1.0, 89)]
FACIAL = [("FAC60", "Facial 60", 1.0, 109), ("FAC90", "Facial 90", 1.5, 149), ("ADVPEEL60", "Advanced peel 60", 1.0, 159)]


def period_data(start, end, monthly):
    services, addons, sales, tips, time_entries, time_off = [], [], [], [], [], []
    tip_seen = set()
    staff = {s[0]: s for s in STAFF}
    workdays = {"E101": {0, 1, 2, 3, 4}, "E102": {1, 2, 3, 4, 5}, "E103": {0, 2, 3, 4, 5}, "E104": {3, 4, 5, 6},
                "E107": {0, 1, 3, 4}, "E201": {1, 2, 3, 4, 5}, "E202": {0, 1, 2, 3}, "E204": {0, 1, 2, 3, 4},
                "E301": {0, 1, 2, 3, 4}, "E303": {2, 3, 4, 5}}
    for emp, wd in workdays.items():
        _, first, last, role, home, *_ = staff[emp]
        name = POS_SPELLING.get(emp, f"{last}, {first}")
        for d in days(start, end):
            if d.weekday() not in wd:
                continue
            hire, term = staff[emp][6], staff[emp][7]
            if hire and d < dt.date.fromisoformat(hire):
                continue
            n = rng.randint(3, 5)
            for _ in range(n):
                if role == "esthetician" or (emp == "E107" and rng.random() < 0.3):
                    code, label, h, price, cat = (*rng.choice(FACIAL), "facial")
                elif role == "stretch_therapist":
                    code, label, h, price, cat = (*rng.choice(STRETCH), "stretch")
                else:
                    code, label, h, price, cat = (*rng.choice(MASSAGE), "massage")
                if emp == "E107" and cat == "facial":
                    rowname = "Rivera, Sammy"
                else:
                    rowname = name
                services.append({"employee_name": rowname, "location": LOCS[home]["pos_labels"][0], "date": d.isoformat(),
                                 "service_code": code, "service_name": label, "category": cat, "quantity": "1",
                                 "service_hours": f"{h:.2f}", "revenue": f"{price:.2f}"})
                r = rng.random()
                if cat in ("massage", "stretch") and r < 0.18:
                    a = rng.choice([("CBDSCNT", "CBD Scented", 30), ("CUPCUS", "Custom Cupping", 30), ("RTR10", "Rapid Tension Relief", 15),
                                    ("HOTSTONE", "Hot Stone", 20), ("KTAPE", "Kinesiology Tape", 15)])
                    addons.append({"employee_name": rowname, "location": LOCS[home]["pos_labels"][0], "date": d.isoformat(),
                                   "addon_code": a[0], "addon_name": a[1], "quantity": "1", "customer_price": f"{a[2]:.2f}"})
                if cat == "facial" and r < 0.35:
                    addons.append({"employee_name": rowname, "location": LOCS[home]["pos_labels"][0], "date": d.isoformat(),
                                   "addon_code": "SKNENZ", "addon_name": "Enzyme boost", "quantity": "1", "customer_price": "15.00"})
                amt = rng.randint(1200, 2600)
                while (rowname, d, amt) in tip_seen:
                    amt += 1
                tip_seen.add((rowname, d, amt))
                tips.append({"employee_name": rowname, "location": LOCS[home]["pos_labels"][0], "date": d.isoformat(),
                             "tip_type": "card", "amount": f"{amt / 100:.2f}"})
            if rng.random() < 0.15:
                time_entries.append({"employee_name": name, "location": LOCS[home]["pos_labels"][0], "date": d.isoformat(),
                                     "category": "lobby", "hours": "1.00"})
    # a refunded service and its add-on
    if services:
        s = dict(services[3]); s["refund"] = "Y"; services.append(s)
    # trainer / trainee / meeting
    for d in days(start, end):
        if d.isoformat() == "2026-10-20":
            time_entries += [{"employee_id": "E102", "location": "DT", "date": d.isoformat(), "category": "trainer", "hours": "4.00"},
                             {"employee_id": "E204", "location": "EC", "date": d.isoformat(), "category": "trainee", "hours": "4.00"}]
        if d.isoformat() in ("2026-10-07", "2026-10-21"):
            for emp in ("E101", "E103", "E201", "E301"):
                time_entries.append({"employee_id": emp, "location": staff[emp][4], "date": d.isoformat(), "category": "meeting", "hours": "1.00"})
    # front desk shifts
    fd_plan = {
        "E105": {"DT": {0: 7.5, 1: 8, 2: 8, 3: 8, 4: 4.5}, "EC": {5: 6}},
        "E106": {"DT": {2: 6, 3: 6, 4: 6, 5: 8, 6: 6}},
        "E203": {"EC": {0: 7, 1: 7, 2: 7, 3: 7, 4: 7}},
        "E302": {"VA": {0: 8, 1: 8, 2: 8, 3: 8, 4: 8}},
    }
    for emp, plan in fd_plan.items():
        for d in days(start, end):
            term = staff[emp][7]
            if term and d > dt.date.fromisoformat(term):
                continue
            for loc, sched in plan.items():
                h = sched.get(d.weekday())
                if not h:
                    continue
                if emp == "E105" and dt.date(2026, 10, 11) <= d <= dt.date(2026, 10, 15):
                    h = h + 1.0 if loc == "DT" else h          # long boundary week
                if emp == "E105" and d in (dt.date(2026, 10, 16), dt.date(2026, 10, 17)):
                    h = {4: 4.5, 5: 7.0}.get(d.weekday(), h)
                if emp == "E105" and dt.date(2026, 10, 18) <= d <= dt.date(2026, 10, 24) and loc == "EC":
                    h = 9.0                                    # cross-location overtime week
                if emp == "E105" and d == dt.date(2026, 10, 22):
                    time_entries.append({"employee_id": emp, "location": "EC", "date": d.isoformat(), "category": "worked", "hours": "4.00"})
                time_entries.append({"employee_name": POS_SPELLING.get(emp, f"{staff[emp][2]}, {staff[emp][1]}"),
                                     "location": loc, "date": d.isoformat(), "category": "worked", "hours": f"{h:.2f}"})
    # sales: gift cards every period, retail and memberships in the month
    sale_days = list(days(start, end))
    for emp, loc in (("E105", "DT"), ("E106", "DT"), ("E203", "EC"), ("E302", "VA")):
        for _ in range(rng.randint(3, 6)):
            d = rng.choice(sale_days)
            if staff[emp][7] and d > dt.date.fromisoformat(staff[emp][7]):
                continue
            sales.append({"employee_id": emp, "location": loc, "date": d.isoformat(), "category": "gift_card", "item": "Gift card",
                          "quantity": "1", "amount": f"{rng.choice([50, 75, 100, 150]):.2f}"})
    if monthly:
        month = list(days(dt.date(2026, 10, 1), dt.date(2026, 10, 31)))
        for emp, loc, n in (("E105", "DT", 7), ("E106", "DT", 4), ("E203", "EC", 6), ("E302", "VA", 9)):
            for i in range(n):
                d = rng.choice(month)
                if staff[emp][7] and d > dt.date.fromisoformat(staff[emp][7]):
                    d = dt.date(2026, 10, 12)
                sales.append({"employee_id": emp, "location": loc, "date": d.isoformat(), "category": "membership",
                              "item": "Monthly membership", "item_type": "new", "quantity": "1", "amount": "79.00"})
            sales.append({"employee_id": emp, "location": loc, "date": rng.choice(month).isoformat() if emp != "E203" else "2026-10-05",
                          "category": "membership", "item": "Membership renewal", "item_type": "renewal", "quantity": "1", "amount": "79.00"})
        for emp, loc in (("E103", "DT"), ("E202", "EC"), ("E303", "VA"), ("E101", "DT")):
            for _ in range(rng.randint(2, 5)):
                sales.append({"employee_id": emp, "location": loc, "date": rng.choice(month).isoformat(), "category": "retail",
                              "item": "Serum", "quantity": "1", "amount": f"{rng.choice([38, 54, 72, 96]):.2f}"})
    # time off
    if start.day == 1:
        time_off += [{"employee_id": "E102", "date": "2026-10-06", "type": "sick", "hours": "6.00"},
                     {"employee_id": "E106", "date": "2026-10-09", "type": "sick", "hours": "6.00"}]
    else:
        time_off += [{"employee_id": "E202", "date": "2026-10-27", "type": "sick", "hours": "5.00"},
                     {"employee_id": "E302", "date": "2026-10-30", "type": "pto", "hours": "8.00"},
                     {"employee_id": "M1", "date": "2026-10-23", "type": "pto", "hours": "8.00"},
                     {"employee_id": "E101", "date": "2026-10-29", "type": "sick", "hours": "4.00"}]
    # a declared cash tip
    tips.append({"employee_id": "E301", "location": "VA", "date": (start + dt.timedelta(days=3)).isoformat(),
                 "tip_type": "cash", "amount": "40.00"})
    return services, addons, sales, tips, time_entries, time_off


def totals(rows, loc_label_to_id, fields, lo, hi):
    out = defaultdict(lambda: defaultdict(lambda: D(0)))
    for r in rows:
        d = dt.date.fromisoformat(r["date"])
        if not (lo <= d <= hi):
            continue
        loc = loc_label_to_id.get(r.get("location"), r.get("location"))
        sign = -1 if r.get("refund") == "Y" else 1
        for f in fields:
            if r.get(f):
                out[loc][f] += sign * D(r[f])
    return out


def main():
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    cfg = config()
    (DEST / "payroll_config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    label_to_id = {}
    for loc in LOCS.values():
        for lab in [loc["id"], *loc["pos_labels"]]:
            label_to_id[lab] = loc["id"]

    # HRIS-style exports (the raw files the bamboohr profile maps)
    periods = [
        (dt.date(2026, 10, 1), dt.date(2026, 10, 15), dt.date(2026, 10, 20), False),
        (dt.date(2026, 10, 16), dt.date(2026, 10, 31), dt.date(2026, 11, 5), True),
    ]
    for start, end, pay, monthly in periods:
        pid = f"{start}_{end}"
        pdir = DEST / "periods" / pid
        for sub in ("raw", "inputs", "output"):
            (pdir / sub).mkdir(parents=True, exist_ok=True)
        (pdir / "output" / ".keep").write_text("")
        roster = []
        for eid, first, last, role, home, rate, hire, term in STAFF:
            status = "Terminated" if term and dt.date.fromisoformat(term) <= end else "Active"
            per = "Year" if role == "manager" else "Hour"
            roster.append({"Employee #": eid, "First Name": first, "Last Name": last, "Status": status,
                           "Hire Date": dt.date.fromisoformat(hire).strftime("%m/%d/%Y"),
                           "Termination Date": dt.date.fromisoformat(term).strftime("%m/%d/%Y") if term else "",
                           "Location": LOCS[home]["hris_labels"][0], "Job Title": next(r for r in ROLES if r["id"] == role)["hris_titles"][0],
                           "Pay Rate": f"${D(rate):,.2f} USD per {per}", "Pay Type": "Salary" if role == "manager" else "Hourly",
                           "Work Email": f"{first.lower()}@example.com"})
        write_csv(pdir / "raw" / "bamboohr_roster_export.csv", list(roster[0].keys()), roster)
        services, addons, sales, tips, time_entries, time_off = period_data(start, end, monthly)
        write_csv(pdir / "raw" / "bamboohr_time_off_used.csv", ["Employee #", "Employee Name", "Date", "Time Off Type", "Hours"],
                  [{"Employee #": r["employee_id"], "Employee Name": "", "Date": dt.date.fromisoformat(r["date"]).strftime("%m/%d/%Y"),
                    "Time Off Type": {"sick": "Sick", "pto": "Paid Time Off"}[r["type"]], "Hours": r["hours"]} for r in time_off])
        cols = lambda name: list(__import__("spapay.inputs", fromlist=["SPEC"]).SPEC[name])
        write_csv(pdir / "inputs" / "services.csv", cols("services"), services)
        write_csv(pdir / "inputs" / "addons.csv", cols("addons"), addons)
        write_csv(pdir / "inputs" / "sales.csv", cols("sales"), sales)
        write_csv(pdir / "inputs" / "tips.csv", cols("tips"), tips)
        write_csv(pdir / "inputs" / "time_entries.csv", cols("time_entries"), time_entries)
        adjustments = []
        metrics = []
        if monthly:
            adjustments = [
                {"employee_id": "E201", "location": "EC", "pay_code": "back_pay", "description": "Missed lobby hour 10/3",
                 "amount": "15.55", "taxable": "Y", "include_in_regular_rate": "N", "approved_by": "Owner"},
                {"employee_id": "M1", "location": "DT", "pay_code": "reimbursement", "description": "Linen supplies receipt",
                 "amount": "62.40", "taxable": "N", "include_in_regular_rate": "N", "approved_by": "Owner"}]
            metrics = [{"location": "DT", "metric": m, "value": v, "window_start": "2026-10-01", "window_end": "2026-10-31"}
                       for m, v in (("memberships_sold", 30), ("service_guests", 190), ("rebooked_guests", 62))] + \
                      [{"location": "EC", "metric": m, "value": v, "window_start": "2026-10-01", "window_end": "2026-10-31"}
                       for m, v in (("memberships_sold", 18), ("service_guests", 160), ("rebooked_guests", 52))] + \
                      [{"location": "VA", "metric": m, "value": v, "window_start": "2026-10-01", "window_end": "2026-10-31"}
                       for m, v in (("memberships_sold", 25), ("service_guests", 150), ("rebooked_guests", 40))]
        write_csv(pdir / "inputs" / "adjustments.csv", cols("adjustments"), adjustments)
        write_csv(pdir / "inputs" / "location_metrics.csv", cols("location_metrics"), metrics)

        sources = []
        svc_t = totals(services, label_to_id, ("service_hours", "quantity"), start, end)
        tip_t = totals([t for t in tips if t["tip_type"] == "card"], label_to_id, ("amount",), start, end)
        add_t = totals(addons, label_to_id, ("quantity",), start, end)
        for loc in LOCS:
            sources.append({"file": f"raw/{loc}_service_detail.xlsx", "report": "Service detail by provider", "location_id": loc,
                            "date_from": str(start), "date_to": str(end), "mapped_to": "services",
                            "totals": {k: str(v) for k, v in svc_t[loc].items()}})
            sources.append({"file": f"raw/{loc}_addons.xlsx", "report": "Add-ons by provider", "location_id": loc,
                            "date_from": str(start), "date_to": str(end), "mapped_to": "addons",
                            "totals": {k: str(v) for k, v in add_t[loc].items()}})
        period = {
            "period_start": str(start), "period_end": str(end), "pay_date": str(pay), "include_monthly": monthly,
            "monthly_window": {"start": "2026-10-01", "end": "2026-10-31"} if monthly else None,
            "windows": {"gift_cards": {"start": "2026-10-16", "end": "2026-10-29"}} if monthly else {},
            "attestations": ([{"input": "time_off", "location_id": "EC", "statement": "Nobody at Eastside took time off", "by": "Owner"},
                              {"input": "time_off", "location_id": "VA", "statement": "Nobody at Riverside took time off", "by": "Owner"}]
                             if not monthly else []),
            "sources": sources, "approved_variances": [], "expected_activity":
                ([{"employee_id": "E102", "input": "time_entries", "category": "trainer", "minimum": "1",
                   "reason": "Owner asked Downtown to record Ben's training of Jon on 10/20"}] if monthly else []),
            "acknowledged_warnings": ([{"code": "INC_OUTSIDE_WINDOW", "match": "gift_cards", "by": "Owner",
                                        "note": "Holiday gift card commission covers sales through 10/29 only"}] if monthly else []),
            "salary_proration": None,
            "notes": "Sample period. Raw HRIS exports are in raw/; run hris-import to build roster.csv, pay_rates.csv and time_off.csv.",
        }
        (pdir / "period.json").write_text(json.dumps(period, indent=2) + "\n")
    print(f"sample written to {DEST}")


if __name__ == "__main__":
    main()
