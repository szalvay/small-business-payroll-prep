# payroll_config.json reference

The config is the owner's pay rules in machine form. `payroll.py validate` checks it;
`payroll.py rulebook` renders it as the Pay Rules Book the owner signs. A complete,
working example is `assets/sample_workspace/payroll_config.json`.

Conventions:

- Money, rates, hours and thresholds are strings of numbers (`"17.50"`), so nothing is
  lost to floating point. Plain numbers are accepted too.
- Dates are `YYYY-MM-DD`.
- **Percent rates are written as percents**: `"10"` is 10%, `"1"` is 1%, `"0.5"` is half a
  percent. Validation fails above 100 and warns below 1.
- IDs (locations, roles, incentives, pools) are short, stable, and never reused.

## company

| Field | Values | Meaning |
|---|---|---|
| `name` | text | Business name shown on every output |
| `pay_frequency` | `weekly`, `biweekly`, `semi_monthly`, `monthly` | Sets salary per period (52, 26, 24, 12 a year) |
| `workweek_start` | `sunday` ... `saturday` | The fixed 7-day week overtime is judged on |
| `ot_aggregation` | `employer` (default), `location` | Add hours across all locations of the same employer, or keep each location separate |
| `min_wage_makeup` | `flag` (default), `auto` | A workweek under minimum wage stops the run (`flag`) or gets a make-up line (`auto`) |
| `cash_tips` | `report_only` (default), `pay` | Declared cash tips are memo lines, or paid as earnings |
| `notes` | text | Anything worth keeping with the rules |

## approval

Written by `payroll.py approve --by "<name>"`: `approved_by`, `approved_on`, `notes`,
`rules_fingerprint`. The fingerprint is a hash of every other section; any rule change
makes the approval stale and the run NOT CLEAR until the owner approves again. Never
edit this block by hand.

## systems

| Field | Meaning |
|---|---|
| `hris` | Profile used by `hris-import` (`bamboohr`, `hibob`, `paylocity`, `adp_wfn`, `generic`, or a workspace profile) |
| `payroll` | Profile used for the upload files |
| `payroll_exports` | Optional list of outbound export ids to write (default: all the profile has) |
| `payroll_settings` | Settings the profile needs, e.g. `split_by_location`, `co_code`, `batch_suffix`, `reviewer`, `submitter` |
| `pos` | Name of the booking/POS system (documentation) |
| `pos_reports` | The export checklist: `report`, `maps_to` (input file), `filters`, `frequency` (`pay_period` or `monthly`) |

## employers

`[{"id": "E1", "legal_name": "Example Spa LLC"}]`. Each location names its employer.
Overtime adds hours across locations of the same employer.

## locations

| Field | Meaning |
|---|---|
| `id` | Short code used everywhere (`DT`) |
| `name`, `city`, `state` | `state` picks the `state_rules` entry |
| `employer_id` | Which employer runs it |
| `min_wage` | List of `{"rate", "effective_from"}`. Add the next increase as soon as it is known |
| `pos_labels` | Every way the POS names this location (name, store number) |
| `hris_labels` | Every way the HR system names it |
| `payroll_code` | Department / cost center code for the upload file |

## state_rules

Keyed by state code. Load presets from `assets/states/` (see `state-rules.md`).

| Field | Meaning |
|---|---|
| `weekly_ot_threshold` | Usually `"40"` |
| `daily_ot` | `null`, or `{"threshold": "8", "double_threshold": "12"}` |
| `seventh_day_ot` | `true` where the seventh consecutive day has special overtime |
| `piece_rate_nonproductive_separate` | `true` where piece-rate staff must be paid separately for time between clients |
| `confirmed_by_owner` | Set `true` only after the owner confirms with their provider or counsel. Unconfirmed is a warning on every run |
| `notes` | Source and caveats |

## roles

| Field | Values | Meaning |
|---|---|---|
| `id`, `label` | | |
| `pay_basis` | `piece_service_hour`, `piece_per_service`, `service_revenue_pct`, `hourly`, `salary` | How the main pay is figured |
| `hours_worked_source` | `services_plus_time`, `clock` | Hours for overtime and minimum wage: service hours plus recorded non-service time, or the time clock |
| `service_categories` | list | Service categories this role performs; routes dual-role services |
| `tips` | bool | Role receives tips (a tipped role with no tips file stops the run) |
| `exempt` | bool | Salaried and exempt from overtime |
| `hris_titles` | list | HR job titles that mean this role; `"re:<regex>"` allowed |

Rate types in `pay_rates.csv` must fit the basis: `service_hour`, `per_service`,
`service_pct` (a percent, `"40"` = 40%), `hourly`, `salary_annual` or `salary_period`.

Which engine pay types each basis produces (each needs a processor code in `pay_codes`):

| pay_basis | Pay types |
|---|---|
| `piece_service_hour` | `service_wages`, plus `ot_premium` for overtime |
| `piece_per_service` | `service_per_unit`, plus `ot_premium` |
| `service_revenue_pct` | `service_commission`, plus `ot_premium` |
| `hourly` | `regular`, `overtime` (and `doubletime` in daily-overtime states), plus `ot_premium` when incentives raise the regular rate |
| `salary` | `salary` |

Roles with `tips: true` produce `card_tips` (and `cash_tips` when cash tips are recorded).
`min_wage_makeup` appears when `company.min_wage_makeup` is `auto`, and
`nonproductive_time` in states with `piece_rate_nonproductive_separate`. `validate` fails
until every pay type the rules can produce has a non-blank `code`.

For piece-rate or commission roles whose hours come from the clock
(`hours_worked_source: clock`), `worked` time with no `time_pay` rule counts as hours
worked for overtime and minimum wage but is not paid on its own: their pay comes from
services. Add a `worked` rule only if you really pay clock time on top of services.

## time_pay

How each kind of recorded non-service time is paid, per role (`"*"` = any role).

`{"role": "massage_therapist", "category": "lobby", "basis": "min_wage", "pay_code": "lobby"}`

- `category`: `worked`, `lobby`, `training`, `trainee`, `trainer`, `meeting`, `cleaning`,
  `travel`, `waiting`, `rest_recovery`, `other`
- `basis`: `min_wage` (the location's), `base_rate` (the person's rate), `fixed`
  (with `fixed_rate`), `regular_rate` (that week's average hourly earnings, for paid rest
  periods), `unpaid`
- A kind of time with no rule stops the run. Hourly roles default to `base_rate` /
  `regular`.

## time_off_pay

Same shape with `type` instead of `category`: `sick`, `pto`, `vacation`, `holiday`,
`bereavement`, `jury_duty`, `unpaid`. `regular_rate` pays the period's average hourly
earnings. Time off for exempt salaried staff at `base_rate` is covered by salary.

## incentives

Spiffs, commissions and overrides. One entry per program.

| Field | Meaning |
|---|---|
| `id`, `label` | |
| `source` | `addons`, `services` or `sales` |
| `kind` | `per_unit` (dollars per unit) or `percent` (percent of `amount` for sales, `revenue` for services) |
| `rates` | What it pays on: `{"match", "value", "rate", "only_employees"}`. `match` is `code_prefix`, `code`, `category`, `item_contains` or `any`. A rate of `"0"` records a code that pays nothing |
| `frequency` | `pay_period` (default) or `monthly` (paid only on runs with `include_monthly`, over `monthly_window`) |
| `eligible_roles`, `eligible_employees` | Who can earn it; empty = anyone |
| `tiers` | `[{"from": "1", "to": "5", "rate": "10"}, {"from": "6", "rate": "15"}]` |
| `tier_method` | `marginal` (each tier pays only its units) or `highest` (all units at the highest tier reached) |
| `tier_scope` | `employee_location` (default) or `employee` (count across locations) |
| `exclude` | `[{"field": "item_type", "values": ["renewal"]}]` |
| `credit` | `seller` (default) or `location` (pays `recipients` on the whole location's base) |
| `recipients` | For `credit: location`: `{"location_id", "employee_id", "share"}` |
| `pay_code` | Pay type key (must exist in `pay_codes`) |
| `include_in_regular_rate` | Default `true`. Non-discretionary pay raises the overtime regular rate |

Every add-on code seen in a period must match some rate (even `"0"`), or the run warns.
Rows that matched but were not payable (wrong role, `only_employees`, excluded, outside
a window) are listed on the Incentive Notes tab.

## stipends

`{"id", "employee_id", "label", "amount", "location_id", "effective_from", "effective_through", "pay_code"}`.
A fixed amount per pay period between the dates.

## manager_allocation

`[{"employee_id": "M1", "location_id": "DT", "share": "0.5"}, ...]`. Splits a salary's
cost across locations; shares per person must add to 1. Cents are allocated so the
parts add back to the salary exactly.

## bonus_pools

Pass/fail scorecard bonuses.

| Field | Meaning |
|---|---|
| `id`, `label`, `frequency` (`monthly` default) | |
| `pool_per_location` | The most each location can pay |
| `metrics` | `{"id", "label", "numerator", "denominator", "compare" (">=" etc.), "threshold", "weight"}`. Names refer to `location_metrics.csv`. Weights add to 1 at most |
| `recipients` | `{"location_id", "employee_id", "share"}`; two people can each get `share` 1 |
| `pay_code`, `include_in_regular_rate` | Non-exempt recipients of promised bonuses need `true` |

## employee_overrides

Per-person exceptions, keyed by `employee_id`:

- `secondary_role`: a second role (dual-role staff)
- `pos_names`: other spellings in POS reports
- `payroll_id`, `home_location`
- `rates`: extra dated rate rows `{"role", "rate", "rate_type", "effective_from"}`, e.g. a
  ramp, the second role's rate, or the old rate before a mid-period raise

## pay_codes

Every pay type the engine can produce, mapped to the payroll system:

`"lobby": {"label": "Lobby", "code": "Lobby", "export_as": "amount"}`

- `code` must match the payroll system's earning name or code exactly
- `export_as`: `hours` (sent as hours, paid at the payroll system's rate on file),
  `amount` (sent as dollars) or `none` (shown in the workbook, left out of the upload, for
  example time off the payroll system already pays)
- Engine pay types: `service_wages`, `service_per_unit`, `service_commission`, `regular`,
  `overtime`, `doubletime`, `ot_premium`, `card_tips`, `cash_tips`, `salary`,
  `min_wage_makeup`, `nonproductive_time`, `rest_recovery`, plus every `pay_code` used by
  time pay, time off, incentives, stipends, bonus pools and adjustments.

## checks

```json
"checks": {
  "plausibility": {"min_avg_service_hours": "0.25", "max_avg_service_hours": "4",
                   "max_weekly_hours": "70", "anomaly_threshold": "0.25"},
  "unmapped_addons": "warn"
}
```

## intake_notes

`[{"id", "topic", "question", "answer"}]`: answers that do not fit a table, kept with the
rules. Open items live here until the owner decides.

# period.json reference

| Field | Meaning |
|---|---|
| `period_start`, `period_end`, `pay_date` | |
| `include_monthly`, `monthly_window` | Month-end runs pay monthly incentives and pools over `{"start", "end"}`. `new-period --monthly` fills in the calendar month of the period end; a month-end run without a window is BLOCKED |
| `windows` | Per incentive or pool id: `{"start", "end"}` (seasonal gift card windows). Matching rows inside the period but outside the window are reported |
| `attestations` | `{"input", "location_id", "statement", "by"}`: an input with genuinely nothing this period (`time_off` must be attested per location when there are no rows) |
| `sources` | One per report: `file`, `report`, `location_id`, `date_from`, `date_to`, `mapped_to`, `totals` (the report's own printed totals), and `window` when the report covers more than the pay period: an id from `windows`, `"monthly"`, or `{"start", "end"}` |
| `expected_activity` | `{"employee_id", "input", "category", "minimum", "reason"}`: something the owner said must be in the data |
| `approved_variances` | `{"check", "location_id", "reason", "by"}`: a reconciliation difference the owner accepted (shows PASS*) |
| `acknowledged_warnings` | `{"code", "match", "by", "note"}`: a warning the owner decided is fine. Unused entries are reported so they cannot hide a future warning |
| `salary_proration` | Optional factor (e.g. `"0.5"`) overriding day-count proration |
| `notes` | |

## history/weeks.json

Written by every run that gets past the gates: hours, straight-time earnings and
overtime paid per person, per day and per workweek. The next period reads it for the
boundary week and for monthly overtime true-ups. Re-running a period replaces its own
entries, so re-runs never double count.

Run periods in order. When a period starts mid-week and no earlier run covers the days
before it (the first period you run with this tool, or a skipped period), the run warns
`GATE_HISTORY_GAP`. Either run the earlier period first (its hours are recorded even if
it was paid some other way), or acknowledge the warning and check that week's overtime
by hand.

