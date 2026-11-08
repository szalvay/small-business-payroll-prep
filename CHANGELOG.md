# Changelog

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
