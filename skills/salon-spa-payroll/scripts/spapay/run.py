"""One pay run: gates -> calculation -> checks -> independent audit -> outputs.

Only this module may print ALL CLEAR, and only with an evidence file behind it.
Exit codes: 0 ALL CLEAR, 1 BLOCKED (fix inputs/rules first), 2 NOT CLEAR (built, needs review).
"""
from __future__ import annotations

import csv
import datetime as _dt
from collections import defaultdict
from pathlib import Path

from . import __version__
from .audit import audit
from .calc import calculate
from .checks import run_checks
from .config import load_config, validate_config
from .connectors import export_payroll, load_profile
from .gates import run_gates
from .inputs import load_inputs
from .period import CONFIG_NAME, History, Period, find_workspace
from .report import write_summary
from .util import D, ZERO, Findings, file_sha256, fmt_money, money, write_json
from .workbook import build_workbook


def run_period(period_dir, write_history=True, draft=False):
    period = Period(period_dir)
    workspace = find_workspace(period.dir)
    cfg = load_config(workspace / CONFIG_NAME)
    findings = Findings()
    findings.extend(validate_config(cfg))
    period.output_dir.mkdir(parents=True, exist_ok=True)

    inputs, in_findings = load_inputs(period, cfg)
    findings.extend(in_findings)
    if not findings.has_fail:
        findings.extend(run_gates(cfg, period, inputs))
    if findings.has_fail:
        status = "BLOCKED"
        _write_blocked(period, cfg, findings)
        return {"status": status, "exit": 1, "findings": findings, "period": period, "cfg": cfg}

    history = History(workspace)
    result = calculate(cfg, period, inputs, history)
    findings.extend(result.findings)
    checks = run_checks(cfg, period, inputs, result)
    audit_result = audit(cfg, period, inputs, result)
    _anomalies(workspace, period, inputs, result, cfg, findings)

    exports, export_findings = [], Findings()
    systems = cfg.data.get("systems", {})
    profile_id = systems.get("payroll") or "generic"
    try:
        profile = load_profile(profile_id, workspace)
        wanted = systems.get("payroll_exports") or [o["id"] for o in profile.get("outbound", [])]
        for export_id in wanted:
            path, summary, ef = export_payroll(profile, export_id, cfg, period, inputs, result.lines)
            exports.append(summary)
            export_findings.extend(ef)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        export_findings.fail("EXPORT", f"payroll export failed: {exc}")
    findings.extend(export_findings)

    earnings_total = sum((l["amount"] for l in result.lines if l["kind"] != "memo"), ZERO)
    exported_expected = sum((l["amount"] for l in result.lines
                             if (cfg.pay_codes.get(l["pay_code"]) or {}).get("export_as", "amount") != "none"), ZERO)
    exported = sum((ex["grand_total"] for ex in exports), ZERO)
    if exports:
        variance = (exported - exported_expected).quantize(D("0.01"))
        checks.append({"check": "Upload files carry every exportable dollar", "location_id": "*",
                       "input_total": money(exported_expected), "paid_total": money(exported), "variance": variance,
                       "status": "PASS" if abs(variance) <= D("0.05") else "FAIL",
                       "note": "" if abs(variance) <= D("0.05") else "an export filter dropped or doubled something"})

    open_warnings = _acknowledge(period, findings)
    reasons = []
    if open_warnings:
        reasons.append(f"{len(open_warnings)} warning(s) need a decision: fix the input, or acknowledge each one in "
                       "period.json acknowledged_warnings with who decided and why")
    if findings.has_fail:
        reasons.append("calculation or export findings marked FAIL")
    if any(c["status"] == "FAIL" for c in checks):
        reasons.append("a reconciliation check failed")
    if audit_result["status"] != "PASS":
        reasons.append("the independent audit disagrees with the engine")
    if not cfg.approved and not draft:
        reasons.append("the owner has not signed off the current Pay Rules Book")
    status = "ALL CLEAR" if not reasons else "NOT CLEAR"

    stamp = period.end.isoformat()
    wb_path = period.output_dir / f"payroll_review_{stamp}.xlsx"
    build_workbook(wb_path, cfg, period, inputs, result, checks, audit_result, findings, status, exports)
    _employee_totals(period, result)
    evidence = {
        "status": status, "reasons": reasons, "engine_version": __version__,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "period": period.id, "pay_date": period.pay_date, "config_fingerprint": cfg.fingerprint(),
        "rules_approved": cfg.approved, "earnings_total": str(money(earnings_total)),
        "people_paid": len({l["employee_id"] for l in result.lines}),
        "checks": [{k: (str(v) if not isinstance(v, str) else v) for k, v in c.items()} for c in checks],
        "audit_status": audit_result["status"], "audit_mismatches": len(audit_result["mismatches"]),
        "findings": {s: len(findings.of(s)) for s in ("FAIL", "WARN", "INFO")},
        "warnings_acknowledged": [{"code": i["code"], "message": i["message"], "by": i["acknowledged"]}
                                  for i in findings.of("WARN") if i.get("acknowledged")],
        "inputs": {name: file_sha256(path) for name, path in inputs.files.items()},
        "outputs": {"workbook": str(wb_path.name), "exports": [Path(e["file"]).name for e in exports]},
    }
    write_json(period.output_dir / "evidence.json", evidence)
    write_summary(period, cfg, status, reasons, result, checks, audit_result, findings, exports, earnings_total)
    if write_history:
        history.record(period.id, result.history_days, result.history_weeks)
    return {"status": status, "exit": 0 if status == "ALL CLEAR" else 2, "findings": findings, "result": result,
            "checks": checks, "audit": audit_result, "exports": exports, "period": period, "cfg": cfg,
            "workbook": wb_path, "earnings_total": earnings_total, "reasons": reasons}


# Warnings handled by their own reason (the rules sign-off) rather than per-period acknowledgment.
SELF_REPORTING = {"CFG_NOT_APPROVED", "CFG_APPROVAL_STALE"}


def _acknowledge(period, findings):
    """A WARN blocks ALL CLEAR until someone decides it is fine. Returns the open ones."""
    used = set()
    open_items = []
    for item in findings.of("WARN"):
        if item["code"] in SELF_REPORTING:
            continue
        for i, ack in enumerate(period.acknowledged):
            if ack.get("code") != item["code"]:
                continue
            if ack.get("match") and ack["match"].lower() not in item["message"].lower():
                continue
            item["acknowledged"] = f"{ack.get('by', '?')}: {ack.get('note', '')}".strip()
            used.add(i)
            break
        else:
            open_items.append(item)
    for i, ack in enumerate(period.acknowledged):
        if i not in used:
            findings.info("ACK_UNUSED", f"acknowledged_warnings entry {ack.get('code')} / {ack.get('match', '*')!r} matched no "
                          "warning this run; remove it so it cannot hide a future one")
    return open_items


def _write_blocked(period, cfg, findings):
    lines = [f"# BLOCKED: {cfg.company.get('name', '')} {period.start} to {period.end}", "",
             "Nothing was calculated. Fix these first:", ""]
    for i in findings.of("FAIL"):
        lines.append(f"- **{i['code']}** {i['message']}")
    if findings.of("WARN"):
        lines += ["", "Warnings:", ""] + [f"- {i['message']}" for i in findings.of("WARN")]
    (period.output_dir / "run_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(period.output_dir / "evidence.json", {"status": "BLOCKED", "period": period.id,
               "fails": [i["message"] for i in findings.of("FAIL")]})


def _employee_totals(period, result):
    totals = defaultdict(lambda: {"gross": ZERO, "hours": ZERO, "name": ""})
    for l in result.lines:
        t = totals[l["employee_id"]]
        t["name"] = l["employee"]
        if l["kind"] != "memo":
            t["gross"] += l["amount"]
        if l["pay_code"] in ("service_wages", "service_per_unit", "service_commission", "regular", "overtime", "doubletime"):
            t["hours"] += l["hours"] or ZERO
    with open(period.output_dir / "employee_totals.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["employee_id", "name", "gross", "hours"])
        for emp, t in sorted(totals.items()):
            w.writerow([emp, t["name"], f"{money(t['gross'])}", f"{t['hours']:.2f}"])


def _anomalies(workspace, period, inputs, result, cfg, findings):
    """Compare with the most recent earlier period's employee_totals.csv."""
    prior = None
    for pdir in sorted((workspace / "periods").glob("*")):
        f = pdir / "output" / "employee_totals.csv"
        try:
            end = _dt.date.fromisoformat(pdir.name.split("_")[1])
        except (IndexError, ValueError):
            continue
        if end < period.start and f.exists():
            prior = f
    if prior is None:
        findings.info("ANOMALY_NONE", "no earlier period output found; nothing to compare against")
        return
    threshold = D(cfg.checks.get("plausibility", {}).get("anomaly_threshold", "0.25"))
    before = {}
    with open(prior, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            before[row["employee_id"]] = (row["name"], D(row["gross"]), D(row["hours"]))
    now = defaultdict(lambda: ZERO)
    for l in result.lines:
        if l["kind"] != "memo":
            now[l["employee_id"]] += l["amount"]
    for emp_id, (name, gross, _) in before.items():
        emp = inputs.employees.get(emp_id)
        if emp_id not in now and emp and emp.status == "active":
            findings.warn("ANOMALY_MISSING", f"{name} was paid {fmt_money(gross)} last period and nothing this period while still active")
        elif emp_id in now and gross > 0:
            change = (now[emp_id] - gross) / gross
            if abs(change) > threshold:
                findings.info("ANOMALY_CHANGE", f"{name}: gross {fmt_money(gross)} -> {fmt_money(now[emp_id])} ({change:+.0%})")
    for emp_id in now:
        if emp_id not in before:
            findings.info("ANOMALY_NEW", f"{inputs.employees[emp_id].name} is paid for the first time compared with last period")
