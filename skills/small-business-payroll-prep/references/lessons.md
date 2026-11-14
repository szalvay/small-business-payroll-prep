# Lessons: why each gate and check exists

Each row below is a failure mode that payroll of this kind is exposed to: commission and
piece-rate pay, tips, overtime by workweek, several locations, and numbers pulled from
point-of-sale and HR exports. Most payroll errors of this type are omissions or mapping
slips, not arithmetic mistakes. Each risk is now covered by a gate (stops the run before
anything is calculated), a check (reconciles after), or a warning (needs a decision).

| # | What can go wrong | What catches it now |
|---|---|---|
| 1 | If the sick-time export is missing, no sick hours are paid, and every reconciliation can still balance because zero matches zero. | `GATE_TIMEOFF_MISSING`: time off needs rows or a written attestation per location |
| 2 | If service hours are read one column off, every provider can show zero hours, while a stray column makes one person look plausible. | `GATE_ZERO_SVC_HOURS`, `GATE_SVC_AVG`, and report totals in `sources` (`GATE_SOURCE_TOTAL`) |
| 3 | If quantity and service hours are swapped, people would be paid per appointment count instead of per hour. | `GATE_SVC_AVG` (implausible hours per service), report totals |
| 4 | If scheduled "bookable" time stands in for missing service hours, pay can be overstated by dozens of hours. | One source for service hours; there is no fallback anywhere in the engine |
| 5 | Add-on spiffs could be paid at the customer's price instead of the employer's rate. | Incentives pay only configured rates; `customer_price` is never read for pay |
| 6 | A new add-on code can appear and silently pay nothing. | `INC_ADDON_UNMAPPED`: every add-on code needs a rate, even 0 |
| 7 | Overtime could be computed on the pay-period total (over 80) instead of per week (over 40). | Per-workweek overtime only; the audit recomputes weekly overtime hours independently |
| 8 | A full-week time clock export on a boundary week would pay days already paid last period. | `GATE_DATE` (time rows must be inside the period) and history-based boundary weeks; `GATE_SOURCE_DATES` |
| 9 | A boundary week can cross 40 hours only when both periods are added together, so the overtime is easy to miss. | `history/weeks.json` carries each week's hours and premium across periods |
| 10 | A terminated employee can still appear in a POS report, which could pay a commission already settled on their final check. | `GATE_TERMED`, `GATE_TERMED_PRIOR`; `GATE_FINAL_PAY` reminder |
| 11 | Someone can be dropped because the export was filtered after they left, or their name is spelled differently. | `GATE_NO_ACTIVITY`, name variants and `pos_names`, unknown-name FAILs with suggestions |
| 12 | One person can appear twice when the POS and HR systems spell the name differently. | Name resolution to one employee id; ambiguous names FAIL |
| 13 | A gift card commission computed from a "% of sales" column would pay a few cents. | Percent incentives use `amount` only; rates are written as percents and validated |
| 14 | Membership commission could be taken from the POS's internal tracking column instead of the sold count and the owner's tiers. | Tiered incentives from sold units with explicit exclusions |
| 15 | A one-off payment that reuses a pay type name summed by a reconciliation makes a check fail for the wrong reason. | Adjustments carry their own pay codes and an approver |
| 16 | A pay type label off by one word can make the payroll upload reject the file. | `pay_codes[].code` per pay type, set once from the payroll system; missing codes FAIL |
| 17 | A hand edit to a workbook cell is lost when the file is rebuilt. | No hand edits: rules live in the config, one-offs in adjustments, decisions in `period.json` |
| 18 | A summary could say "all passed" while a reconciliation cell shows FAIL. | Only `payroll.py run` prints ALL CLEAR, and only with `evidence.json`; warnings need acknowledgment |
| 19 | Checks that compare a workbook to itself can pass while the underlying number is wrong. | An independent audit recomputes pay from the inputs with separate code |
| 20 | A stipend can keep paying after the coverage it was for has ended. | Stipends have `effective_from` / `effective_through` |
| 21 | A monthly commission raises the overtime rate for weeks already paid, which needs a true-up. | Monthly incentives are spread over the month and a true-up premium is paid for overtime weeks |
| 22 | If someone sells at a location where they had no hours that period, the commission can vanish. | Incentives pay the seller wherever the sale happened |
| 23 | A rate change mid-period could be applied to the whole period. | Dated rate rows; hourly lines split by rate; `EXPORT_RATE_ON_FILE` when the payroll system pays hours at one rate |
| 24 | A split salary can lose a cent, so cost-split reports do not tie. | Penny-exact allocation |
| 25 | A corrupt or truncated export could be read as "no data". | Unreadable files stop the mapping; report totals catch partial files |
| 26 | A failed re-run could leave the earlier run's "all clear" files in the folder, so the wrong file gets sent. | Every run clears the previous outputs first; upload files from a run that is not clear are named `DO_NOT_UPLOAD_` |
| 27 | Running a period before the one ahead of it means its first workweek's overtime ignores the earlier days. | `GATE_HISTORY_GAP` |

When you find a new way payroll can go wrong, add a gate or check for it, add a test
that reproduces it in `tests/`, and add a row here.
