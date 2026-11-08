"""The intake workbook: a detailed, fillable form that compiles into payroll_config.json.

One tab per part of the pay rules. Every table has a header row (row 6), an example
row above it, dropdowns where the answer is a fixed set, and help text. The same
spec builds the blank form, pre-fills it from an existing config (so owners can edit
their rules in Excel), and compiles it back.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .config import (ENGINE_PAY_KEYS, FREQUENCIES, HOURS_SOURCES, INCENTIVE_KINDS, INCENTIVE_SOURCES, MATCH_TYPES,
                     PAY_BASES, PAY_FREQUENCIES, RATE_BASES, SCHEMA_VERSION, TIME_CATEGORIES, TIME_OFF_TYPES)
from .util import D, Findings

NAVY, ORANGE, YELLOW, CREAM, TINT = "141034", "E58700", "F8D300", "F6ECD4", "FBF6EA"
HEADER_ROW, EXAMPLE_ROW, FIRST_DATA = 6, 5, 7
YESNO = ["yes", "no"]
DAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
SYSTEMS = ["bamboohr", "adp_wfn", "paylocity", "hibob", "gusto", "generic", "other"]
INPUTS = ["services", "addons", "sales", "tips", "time_entries", "time_off", "location_metrics"]

# (tab, intro, columns[(header, key, kind, choices, help)], example row)
TABLES = [
    ("Employers", "Each legal entity that issues paychecks. Locations owned by the same entity share overtime.",
     [("Employer ID", "id", "str", None, "Short code, e.g. E1"), ("Legal name", "legal_name", "str", None, ""),
      ("Notes", "notes", "str", None, "")],
     ["E1", "Willowbrook Spa LLC", ""]),
    ("Locations", "Every location that has staff. Minimum wage is per location because cities and counties differ.",
     [("Location ID", "id", "str", None, "Short code used everywhere else"), ("Name", "name", "str", None, ""),
      ("Employer ID", "employer_id", "str", None, "From the Employers tab"), ("City", "city", "str", None, ""),
      ("State", "state", "str", None, "Two letters"), ("Min wage", "mw_rate", "num", None, "Current rate for this location"),
      ("Min wage effective from", "mw_from", "date", None, "YYYY-MM-DD"), ("Next min wage", "mw_next", "num", None, "If a change is scheduled"),
      ("Next effective from", "mw_next_from", "date", None, ""), ("POS names for this location", "pos_labels", "list", None, "How the POS labels it; separate with ;"),
      ("HRIS names for this location", "hris_labels", "list", None, "How the HR system labels it; separate with ;"),
      ("Payroll department / cost center code", "payroll_code", "str", None, "Optional; goes on the payroll file")],
     ["DT", "Downtown", "E1", "Portland", "OR", 16.30, "2025-07-01", "", "", "Downtown;0101", "Downtown Portland", "100"]),
    ("State Rules", "Overtime and piece-rate rules per state. Start from the preset, then confirm with your payroll provider or counsel.",
     [("State", "state", "str", None, ""), ("Weekly OT after hours", "weekly_ot_threshold", "num", None, "Usually 40"),
      ("Daily OT after hours", "daily_threshold", "num", None, "Blank if your state has no daily overtime"),
      ("Daily double time after hours", "double_threshold", "num", None, ""), ("Seventh consecutive day rule", "seventh_day_ot", "bool", YESNO, ""),
      ("Piece-rate non-productive time paid separately", "piece_rate_nonproductive_separate", "bool", YESNO, "Yes in California"),
      ("Confirmed by owner", "confirmed_by_owner", "bool", YESNO, "Only say yes after checking"), ("Notes", "notes", "str", None, "")],
     ["OR", 40, "", "", "no", "no", "yes", "Confirmed with payroll provider"]),
    ("Roles", "Every kind of job, and how it is paid. Dual-role people get a secondary role on the Employee Notes tab.",
     [("Role ID", "id", "str", None, "e.g. massage_therapist"), ("Label", "label", "str", None, ""),
      ("Pay basis", "pay_basis", "str", sorted(PAY_BASES), "How the main pay is figured"),
      ("Exempt from overtime", "exempt", "bool", YESNO, "Only true salaried exempt managers"),
      ("Hours worked come from", "hours_worked_source", "str", sorted(HOURS_SOURCES), "clock = time clock; services_plus_time = service time + recorded non-service time"),
      ("Service categories", "service_categories", "list", None, "For service roles: massage;stretch or facial"),
      ("Receives tips", "tips", "bool", YESNO, ""), ("HRIS job titles", "hris_titles", "list", None, "Exact titles in the HR system; separate with ;")],
     ["massage_therapist", "Massage Therapist", "piece_service_hour", "no", "services_plus_time", "massage", "yes", "Massage Therapist;LMT"]),
    ("Time Pay", "How each kind of non-service or clocked time is paid, per role (* = every role).",
     [("Role ID", "role", "str", None, "* for every role"), ("Kind of time", "category", "str", sorted(TIME_CATEGORIES), ""),
      ("Paid at", "basis", "str", sorted(RATE_BASES), "min_wage, base_rate (their rate), fixed, regular_rate, unpaid"),
      ("Fixed rate", "fixed_rate", "num", None, "Only for 'fixed'"), ("Pay code key", "pay_code", "str", None, "From the Pay Codes tab"),
      ("Notes / limits", "notes", "str", None, "e.g. lobby capped at 4 hours a month")],
     ["massage_therapist", "lobby", "min_wage", "", "lobby", "Up to 4 hours a month"]),
    ("Time Off", "How sick, PTO and holiday hours are paid, per role (* = every role).",
     [("Role ID", "role", "str", None, ""), ("Type", "type", "str", sorted(TIME_OFF_TYPES), ""),
      ("Paid at", "basis", "str", sorted(RATE_BASES), ""), ("Fixed rate", "fixed_rate", "num", None, ""),
      ("Pay code key", "pay_code", "str", None, "")],
     ["massage_therapist", "sick", "min_wage", "", "sick"]),
    ("Incentives", "Commissions, spiffs and bonuses that are counted from sales, services or add-ons.",
     [("Incentive ID", "id", "str", None, "e.g. addon_spiff"), ("Label", "label", "str", None, ""),
      ("Counted from", "source", "str", sorted(INCENTIVE_SOURCES), "addons, services or sales"),
      ("Kind", "kind", "str", sorted(INCENTIVE_KINDS), "per_unit ($ each) or percent (% of sales)"),
      ("Frequency", "frequency", "str", sorted(FREQUENCIES), "monthly = paid on the month-end run"),
      ("Eligible roles", "eligible_roles", "list", None, "Role IDs; blank = everyone"),
      ("Eligible employee IDs", "eligible_employees", "list", None, "For one-person deals"),
      ("Tier method", "tier_method", "str", ["none", "marginal", "highest"], "marginal: first 5 at $10, the rest at $15"),
      ("Tier counted per", "tier_scope", "str", ["employee_location", "employee"], ""),
      ("Credit goes to", "credit", "str", ["seller", "location"], "location = named recipients get a % of the location total"),
      ("Exclude where field", "exclude_field", "str", None, "e.g. item_type"), ("Exclude values", "exclude_values", "list", None, "e.g. renewal;transfer"),
      ("Counts in regular rate", "include_in_regular_rate", "bool", YESNO, "Commissions do; discretionary gifts do not"),
      ("Pay code key", "pay_code", "str", None, ""), ("Notes", "notes", "str", None, "")],
     ["addon_spiff", "Add-on spiffs", "addons", "per_unit", "pay_period", "massage_therapist;stretch_therapist", "", "none",
      "employee_location", "seller", "", "", "yes", "enhancements", "Employer rates, never the customer price"]),
    ("Incentive Rates", "What each incentive pays on. Add-on and service codes match by prefix (CBD matches CBDSCNT).",
     [("Incentive ID", "incentive", "str", None, ""), ("Match", "match", "str", sorted(MATCH_TYPES), ""),
      ("Value", "value", "str", None, "The code, prefix, category or text"), ("Rate", "rate", "num", None, "$ per unit, or % for percent incentives"),
      ("Only for employee IDs", "only_employees", "list", None, "Blank = everyone eligible")],
     ["addon_spiff", "code_prefix", "CBD", 10, ""]),
    ("Incentive Tiers", "Optional. Tiers for an incentive (units for per_unit, dollars for percent).",
     [("Incentive ID", "incentive", "str", None, ""), ("From", "from", "num", None, ""), ("To", "to", "num", None, "Blank = no top"),
      ("Rate", "rate", "num", None, "")],
     ["memberships", 1, 5, 10]),
    ("Location Recipients", "For incentives with credit = location: who receives what share of each location's total.",
     [("Incentive ID", "incentive", "str", None, ""), ("Location ID", "location_id", "str", None, ""),
      ("Employee ID", "employee_id", "str", None, ""), ("Share", "share", "num", None, "1 = 100%")],
     ["mgr_gc_override", "DT", "M1", 1]),
    ("Stipends", "Fixed extra pay per pay period, e.g. covering a second location.",
     [("Stipend ID", "id", "str", None, ""), ("Employee ID", "employee_id", "str", None, ""), ("Label", "label", "str", None, ""),
      ("Amount per pay period", "amount", "num", None, ""), ("Location ID", "location_id", "str", None, "Where the cost lands"),
      ("Effective from", "effective_from", "date", None, ""), ("Effective through", "effective_through", "date", None, ""),
      ("Pay code key", "pay_code", "str", None, "")],
     ["cover_ec", "M1", "Covering Eastside", 250, "EC", "2026-01-01", "", "stipend"]),
    ("Cost Split", "How each salaried manager's cost is split across locations (shares add to 1).",
     [("Employee ID", "employee_id", "str", None, ""), ("Location ID", "location_id", "str", None, ""), ("Share", "share", "num", None, "")],
     ["M1", "DT", 0.5]),
    ("Bonus Pools", "Manager bonuses paid from location scorecard numbers.",
     [("Pool ID", "id", "str", None, ""), ("Label", "label", "str", None, ""), ("Frequency", "frequency", "str", sorted(FREQUENCIES), ""),
      ("Pool per location", "pool_per_location", "num", None, "Most it can pay per location"), ("Pay code key", "pay_code", "str", None, ""),
      ("Counts in regular rate", "include_in_regular_rate", "bool", YESNO, "Yes if any recipient is non-exempt")],
     ["mgr_bonus", "Manager scorecard bonus", "monthly", 600, "bonus", "no"]),
    ("Bonus Metrics", "Each pass/fail target and the share of the pool it unlocks.",
     [("Pool ID", "pool", "str", None, ""), ("Metric ID", "id", "str", None, ""), ("Label", "label", "str", None, ""),
      ("Numerator metric", "numerator", "str", None, "Name used in location_metrics.csv"), ("Denominator metric", "denominator", "str", None, "Blank = just the numerator"),
      ("Compare", "compare", "str", [">=", ">", "<=", "<"], ""), ("Threshold", "threshold", "num", None, "0.14 = 14%"), ("Weight", "weight", "num", None, "0.5 = half the pool")],
     ["mgr_bonus", "close_rate", "Membership close rate", "memberships_sold", "service_guests", ">=", 0.14, 0.5]),
    ("Bonus Recipients", "Who is paid each location's pool, and in what share.",
     [("Pool ID", "pool", "str", None, ""), ("Location ID", "location_id", "str", None, ""), ("Employee ID", "employee_id", "str", None, ""),
      ("Share", "share", "num", None, "1 = 100%")],
     ["mgr_bonus", "DT", "M1", 1]),
    ("Pay Codes", "Every pay type and the exact earning code your payroll system expects. A mismatch fails the upload.",
     [("Pay code key", "key", "str", None, "Used in the other tabs"), ("Label", "label", "str", None, ""),
      ("Payroll system code", "code", "str", None, "Exactly as your payroll system spells it"),
      ("Send as", "export_as", "str", ["hours", "amount", "none"], "none = your payroll system already pays it from its own records")],
     ["service_wages", "Service pay", "Commission", "amount"]),
    ("Employee Notes", "Durable facts about specific people: second role, POS spellings, payroll ID, extra or scheduled rates.",
     [("Employee ID", "employee_id", "str", None, ""), ("Secondary role", "secondary_role", "str", None, ""),
      ("Other POS spellings", "pos_names", "list", None, "e.g. Doe, Jo;JO DOE"), ("Payroll ID / file #", "payroll_id", "str", None, ""),
      ("Home location override", "home_location", "str", None, ""), ("Rate role", "rate_role", "str", None, "For an extra or scheduled rate"),
      ("Rate", "rate", "num", None, ""), ("Rate type", "rate_type", "str", ["hourly", "service_hour", "per_service", "service_pct", "salary_annual", "salary_period"], ""),
      ("Rate effective from", "effective_from", "date", None, "")],
     ["E107", "esthetician", "Rivera, Sam", "000107", "", "esthetician", 24, "service_hour", ""]),
    ("POS Reports", "Every report you export each pay period, so Claude can give you an exact checklist.",
     [("Report name", "report", "str", None, "As named in your POS"), ("What it shows", "shows", "str", None, ""),
      ("Maps to", "maps_to", "str", INPUTS, "Which canonical input it fills"), ("Filters / settings", "filters", "str", None, "e.g. service providers only, sort by provider"),
      ("Frequency", "frequency", "str", sorted(FREQUENCIES), ""), ("Gotchas", "gotchas", "str", None, "What has gone wrong with it before")],
     ["Service detail by provider", "Every service line with service hours", "services", "Pay period dates; all providers", "pay_period",
      "Quantity and service hours columns sit side by side; do not swap them"]),
]

COMPANY_FIELDS = [
    ("Company name", "name", "str", None, ""),
    ("Pay frequency", "pay_frequency", "str", sorted(PAY_FREQUENCIES), ""),
    ("Workweek starts on", "workweek_start", "str", DAYS, "The day your 7-day overtime week begins"),
    ("Overtime adds up hours across", "ot_aggregation", "str", ["employer", "location"], "employer = all locations of one legal entity"),
    ("If a week falls below minimum wage", "min_wage_makeup", "str", ["flag", "auto"], "flag = stop and ask; auto = add make-up pay"),
    ("Cash tips are", "cash_tips", "str", ["report_only", "pay"], "report_only = declared for taxes, not paid by you"),
    ("HR system (HRIS)", "hris", "str", SYSTEMS, ""),
    ("Payroll system", "payroll", "str", SYSTEMS, ""),
    ("Payroll company code (ADP Co Code)", "co_code", "str", None, "Only for ADP"),
    ("Split payroll file by location", "split_by_location", "bool", YESNO, ""),
    ("POS / booking system", "pos", "str", None, ""),
    ("Time clock", "time_clock", "str", None, ""),
    ("Who reviews payroll before it is submitted", "reviewer", "str", None, ""),
    ("Who submits to the payroll system", "submitter", "str", None, ""),
]

QUESTIONS_FILE = Path(__file__).resolve().parents[2] / "assets" / "intake" / "questions.json"


def load_questions():
    """(section title, id, question, why) for every question in the bank."""
    data = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    return [(sec["title"], q["id"], q["q"], q.get("why", "")) for sec in data["sections"] for q in sec["questions"]]


def _band(ws, hook, label, cols):
    navy, stripe = PatternFill("solid", fgColor=NAVY), PatternFill("solid", fgColor=ORANGE)
    for c in range(1, cols + 1):
        ws.cell(row=1, column=c).fill = navy
        ws.cell(row=2, column=c).fill = navy
        ws.cell(row=3, column=c).fill = stripe
    ws.row_dimensions[1].height = 34
    ws.row_dimensions[3].height = 4
    ws["A1"] = hook.upper()
    ws["A1"].font = Font(name="Anton", size=20, color=YELLOW)
    ws["A2"] = label
    ws["A2"].font = Font(name="Oswald", size=11, bold=True, color=CREAM)


def _header(ws, row, headers):
    for c, (h, *_rest) in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(name="Oswald", bold=True, color=CREAM)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[row].height = 32


def _write_value(kind, value):
    if value is None:
        return None
    if kind == "list":
        return ";".join(str(v) for v in value) if isinstance(value, (list, tuple)) else value
    if kind == "bool":
        return "yes" if value else "no"
    if kind == "num":
        try:
            return float(D(value))
        except (ValueError, TypeError):
            return value
    return value


def build_intake_workbook(path, cfg=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Start Here"
    _band(ws, "Payroll intake", "Salon & Spa Payroll Prep · catch the errors and omissions before payday", 6)
    intro = [
        "This workbook is your pay rules, written down once. Claude turns it into the settings file and a plain-English Pay Rules Book you sign.",
        "Fill the tabs left to right. Each tab has an example row (grey) above its header; type your answers from row 7 down. Leave tabs you do not need empty.",
        "Have these nearby: offer letters and comp plans, the employee handbook (time off, lobby rules), your POS report list, "
        "your payroll system's list of earning codes, and one roster export from your HR system.",
        "Anything that does not fit a table goes on the Questions tab. Nothing here is legal advice: confirm state rules with your payroll provider or counsel.",
        "No Social Security numbers, bank details or dates of birth belong anywhere in this workbook.",
    ]
    for i, t in enumerate(intro, start=5):
        ws.cell(row=i, column=1, value=t).alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=6)
        ws.row_dimensions[i].height = 48
    ws.column_dimensions["A"].width = 30
    for c in "BCDEF":
        ws.column_dimensions[c].width = 22

    # Company (key / value)
    ws = wb.create_sheet("Company")
    _band(ws, "Company", "The basics that apply to everyone", 3)
    ws.cell(row=4, column=1, value="One answer per line. Dropdowns show the allowed values.")
    _header(ws, HEADER_ROW, [("Question",), ("Answer",), ("Help",)])
    comp = (cfg.company if cfg else {}) | ({**(cfg.data.get("systems", {}) or {}), **(cfg.data.get("systems", {}).get("payroll_settings") or {})} if cfg else {})
    for i, (label, key, kind, choices, help_) in enumerate(COMPANY_FIELDS):
        r = FIRST_DATA + i
        ws.cell(row=r, column=1, value=label).font = Font(name="Oswald", bold=True, color=NAVY)
        ws.cell(row=r, column=2, value=_write_value(kind, comp.get(key)))
        ws.cell(row=r, column=3, value=help_)
        if choices:
            dv = DataValidation(type="list", formula1='"' + ",".join(choices) + '"', allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(ws.cell(row=r, column=2))
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 60

    rows_from_cfg = _rows_from_config(cfg) if cfg else {}
    for tab, intro_text, cols, example in TABLES:
        ws = wb.create_sheet(tab)
        _band(ws, tab, intro_text, len(cols))
        ws.cell(row=4, column=1, value="Help: " + " | ".join(f"{h}: {hp}" for h, _, _, _, hp in cols if hp))
        ws.cell(row=4, column=1).alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=max(2, len(cols)))
        ws.row_dimensions[4].height = 60
        for c, v in enumerate(example, start=1):
            cell = ws.cell(row=EXAMPLE_ROW, column=c, value=v)
            cell.font = Font(italic=True, color="8A8597")
        ws.cell(row=EXAMPLE_ROW, column=len(cols) + 1, value="<- example").font = Font(italic=True, color=ORANGE)
        _header(ws, HEADER_ROW, cols)
        for i, row in enumerate(rows_from_cfg.get(tab, [])):
            for c, (h, key, kind, choices, _) in enumerate(cols, start=1):
                ws.cell(row=FIRST_DATA + i, column=c, value=_write_value(kind, row.get(key)))
        for c, (h, key, kind, choices, _) in enumerate(cols, start=1):
            ws.column_dimensions[get_column_letter(c)].width = max(14, min(36, len(h) + 4))
            if choices:
                dv = DataValidation(type="list", formula1='"' + ",".join(choices) + '"', allow_blank=True)
                ws.add_data_validation(dv)
                dv.add(f"{get_column_letter(c)}{FIRST_DATA}:{get_column_letter(c)}500")
        ws.freeze_panes = ws.cell(row=FIRST_DATA, column=1)

    ws = wb.create_sheet("Questions")
    _band(ws, "Questions", "The things tables cannot hold. Short answers are fine; skip what does not apply.", 5)
    _header(ws, HEADER_ROW, [("Topic",), ("#",), ("Question",), ("Why we ask",), ("Answer",)])
    notes = {}
    for n in (cfg.data.get("intake_notes", []) if cfg else []):
        notes[n.get("id") or n["question"]] = n.get("answer", "")
    for i, (topic, qid, q, why) in enumerate(load_questions()):
        r = FIRST_DATA + i
        ws.cell(row=r, column=1, value=topic).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(row=r, column=2, value=qid).alignment = Alignment(vertical="top")
        ws.cell(row=r, column=3, value=q).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(row=r, column=4, value=why).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(row=r, column=4).font = Font(italic=True, color="5A5872")
        cell = ws.cell(row=r, column=5, value=notes.get(qid, notes.get(q, "")))
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        cell.fill = PatternFill("solid", fgColor=TINT)
    for col, width in zip("ABCDE", (18, 16, 60, 48, 60)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = ws.cell(row=FIRST_DATA, column=3)
    wb.save(path)
    return path


def _rows_from_config(cfg):
    d = cfg.data
    out = defaultdict(list)
    out["Employers"] = d.get("employers", [])
    for loc in d.get("locations", []):
        mw = sorted(loc.get("min_wage", []), key=lambda m: m.get("effective_from") or "")
        row = {**loc}
        if mw:
            row["mw_rate"], row["mw_from"] = mw[0]["rate"], mw[0].get("effective_from")
        if len(mw) > 1:
            row["mw_next"], row["mw_next_from"] = mw[1]["rate"], mw[1].get("effective_from")
        out["Locations"].append(row)
    for state, sr in d.get("state_rules", {}).items():
        daily = sr.get("daily_ot") or {}
        out["State Rules"].append({**sr, "state": state, "daily_threshold": daily.get("threshold"),
                                   "double_threshold": daily.get("double_threshold")})
    out["Roles"] = d.get("roles", [])
    out["Time Pay"] = d.get("time_pay", [])
    out["Time Off"] = d.get("time_off_pay", [])
    for inc in d.get("incentives", []):
        ex = (inc.get("exclude") or [{}])[0]
        out["Incentives"].append({**inc, "tier_method": inc.get("tier_method", "none") if inc.get("tiers") else "none",
                                  "exclude_field": ex.get("field"), "exclude_values": ex.get("values")})
        for r in inc.get("rates", []):
            out["Incentive Rates"].append({**r, "incentive": inc["id"]})
        for t in inc.get("tiers", []):
            out["Incentive Tiers"].append({**t, "incentive": inc["id"]})
        for r in inc.get("recipients", []):
            out["Location Recipients"].append({**r, "incentive": inc["id"]})
    out["Stipends"] = d.get("stipends", [])
    out["Cost Split"] = d.get("manager_allocation", [])
    for bp in d.get("bonus_pools", []):
        out["Bonus Pools"].append(bp)
        for m in bp.get("metrics", []):
            out["Bonus Metrics"].append({**m, "pool": bp["id"]})
        for r in bp.get("recipients", []):
            out["Bonus Recipients"].append({**r, "pool": bp["id"]})
    out["Pay Codes"] = [{"key": k, **v} for k, v in d.get("pay_codes", {}).items()]
    for o in d.get("employee_overrides", []):
        rates = o.get("rates") or [{}]
        for i, r in enumerate(rates):
            base = o if i == 0 else {"employee_id": o["employee_id"]}
            out["Employee Notes"].append({**base, "rate_role": r.get("role"), "rate": r.get("rate"),
                                          "rate_type": r.get("rate_type"), "effective_from": r.get("effective_from")})
    out["POS Reports"] = d.get("systems", {}).get("pos_reports", [])
    return out


# ------------------------------------------------------------------ compile
def _read_table(ws, cols, findings, tab):
    rows = []
    for r in range(FIRST_DATA, ws.max_row + 1):
        values = [ws.cell(row=r, column=c).value for c in range(1, len(cols) + 1)]
        if all(v in (None, "") for v in values):
            continue
        row = {}
        for (h, key, kind, choices, _), v in zip(cols, values):
            if v in (None, ""):
                continue
            if kind == "list":
                row[key] = [s.strip() for s in str(v).split(";") if s.strip()]
            elif kind == "bool":
                row[key] = str(v).strip().lower() in ("yes", "y", "true", "1")
            elif kind == "num":
                try:
                    row[key] = str(D(v).normalize()) if D(v) == D(v).to_integral() else str(D(v))
                except ValueError:
                    findings.fail("INTAKE_NUM", f"{tab} row {r}: '{h}' must be a number, got {v!r}")
            elif kind == "date":
                row[key] = v.date().isoformat() if hasattr(v, "date") else str(v).strip()
            else:
                row[key] = str(v).strip()
            if choices and kind == "str" and key in row and row[key] not in choices:
                findings.fail("INTAKE_CHOICE", f"{tab} row {r}: '{h}' must be one of {choices}, got {row[key]!r}")
        rows.append(row)
    return rows


def compile_intake(path):
    f = Findings()
    wb = load_workbook(path, data_only=True)
    company, systems, settings = {}, {}, {}
    ws = wb["Company"]
    for i, (label, key, kind, choices, _) in enumerate(COMPANY_FIELDS):
        v = ws.cell(row=FIRST_DATA + i, column=2).value
        if v in (None, ""):
            continue
        v = (str(v).strip().lower() in ("yes", "y", "true")) if kind == "bool" else str(v).strip()
        if key in ("hris", "payroll", "pos", "time_clock"):
            systems[key] = v
        elif key in ("co_code", "split_by_location"):
            settings[key] = v
        elif key in ("reviewer", "submitter"):
            company.setdefault("process", {})[key] = v
        else:
            company[key] = v
    t = {tab: _read_table(wb[tab], cols, f, tab) for tab, _, cols, _ in TABLES if tab in wb.sheetnames}

    locations = []
    for row in t.get("Locations", []):
        mw = []
        if row.get("mw_rate"):
            mw.append({"rate": row["mw_rate"], "effective_from": row.get("mw_from")})
        if row.get("mw_next"):
            mw.append({"rate": row["mw_next"], "effective_from": row.get("mw_next_from")})
        locations.append({k: row[k] for k in ("id", "name", "employer_id", "city", "state", "payroll_code") if k in row}
                         | {"min_wage": mw, "pos_labels": row.get("pos_labels", []), "hris_labels": row.get("hris_labels", [])})
    state_rules = {}
    for row in t.get("State Rules", []):
        st = row.pop("state", None)
        if not st:
            continue
        daily = None
        if row.get("daily_threshold"):
            daily = {"threshold": row["daily_threshold"]}
            if row.get("double_threshold"):
                daily["double_threshold"] = row["double_threshold"]
        state_rules[st] = {"weekly_ot_threshold": row.get("weekly_ot_threshold", "40"), "daily_ot": daily,
                           "seventh_day_ot": row.get("seventh_day_ot", False),
                           "piece_rate_nonproductive_separate": row.get("piece_rate_nonproductive_separate", False),
                           "confirmed_by_owner": row.get("confirmed_by_owner", False), "notes": row.get("notes", "")}
    incentives = []
    rates, tiers, recips = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in t.get("Incentive Rates", []):
        rates[r.pop("incentive", "")].append(r)
    for r in t.get("Incentive Tiers", []):
        tiers[r.pop("incentive", "")].append(r)
    for r in t.get("Location Recipients", []):
        recips[r.pop("incentive", "")].append(r)
    for row in t.get("Incentives", []):
        inc = {k: v for k, v in row.items() if k not in ("exclude_field", "exclude_values", "notes")}
        if row.get("exclude_field"):
            inc["exclude"] = [{"field": row["exclude_field"], "values": row.get("exclude_values", [])}]
        if inc.get("tier_method") == "none":
            inc.pop("tier_method")
        inc["rates"] = rates.get(row.get("id"), [])
        if tiers.get(row.get("id")):
            inc["tiers"] = tiers[row["id"]]
            inc.setdefault("tier_method", "marginal")
        if recips.get(row.get("id")):
            inc["recipients"] = recips[row["id"]]
        incentives.append(inc)
    pools = []
    mets, preci = defaultdict(list), defaultdict(list)
    for r in t.get("Bonus Metrics", []):
        mets[r.pop("pool", "")].append(r)
    for r in t.get("Bonus Recipients", []):
        preci[r.pop("pool", "")].append(r)
    for row in t.get("Bonus Pools", []):
        pools.append({**row, "metrics": mets.get(row.get("id"), []), "recipients": preci.get(row.get("id"), [])})
    overrides = {}
    for row in t.get("Employee Notes", []):
        o = overrides.setdefault(row["employee_id"], {"employee_id": row["employee_id"]})
        for k in ("secondary_role", "pos_names", "payroll_id", "home_location"):
            if row.get(k):
                o[k] = row[k]
        if row.get("rate"):
            o.setdefault("rates", []).append({"role": row.get("rate_role"), "rate": row["rate"], "rate_type": row.get("rate_type"),
                                              "effective_from": row.get("effective_from", "")})
    pay_codes = {}
    for row in t.get("Pay Codes", []):
        key = row.pop("key", None)
        if key:
            pay_codes[key] = {"label": row.get("label", key), "code": row.get("code", ""), "export_as": row.get("export_as", "amount")}
    if settings:
        systems["payroll_settings"] = settings
    if t.get("POS Reports"):
        systems["pos_reports"] = t["POS Reports"]
    notes = []
    if "Questions" in wb.sheetnames:
        wsq = wb["Questions"]
        for r in range(FIRST_DATA, wsq.max_row + 1):
            qid, q, a = wsq.cell(row=r, column=2).value, wsq.cell(row=r, column=3).value, wsq.cell(row=r, column=5).value
            if q and a not in (None, ""):
                notes.append({"id": qid, "topic": wsq.cell(row=r, column=1).value, "question": q, "answer": str(a)})
    data = {
        "schema_version": SCHEMA_VERSION, "company": company, "approval": {}, "systems": systems,
        "employers": t.get("Employers", []), "locations": locations, "state_rules": state_rules,
        "roles": t.get("Roles", []), "time_pay": [{k: v for k, v in r.items() if k != "notes"} for r in t.get("Time Pay", [])],
        "time_off_pay": t.get("Time Off", []), "incentives": incentives, "stipends": t.get("Stipends", []),
        "manager_allocation": t.get("Cost Split", []), "bonus_pools": pools,
        "employee_overrides": list(overrides.values()), "pay_codes": pay_codes,
        "checks": {"plausibility": {"min_avg_service_hours": "0.25", "max_avg_service_hours": "4",
                                    "max_weekly_hours": "70", "anomaly_threshold": "0.25"}},
        "intake_notes": notes,
    }
    for key in ENGINE_PAY_KEYS:
        if key not in pay_codes:
            f.info("INTAKE_PAYCODE", f"no payroll code yet for engine pay type '{key}' ({ENGINE_PAY_KEYS[key]}); add it if you use it")
    return data, f
