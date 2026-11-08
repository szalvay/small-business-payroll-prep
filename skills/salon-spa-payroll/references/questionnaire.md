# Intake questionnaire

<!-- Generated from assets/intake/questions.json by tools/build_docs.py. Edit the JSON, not this file. -->

This is the owner interview that turns how a business actually pays people into
`payroll_config.json`. The same questions appear on the Questions tab of the intake
workbook (`payroll.py intake-workbook`), so an owner can answer on paper instead.

## How to run the interview

- **One question at a time.** Ask, wait, then ask the next. Owners answer far better
  when they are not handed a wall of questions.
- **Skip what does not apply.** A single-location massage studio with no front desk
  skips half of this. Say which sections you are skipping and why.
- **Use their words, then confirm in yours.** After each section, read back what you
  heard as rules ("So: lobby time for massage therapists is paid at minimum wage, under
  the pay type Lobby. Right?"). Write the config only from confirmed answers.
- **Ask for documents when they exist.** An offer letter, a comp plan, a past payroll
  register or an import template beats memory. Read them and confirm what you found.
- **Never guess a rate, a threshold or a pay type name.** If the owner does not know,
  record it as an open item in `intake_notes` and leave the config value blank so the
  run stops and asks, instead of quietly paying the wrong amount.
- **Every special deal is a rule.** When the owner says "except for one person", stop and
  capture that exception as an override or a dated rate.
- **State rules are presets, not advice.** Load the state preset that fits, show the
  owner what it says, and ask them to confirm it with their payroll provider or counsel.
  Set `confirmed_by_owner` only when they say they have.
- **Finish with the Pay Rules Book.** Render it (`payroll.py rulebook`), walk the owner
  through every rule, fix what is wrong, and record their sign-off
  (`payroll.py approve --by "<name>"`). A run never shows ALL CLEAR on unsigned rules.

Each question below lists why it matters and where the answer lands (`maps_to`).


## Before we start

Have these handy if you can: one or two recent payroll registers, an offer letter or comp plan for each kind of role, the list of reports you pull from your booking/POS system, and an export of your roster from your HR or payroll system. None of it is required to begin; the interview works from memory and fills gaps later.

**start.1** In one or two sentences, how does payroll work today, from closing the period to people getting paid?

- Why: Shows which steps are manual, who does them and where errors slip in.
- Lands in: `intake_notes`

**start.2** What went wrong in past payrolls that you never want to see again?

- Why: Every past mistake becomes a check. Most real payroll errors are omissions (a missing export, a dropped person), not arithmetic.
- Lands in: `intake_notes; checks`
- Follow up: Was it caught before payday? By whom?

**start.3** Who will run this each period, who reviews the numbers, and who submits to the payroll system?

- Why: The review workbook and sign-off lines are written for these people.
- Lands in: `systems.payroll_settings.reviewer / submitter`

## The business, its entities and locations

Overtime is counted per legal employer, and minimum wage is set by where the work happens. Getting entities and locations right first prevents two of the most expensive mistakes.

**company.1** What is the business called, and how often do you pay (weekly, every two weeks, twice a month, monthly)?

- Why: Sets the pay frequency, which drives salary per period.
- Lands in: `company.name, company.pay_frequency`

**company.2** How many days after the period ends is payday?

- Why: Sets how much time the export, review and fix loop has; final-pay deadlines for people who leave can be sooner.
- Lands in: `period.json pay_date`

**company.3** What day does your workweek start? (Check your payroll system; it is often Sunday.)

- Why: Weekly overtime is judged on this fixed 7-day week, not on the pay period.
- Lands in: `company.workweek_start`

**company.4** List each legal entity (LLC or corporation) that employs people. Are all locations under one entity or separate ones?

- Why: Hours at two locations of the same employer are added together for overtime. Separate entities are generally counted separately; confirm with your payroll provider if ownership is shared.
- Lands in: `employers[], locations[].employer_id, company.ot_aggregation`

**company.5** List every location: a short code, its name, city and state, and which entity runs it.

- Why: Every hour and every sale is tied to a location for minimum wage, overtime and cost reporting.
- Lands in: `locations[]`

**company.6** What is the minimum wage at each location today, and when does it next change? Some cities and counties set their own.

- Why: Non-service time and sick pay are often paid at minimum wage, and every workweek must clear it. Oregon, for example, has three regional rates.
- Lands in: `locations[].min_wage[] with effective_from`

**company.7** How does each location appear in your booking/POS reports and in your HR system (names, numbers, codes)?

- Why: So a report labelled '0102' or 'Eastside Salem' lands on the right location.
- Lands in: `locations[].pos_labels, locations[].hris_labels`

**company.8** Does your payroll system track locations as departments, divisions or cost centers? What are the codes?

- Why: Lets the payroll file split pay by location.
- Lands in: `locations[].payroll_code, systems.payroll_settings.split_by_location`

## Systems

The engine never logs into anything. It reads exports you download. These answers decide which export layouts to expect and which payroll file to produce.

**systems.1** Which booking/POS system do you use? Which reports do you pull for payroll today?

- Why: Each report becomes one canonical input file. Claude maps the columns once and records them.
- Lands in: `systems.pos, systems.pos_reports[]`

**systems.2** Which HR system holds your roster and pay rates (BambooHR, HiBob, Paylocity, ADP, Gusto, a spreadsheet)?

- Why: Picks the HRIS on-ramp that turns its roster and time-off exports into inputs.
- Lands in: `systems.hris`

**systems.3** Which payroll system pays people? Do you upload hours, dollar amounts, or both?

- Why: Picks the outbound file layout.
- Lands in: `systems.payroll, systems.payroll_exports`

**systems.4** Do staff clock in and out? In which system? Do service providers clock, or only the front desk?

- Why: Decides whether hours worked come from the clock or from service time plus recorded non-service time.
- Lands in: `roles[].hours_worked_source`

**systems.5** In your payroll system, what are the exact names of each pay type you upload (for example 'Commission', 'Credit Card Tips')?

- Why: An upload with a pay type name that is off by one character is rejected or, worse, mapped to the wrong earning.
- Lands in: `pay_codes{}.code`

**systems.6** Which employee number does your payroll system use? Is it the same as the HR system's?

- Why: The payroll file must carry the number the payroll system knows.
- Lands in: `roster payroll_id`

## Roles and who is who

A role is a way of being paid. Most spas have four or five.

**roles.1** List each role (for example massage therapist, esthetician, stretch therapist, nail tech, stylist, front desk, manager).

- Why: Every rule hangs off a role.
- Lands in: `roles[]`

**roles.2** For each role: is it paid per hour of service, per service performed, a percent of service revenue, hourly on the clock, or salary?

- Why: The pay basis decides which inputs the role needs and how its hours are counted.
- Lands in: `roles[].pay_basis`

**roles.3** Which service categories does each service role perform (massage, facial, stretch, nails, hair...)?

- Why: A dual-role person's services are paid at the rate of the role that matches the category.
- Lands in: `roles[].service_categories`

**roles.4** Which roles receive tips?

- Why: If a tipped role has no tips file, the run stops instead of paying zero tips.
- Lands in: `roles[].tips`

**roles.5** Is any salaried role exempt from overtime? Is any manager paid hourly?

- Why: Exempt salary is not checked for overtime; non-exempt staff always are.
- Lands in: `roles[].exempt`

**roles.6** How do your HR system's job titles map to these roles?

- Why: Lets the HRIS import assign roles without hand edits.
- Lands in: `roles[].hris_titles`

**roles.7** Does anyone hold two roles (for example massage therapist and esthetician)? At what rate is each paid?

- Why: Their services are split by category and paid at each role's rate; their incentives follow the role that earned them.
- Lands in: `employee_overrides[].secondary_role, rates`

**roles.8** Does anyone work at more than one location? Which is their home location?

- Why: Their hours are combined for overtime across locations of the same employer, and time off is charged to the home location.
- Lands in: `roster home_location`

**roles.9** Does anyone have a pay deal that differs from the standard plan (a ramp, a guaranteed rate, a special spiff)?

- Why: Special deals are the most common source of missed pay. Each one becomes an override or a rate row with dates.
- Lands in: `employee_overrides[], pay_rates effective_from`
- Follow up: Where is it written down? When does it change next?

**roles.10** Are there contractors or booth renters? (They are outside this payroll and should not appear in it.)

- Why: Keeps them out of the employee checks.
- Lands in: `intake_notes`

**roles.11** Do names in your POS differ from legal names (nicknames, 'NICK: Last, First', capitalization)?

- Why: Name aliases stop one person appearing as two.
- Lands in: `employee_overrides[].pos_names`

## Service pay

For service providers this is most of the paycheck. The single most damaging error in spa payroll is paying service hours from the wrong column or the wrong report.

**service.1** Which report is the single source of truth for service hours? Is it actual service time, never scheduled or bookable time?

- Why: Scheduled or bookable time includes empty gaps and overstates pay. The engine pays only the service-hours column of the service report.
- Lands in: `systems.pos_reports (services)`

**service.2** Does that report total each provider's service hours and service count? (Those totals are recorded each period and checked.)

- Why: If the mapped rows do not add up to the report's own totals, the run stops.
- Lands in: `period.json sources[].totals`

**service.3** What is each provider's service rate, and where is it kept?

- Why: Rates come from the HR export or a rates file, with an effective date for every change.
- Lands in: `pay_rates.csv`

**service.4** Do upgrades, add-on minutes or extensions count as service time?

- Why: Upgrade codes often carry real service minutes that must be paid to the right role.
- Lands in: `intake_notes; services mapping`

**service.5** How are refunds, comps, no-shows and late cancellations handled for pay?

- Why: Refunded lines are negative rows; a paid no-show fee may or may not pay the provider.
- Lands in: `services refund rows, adjustments`

**service.6** When two providers share a service (couples, four-hands), who gets credit for the hours?

- Why: The report must credit each provider their own time.
- Lands in: `intake_notes`

**service.7** Do rates change by step, tenure or performance during the year? How are you told?

- Why: A missed step increase is an underpayment that compounds. Each change is a dated rate row.
- Lands in: `pay_rates effective_from`

**service.8** If a provider clocks in, is the time between clients paid separately? (Some states require it for piece-rate pay.)

- Why: California-style rules need non-productive time paid on its own.
- Lands in: `state_rules[].piece_rate_nonproductive_separate`

## Non-service time

Lobby, training and meetings are where piece-rate staff are most often underpaid, because the time lives in a different report from the services.

**time.1** Which kinds of non-service time do you pay: lobby/floor, training, being trained, training others, meetings, cleaning, travel, waiting?

- Why: Each kind gets its own rule; a kind with no rule stops the run rather than paying zero.
- Lands in: `time_pay[]`

**time.2** At what rate is each paid: minimum wage, the person's own rate, a fixed rate, or their regular rate?

- Why: The rate basis per role and kind.
- Lands in: `time_pay[].basis, fixed_rate`

**time.3** Which report holds that time? Is it the same report for every location?

- Why: Becomes the time entries input; it is the only place training and lobby hours come from.
- Lands in: `systems.pos_reports (time_entries)`

**time.4** Are there caps (for example 4 lobby hours a month)? What happens above the cap?

- Why: Caps are a policy; hours worked above them must still be paid. The engine pays what was recorded and flags it.
- Lands in: `intake_notes`

**time.5** What pay type name does each kind go under in your payroll system (for example Training covers both trainee and trainer)?

- Why: Pay type names must match the payroll system exactly.
- Lands in: `time_pay[].pay_code, pay_codes`

**time.6** Do any staff work in a state that requires paid rest or recovery periods for piece-rate workers?

- Why: Those periods are paid at the regular rate, not minimum wage.
- Lands in: `time_pay basis regular_rate`

## Add-ons and enhancements

Add-on reports usually show the customer price. Paying that price instead of your spiff rate is a classic overpayment, and an add-on code nobody listed silently pays nothing.

**addons.1** List every add-on or enhancement code your POS uses and what you pay the provider for each one. Include the ones that pay nothing.

- Why: Every code gets a rate, even $0. A new code with no rate stops the run until you decide.
- Lands in: `incentives[source=addons].rates[]`

**addons.2** Do codes share a prefix (for example CBD, CBD-SCENTED, CBD-UNSCENTED all pay the same)?

- Why: One prefix rule covers the family.
- Lands in: `rates[].match = code_prefix`

**addons.3** Which roles earn add-on pay? Does an esthetician's enhancement pay differently from a massage add-on?

- Why: Role gating per incentive.
- Lands in: `incentives[].eligible_roles`

**addons.4** Do any add-ons pay only certain people (a certification, a pilot)?

- Why: Restricted rates pay only the named people; everyone else's units are listed as unpaid.
- Lands in: `rates[].only_employees`

**addons.5** Does the add-on report show a code, a description, or 'CODE: Description'?

- Why: Matching works on the code before the colon.
- Lands in: `addons mapping`

## Retail, memberships, packages and gift cards

Sales incentives are often monthly or seasonal. The question is always: which sales, by whom, over which dates, at what rate.

**sales.1** Do you pay commission on retail? What percent, to which roles, and is it paid every period or monthly?

- Why: Monthly incentives are paid only on the month-end run, over the whole month.
- Lands in: `incentives (retail)`

**sales.2** How are membership sales paid? Per sale, tiered (first 5 at one rate, then another), or a percent?

- Why: Tiers are counted per person per location unless you say otherwise.
- Lands in: `incentives (memberships).tiers, tier_method, tier_scope`

**sales.3** Which membership transactions do NOT pay: renewals, upgrades, transfers, conversions, cancellations within a grace period?

- Why: Exclusions are explicit rules, so they are applied the same way every time.
- Lands in: `incentives[].exclude`

**sales.4** Do gift card or package sales pay commission? Always, or only in seasonal windows (holidays, Mother's Day)? Exact dates?

- Why: Windows are set per period; sales just outside a window are reported, not silently dropped.
- Lands in: `incentives (gift cards), period.json windows`

**sales.5** Is the commission base the sale amount, the quantity, or something else? Which report column?

- Why: Paying on a percentage column instead of the dollar column has produced commissions of a penny.
- Lands in: `sales mapping, incentives[].kind`

**sales.6** Do managers earn an override on their location's sales? On which sales, at what rate?

- Why: Location-credit incentives pay named people on the whole location's total.
- Lands in: `incentives[].credit = location, recipients`

**sales.7** If someone sells at a location where they did not work any hours that period, should they still be paid there?

- Why: This edge case dropped real commissions before. The engine pays the seller wherever the sale happened.
- Lands in: `intake_notes`

**sales.8** Are refunds and chargebacks clawed back from commission? Within what time?

- Why: Refund rows reduce the base; the engine never claws back below zero without your adjustment.
- Lands in: `sales refund rows, adjustments`

## Tips

**tips.1** Are card tips paid on the paycheck in full to the person who earned them?

- Why: Tips pass through untouched and are reconciled to the tips report total.
- Lands in: `R-TIPS`

**tips.2** Do you pool or share tips (for example with the front desk)? On what formula?

- Why: Pooling needs an explicit rule and is regulated; confirm it with your payroll provider or counsel first.
- Lands in: `intake_notes`

**tips.3** Are cash tips declared through payroll? Only reported, or also paid?

- Why: Declared cash tips are usually reported for taxes, not paid again.
- Lands in: `company.cash_tips`

**tips.4** Do you add a service charge to bills? Is any of it paid to staff?

- Why: A service charge is not a tip; if shared it is wages and belongs in the regular rate.
- Lands in: `intake_notes; adjustments`

**tips.5** Which report gives tips per provider per day? Does it include prepaid tips or tips on gift cards?

- Why: The tips report is also proof of who worked; someone with tips and no pay is a red flag.
- Lands in: `systems.pos_reports (tips)`

## Sick time, PTO and holidays

A missing time-off export pays nobody's sick hours, and every other check still passes. The engine will not run without either the rows or a statement that nobody took time off.

**timeoff.1** How is sick time paid for each role? (Piece-rate staff are often paid at minimum wage or their regular rate; check your state.)

- Why: Sick pay rules by role and type.
- Lands in: `time_off_pay[]`

**timeoff.2** Do you offer PTO, vacation, holidays, bereavement or jury duty pay? To whom, at what rate?

- Why: Each type needs a rule, or the run stops.
- Lands in: `time_off_pay[]`

**timeoff.3** Where does time off come from: your HR system's time-off report, the payroll system, a spreadsheet?

- Why: Becomes the time-off input for exactly the pay period dates.
- Lands in: `systems.hris, time_off.csv`

**timeoff.4** Does your payroll system already pay approved time off from its own records?

- Why: If it does, the engine shows time off in the review but leaves it out of the upload so it is not paid twice.
- Lands in: `pay_codes[sick|pto].export_as = none`

**timeoff.5** For people who work at several locations, which location carries their time off?

- Why: Time off is charged to the home location.
- Lands in: `roster home_location`

## Overtime and the minimum-wage floor

Overtime is per workweek, never per pay period, and a week that straddles two pay periods is judged on its combined hours. Commissions and non-discretionary bonuses raise the rate overtime is paid at.

**overtime.1** Do you have staff in a state with daily overtime, double time or seventh-day rules (for example California)?

- Why: Loads the state's preset, which you confirm with your payroll provider or counsel.
- Lands in: `state_rules[]`

**overtime.2** Do service providers ever work more than 40 hours in a week, counting service time plus lobby, training and meetings?

- Why: Piece-rate staff earn overtime too, as a half-time premium on their regular rate.
- Lands in: `R-OT`

**overtime.3** Are commissions, spiffs and bonuses included when you figure the overtime rate today?

- Why: Non-discretionary incentives belong in the regular rate. Monthly ones are trued up across the weeks they were earned.
- Lands in: `incentives[].include_in_regular_rate`

**overtime.4** If a week's pay ever came out under minimum wage for the hours worked, would you rather be stopped to decide, or have a make-up line added automatically?

- Why: The floor is checked every workweek.
- Lands in: `company.min_wage_makeup (flag or auto)`

**overtime.5** When the time clock is exported, is it pulled for exactly the pay period dates (not full weeks)?

- Why: A full-week export on a boundary week re-pays days already paid last period.
- Lands in: `period.json sources date checks`

## Managers, stipends and bonus pools

**managers.1** List each manager, their annual salary (or per-period pay), and the locations they run.

- Why: Salary per period and the cost split across locations.
- Lands in: `pay_rates (salary_annual), manager_allocation[]`

**managers.2** Are any managers paid a stipend for covering another location? From when, until when?

- Why: Stipends with an end date stop on their own instead of being paid forever.
- Lands in: `stipends[] effective_from / effective_through`

**managers.3** How are manager bonuses earned? Which metrics, which thresholds, what is each worth, and how often?

- Why: Each metric is a pass/fail rule with a weight; the pool per location is fixed.
- Lands in: `bonus_pools[].metrics`

**managers.4** Where do the metric numbers come from (a scorecard report?) and for which dates?

- Why: Recorded each bonus period as location metrics.
- Lands in: `location_metrics.csv`

**managers.5** Who is paid each location's bonus? Can two people both receive it in full, or is it shared?

- Why: Recipients and shares per location, separate from who manages it day to day.
- Lands in: `bonus_pools[].recipients`

**managers.6** Is the bonus discretionary (you decide after the fact) or promised in advance?

- Why: Promised bonuses for non-exempt staff belong in the overtime regular rate.
- Lands in: `bonus_pools[].include_in_regular_rate`

## One-off pay

**adjustments.1** How do one-off items happen today: signing bonuses, referral bonuses, back pay, reimbursements?

- Why: Each one is an adjustments row naming who approved it, so it survives a rebuild and shows in the audit trail.
- Lands in: `adjustments.csv`

**adjustments.2** What pay type names do those use in your payroll system? Are reimbursements non-taxable there?

- Why: A one-off that reuses a regular pay type name gets mixed into the wrong reconciliation.
- Lands in: `pay_codes, adjustments taxable`

**adjustments.3** Who is allowed to approve a one-off payment?

- Why: Recorded on every adjustment line.
- Lands in: `adjustments approved_by`

## Hires, terminations and changes

**people_changes.1** How do you learn about new hires, terminations, leaves and rate changes before payroll?

- Why: Terminated staff still appear in POS reports; new hires may not appear in a report pulled with an old filter.
- Lands in: `roster status, hire_date, termination_date`

**people_changes.2** When someone leaves, how is their final pay handled, and how fast?

- Why: Final-pay deadlines vary by state and can be earlier than the next payday. The run reminds you each time.
- Lands in: `GATE_FINAL_PAY`

**people_changes.3** If someone is active but shows no hours, services or time off, what is usually going on?

- Why: Silence is a warning: a filtered export, a wrong location, or a leave nobody recorded.
- Lands in: `GATE_NO_ACTIVITY`

**people_changes.4** Have you paid anyone off-cycle recently whose activity might show up again in this period's reports?

- Why: Prevents paying the same commission twice.
- Lands in: `adjustments, roster`

## What you hand to the payroll system

**outputs.1** Can you download your payroll system's import template (hours and/or extra pay)? Please share the header row.

- Why: Every connector profile is a starting point; your own template is the truth.
- Lands in: `connectors/<profile>.json`

**outputs.2** Does your payroll system pay hours at the rate it has on file, or do you send the rate?

- Why: If someone's rate changed mid-period, one rate on file cannot pay both; the run warns.
- Lands in: `profile include_rate`

**outputs.3** Should the file be split by location or department?

- Why: Location codes are added to each line when you need them.
- Lands in: `payroll_settings.split_by_location`

**outputs.4** Any company code, batch ID or file naming rule the upload needs?

- Why: Some systems (ADP paydata) reject a file with the wrong name or batch.
- Lands in: `payroll_settings.co_code, batch_suffix`

_87 questions in 15 sections._
