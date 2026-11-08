# Independent review brief

Use this when a run matters more than usual: the first live period, a new location, a
changed rule, or any period where the owner asks for a second look. Give it to a
separate agent that did not build the period, so the work is not grading itself.

## Brief for the reviewer

You are reviewing one pay period produced by the small-business-payroll-prep engine. You did not
build it. Your job is to find what is wrong or missing, not to confirm it is right.
Report findings with evidence (file, row, numbers). Do not edit any file.

Inputs you can read:

- `payroll_config.json` and `PAY_RULES_BOOK.md` in the workspace
- `periods/<period>/period.json`, `raw/`, `inputs/`
- `periods/<period>/output/`: `payroll_review_<date>.xlsx`, `run_summary.md`,
  `evidence.json`, the upload file(s), `hris_import_report.md`

Work through these, in order:

1. **Status.** `evidence.json` status and reasons. Is the config fingerprint the one in
   the signed rulebook? Any acknowledged warnings: is each one plausible and attributed
   to a person?
2. **Raw to inputs.** Pick at least three raw reports. For each, find its `sources`
   entry, confirm the location, report type and date range in the raw file's header, and
   re-add its grand total yourself. Spot-check five rows against `inputs/`.
3. **People.** Compare the roster with everyone in the raw reports. Anyone in a report
   but not paid? Anyone paid with no hours, services or tips? Anyone who left during the
   period?
4. **Service pay.** For three providers, recompute service hours times rate from
   `inputs/services.csv` and `pay_rates.csv`, and compare with the Employees tab.
5. **Overtime.** On the Overtime tab, pick every week with overtime and every boundary
   week. Recompute hours and the premium by hand. Check the history hours for boundary
   weeks against the previous period's output.
6. **Incentives.** Read the Incentive Notes tab. Is every unpaid line explained by a rule
   the owner signed? Recompute one tiered incentive by hand.
7. **Upload files.** Sum the amounts and hours in each file and compare with the By Pay
   Type tab for exportable pay types. Check pay type codes against `pay_codes`.
8. **Change since last period.** Read the anomaly findings. Is each big change explained
   by the inputs?

Report:

- `BLOCKING`: anything that would pay someone the wrong amount or leave someone out
- `QUESTION`: anything the owner must decide
- `NOTE`: everything else

Finish with one line: whether you agree the period can go to the owner for approval.
