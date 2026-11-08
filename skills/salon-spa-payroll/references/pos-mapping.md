# Mapping POS and booking-system reports

The engine never reads a POS report directly. Claude reads each raw export in
`raw/`, maps it into the canonical CSVs (`input-formats.md`), and records the report in
`period.json` `sources` with the totals the report itself prints. The run then proves
the mapped rows add up to those totals, so a dropped person, a doubled page or a
shifted column stops the run instead of shipping.

## The mapping procedure (every report, every period)

1. **Open the raw file and find the header row by its text.** Reports often have title
   rows, filter rows and per-employee "For: Name" blocks above the data. Never assume
   the header is on row 1 or that a column sits where it did last period. Column
   positions shift between locations and between periods when optional columns
   appear or disappear.
2. **Confirm the report is the right one:** the location name or number in its header,
   the report type, and the date range. A report for the wrong location or a full week
   instead of the pay period is the most common pull mistake.
3. **Map by meaning, not by look.** Two numeric columns next to each other (quantity
   and service hours; amount and percent of sales) are easy to swap. Check a few rows
   by hand: does 6 services and 6.5 hours look right for that person's day?
4. **Write one row per fact.** One service line, one add-on line, one tip, one day of
   time. Keep refunds as rows with `refund = Y`. Skip subtotal and total rows, and
   system placeholder "employees" (training slots, external, house accounts).
5. **Record the source** in `period.json`:
   ```json
   {"file": "raw/EC_service_detail.xlsx", "report": "Service detail by provider",
    "location_id": "EC", "date_from": "2026-10-16", "date_to": "2026-10-31",
    "mapped_to": "services", "totals": {"service_hours": "127", "quantity": "118"}}
   ```
   Take `totals` from the report's own grand-total line, not from your mapped rows.
   Checkable totals: services `service_hours`, `quantity`, `revenue`; addons `quantity`;
   sales `amount`, `quantity`; tips `amount`; time_entries `hours`; time_off `hours`.
6. **Run `payroll.py check <period>`** and fix what it reports before running.

If a mapping is reused every period, write it down in `intake_notes` (report name,
header text for each canonical column, rows to skip) so the next period is mechanical.

## Which report feeds which input

| Input | What to look for | Never use |
|---|---|---|
| services | Service detail or service sales by provider, with actual service time per line | Scheduled, bookable or "work time" from a schedule report (it includes empty gaps) |
| addons | Add-on / enhancement detail with the add-on code per line | The customer price as pay |
| sales | Sales by employee: retail, memberships, packages, gift cards, with the dollar amount and a type | A "% of sales" column as the commission base |
| tips | Tips by provider (card tips; declared cash tips if tracked) | Tips netted against anything |
| time_entries | Time clock detail, or a time-category report (lobby, training, meetings) | A clock export covering days outside the pay period |
| time_off | The HR system's time-off-used report for exactly the period | A balances report |
| location_metrics | The scorecard or KPI report for the bonus window | Numbers retyped from a dashboard without the report |

## Habits that prevent known failures

- **Service hours have one source.** If the service report shows zero hours for people
  who clearly worked, the column is mapped wrong; never fall back to schedule time.
- **Codes before descriptions.** Add-on and service codes often come as
  `CODE: Description`. Keep the whole string in the code column; matching uses the part
  before the colon.
- **Names will not match exactly.** POS names come in capitals, lower case, with
  nicknames (`NICK: Last, First`) or as First Last. The engine matches spelling variants
  and `pos_names` aliases; when it cannot, it stops and suggests the closest roster
  name. Add the alias rather than editing the report.
- **Terminated staff still appear in POS reports.** Do not drop them while mapping. The
  run checks activity against termination dates and tells the owner.
- **Tips prove presence.** Someone with tips and no service hours is a mapping problem,
  not a bonus.
- **Corrupt or truncated exports happen.** A file that will not open, or is far smaller
  than usual, gets downloaded again. Never map a partial file.
- **Monthly and seasonal reports cover their own window.** Retail and membership reports
  for monthly commissions cover the whole month (`monthly_window`); a seasonal gift card
  report covers the window in `period.json` `windows`. Record the `window` on the source.

## Notes for specific systems

These are patterns seen in real exports, not official documentation. Report names and
layouts change; trust the header text in front of you.

**Meevo.** Reports are identified by codes. Employee service detail reports put each
provider in a "For:" block with a "Total for Services" line; actual service hours sit in
a column whose position differs by location and can move between periods, so find it by
header every time. The employee payroll report is a good source for card tips. The
add-on detail report carries the add-on type code (the part before the colon). Time
clock reports by week must be pulled for the pay-period dates only. Category-filtered
reports (front desk only, service providers only) depend on the filter being set in the
UI; check the people in the file match the category.

**Mindbody, Boulevard, Vagaro, Zenoti, Phorest, Square Appointments and others.** Look
for a payroll or commission report by staff member with line detail, a sales-by-staff
report, a tips report and the time clock export. Prefer line-level detail exports to
summary reports; summaries are useful for the `totals` you record in `sources`.

If a business uses a system not listed here, ask the owner which report they use today
for each input, map it once with them watching, and save the mapping in `intake_notes`.
