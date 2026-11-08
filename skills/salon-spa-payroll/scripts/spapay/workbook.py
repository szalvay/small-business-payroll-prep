"""Review workbook: everything a reviewer needs to check a run, one tab per question."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .util import ZERO

# Duotone Tape brand (assets/brand/brand.json): navy panels, yellow hooks, one orange stripe, square.
NAVY, ORANGE, YELLOW, CREAM, CREAM_TINT = "141034", "E58700", "F8D300", "F6ECD4", "FBF6EA"
HEAD = PatternFill("solid", fgColor=NAVY)
BAND = PatternFill("solid", fgColor=CREAM_TINT)
STRIPE = PatternFill("solid", fgColor=ORANGE)
PASS = PatternFill("solid", fgColor="D8EFDD")
FAIL = PatternFill("solid", fgColor="F8D7DA")
WARN = PatternFill("solid", fgColor="FFF1CC")
WHITE_BOLD = Font(name="Oswald", bold=True, color=CREAM)
BOLD = Font(name="Oswald", bold=True, color=NAVY)
HOOK = Font(name="Anton", size=22, color=YELLOW)
TITLE_LABEL = Font(name="Oswald", size=11, bold=True, color=CREAM)
MONEY = '"$"#,##0.00;[Red]-"$"#,##0.00'
HOURS = '#,##0.00'


def _num(v):
    if isinstance(v, Decimal):
        return float(v)
    return v


def _table(ws, headers, rows, money_cols=(), hour_cols=(), widths=None, start_row=1, status_col=None):
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=c, value=h)
        cell.fill, cell.font = HEAD, WHITE_BOLD
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for r, row in enumerate(rows, start=start_row + 1):
        for c, value in enumerate(row, start=1):
            if hasattr(value, "isoformat") and not isinstance(value, str):
                value = value.isoformat()
            cell = ws.cell(row=r, column=c, value=_num(value))
            if headers[c - 1] in money_cols:
                cell.number_format = MONEY
            elif headers[c - 1] in hour_cols:
                cell.number_format = HOURS
            if (r - start_row) % 2 == 0:
                cell.fill = BAND
        if status_col is not None:
            st = str(row[status_col])
            fill = PASS if st.startswith("PASS") else FAIL if st == "FAIL" else WARN if st == "WARN" else None
            if fill:
                ws.cell(row=r, column=status_col + 1).fill = fill
    ws.freeze_panes = ws.cell(row=start_row + 1, column=2 if len(headers) > 3 else 1)
    for c, h in enumerate(headers, start=1):
        width = (widths or {}).get(h)
        if width is None:
            longest = max([len(str(h))] + [len(str(_num(row[c - 1]))) for row in rows[:300]] or [10])
            width = min(max(10, longest + 2), 60)
        ws.column_dimensions[get_column_letter(c)].width = width


def brand_band(ws, hook, label, cols=8):
    """Navy title panel with a yellow Anton hook, cream Oswald label and one orange stripe."""
    for r in (1, 2):
        for c in range(1, cols + 1):
            ws.cell(row=r, column=c).fill = HEAD
    for c in range(1, cols + 1):
        ws.cell(row=3, column=c).fill = STRIPE
    ws.row_dimensions[1].height = 36
    ws.row_dimensions[3].height = 4
    ws["A1"] = hook.upper()
    ws["A1"].font = HOOK
    ws["A2"] = label
    ws["A2"].font = TITLE_LABEL


def build_workbook(path, cfg, period, inputs, result, checks, audit_result, findings, status, exports):
    wb = Workbook()
    lines = result.lines
    emps = inputs.employees

    # ---- Summary
    ws = wb.active
    ws.title = "Summary"
    brand_band(ws, f"{status}", f"{cfg.company.get('name')}  ·  pay period {period.start} to {period.end}"
               + (f"  ·  pay date {period.pay_date}" if period.pay_date else ""), cols=6)
    ws["A1"].font = Font(name="Anton", size=22, color=YELLOW if status == "ALL CLEAR" else "FF6B5B")
    ws["A4"] = ("Rules signed off by " + cfg.data.get("approval", {}).get("approved_by", "")
                if cfg.approved else "Rules NOT signed off (see the Pay Rules Book)")
    ws["A4"].font = BOLD
    earnings = [l for l in lines if l["kind"] != "memo"]
    totals = defaultdict(lambda: ZERO)
    for l in earnings:
        totals[l["location_id"]] += l["amount"]
    rows = [[loc, cfg.locations[loc].get("name", ""), len({l["employee_id"] for l in earnings if l["location_id"] == loc}), totals[loc]]
            for loc in cfg.locations]
    rows.append(["ALL", "", len({l["employee_id"] for l in earnings}), sum(totals.values(), ZERO)])
    _table(ws, ["Location", "Name", "People paid", "Gross earnings"], rows, money_cols={"Gross earnings"}, start_row=6)
    r = len(rows) + 9
    counts = [
        ["Gate / calculation FAILs", len(findings.of("FAIL"))],
        ["Warnings", f"{len(findings.of('WARN'))} ({sum(1 for i in findings.of('WARN') if i.get('acknowledged'))} acknowledged)"],
        ["Checks passed", f"{sum(1 for c in checks if c['status'].startswith('PASS'))} of {len(checks)}"],
        ["Independent audit", audit_result["status"] if audit_result else "not run"],
    ]
    for i, (k, v) in enumerate(counts):
        ws.cell(row=r + i, column=1, value=k).font = BOLD
        ws.cell(row=r + i, column=2, value=v)
    r += len(counts) + 1
    ws.cell(row=r, column=1, value="Files for the payroll system").font = BOLD
    for i, ex in enumerate(exports):
        ws.cell(row=r + 1 + i, column=1, value=ex["file"].split("/")[-1])
        ws.cell(row=r + 1 + i, column=2, value=f"{ex['rows']} rows, {ex['employees']} people")
    ws.column_dimensions["A"].width = 44

    # ---- By location x pay type
    ws = wb.create_sheet("By Pay Type")
    pivot = defaultdict(lambda: ZERO)
    hours = defaultdict(lambda: ZERO)
    codes = sorted({l["pay_code"] for l in lines})
    for l in lines:
        pivot[(l["location_id"], l["pay_code"])] += l["amount"]
        hours[(l["location_id"], l["pay_code"])] += l["hours"] or ZERO
    rows = []
    for code in codes:
        rows.append([code, cfg.pay_code_label(code), (cfg.pay_codes.get(code) or {}).get("code", ""),
                     *[pivot[(loc, code)] for loc in cfg.locations], sum((pivot[(loc, code)] for loc in cfg.locations), ZERO),
                     sum((hours[(loc, code)] for loc in cfg.locations), ZERO)])
    heads = ["Pay type", "Label", "Processor code", *cfg.locations, "Total", "Hours"]
    _table(ws, heads, rows, money_cols=set(cfg.locations) | {"Total"}, hour_cols={"Hours"})

    # ---- Employees
    ws = wb.create_sheet("Employees")
    per = defaultdict(lambda: defaultdict(lambda: ZERO))
    hrs = defaultdict(lambda: defaultdict(lambda: ZERO))
    for l in lines:
        key = (l["employee_id"], l["location_id"])
        per[key][l["pay_code"]] += l["amount"]
        if l["hours"]:
            hrs[key][l["pay_code"]] += l["hours"]
    rows = []
    for (emp_id, loc), amounts in sorted(per.items(), key=lambda kv: (kv[0][1], emps[kv[0][0]].name)):
        emp = emps[emp_id]
        svc_h = sum((hrs[(emp_id, loc)][c] for c in ("service_wages", "service_per_unit", "service_commission")), ZERO)
        gross = sum((v for c, v in amounts.items() if not (c == "cash_tips" and cfg.company.get("cash_tips", "report_only") == "report_only")), ZERO)
        rows.append([loc, emp_id, emp.name, emp.role, emp.status, svc_h,
                     hrs[(emp_id, loc)]["regular"] + hrs[(emp_id, loc)]["overtime"] + hrs[(emp_id, loc)]["doubletime"],
                     hrs[(emp_id, loc)]["overtime"] + hrs[(emp_id, loc)]["doubletime"],
                     *[amounts.get(c, ZERO) for c in codes], gross])
    heads = ["Location", "Employee ID", "Name", "Role", "Status", "Service hrs", "Hourly hrs", "OT/DT hrs", *codes, "Gross"]
    _table(ws, heads, rows, money_cols=set(codes) | {"Gross"}, hour_cols={"Service hrs", "Hourly hrs", "OT/DT hrs"})

    # ---- Earnings lines
    ws = wb.create_sheet("Earnings Lines")
    rows = [[l["location_id"], l["employee_id"], l["employee"], l["role"], l["pay_code"], l["label"], l["processor_code"],
             l["hours"], l["rate"], l["amount"], l["kind"], l["rule"], l["detail"]] for l in lines]
    _table(ws, ["Location", "Employee ID", "Name", "Role", "Pay type", "Label", "Processor code", "Hours", "Rate",
                "Amount", "Kind", "Rule", "Detail"], rows, money_cols={"Amount"}, hour_cols={"Hours"},
           widths={"Detail": 70})

    # ---- Overtime
    ws = wb.create_sheet("Overtime")
    rows = [[w["employee"], w["employer"], w["week_start"], w["prior_hours"], w["current_hours"], w["total_hours"],
             w["ot_hours"], w["dt_hours"], w["regular_rate"].quantize(Decimal("0.0001")), w["straight_earnings"],
             w["premium_due"], w["paid_before"], w["premium_now"], w["min_wage_required"], w["makeup_now"]]
            for w in sorted(result.weeks, key=lambda w: (w["employee"], w["week_start"]))]
    _table(ws, ["Employee", "Employer", "Week starting", "Hours paid last period", "Hours this period", "Week total",
                "OT hours", "DT hours", "Regular rate", "Straight-time earnings", "Premium due", "Premium paid before",
                "Premium now", "Minimum wage required", "Make-up now"], rows,
           money_cols={"Straight-time earnings", "Premium due", "Premium paid before", "Premium now", "Minimum wage required", "Make-up now"},
           hour_cols={"Hours paid last period", "Hours this period", "Week total", "OT hours", "DT hours"})

    # ---- Checks
    ws = wb.create_sheet("Checks")
    rows = [[c["check"], c["location_id"], c["input_total"], c["paid_total"], c["variance"], c["status"], c["note"]] for c in checks]
    _table(ws, ["Check", "Location", "From inputs", "Paid", "Variance", "Status", "Note"], rows, status_col=5,
           widths={"Check": 52, "Note": 60})

    # ---- Audit
    ws = wb.create_sheet("Audit")
    if audit_result:
        rows = [[m["employee"], m["pay_code"], m["engine"], m["audit"], m["difference"]] for m in audit_result["mismatches"]]
        ws["A1"] = f"Independent recomputation: {audit_result['status']}"
        ws["A1"].font = BOLD
        _table(ws, ["Employee", "Pay type", "Engine", "Audit", "Difference"], rows or [["(no differences)", "", "", "", ""]],
               money_cols={"Engine", "Audit", "Difference"}, start_row=3)
        start = len(rows or [1]) + 6
        ws.cell(row=start - 1, column=1, value="Hourly + overtime: straight time for every hour + premium, both ways").font = BOLD
        rows2 = [[o["employee"], o["engine"], o["straight_plus_premium"], o["difference"]] for o in audit_result["ot_equivalence"]]
        _table(ws, ["Employee", "Engine (regular + OT + premium)", "Straight time + premium", "Difference"],
               rows2 or [["(none)", "", "", ""]], money_cols={"Engine (regular + OT + premium)", "Straight time + premium", "Difference"},
               start_row=start)

    # ---- Findings
    ws = wb.create_sheet("Findings")
    order = {"FAIL": 0, "WARN": 1, "INFO": 2}
    rows = [[i["severity"], i["code"], i["message"], i.get("acknowledged", "")]
            for i in sorted(findings.items, key=lambda i: order[i["severity"]])]
    _table(ws, ["Severity", "Code", "Message", "Acknowledged by"], rows or [["", "", "No findings", ""]], status_col=0,
           widths={"Message": 110, "Acknowledged by": 40})

    # ---- Incentive notes
    ws = wb.create_sheet("Incentive Notes")
    state_text = {0: "No rate in any incentive (paid $0)", 1: "Excluded by a rule (paid $0)", 2: "Matched, but not payable to this seller"}
    rows = [[n["source"], state_text.get(n["state"], ""), n["reason"], n["subject"], n["units"], n["amount"], ", ".join(n["people"])]
            for n in result.incentive_notes]
    _table(ws, ["Source", "Outcome", "Why", "Code / person", "Units", "$", "People"],
           rows or [["", "Every add-on and sale was paid by an incentive", "", "", "", "", ""]],
           money_cols={"$"}, widths={"Outcome": 36, "Why": 44, "People": 40})

    # ---- Inputs
    ws = wb.create_sheet("Inputs")
    from .util import file_sha256
    rows = [[name, str(path.name), len(inputs.rows.get(name, [])) if name not in ("roster", "pay_rates") else "",
             file_sha256(path)[:16]] for name, path in sorted(inputs.files.items())]
    _table(ws, ["Input", "File", "Rows used", "SHA-256 (first 16)"], rows)
    start = len(rows) + 4
    ws.cell(row=start - 1, column=1, value="Source reports recorded in period.json").font = BOLD
    rows2 = [[s.get("file", ""), s.get("report", ""), s.get("location_id", ""), s.get("date_from", ""), s.get("date_to", ""),
              s.get("mapped_to", ""), ", ".join(f"{k}={v}" for k, v in (s.get("totals") or {}).items())] for s in period.sources]
    _table(ws, ["File", "Report", "Location", "From", "To", "Mapped to", "Report totals"], rows2 or [["(none recorded)", "", "", "", "", "", ""]],
           start_row=start)
    wb.save(path)
    return path
