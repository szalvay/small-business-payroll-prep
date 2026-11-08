# Lessons: why each gate and check exists

This skill grew out of running real multi-location spa payrolls by hand and with code.
Almost every error that reached a paycheck, or nearly did, was an omission or a mapping
slip, not an arithmetic mistake. Each lesson below is now a gate (stops the run before
anything is calculated), a check (reconciles after), or a warning (needs a decision).

| # | What went wrong | What catches it now |
|---|---|---|
| 1 | The sick-time export was missing. Nobody's sick hours were paid, and every reconciliation still balanced because zero matched zero. | `GATE_TIMEOFF_MISSING`: time off needs rows or a written attestation per location |
| 2 | Service hours were read one column off. Every provider showed zero hours, while a stray column made one person look plausible. | `GATE_ZERO_SVC_HOURS`, `GATE_SVC_AVG`, and report totals in `sources` (`GATE_SOURCE_TOTAL`) |
| 3 | Quantity and service hours were swapped, so people were paid per appointment count instead of per hour. | `GATE_SVC_AVG` (implausible hours per service), report totals |
| 4 | Scheduled "bookable" time was used when actual service hours were missing, overpaying by dozens of hours. | One source for service hours; there is no fallback anywhere in the engine |
| 5 | Add-on spiffs were paid at the customer's price instead of the employer's rate. | Incentives pay only configured rates; `customer_price` is never read for pay |
| 6 | A new add-on code appeared and silently paid nothing. | `INC_ADDON_UNMAPPED`: every add-on code needs a rate, even 0 |
| 7 | Overtime was computed on the pay-period total (over 80) instead of per week (over 40). | Per-workweek overtime only; the audit recomputes weekly overtime hours independently |
| 8 | A full-week time clock export on a boundary week paid days that were already paid last period. | `GATE_DATE` (time rows must be inside the period) and history-based boundary weeks; `GATE_SOURCE_DATES` |
| 9 | A boundary week crossed 40 hours only when both periods were added together, and the overtime was missed. | `history/weeks.json` carries each week's hours and premium across periods |
| 10 | A terminated employee still appeared in a POS report and was paid a commission already settled on their final check. | `GATE_TERMED`, `GATE_TERMED_PRIOR`; `GATE_FINAL_PAY` reminder |
| 11 | Someone was dropped because the export was filtered after they left, or their name was spelled differently. | `GATE_NO_ACTIVITY`, name variants and `pos_names`, unknown-name FAILs with suggestions |
| 12 | One person appeared twice because the POS and HR systems spelled the name differently. | Name resolution to one employee id; ambiguous names FAIL |
| 13 | A gift card commission was computed from a "% of sales" column and paid a few cents. | Percent incentives use `amount` only; rates are written as percents and validated |
| 14 | Membership commission was paid from the POS's internal tracking column instead of the sold count and the owner's tiers. | Tiered incentives from sold units with explicit exclusions |
| 15 | A one-off payment reused a pay type name that a reconciliation summed, so a check failed for the wrong reason. | Adjustments carry their own pay codes and an approver |
| 16 | A pay type label was off by a word and the payroll upload rejected it. | `pay_codes[].code` per pay type, set once from the payroll system; missing codes FAIL |
| 17 | A hand edit to a workbook cell was lost when the file was rebuilt. | No hand edits: rules live in the config, one-offs in adjustments, decisions in `period.json` |
| 18 | A summary said "all passed" while a reconciliation cell showed FAIL. | Only `payroll.py run` prints ALL CLEAR, and only with `evidence.json`; warnings need acknowledgment |
| 19 | Checks that compared a workbook to itself passed while the underlying number was wrong. | An independent audit recomputes pay from the inputs with separate code |
| 20 | A stipend kept paying after the coverage it was for had ended. | Stipends have `effective_from` / `effective_through` |
| 21 | A monthly commission raised the overtime rate for weeks already paid, and nobody trued it up. | Monthly incentives are spread over the month and a true-up premium is paid for overtime weeks |
| 22 | Someone sold at a location where they had no hours that period and the commission vanished. | Incentives pay the seller wherever the sale happened |
| 23 | A rate change mid-period was applied to the whole period. | Dated rate rows; hourly lines split by rate; `EXPORT_RATE_ON_FILE` when the payroll system pays hours at one rate |
| 24 | A split salary lost a cent, so cost-split reports did not tie. | Penny-exact allocation |
| 25 | A corrupt or truncated export was read as "no data". | Unreadable files stop the mapping; report totals catch partial files |

When a new kind of mistake happens, add a gate or check for it, add a test that
reproduces it in `tests/`, and add a row here.
