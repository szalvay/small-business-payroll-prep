# HR and payroll system on-ramps

A connector profile is a JSON file that says how to read a system's exports (inbound)
and how to write its import files (outbound). Profiles ship in `assets/connectors/`:

| Profile | Inbound | Outbound |
|---|---|---|
| `bamboohr` | roster + pay rates, Time Off Used | Import Hours file (REG / OT / DT) + Extra Pay upload (dollar amounts) |
| `adp_wfn` | roster + pay rates, time off | Paydata batch (`EPI<co><nn>.csv`): Reg / O/T hours, Hours 3/4 and Earnings 3/4/5 code + amount pairs |
| `paylocity` | roster + pay rates, time off | Earnings import in the Det / Det Code layout |
| `hibob` | People data report, time off report | One-time payments (amounts); hours go to whichever provider actually pays them |
| `generic` | any CSV / XLSX with recognizable headers | One row per person, location and pay code |

`payroll.py profiles <workspace>` lists them, including workspace copies.

**Every profile is a starting template.** Import layouts vary by account and change
over time. Before the first live upload, download the import template from the owner's
own account, compare headers and order, and adjust a copy of the profile. Each profile
says this in its `status` field and lists practical notes in `docs`.

## Inbound: roster, rates and time off

```bash
payroll.py hris-import <period> --roster raw/roster.xlsx --time-off raw/time_off.csv
payroll.py hris-import <period> --profile generic --roster raw/people.csv --map job_title="Position Name"
```

- Columns are found by header aliases (`inbound.roster.columns`). Missing a required
  field (`employee_id`, `first_name`, `last_name`, `status`, `location`, `job_title`,
  `pay_rate`) is a FAIL naming the headers it saw; fix with `--map field=Header` or by
  adding the header to a workspace copy of the profile.
- **Roles** come from `roles[].hris_titles` in the config (exact title, or `re:<regex>`).
  An unmapped title is a FAIL; add the title to the right role.
- **Locations** come from `locations[].hris_labels`.
- **Status** values are mapped through `value_maps.status` (Active, Terminated, Leave...).
- **Pay rates** are parsed from text like `$17.00 USD per Hour` or `58,000 per Year`. The
  rate type follows the role's pay basis. A rate effective inside the period is a
  warning: add the earlier rate as a dated `employee_overrides` rate row.
- `employee_overrides[].rates` from the config are appended, so ramps and second-role
  rates live in one place.
- **Time off** rows are kept only inside the period; start/end ranges are spread over
  weekdays. Types are mapped through `type_map`.
- Everything the import did is written to `output/hris_import_report.md`. Read it.

## Outbound: the upload files

Set `systems.payroll` in the config. Each run writes every outbound export the profile
has (or those listed in `systems.payroll_exports`) to `output/`, and checks that the
files together carry exactly the exportable earnings.

Pay type names come from `pay_codes[].code`. They must match the payroll system's
earning names or codes exactly; one wrong character fails the upload or, worse, lands
on the wrong earning.

`export_as` decides what goes where:

- `hours`: sent as hours (regular, overtime, double time). The payroll system pays them
  at the rate it has on file. If someone earned hours at two base rates this period
  (a raise mid-period), the run warns that one rate on file cannot pay both.
- `amount`: sent as dollars (commissions, tips, spiffs, piece-rate pay, salary lines,
  premiums).
- `none`: shown in the workbook, left out of the upload. Use for time off when the
  payroll system already pays approved time off from its own records, so it is not paid
  twice.

Settings in `systems.payroll_settings`:

| Setting | Used by | Meaning |
|---|---|---|
| `split_by_location` | all | One line per location (department / cost center = `locations[].payroll_code`) |
| `co_code` | adp_wfn | Company code; required, and part of the file name |
| `batch_suffix` | adp_wfn | Two characters after the company code (default `01`) |
| `batch_id` | adp_wfn | Defaults to the pay date as YYMMDD |

## Customizing or adding a profile

Copy a profile to `<workspace>/connectors/<id>.json` and edit it there. A workspace
profile with the same `id` replaces the built-in one; a new `id` adds a profile.

Outbound layouts:

- `long`: one row per aggregated line. `columns` is a list of `[header, field]`. Fields:
  `employee_id`, `payroll_id`, `first_name`, `last_name`, `name`, `location_id`,
  `location_name`, `location_code`, `code`, `label`, `hours`, `hours_always`, `rate`,
  `amount`, `rate_type` (via `rate_type_map`), `det`, `blank`, `const:<text>`,
  `date:<period_start|period_end|pay_date>|<mdy|iso|ymd>`, `setting:<name>`.
  Options: `include` (`all`, `hours`, `amount`), `include_rate`, `include_header`,
  `delimiter` (`tab`), `filename` with `{period_end}`, `{pay_date}`, `{period_start}` or
  any setting name.
- `adp_epi`: ADP paydata batch; options `hours_slots`, `earnings_slots`,
  `regular_keys`, `overtime_keys`.

After editing, run a period and open the file next to the system's own template before
uploading. Upload to a test or preview batch first if the system offers one.
