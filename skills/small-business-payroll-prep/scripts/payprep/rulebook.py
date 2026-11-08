"""The Pay Rules Book: the config in plain English, for the owner to read and sign.

Every rule has an ID that also appears on the earnings lines it produces, so a
reviewer can trace any dollar on the review workbook back to a sentence here.
"""
from __future__ import annotations

import datetime as _dt
import html

from .config import PAY_FREQUENCIES
from .report import page
from .util import D, fmt_money, write_json

BASIS_TEXT = {
    "min_wage": "the location's minimum wage",
    "base_rate": "their own rate",
    "fixed": "a fixed rate of {rate}",
    "regular_rate": "their regular rate (average hourly earnings that week)",
    "unpaid": "nothing extra (it still counts as hours worked)",
}
PAY_BASIS_TEXT = {
    "piece_service_hour": "paid a piece rate for every hour of client service they perform",
    "piece_per_service": "paid a set amount per service performed",
    "service_revenue_pct": "paid a percentage of the service revenue they produce",
    "hourly": "paid hourly for every hour on the clock",
    "salary": "paid a salary",
}


def _basis(row):
    text = BASIS_TEXT.get(row.get("basis"), row.get("basis"))
    return text.format(rate=fmt_money(row.get("fixed_rate") or 0))


def build_rules(cfg):
    """Return [(section, [(rule_id, sentence)])]."""
    sections = []
    c = cfg.company
    rules = [
        ("R-CO-1", f"{c.get('name')} pays {c.get('pay_frequency', '').replace('_', '-')} "
                   f"({PAY_FREQUENCIES.get(c.get('pay_frequency'), '?')} pay days a year). The workweek starts on {cfg.workweek_start.title()}."),
        ("R-CO-2", "Overtime is counted per workweek, never by adding up the pay period. A workweek that straddles two pay "
                   "periods is judged on its combined hours, and only what the earlier check did not pay is paid now."),
        ("R-CO-3", "Hours worked at different locations of the same employer are added together for overtime."
                   if c.get("ot_aggregation", "employer") == "employer" else
                   "Each location is treated as its own employer for overtime."),
        ("R-MINWAGE", "Every workweek, straight-time pay must cover hours worked times the minimum wage where they were worked. "
                      + ("Any shortfall is added automatically as make-up pay." if c.get("min_wage_makeup") == "auto"
                         else "Any shortfall stops the run until the owner decides how to pay it.")),
        ("R-TIPS", "Card tips are passed through to the person who earned them, in full. Cash tips are "
                   + ("reported for taxes but not paid by the business." if c.get("cash_tips", "report_only") == "report_only"
                      else "paid through payroll.")),
        ("R-ADJ", "One-off pay (bonuses, back pay, reimbursements) is paid only from an adjustments line naming who approved it."),
    ]
    sections.append(("Company", rules))

    rules = []
    for emp_id, emp in cfg.employers.items():
        locs = [l for l in cfg.locations.values() if l.get("employer_id") == emp_id]
        rules.append((f"R-EMP-{emp_id}", f"{emp.get('legal_name', emp_id)} employs the staff at "
                      + ", ".join(l.get("name", l["id"]) for l in locs) + "."))
    for loc_id, loc in cfg.locations.items():
        wages = "; ".join(f"{fmt_money(m['rate'])} from {m.get('effective_from') or 'the start'}" for m in loc.get("min_wage", []))
        rules.append((f"R-LOC-{loc_id}", f"{loc.get('name', loc_id)} ({loc.get('city', '')} {loc.get('state', '')}): "
                      f"minimum wage {wages}."))
    sections.append(("Employers and locations", rules))

    rules = []
    for state, sr in cfg.state_rules.items():
        parts = [f"weekly overtime after {sr.get('weekly_ot_threshold', 40)} hours"]
        if sr.get("daily_ot"):
            d = sr["daily_ot"]
            parts.append(f"daily overtime after {d.get('threshold')} hours" + (f" and double time after {d['double_threshold']}" if d.get("double_threshold") else ""))
        if sr.get("seventh_day_ot"):
            parts.append("seventh consecutive day rules")
        if sr.get("piece_rate_nonproductive_separate"):
            parts.append("piece-rate staff are paid separately, at least minimum wage, for non-productive time on the clock")
        rules.append((f"R-STATE-{state}", f"{state}: " + "; ".join(parts) + "."
                      + ("" if sr.get("confirmed_by_owner") else " NOT YET CONFIRMED by the owner.")
                      + (f" Note: {sr['notes']}" if sr.get("notes") else "")))
    sections.append(("State rules (confirm with your payroll provider or counsel)", rules))

    rules = []
    for role_id, role in cfg.roles.items():
        text = f"{role.get('label', role_id)}: {PAY_BASIS_TEXT.get(role.get('pay_basis'), role.get('pay_basis'))}"
        if role.get("pay_basis", "").startswith("piece") or role.get("pay_basis") == "service_revenue_pct":
            cats = ", ".join(role.get("service_categories") or ["any category"])
            text += f" (services in: {cats})"
            text += ". Hours worked come from " + ("the time clock." if role.get("hours_worked_source") == "clock"
                                                   else "service time plus recorded non-service time.")
        else:
            text += "."
        if role.get("exempt"):
            text += " Exempt from overtime."
        rules.append((f"R-ROLE-{role_id}", text))
    sections.append(("Roles", rules))

    rules = []
    for row in cfg.data.get("time_pay", []):
        who = "Everyone" if row["role"] == "*" else cfg.roles.get(row["role"], {}).get("label", row["role"])
        rules.append((f"R-TIME-{row['role']}-{row['category']}".upper(),
                      f"{who}: {row['category'].replace('_', ' ')} time is paid at {_basis(row)} (pay type {row.get('pay_code') or row['category']})."))
    for row in cfg.data.get("time_off_pay", []):
        who = "Everyone" if row["role"] == "*" else cfg.roles.get(row["role"], {}).get("label", row["role"])
        rules.append((f"R-TIMEOFF-{row['role']}-{row['type']}".upper(),
                      f"{who}: {row['type']} hours are paid at {_basis(row)} (pay type {row.get('pay_code') or row['type']})."))
    sections.append(("Non-service time and time off", rules))

    rules = []
    for inc in cfg.incentives:
        rules.append((f"R-INC-{inc['id']}".upper(), incentive_text(cfg, inc)))
    sections.append(("Commissions, spiffs and incentives", rules))

    rules = []
    for st in cfg.stipends:
        rules.append((f"R-STIPEND-{st.get('id', st['employee_id'])}".upper(),
                      f"{st['employee_id']} receives {fmt_money(st['amount'])} per pay period ({st.get('label', 'stipend')})"
                      + (f" from {st['effective_from']}" if st.get("effective_from") else "")
                      + (f" through {st['effective_through']}" if st.get("effective_through") else "") + "."))
    for bp in cfg.bonus_pools:
        mets = "; ".join(f"{m.get('label', m['id'])} ({m['numerator']}" + (f" / {m['denominator']}" if m.get('denominator') else "")
                         + f") {m.get('compare', '>=')} {m['threshold']} earns {D(m['weight']) * 100:.0f}%" for m in bp.get("metrics", []))
        rec = ", ".join(f"{r['location_id']} -> {r['employee_id']}" + (f" ({D(r.get('share', 1)) * 100:.0f}%)" if D(r.get("share", 1)) != 1 else "")
                        for r in bp.get("recipients", []))
        rules.append((f"R-POOL-{bp['id']}".upper(), f"{bp.get('label', bp['id'])}: up to {fmt_money(bp['pool_per_location'])} per location "
                      f"{'per month' if bp.get('frequency', 'monthly') == 'monthly' else 'per pay period'}. {mets}. Paid to: {rec}."))
    alloc = {}
    for row in cfg.data.get("manager_allocation", []):
        alloc.setdefault(row["employee_id"], []).append(f"{row['location_id']} {D(row['share']) * 100:.0f}%")
    for emp, parts in alloc.items():
        rules.append((f"R-ALLOC-{emp}".upper(), f"{emp}'s salary cost is split {', '.join(parts)}."))
    if rules:
        sections.append(("Managers, stipends and bonus pools", rules))

    rules = []
    for key, entry in sorted(cfg.pay_codes.items()):
        how = {"hours": "sent as hours (paid at the rate on file in the payroll system)", "amount": "sent as a dollar amount",
               "none": "not sent (the payroll system pays it from its own records)"}[entry.get("export_as", "amount")]
        rules.append((f"R-CODE-{key}".upper(), f"{entry.get('label', key)} goes to the payroll system as code '{entry.get('code', '')}', {how}."))
    sections.append((f"Pay codes for {cfg.data.get('systems', {}).get('payroll', 'the payroll system')}", rules))
    return sections


def render(cfg, md_path, html_path=None):
    sections = build_rules(cfg)
    fp = cfg.fingerprint()
    appr = cfg.data.get("approval") or {}
    md = [f"# Pay Rules Book: {cfg.company.get('name')}", "",
          f"Rules fingerprint `{fp}`. Generated {_dt.date.today().isoformat()}.", "",
          "Read every rule. If one is wrong, change it before signing; payroll runs refuse to show ALL CLEAR "
          "until the rules on file match a signed book.", ""]
    for title, rules in sections:
        md += [f"## {title}", ""] + [f"- **{rid}** {text}" for rid, text in rules] + [""]
    md += ["## Sign-off", "",
           f"Approved by: {appr.get('approved_by') or '________________________'}   "
           f"Date: {appr.get('approved_on') or '__________'}   Fingerprint: {appr.get('rules_fingerprint') or fp}", ""]
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))
    if html_path:
        body = [f"<p>Rules fingerprint <b>{fp}</b>. Every dollar in a payroll run points back to one of these rule IDs.</p>"]
        for title, rules in sections:
            body.append(f"<h2>{html.escape(title)}</h2>")
            body += [f"<div class='rule'><span class='id'>{html.escape(rid)}</span>{html.escape(text)}</div>" for rid, text in rules]
        signed = bool(appr.get("approved_by")) and appr.get("rules_fingerprint") == fp
        body.append("<div class='sign'><h3>Owner sign-off</h3>"
                    + (f"<p>Approved by <b>{html.escape(appr['approved_by'])}</b> on {html.escape(str(appr.get('approved_on')))}.</p>" if signed else
                       "<div class='line'></div>Name &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Date &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Signature")
                    + "</div>")
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(page("Pay rules book", f"{cfg.company.get('name')} · fingerprint {fp}", "".join(body),
                          title=f"Pay Rules Book: {cfg.company.get('name')}"))
    return fp


def approve(cfg, approved_by, notes=""):
    cfg.data["approval"] = {"approved_by": approved_by, "approved_on": _dt.date.today().isoformat(),
                            "rules_fingerprint": cfg.fingerprint(), "notes": notes}
    write_json(cfg.path, cfg.data)
    return cfg.data["approval"]


def _pct_text(rate):
    value = D(rate)
    text = f"{value:f}".rstrip("0").rstrip(".") if "." in f"{value:f}" else f"{value:f}"
    return f"{text}%"


def incentive_text(cfg, inc):
    """One plain-English sentence per incentive, the way an owner would say it."""
    noun = {"addons": "add-on", "services": "service", "sales": "sale"}[inc["source"]]
    if inc.get("credit") == "location":
        who = ", ".join(sorted({r["employee_id"] for r in inc.get("recipients", [])})) or "the named recipients"
    else:
        who = ", ".join(cfg.roles.get(r, {}).get("label", r) for r in inc.get("eligible_roles", [])) or "Anyone"
        if inc.get("eligible_employees"):
            who += " and " + ", ".join(inc["eligible_employees"])

    def target(r, plural=False):
        v = r.get("value", "")
        many = noun + "s" if plural else noun
        return {"code_prefix": f"{many} with a code starting {v}", "code": f"{v} {many}",
                "category": f"{v.replace('_', ' ')} {many}", "item_contains": f"{many} whose name contains '{v}'",
                "any": f"{many}"}[r["match"]]

    what = []
    for r in inc.get("rates", []):
        if inc.get("tiers"):
            what.append(target(r, plural=True))
        elif inc["kind"] == "per_unit":
            what.append(f"{fmt_money(r['rate'])} for each {target(r)}")
        else:
            what.append(f"{_pct_text(r['rate'])} of {target(r, plural=True)}")
        if r.get("only_employees"):
            what[-1] += f" (only {', '.join(r['only_employees'])})"
    if inc.get("tiers"):
        tiers = []
        for t in sorted(inc["tiers"], key=lambda t: D(t["from"])):
            rate = fmt_money(t["rate"]) + " each" if inc["kind"] == "per_unit" else _pct_text(t["rate"])
            tiers.append(f"{t['from']}{'-' + str(t['to']) if t.get('to') else '+'} at {rate}")
        how = "each tier pays only the units inside it" if inc.get("tier_method", "marginal") == "marginal" \
            else "every unit pays the highest tier reached"
        text = f"{inc.get('label', inc['id'])}: {who} earn on {' and '.join(what)}, tiered ({how}): {', '.join(tiers)}"
    else:
        text = f"{inc.get('label', inc['id'])}: {who} earn " + "; ".join(what)
    if inc.get("credit") == "location":
        text += ", counted on the whole location's total"
    text += ". " + ("Monthly, paid on the month-end run" if inc.get("frequency") == "monthly" else "Every pay period")
    if inc.get("exclude"):
        text += "; not counting " + ", ".join(f"{e['field'].replace('_', ' ')} {' or '.join(e['values'])}" for e in inc["exclude"])
    text += f". Pay type {inc.get('pay_code') or inc['id']}."
    if inc["kind"] == "per_unit" and inc["source"] == "addons":
        text += " Customer prices are never used, only these rates."
    return text
