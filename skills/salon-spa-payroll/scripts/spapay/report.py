"""Run summary (markdown + branded HTML) and the shared Duotone Tape page shell."""
from __future__ import annotations

import html
from decimal import Decimal
from collections import defaultdict

from .util import ZERO, fmt_money

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Anton&family=Oswald:wght@400;500;700&display=swap');
:root { --navy:#141034; --orange:#E58700; --yellow:#F8D300; --cream:#F6ECD4; --tint:#FBF6EA; }
* { box-sizing:border-box; border-radius:0; box-shadow:none; }
body { margin:0; background:var(--tint); color:var(--navy); font-family:Oswald, 'Arial Narrow', Arial, sans-serif; font-size:15px; line-height:1.5; }
header { background:var(--navy); border-bottom:6px solid var(--orange); padding:28px 40px 22px; }
header .hook { font-family:Anton, Impact, sans-serif; text-transform:uppercase; color:var(--yellow); font-size:44px; line-height:1; margin:0; letter-spacing:.5px; }
header .hook span { color:#fff; }
header .label { color:var(--cream); font-weight:500; margin-top:8px; letter-spacing:.3px; }
main { max-width:1040px; margin:0 auto; padding:28px 40px 60px; }
h2 { font-family:Anton, Impact, sans-serif; text-transform:uppercase; font-weight:400; font-size:26px; margin:34px 0 10px; }
h2:after { content:""; display:block; width:56px; height:4px; background:var(--orange); margin-top:6px; }
h3 { font-weight:700; text-transform:uppercase; font-size:16px; margin:22px 0 6px; }
table { border-collapse:collapse; width:100%; margin:8px 0 18px; background:#fff; }
th { background:var(--navy); color:var(--cream); text-align:left; font-weight:500; padding:7px 10px; text-transform:uppercase; font-size:13px; letter-spacing:.4px; }
td { padding:6px 10px; border-bottom:1px solid #E7DCC2; vertical-align:top; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
.pill { display:inline-block; padding:1px 8px; font-weight:700; font-size:12px; }
.PASS { background:#D8EFDD; } .FAIL { background:#F8D7DA; } .WARN { background:#FFF1CC; } .INFO { background:#EAE7F3; }
.status { display:inline-block; background:var(--navy); color:var(--yellow); font-family:Anton, Impact, sans-serif; font-size:28px; padding:6px 16px; text-transform:uppercase; }
.status.bad { color:#FF8A7A; }
.rule { border-left:4px solid var(--orange); background:#fff; padding:10px 14px; margin:10px 0; }
.rule .id { font-weight:700; color:var(--orange); margin-right:8px; }
.sign { margin-top:30px; background:#fff; border-top:4px solid var(--navy); padding:18px; }
.sign .line { border-bottom:1px solid var(--navy); height:34px; margin:10px 0 2px; }
footer { color:#6b6680; font-size:12px; padding:0 40px 30px; max-width:1040px; margin:0 auto; }
@media print { body { background:#fff; } header { -webkit-print-color-adjust:exact; print-color-adjust:exact; } }
"""


def page(hook, label, body, title=None):
    hook_html = html.escape(hook)
    return (f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title or hook)}</title><style>{CSS}</style></head><body>"
            f"<header><p class='hook'>{hook_html}</p><div class='label'>{html.escape(label)}</div></header>"
            f"<main>{body}</main><footer>Salon &amp; Spa Payroll Prep · catch the errors and omissions before payday · "
            f"not legal, tax or payroll advice; the owner reviews every run.</footer></body></html>")


def table(headers, rows, num_cols=()):
    num_th = " class='num'"
    out = ["<table><tr>" + "".join(f"<th{num_th if h in num_cols else ''}>{html.escape(str(h))}</th>"
                                   for h in headers) + "</tr>"]
    for row in rows:
        cells = []
        for h, v in zip(headers, row):
            cls = " class='num'" if h in num_cols else ""
            text = f"{v:,.2f}" if isinstance(v, Decimal) and h in num_cols else str(v)
            if text in ("PASS", "PASS*", "FAIL", "WARN", "INFO"):
                text = f"<span class='pill {text.rstrip('*')}'>{text}</span>"
            else:
                text = html.escape(text)
            cells.append(f"<td{cls}>{text}</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</table>")
    return "".join(out)


def write_summary(period, cfg, status, reasons, result, checks, audit_result, findings, exports, earnings_total):
    loc_totals = defaultdict(lambda: ZERO)
    for l in result.lines:
        if l["kind"] != "memo":
            loc_totals[l["location_id"]] += l["amount"]
    memo = sum((l["amount"] for l in result.lines if l["kind"] == "memo"), ZERO)
    memo_note = f" Plus {fmt_money(memo)} in declared cash tips, reported for taxes only." if memo else ""
    md = [f"# {status}: {cfg.company.get('name')} payroll {period.start} to {period.end}", ""]
    if reasons:
        md += ["Not clear because:", ""] + [f"- {r}" for r in reasons] + [""]
    md += [f"Gross earnings: **{fmt_money(earnings_total)}** for {len({l['employee_id'] for l in result.lines})} people.{memo_note}", ""]
    md += ["| Location | Gross |", "|---|---:|"] + [f"| {cfg.locations[k].get('name', k)} | {fmt_money(v)} |" for k, v in loc_totals.items()] + [""]
    failed = [c for c in checks if c["status"] == "FAIL"]
    md += [f"Checks: {len(checks) - len(failed)} of {len(checks)} pass. Independent audit: {audit_result['status']}."]
    for c in failed:
        md.append(f"- FAIL {c['check']} ({c['location_id']}): inputs {c['input_total']}, paid {c['paid_total']}, variance {c['variance']}")
    for m in audit_result["mismatches"]:
        md.append(f"- AUDIT {m['employee']} {m['pay_code']}: engine {m['engine']}, audit {m['audit']}")
    if findings.of("FAIL") or findings.of("WARN"):
        md += ["", "## Findings", ""]
        md += [f"- **FAIL** {i['message']}" for i in findings.of("FAIL")]
        md += [f"- WARN {i['message']}" + (f" _(acknowledged: {i['acknowledged']})_" if i.get("acknowledged") else "")
               for i in findings.of("WARN")]
    if exports:
        md += ["", "## Files for the payroll system", ""]
        for ex in exports:
            md.append(f"- `{ex['file'].split('/')[-1]}`: {ex['rows']} rows, {ex['employees']} people, "
                      f"{fmt_money(ex['amount_total'])} in amounts + {ex['hours_total']:.2f} hours")
        md.append(f"- {exports[0]['note']}")
    md += ["", "Nothing is paid until the owner reviews the workbook and approves."]
    (period.output_dir / "run_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    body = [f"<div class='status{'' if status == 'ALL CLEAR' else ' bad'}'>{html.escape(status)}</div>"]
    if reasons:
        body.append("<ul>" + "".join(f"<li>{html.escape(r)}</li>" for r in reasons) + "</ul>")
    body.append(f"<h2>Totals</h2><p>Gross earnings <b>{fmt_money(earnings_total)}</b> for "
                f"{len({l['employee_id'] for l in result.lines})} people.{html.escape(memo_note)}</p>")
    body.append(table(["Location", "Gross"], [[cfg.locations[k].get("name", k), fmt_money(v)] for k, v in loc_totals.items()], {"Gross"}))
    body.append("<h2>Checks</h2>" + table(["Check", "Location", "Inputs", "Paid", "Variance", "Status"],
                [[c["check"], c["location_id"], c["input_total"], c["paid_total"], c["variance"], c["status"]] for c in checks],
                {"Inputs", "Paid", "Variance"}))
    body.append(f"<h2>Independent audit</h2><p><span class='pill {audit_result['status']}'>{audit_result['status']}</span> "
                f"{len(audit_result['mismatches'])} differences.</p>")
    if findings.items:
        order = {"FAIL": 0, "WARN": 1, "INFO": 2}
        body.append("<h2>Findings</h2>" + table(["Severity", "Message", "Acknowledged by"],
                    [[i["severity"], i["message"], i.get("acknowledged", "")]
                     for i in sorted(findings.items, key=lambda i: order[i["severity"]])]))
    if exports:
        body.append("<h2>Files for the payroll system</h2>" + table(["File", "Rows", "People", "Amounts", "Hours"],
                    [[e["file"].split("/")[-1], e["rows"], e["employees"], fmt_money(e["amount_total"]), f"{e['hours_total']:.2f}"] for e in exports],
                    {"Rows", "People", "Amounts", "Hours"}))
    (period.output_dir / "run_summary.html").write_text(
        page("Payroll run", f"{cfg.company.get('name')} · {period.start} to {period.end}", "".join(body)), encoding="utf-8")
