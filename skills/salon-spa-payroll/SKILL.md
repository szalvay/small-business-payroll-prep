---
name: salon-spa-payroll
description: Prepare and check payroll for salons, spas, massage and wellness businesses, including multi-location ones. Handles piece-rate service pay, lobby and training time, add-on spiffs, retail, membership and gift card commissions, tips, sick time, weekly overtime across locations and pay periods, manager salaries, stipends and bonus pools, then writes import files for BambooHR, ADP Workforce Now, Paylocity, HiBob or a generic CSV. Use when someone wants to set up their pay rules, run or check a pay period from POS and HR exports, find payroll errors before payday, or build a payroll import file.
license: Apache-2.0
---

# Salon & Spa Payroll Prep

Catch the errors and omissions before payday.

This skill turns an owner's pay rules and their booking/POS and HR exports into a
checked payroll: a review workbook, an evidence trail, and upload files for their
payroll system. It never submits payroll. A person reviews and submits.

Everything runs through one command line tool in this skill's folder:

```bash
python3 scripts/payroll.py --help          # needs Python 3.10+ and openpyxl (pip install openpyxl)
```

Run it with the skill folder's absolute path when working elsewhere, for example
`python3 <skill-dir>/scripts/payroll.py run <period-folder>`.

## Ground rules (read these first)

1. **Only `payroll.py run` decides ALL CLEAR.** Exit 0 plus `output/evidence.json` with
   `"status": "ALL CLEAR"` is the only ALL CLEAR. Never describe a run as clean, done or
   ready from your own reading of numbers. Exit 2 is NOT CLEAR, exit 1 is BLOCKED.
2. **Never invent a rate, threshold, window or pay type name.** If the owner has not
   told you, leave it blank so the run stops and asks. A guessed number becomes a
   paycheck.
3. **The owner's signed rules are the law of the run.** Rule changes go into
   `payroll_config.json`, then the Pay Rules Book is re-rendered and re-approved.
   Never hand-edit a number in a workbook or an export file; fix the input or the rule
   and run again.
4. **A warning needs a decision.** Every WARN blocks ALL CLEAR until the input is fixed
   or someone records an acknowledgment in `period.json` (`acknowledged_warnings`, with
   who decided and why). Do not acknowledge on the owner's behalf; ask them.
5. **Not legal or tax advice.** State presets are starting points. Tell the owner to
   confirm overtime, minimum wage, sick pay, tip and final-pay rules with their payroll
   provider or employment counsel.
6. **Keep sensitive data out.** The engine needs names, IDs, rates and hours only. Never
   ask for or store Social Security numbers, bank details or dates of birth. If an export
   contains them, do not copy those columns anywhere.

## The workspace

```
<workspace>/
  payroll_config.json          the owner's rules (from the intake)
  PAY_RULES_BOOK.md / .html    the rules in plain English, with the owner's sign-off
  connectors/                  optional edited copies of HRIS / payroll profiles
  history/weeks.json           hours and overtime already paid, per workweek (written by runs)
  periods/<start>_<end>/
    period.json                dates, monthly window, windows, attestations, sources, acknowledgments
    raw/                       exports exactly as downloaded
    inputs/                    canonical CSVs the engine reads
    output/                    review workbook, upload files, run summary, evidence.json
```

Try the made-up sample first if the owner wants to see it work:
`payroll.py sample ./demo`, then `approve ./demo --by "<name>"`, `hris-import` and `run`
for each period in `demo/periods/` (see `references/getting-started.md`).

## What the owner wants decides the mode

### 1. Set up (intake)

The owner has no `payroll_config.json` yet, or wants to change how people are paid.

1. Ask how they want to answer: an interview with you, or the fillable intake workbook
   (`payroll.py intake-workbook intake.xlsx`, then `compile-intake intake.xlsx payroll_config.json`).
2. For the interview, follow `references/questionnaire.md`: one question at a time,
   skip what does not apply, read back each section as rules before writing anything.
3. Write the config following `references/config-reference.md`. Start from
   `payroll.py init <workspace>`. Load state presets from `assets/states/` and have the
   owner confirm them (`references/state-rules.md`).
4. `payroll.py validate <workspace>` until it says VALID.
5. `payroll.py rulebook <workspace>`, walk the owner through every rule ID, fix, re-render.
6. When the owner agrees, `payroll.py approve <workspace> --by "<owner name>"`.

### 2. Start a pay period

`payroll.py new-period <workspace> --start YYYY-MM-DD --end YYYY-MM-DD --pay-date YYYY-MM-DD`
(add `--monthly --month-start ... --month-end ...` on the run that pays monthly incentives).
It prints the workweeks the period touches, boundary-week warnings and the export
checklist from `systems.pos_reports`. Give the owner that checklist.

### 3. Turn exports into inputs

- HR roster, pay rates and time off: `payroll.py hris-import <period> --roster <file>
  --time-off <file>` using the profile in `systems.hris` (`references/hris-connectors.md`).
  Read `output/hris_import_report.md`; fix FAILs with `--map field=Header` or by editing
  a copy of the profile in `<workspace>/connectors/`.
- POS reports: map each one into the canonical CSVs (`references/input-formats.md`,
  `references/pos-mapping.md`). Map by header text, never by column position. Record
  every report in `period.json` `sources` with its own printed totals, so the run can
  prove nothing was dropped or doubled.
- If an input genuinely has nothing this period (nobody took time off at a location),
  record an attestation in `period.json` instead of an empty file.

Then `payroll.py check <period>`: READY TO RUN, or the exact FAILs to fix.

### 4. Run

`payroll.py run <period>`. It runs the gates, calculates, reconciles every input total
to what was paid, recomputes everything independently (audit), compares with the last
period, writes the payroll files, and prints ALL CLEAR, NOT CLEAR or BLOCKED.

- **BLOCKED:** nothing was calculated. Fix the FAIL lines (usually an input problem) and
  run again.
- **NOT CLEAR:** read the reasons. Fix inputs or rules; for a warning the owner accepts,
  add their acknowledgment to `period.json`. Run again.
- **ALL CLEAR:** send the owner `output/payroll_review_<date>.xlsx`, `run_summary.html`
  and the upload file(s). Point out anything in Findings and Incentive Notes they should
  know. The owner reviews and uploads; you do not.

For high-stakes runs (first live period, a new location, a rules change) have a
separate agent review the outputs with `references/auditor.md` before handing over.

### 5. Change a rule

Edit `payroll_config.json`, `validate`, re-render the rulebook, get the owner's
approval again (`approve`), then re-run the period. The fingerprint in the rulebook
changes with every rule change, so stale approvals are caught automatically.

## Where to look

| Need | File |
|---|---|
| Interview questions, in order, with why each matters | `references/questionnaire.md` |
| Every config field | `references/config-reference.md` |
| The canonical CSV inputs | `references/input-formats.md` |
| Mapping POS reports (and known report pitfalls) | `references/pos-mapping.md` |
| HR and payroll system on-ramps | `references/hris-connectors.md` |
| State presets and what to confirm | `references/state-rules.md` |
| Why each gate and check exists | `references/lessons.md` |
| Independent review brief | `references/auditor.md` |
| First-time walkthrough with the sample | `references/getting-started.md` |
