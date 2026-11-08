# Getting started with the sample spa

The sample is Willowbrook Spa Co., a made-up business with three locations in two
states, sixteen people and two October 2026 pay periods. Every name, rate and minimum
wage in it is fictional. It exercises the hard cases: a dual-role provider, a raise in
the middle of a period, a new hire and a departure, front desk overtime across two
locations and across two pay periods, tiered membership commission, a seasonal gift
card window, a manager override, a stipend and a scorecard bonus pool.

```bash
P=<skill-dir>/scripts/payroll.py
python3 $P sample ./demo                                   # copy the sample workspace
python3 $P validate ./demo                                 # VALID, not yet approved
python3 $P rulebook ./demo                                 # read demo/PAY_RULES_BOOK.html
python3 $P approve ./demo --by "Your Name"                 # sign the rules

for p in 2026-10-01_2026-10-15 2026-10-16_2026-10-31; do
  python3 $P hris-import demo/periods/$p \
    --roster demo/periods/$p/raw/bamboohr_roster_export.csv \
    --time-off demo/periods/$p/raw/bamboohr_time_off_used.csv
  python3 $P run demo/periods/$p
done
```

Run the periods in order: the second one needs the first one's hours for the
boundary week of October 11. The first period starts on a Thursday, so its first
workweek began in September before this tool was in use; its `period.json` shows the
owner's acknowledgment of that (`GATE_HISTORY_GAP`), which is what a real first period
looks like.

The `raw/` folders hold report-style exports (service and add-on detail per location)
next to the mapped `inputs/` CSVs, so you can see what the mapping step turns into what,
and how each report's grand total is recorded in `period.json` `sources`.

What to look at in `demo/periods/2026-10-16_2026-10-31/output/`:

- `run_summary.html`: the one-page result.
- `payroll_review_2026-10-31.xlsx`:
  - **Overtime:** Ella Brooks's boundary week, with hours from the first period carried in.
  - **Earnings Lines:** Grace Kim's service pay at two rates.
  - **Findings:** the gift card sale outside the holiday window, acknowledged by the owner in `period.json`.
  - **Incentive Notes:** the add-ons and sales nobody was paid for, and why.
- `bamboohr_import_hours_2026-10-31.csv` and `bamboohr_extra_pay_2026-10-31.csv`: the
  upload files.

Then try breaking it. Each of these should stop the run or turn it NOT CLEAR:

- Delete `inputs/time_off.csv` in either period.
- Change a `service_hours` value in `inputs/services.csv` (the report totals in
  `period.json` no longer match).
- Add an add-on row with a code nobody has a rate for. The run first stops because the
  add-on report's total in `period.json` no longer matches; raise that total by one and
  it runs, then turns NOT CLEAR until the code gets a rate.
- Change any rate in `payroll_config.json` without approving again.
- Remove the `acknowledged_warnings` entry from the second period.

## Starting a real workspace

```bash
python3 $P init ./my-spa --name "My Spa"
python3 $P intake-workbook ./my-spa/intake.xlsx      # or do the interview with Claude
```

Then follow SKILL.md: intake, validate, rulebook, approve, then one folder per pay
period with `new-period`.
