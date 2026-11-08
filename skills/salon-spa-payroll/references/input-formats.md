# Canonical input files

<!-- Generated from spapay/inputs.py by tools/build_docs.py. Edit the code, not this file. -->

Every POS, HR system and time clock exports differently. Each export is mapped into these plain
CSV files in `periods/<period>/inputs/`, and the engine reads nothing else. One row is one fact;
never pre-total by hand. `payroll.py templates <dir>` writes blank copies with the right headers.

People can be identified by `employee_id` or by `employee_name` (any spelling on the roster or in
`pos_names`). Locations can be a location id or any label in the config.

## roster.csv

Everyone who might be paid this period (from your HR system).

| Column | Type | Required |
|---|---|---|
| `employee_id` | text | yes |
| `first_name` | text | yes |
| `last_name` | text | yes |
| `status` | text | yes |
| `hire_date` | date |  |
| `termination_date` | date |  |
| `home_location` | text | yes |
| `role` | text | yes |
| `secondary_role` | text |  |
| `payroll_id` | text |  |
| `pos_names` | text |  |
| `email` | text |  |

- `status` is `active`, `terminated` or `leave`. Keep people who left during the period on the roster with their `termination_date`.
- `home_location` is a location id or any label from the config. Time off with no location is charged here.
- `pos_names` lists other spellings, separated by `;` (or keep them in the config under employee_overrides[].pos_names).

## pay_rates.csv

Each person's rate for each role; add a row with effective_from for a mid-period change.

| Column | Type | Required |
|---|---|---|
| `employee_id` | text | yes |
| `role` | text | yes |
| `rate` | number | yes |
| `rate_type` | text | yes |
| `effective_from` | date |  |

- One row per person per role. A raise mid-period is a second row with `effective_from`; days before it use the earlier row.
- `rate_type`: `service_hour`, `per_service`, `service_pct` (a percent: 40 = 40%), `hourly`, `salary_annual`, `salary_period`.

## time_entries.csv

Clocked or recorded time, one row per person per day per kind of time.

| Column | Type | Required |
|---|---|---|
| `employee_id` | text |  |
| `employee_name` | text |  |
| `location` | text | yes |
| `date` | date | yes |
| `category` | text | yes |
| `hours` | number | yes |
| `role` | text |  |
| `note` | text |  |

Give `employee_id` or `employee_name` on every row.

- One row per person per day per kind of time. `category`: `worked`, `lobby`, `training`, `trainee`, `trainer`, `meeting`, `cleaning`, `travel`, `waiting`, `rest_recovery`, `other`.
- Export the time clock for exactly the pay period dates, never whole weeks: earlier days of a boundary week were paid last period, and the engine already knows them from history.
- For clocked piece-rate staff, non-service categories recorded inside a clocked shift are break-outs and are not counted twice.

## services.csv

Every service performed, one row per service line, from the POS service detail report.

| Column | Type | Required |
|---|---|---|
| `employee_id` | text |  |
| `employee_name` | text |  |
| `location` | text | yes |
| `date` | date | yes |
| `service_code` | text |  |
| `service_name` | text |  |
| `category` | text | yes |
| `quantity` | number | yes |
| `service_hours` | number | yes |
| `revenue` | number |  |
| `refund` | Y/N |  |

Give `employee_id` or `employee_name` on every row.

- `service_hours` is actual service time from the service detail report. Never scheduled or bookable time.
- `category` routes the line to a role (see roles[].service_categories). `refund = Y` makes the row negative.
- `quantity` is the number of services. The run warns when hours per service look implausible (a swapped column).

## addons.csv

Every add-on/enhancement performed, one row per line, from the POS add-on report.

| Column | Type | Required |
|---|---|---|
| `employee_id` | text |  |
| `employee_name` | text |  |
| `location` | text | yes |
| `date` | date | yes |
| `addon_code` | text | yes |
| `addon_name` | text |  |
| `quantity` | number | yes |
| `customer_price` | number |  |
| `refund` | Y/N |  |

Give `employee_id` or `employee_name` on every row.

- `addon_code` may be `CODE: Description`; matching uses the part before the colon. `customer_price` is kept for reference only and never paid.

## sales.csv

Retail, membership, gift card and package sales credited to a person.

| Column | Type | Required |
|---|---|---|
| `employee_id` | text |  |
| `employee_name` | text |  |
| `location` | text | yes |
| `date` | date | yes |
| `category` | text | yes |
| `item` | text |  |
| `item_type` | text |  |
| `quantity` | number | yes |
| `amount` | number | yes |
| `refund` | Y/N |  |

Give `employee_id` or `employee_name` on every row.

- `category` is the program: `retail`, `membership`, `gift_card`, `package` or your own. `item_type` carries things like `new`, `renewal`, `transfer` for exclusions.
- `amount` is the dollar base for percent incentives. Never map a percent-of-sales column here.

## tips.csv

Card tips (and declared cash tips) per person per day.

| Column | Type | Required |
|---|---|---|
| `employee_id` | text |  |
| `employee_name` | text |  |
| `location` | text | yes |
| `date` | date | yes |
| `tip_type` | text | yes |
| `amount` | number | yes |

Give `employee_id` or `employee_name` on every row.

- `tip_type` is `card` or `cash`. Card tips are passed through in full and reconciled to the report total.

## time_off.csv

Sick, PTO and holiday hours taken, one row per person per day.

| Column | Type | Required |
|---|---|---|
| `employee_id` | text |  |
| `employee_name` | text |  |
| `date` | date | yes |
| `type` | text | yes |
| `hours` | number | yes |
| `location` | text |  |

Give `employee_id` or `employee_name` on every row.

- `type`: `sick`, `pto`, `vacation`, `holiday`, `bereavement`, `jury_duty`, `unpaid`. Only rows inside the pay period.
- If nobody at a location took time off, record an attestation in period.json instead of leaving the file empty.

## adjustments.csv

One-off pay approved by the owner: bonuses, back pay, reimbursements.

| Column | Type | Required |
|---|---|---|
| `employee_id` | text |  |
| `employee_name` | text |  |
| `location` | text | yes |
| `pay_code` | text | yes |
| `description` | text | yes |
| `hours` | number |  |
| `rate` | number |  |
| `amount` | number |  |
| `taxable` | Y/N |  |
| `include_in_regular_rate` | Y/N |  |
| `approved_by` | text | yes |

Give `employee_id` or `employee_name` on every row.

- Every row names `approved_by`. Give `amount`, or `hours` and `rate`. `taxable = N` for reimbursements.
- Use a pay code of its own (e.g. `back_pay`, `signing_bonus`), not one that a reconciliation check sums.

## location_metrics.csv

Location scorecard numbers used by manager bonus pools.

| Column | Type | Required |
|---|---|---|
| `location` | text | yes |
| `metric` | text | yes |
| `value` | number | yes |
| `window_start` | date |  |
| `window_end` | date |  |

- One row per location per metric, with the window it covers. Names match bonus_pools[].metrics numerator/denominator.
