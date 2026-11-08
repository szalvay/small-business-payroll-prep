# Changelog

## 1.1.0 (2026-11)

Now for small businesses in general, not only salons and spas.

- Renamed to Payroll Prep for Small Businesses (`small-business-payroll-prep`); the
  engine package is now `payprep`.
- Intake by industry, following nine industries: Technology & Software, Entertainment,
  Healthcare & Life Sciences, Manufacturing & Industrial, Financial Services, Energy &
  Utilities, Retail, Education, Government & Defense, plus "something else". Each has a
  question pack and an honest list of what it needs that is not built yet. Core sections
  are asked by how people are paid (hourly, salary, piece rate, commission, tips).
  175 questions in all; `intake-workbook --industry <id>` shows only what applies, and
  `company.industry` records the choice.
- A second sample business: a three-store retailer with hourly staff, sales commission
  with returns and employee-purchase exclusions, a per-unit spiff, a tiered monthly
  loyalty bonus, coffee-bar tips, overtime across two stores, California daily overtime,
  double time and the seventh day, ADP exports and an ADP paydata upload
  (`payroll.py sample <dir> --kind retail`).
- Intake workbook examples are industry-neutral.
- README rewritten for owners with no payroll experience, with on-brand diagrams of how
  it fits with existing systems and how a pay period runs, plain-language install steps
  and a glossary.
- 43 engine tests.

## 1.0.0 (2026-11)

First public release.

- Pay engine: piece rate (per service hour, per service, percent of revenue), hourly and
  salary; non-service time; time off; tips; add-on, service and sales incentives with
  tiers, exclusions, per-person rates, monthly frequency and date windows; location
  overrides; stipends; scorecard bonus pools; adjustments.
- Overtime per workweek across locations of the same employer and across pay periods
  (history file), regular rate including incentives, monthly true-up, daily overtime,
  double time and seventh-day rules, minimum-wage floor per workweek.
- Gates, reconciliation checks, an independent audit, anomaly comparison with the last
  period, and acknowledged warnings. Only `payroll.py run` declares ALL CLEAR.
- Intake: 87-question interview guide and a fillable intake workbook that compiles to
  the config; Pay Rules Book with rule IDs, fingerprint and sign-off.
- Connectors: BambooHR, ADP Workforce Now, Paylocity, HiBob and generic profiles for
  roster, rate and time-off imports and payroll upload files.
- Sample three-location spa workspace with report-style raw exports, and 41 engine tests.
