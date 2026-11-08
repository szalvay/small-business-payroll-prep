#!/usr/bin/env python3
"""Generate the reference docs that must never drift from the code.

- references/questionnaire.md from assets/intake/questions.json (also the intake
  workbook's Questions tab)
- references/input-formats.md from spapay.inputs.SPEC

Edit the sources, then run:
    python3 tools/build_docs.py
"""
import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "salon-spa-payroll"
SRC = SKILL / "assets" / "intake" / "questions.json"
OUT = SKILL / "references" / "questionnaire.md"

HEADER = """# Intake questionnaire

<!-- Generated from assets/intake/questions.json by tools/build_docs.py. Edit the JSON, not this file. -->

This is the owner interview that turns how a business actually pays people into
`payroll_config.json`. The same questions appear on the Questions tab of the intake
workbook (`payroll.py intake-workbook`), so an owner can answer on paper instead.

## How to run the interview

- **One question at a time.** Ask, wait, then ask the next. Owners answer far better
  when they are not handed a wall of questions.
- **Skip what does not apply.** A single-location massage studio with no front desk
  skips half of this. Say which sections you are skipping and why.
- **Use their words, then confirm in yours.** After each section, read back what you
  heard as rules ("So: lobby time for massage therapists is paid at minimum wage, under
  the pay type Lobby. Right?"). Write the config only from confirmed answers.
- **Ask for documents when they exist.** An offer letter, a comp plan, a past payroll
  register or an import template beats memory. Read them and confirm what you found.
- **Never guess a rate, a threshold or a pay type name.** If the owner does not know,
  record it as an open item in `intake_notes` and leave the config value blank so the
  run stops and asks, instead of quietly paying the wrong amount.
- **Every special deal is a rule.** When the owner says "except for one person", stop and
  capture that exception as an override or a dated rate.
- **State rules are presets, not advice.** Load the state preset that fits, show the
  owner what it says, and ask them to confirm it with their payroll provider or counsel.
  Set `confirmed_by_owner` only when they say they have.
- **Finish with the Pay Rules Book.** Render it (`payroll.py rulebook`), walk the owner
  through every rule, fix what is wrong, and record their sign-off
  (`payroll.py approve --by "<name>"`). A run never shows ALL CLEAR on unsigned rules.

Each question below lists why it matters and where the answer lands (`maps_to`).

"""


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    lines = [HEADER]
    total = 0
    for sec in data["sections"]:
        lines.append(f"## {sec['title']}\n")
        if sec.get("intro"):
            lines.append(sec["intro"] + "\n")
        for q in sec["questions"]:
            total += 1
            lines.append(f"**{q['id']}** {q['q']}\n")
            lines.append(f"- Why: {q['why']}")
            lines.append(f"- Lands in: `{q['maps_to']}`")
            if q.get("follow_up"):
                lines.append(f"- Follow up: {q['follow_up']}")
            lines.append("")
    lines.append(f"_{total} questions in {len(data['sections'])} sections._\n")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({total} questions)")
    input_formats()


NOTES = {
    "roster": [
        "`status` is `active`, `terminated` or `leave`. Keep people who left during the period on the roster with their `termination_date`.",
        "`home_location` is a location id or any label from the config. Time off with no location is charged here.",
        "`pos_names` lists other spellings, separated by `;` (or keep them in the config under employee_overrides[].pos_names).",
    ],
    "pay_rates": [
        "One row per person per role. A raise mid-period is a second row with `effective_from`; days before it use the earlier row.",
        "`rate_type`: `service_hour`, `per_service`, `service_pct` (a percent: 40 = 40%), `hourly`, `salary_annual`, `salary_period`.",
    ],
    "time_entries": [
        "One row per person per day per kind of time. `category`: `worked`, `lobby`, `training`, `trainee`, `trainer`, `meeting`, `cleaning`, `travel`, `waiting`, `rest_recovery`, `other`.",
        "Export the time clock for exactly the pay period dates, never whole weeks: earlier days of a boundary week were paid last period, and the engine already knows them from history.",
        "For clocked piece-rate staff, non-service categories recorded inside a clocked shift are break-outs and are not counted twice.",
    ],
    "services": [
        "`service_hours` is actual service time from the service detail report. Never scheduled or bookable time.",
        "`category` routes the line to a role (see roles[].service_categories). `refund = Y` makes the row negative.",
        "`quantity` is the number of services. The run warns when hours per service look implausible (a swapped column).",
    ],
    "addons": [
        "`addon_code` may be `CODE: Description`; matching uses the part before the colon. `customer_price` is kept for reference only and never paid.",
    ],
    "sales": [
        "`category` is the program: `retail`, `membership`, `gift_card`, `package` or your own. `item_type` carries things like `new`, `renewal`, `transfer` for exclusions.",
        "`amount` is the dollar base for percent incentives. Never map a percent-of-sales column here.",
    ],
    "tips": [
        "`tip_type` is `card` or `cash`. Card tips are passed through in full and reconciled to the report total.",
    ],
    "time_off": [
        "`type`: `sick`, `pto`, `vacation`, `holiday`, `bereavement`, `jury_duty`, `unpaid`. Only rows inside the pay period.",
        "If nobody at a location took time off, record an attestation in period.json instead of leaving the file empty.",
    ],
    "adjustments": [
        "Every row names `approved_by`. Give `amount`, or `hours` and `rate`. `taxable = N` for reimbursements.",
        "Use a pay code of its own (e.g. `back_pay`, `signing_bonus`), not one that a reconciliation check sums.",
    ],
    "location_metrics": [
        "One row per location per metric, with the window it covers. Names match bonus_pools[].metrics numerator/denominator.",
    ],
}

TYPE_TEXT = {"str": "text", "date": "date", "dec": "number", "bool": "Y/N"}


def input_formats():
    sys.path.insert(0, str(SKILL / "scripts"))
    from spapay.inputs import DESCRIPTIONS, SPEC
    out = ["# Canonical input files", "",
           "<!-- Generated from spapay/inputs.py by tools/build_docs.py. Edit the code, not this file. -->", "",
           "Every POS, HR system and time clock exports differently. Each export is mapped into these plain",
           "CSV files in `periods/<period>/inputs/`, and the engine reads nothing else. One row is one fact;",
           "never pre-total by hand. `payroll.py templates <dir>` writes blank copies with the right headers.", "",
           "People can be identified by `employee_id` or by `employee_name` (any spelling on the roster or in",
           "`pos_names`). Locations can be a location id or any label in the config.", ""]
    for name, cols in SPEC.items():
        out += [f"## {name}.csv", "", DESCRIPTIONS.get(name, ""), "", "| Column | Type | Required |", "|---|---|---|"]
        for col, (kind, req) in cols.items():
            out.append(f"| `{col}` | {TYPE_TEXT.get(kind, kind)} | {'yes' if req else ''} |")
        if name in {"time_entries", "services", "addons", "sales", "tips", "time_off", "adjustments"}:
            out.append("")
            out.append("Give `employee_id` or `employee_name` on every row.")
        out.append("")
        out += [f"- {n}" for n in NOTES.get(name, [])]
        out.append("")
    path = SKILL / "references" / "input-formats.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
