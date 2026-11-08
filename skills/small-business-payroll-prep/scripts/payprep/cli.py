"""Command line for the payroll engine. Run `python3 payroll.py --help`."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import sys
from pathlib import Path

from .config import load_config, validate_config
from .period import CONFIG_NAME, Period, find_workspace, new_period
from .util import fmt_money, workweeks

ASSETS = Path(__file__).resolve().parents[2] / "assets"


def _print_findings(findings, limit=200):
    order = {"FAIL": 0, "WARN": 1, "INFO": 2}
    for i in sorted(findings.items, key=lambda i: order[i["severity"]])[:limit]:
        ack = f"  [acknowledged: {i['acknowledged']}]" if i.get("acknowledged") else ""
        print(f"  {i['severity']:<4} {i['code']}: {i['message']}{ack}")


def _config_path(target):
    p = Path(target)
    if p.is_file():
        return p
    return find_workspace(p) / CONFIG_NAME


def cmd_init(a):
    ws = Path(a.workspace)
    ws.mkdir(parents=True, exist_ok=True)
    dest = ws / CONFIG_NAME
    if dest.exists() and not a.force:
        print(f"{dest} already exists (use --force to overwrite)")
        return 1
    data = json.loads((ASSETS / "templates" / "starter_config.json").read_text())
    if a.name:
        data["company"]["name"] = a.name
    dest.write_text(json.dumps(data, indent=2) + "\n")
    print(f"wrote {dest}; next: fill it in through the intake (interview or intake workbook)")
    return 0


def cmd_validate(a):
    cfg = load_config(_config_path(a.target))
    f = validate_config(cfg)
    _print_findings(f)
    print(f"{'INVALID' if f.has_fail else 'VALID'}: {len(f.of('FAIL'))} fail, {len(f.of('WARN'))} warn; "
          f"fingerprint {cfg.fingerprint()}; approved={cfg.approved}")
    return 1 if f.has_fail else 0


def cmd_rulebook(a):
    from .rulebook import render
    path = _config_path(a.target)
    cfg = load_config(path)
    md = path.parent / "PAY_RULES_BOOK.md"
    html = path.parent / "PAY_RULES_BOOK.html"
    fp = render(cfg, md, html)
    print(f"wrote {md} and {html} (fingerprint {fp})")
    return 0


def cmd_approve(a):
    from .rulebook import approve, render
    path = _config_path(a.target)
    cfg = load_config(path)
    f = validate_config(cfg)
    if f.has_fail:
        _print_findings(f)
        print("cannot approve rules that do not validate")
        return 1
    appr = approve(cfg, a.by, a.notes or "")
    render(load_config(path), path.parent / "PAY_RULES_BOOK.md", path.parent / "PAY_RULES_BOOK.html")
    print(f"approved by {appr['approved_by']} on {appr['approved_on']} (fingerprint {appr['rules_fingerprint']})")
    return 0


def cmd_new_period(a):
    ws = find_workspace(Path(a.workspace))
    cfg = load_config(ws / CONFIG_NAME)
    mw = {"start": a.month_start, "end": a.month_end} if a.month_start and a.month_end else None
    if a.monthly and mw is None:
        end = _dt.date.fromisoformat(a.end)
        first = end.replace(day=1)
        last = (first.replace(day=28) + _dt.timedelta(days=4)).replace(day=1) - _dt.timedelta(days=1)
        mw = {"start": first.isoformat(), "end": last.isoformat()}
        print(f"monthly window set to the calendar month {mw['start']}..{mw['end']} (use --month-start/--month-end to change)")
    pdir = new_period(ws, a.start, a.end, a.pay_date, a.monthly, mw)
    from .inputs import write_templates
    write_templates(pdir / "inputs")
    p = Period(pdir)
    weeks = workweeks(p.start, p.end, cfg.workweek_start)
    print(f"created {pdir}")
    print(f"workweeks touched ({cfg.workweek_start}-start): " + ", ".join(w.isoformat() for w in weeks))
    if weeks and weeks[0] < p.start:
        print(f"  boundary week {weeks[0]}: export time ONLY for {p.start} onward; earlier days were paid last period")
    if weeks and weeks[-1] + _dt.timedelta(days=6) > p.end:
        print(f"  boundary week {weeks[-1]}: export time ONLY through {p.end}")
    pos = cfg.data.get("systems", {}).get("pos_reports", [])
    if pos:
        print("\nexport checklist (from config.systems.pos_reports):")
        for r in pos:
            if r.get("frequency") == "monthly" and not a.monthly:
                continue
            print(f"  [ ] {r.get('report')}  -> inputs/{r.get('maps_to')}.csv   {r.get('filters', '')}")
    print("\ndrop raw exports in raw/, map them into inputs/*.csv, record each in period.json sources, then run `check`")
    return 0


def cmd_templates(a):
    from .inputs import write_templates
    d = write_templates(a.directory)
    print(f"wrote blank input templates to {d}")
    return 0


def cmd_hris_import(a):
    from .connectors import import_hris, load_profile
    period = Period(a.period_dir)
    ws = find_workspace(period.dir)
    cfg = load_config(ws / CONFIG_NAME)
    profile = load_profile(a.profile or cfg.data.get("systems", {}).get("hris") or "generic", ws)
    overrides = {"roster": {}, "time_off": {}}
    for m in a.map or []:
        field, header = m.split("=", 1)
        target = "time_off" if field.startswith("time_off.") else "roster"
        overrides[target][field.split(".", 1)[-1]] = header
    f = import_hris(profile, cfg, period, a.roster, a.time_off, overrides)
    _print_findings(f)
    print(f"see {period.output_dir / 'hris_import_report.md'}")
    return 1 if f.has_fail else 0


def cmd_check(a):
    from .gates import run_gates
    from .inputs import load_inputs
    period = Period(a.period_dir)
    cfg = load_config(find_workspace(period.dir) / CONFIG_NAME)
    f = validate_config(cfg)
    inputs, fi = load_inputs(period, cfg)
    f.extend(fi)
    if not fi.has_fail:
        f.extend(run_gates(cfg, period, inputs))
    _print_findings(f)
    print("READY TO RUN" if not f.has_fail else "BLOCKED: fix the FAIL lines above")
    return 1 if f.has_fail else 0


def cmd_run(a):
    from .run import run_period
    out = run_period(a.period_dir, write_history=not a.no_history, draft=a.draft)
    _print_findings(out["findings"], limit=60)
    period = out["period"]
    print()
    if out["status"] == "BLOCKED":
        print(f"BLOCKED. Nothing calculated. See {period.output_dir / 'run_summary.md'}")
        return 1
    failed = [c for c in out["checks"] if c["status"] == "FAIL"]
    print(f"{out['status']}: gross {fmt_money(out['earnings_total'])}, {len(out['checks']) - len(failed)}/{len(out['checks'])} checks pass, "
          f"audit {out['audit']['status']}")
    for r in out["reasons"]:
        print(f"  - {r}")
    print(f"review workbook: {out['workbook']}")
    for ex in out["exports"]:
        print(f"payroll file:    {ex['file']}")
    return out["exit"]


def cmd_profiles(a):
    from .connectors import list_profiles
    ws = None
    if a.workspace:
        try:
            ws = find_workspace(Path(a.workspace))
        except FileNotFoundError:
            ws = None
    for pid, info in list_profiles(ws).items():
        print(f"{pid:<12} {info['name']:<22} {info['path']}")
    return 0


def cmd_intake_workbook(a):
    from .intake import build_intake_workbook
    cfg = load_config(a.from_config) if a.from_config else None
    try:
        path = build_intake_workbook(a.output, cfg, a.industry)
    except ValueError as e:
        print(e)
        return 1
    print(f"wrote {path}")
    return 0


def cmd_compile_intake(a):
    from .intake import compile_intake
    data, findings = compile_intake(a.workbook)
    out = Path(a.output)
    if out.exists() and not a.force:
        print(f"{out} exists (use --force)")
        return 1
    out.write_text(json.dumps(data, indent=2) + "\n")
    from .config import Config
    vf = validate_config(Config(data, out))
    findings.extend(vf)
    _print_findings(findings)
    print(f"wrote {out}: {'has FAILs to fix' if findings.has_fail else 'valid'}")
    return 1 if findings.has_fail else 0


def cmd_sample(a):
    dest = Path(a.destination)
    if dest.exists() and any(dest.iterdir()):
        print(f"{dest} is not empty")
        return 1
    if a.kind == "retail":
        from .sample_retail import build_retail_sample
        build_retail_sample(dest)
        roster, time_off, what = "adp_worker_export.csv", "adp_time_off.csv", "the sample retail workspace (three stores, two states)"
    else:
        from .sample import build_sample
        build_sample(dest)
        roster, time_off, what = "bamboohr_roster_export.csv", "bamboohr_time_off_used.csv", "the sample spa workspace (three locations, two states)"
    print(f"built {what} in {dest}. Next, as in references/getting-started.md:\n"
          f"  approve {dest} --by \"Your Name\"\n"
          f"  then for each folder in {dest}/periods, oldest first: hris-import <period> --roster <period>/raw/{roster} "
          f"--time-off <period>/raw/{time_off}, then run <period>")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="payroll.py", description="Payroll Prep for Small Businesses: rules in, checked payroll out.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="start a workspace with a starter config")
    s.add_argument("workspace"); s.add_argument("--name"); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("validate", help="check the config")
    s.add_argument("target", help="workspace folder or payroll_config.json"); s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("rulebook", help="render the Pay Rules Book (markdown + branded HTML)")
    s.add_argument("target"); s.set_defaults(fn=cmd_rulebook)
    s = sub.add_parser("approve", help="record the owner's sign-off of the current rules")
    s.add_argument("target"); s.add_argument("--by", required=True); s.add_argument("--notes"); s.set_defaults(fn=cmd_approve)
    s = sub.add_parser("new-period", help="create a pay period folder and print the export checklist")
    s.add_argument("workspace"); s.add_argument("--start", required=True); s.add_argument("--end", required=True)
    s.add_argument("--pay-date"); s.add_argument("--monthly", action="store_true",
                   help="month-end run: pay monthly incentives (window defaults to the calendar month of --end)")
    s.add_argument("--month-start"); s.add_argument("--month-end"); s.set_defaults(fn=cmd_new_period)
    s = sub.add_parser("templates", help="write blank canonical input CSVs")
    s.add_argument("directory"); s.set_defaults(fn=cmd_templates)
    s = sub.add_parser("hris-import", help="turn an HRIS roster / time-off export into canonical inputs")
    s.add_argument("period_dir"); s.add_argument("--profile"); s.add_argument("--roster"); s.add_argument("--time-off")
    s.add_argument("--map", action="append", help="field=Header override, e.g. job_title='Position Name' or time_off.hours=Used")
    s.set_defaults(fn=cmd_hris_import)
    s = sub.add_parser("check", help="run the input gates only")
    s.add_argument("period_dir"); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("run", help="full run: gates, pay, checks, audit, workbook, payroll files")
    s.add_argument("period_dir"); s.add_argument("--draft", action="store_true", help="allow unsigned rules (never ALL CLEAR otherwise)")
    s.add_argument("--no-history", action="store_true"); s.set_defaults(fn=cmd_run)
    s = sub.add_parser("profiles", help="list HRIS / payroll connector profiles")
    s.add_argument("workspace", nargs="?"); s.set_defaults(fn=cmd_profiles)
    s = sub.add_parser("intake-workbook", help="write the fillable intake workbook (blank or pre-filled from a config)")
    s.add_argument("output"); s.add_argument("--from-config")
    s.add_argument("--industry", help="only the questions for this industry (technology, entertainment, healthcare, manufacturing, financial_services, energy_utilities, retail, education, government, other)")
    s.set_defaults(fn=cmd_intake_workbook)
    s = sub.add_parser("compile-intake", help="turn a filled intake workbook into payroll_config.json")
    s.add_argument("workbook"); s.add_argument("output"); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_compile_intake)
    s = sub.add_parser("sample", help="build a made-up sample business to try everything end to end")
    s.add_argument("destination")
    s.add_argument("--kind", choices=["spa", "retail"], default="spa", help="spa (piece rate, add-ons, memberships) or retail (hourly, sales commission, daily overtime)")
    s.set_defaults(fn=cmd_sample)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
