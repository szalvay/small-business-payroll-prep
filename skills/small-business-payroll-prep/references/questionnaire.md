# Intake questionnaire

<!-- Generated from assets/intake/questions.json by tools/build_docs.py. Edit the JSON, not this file. -->

This is the owner interview that turns how a business actually pays people into
`payroll_config.json`. The same questions appear on the Questions tab of the intake
workbook (`payroll.py intake-workbook`), so an owner can answer on paper instead.

## How to run the interview

- **One question at a time.** Ask, wait, then ask the next. Owners answer far better
  when they are not handed a wall of questions.
- **Start with the industry and how people are paid** (`start.1`, `start.2`). They
  decide the rest: core sections marked with a pay model are asked only if someone is
  paid that way, and only the industry packs for the owner's industry are asked. Raise
  the industry's known gaps (below) early, so nobody finds out at the end that the tool
  does not cover something they rely on.
- **Skip what does not apply.** A single store with hourly staff and no commission skips
  half of this. Say which sections you are skipping and why.
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


## Industries, what fits and what does not

| Industry | For example | Packs to ask | Not handled yet |
|---|---|---|---|
| **Technology & Software** | software and SaaS companies, IT services and managed service providers, agencies, startups | Technology & Software | Commission accelerators that change the rate once a quota is reached are not computed; enter them as adjustments. Equity, expense reimbursements and quarterly or annual commissions are entered as adjustments. |
| **Entertainment** | venues and theaters, event companies, family entertainment centers, bowling, cinemas, escape rooms, recreation | Entertainment, Fitness and yoga studios, Cafes and counter-service food | Minimum-call guarantees, union scales, fringe and meal penalties are not computed. Tip pools are not computed: the engine pays the tips the export credits to each person. |
| **Healthcare & Life Sciences** | massage, spa and wellness clinics, med spas, chiropractic, physical therapy, dental, home health, fitness and yoga studios | Clinics and practices, Salons, spas, massage and wellness, Fitness and yoga studios | Shift differentials (nights, weekends) are not built in yet; enter them as adjustments. A guaranteed minimum against production is not computed; enter the top-up as an adjustment. Contractors and providers paid through their own professional corporation stay outside this payroll. |
| **Manufacturing & Industrial** | small manufacturers, food and beverage production, print shops, machine and fabrication shops, woodworking, auto repair | Manufacturing & Industrial, Auto repair, detailing and tire shops | Shift differentials are not built in yet; enter them as adjustments. Union scales and fringe are not computed. |
| **Financial Services** | insurance agencies, mortgage and lending offices, tax preparation, accounting and bookkeeping firms, financial advisors | Financial Services | A draw against commission is not computed; enter draws and repayments as adjustments. Chargebacks older than the commission window are entered as adjustments. |
| **Energy & Utilities** | solar and electrical contractors, HVAC, plumbing, propane and fuel delivery, small utilities, field service and home service trades | Energy & Utilities, Field service and home service trades | Prevailing wage and certified payroll reports are not supported. Shift and hazard differentials are not built in yet; per diem and mileage are entered as adjustments. |
| **Retail** | stores, salons and personal services, cafes and counter-service food, automotive service, pet care | Salons, spas, massage and wellness, Retail stores, Cafes and counter-service food, Auto repair, detailing and tire shops | A draw against commission is not computed; enter it as an adjustment. No tip credit: every hour is held to the full minimum wage, so full-service restaurants and bars are not a fit yet. Tip pools are not computed: work out pool shares before mapping. |
| **Education** | private schools, tutoring and test-prep centers, childcare and preschools, music, art and driving schools | Education | Spreading a 10-month salary over 12 months is not computed; the payroll system has to hold that schedule. Split-shift premiums are not computed. |
| **Government & Defense** | small government contractors and defense subcontractors, public-sector service providers | Government & Defense | Prevailing wage (Davis-Bacon, Service Contract Act), fringe benefits and certified payroll reports are not supported. If most of the payroll is covered contract work, this tool is not a fit yet. Hours are tracked by location, not by contract or charge code. |
| **Something else** | any business with hourly, salaried, commissioned, tipped or piece-rate staff | core sections only | Nothing known; note anything that does not fit. |

Within an industry, ask only the packs that match the business (a store skips the cafe pack unless it has a cafe). A business that spans two industries gets both sets of packs.

## Before we start

Have these handy if you can: one or two recent payroll registers, an offer letter or comp plan for each kind of role, the list of reports you pull from your POS, booking, job or time-clock system, and an export of your roster from your HR or payroll system. None of it is required to begin; the interview works from memory and fills gaps later.

**start.1** Which industry are you in: Technology & Software, Entertainment, Healthcare & Life Sciences, Manufacturing & Industrial, Financial Services, Energy & Utilities, Retail, Education, Government & Defense, or something else? What kind of business within it?

- Why: It decides which industry questions follow and which known gaps to raise early. A business that spans two answers both.
- Lands in: `company.industry`

**start.2** How is anyone paid? Name all that apply: hourly, salary, per service, job, class or unit (piece rate), commission or spiffs, tips.

- Why: It decides which core sections come next. Nobody on piece rate means no service-pay or add-on questions; nobody tipped means no tips questions.
- Lands in: `roles[].pay_basis`

**start.3** In one or two sentences, how does payroll work today, from closing the period to people getting paid?

- Why: Shows which steps are manual, who does them and where errors slip in.
- Lands in: `intake_notes`

**start.4** What went wrong in past payrolls that you never want to see again?

- Why: Every past mistake becomes a check. Most real payroll errors are omissions (a missing export, a dropped person), not arithmetic.
- Lands in: `intake_notes; checks`
- Follow up: Was it caught before payday? By whom?

**start.5** Who will run this each period, who reviews the numbers, and who submits to the payroll system?

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

**company.7** How does each location appear in your POS, booking or job reports and in your HR system (names, numbers, codes)?

- Why: So a report labelled '0102' or 'Eastside Salem' lands on the right location.
- Lands in: `locations[].pos_labels, locations[].hris_labels`

**company.8** Does your payroll system track locations as departments, divisions or cost centers? What are the codes?

- Why: Lets the payroll file split pay by location.
- Lands in: `locations[].payroll_code, systems.payroll_settings.split_by_location`

## Systems

The engine never logs into anything. It reads exports you download. These answers decide which export layouts to expect and which payroll file to produce.

**systems.1** Which POS, booking or job-management system do you use? Which reports do you pull for payroll today?

- Why: Each report becomes one canonical input file. Claude maps the columns once and records them.
- Lands in: `systems.pos, systems.pos_reports[]`

**systems.2** Which HR system holds your roster and pay rates (BambooHR, HiBob, Paylocity, ADP, Gusto, a spreadsheet)?

- Why: Picks the HRIS on-ramp that turns its roster and time-off exports into inputs.
- Lands in: `systems.hris`

**systems.3** Which payroll system pays people? Do you upload hours, dollar amounts, or both?

- Why: Picks the outbound file layout.
- Lands in: `systems.payroll, systems.payroll_exports`

**systems.4** Do staff clock in and out? In which system? Do commissioned or piece-rate staff clock too, or only hourly staff?

- Why: Decides whether hours worked come from the clock or from service time plus recorded non-service time.
- Lands in: `roles[].hours_worked_source`

**systems.5** In your payroll system, what are the exact names of each pay type you upload (for example 'Commission', 'Credit Card Tips')?

- Why: An upload with a pay type name that is off by one character is rejected or, worse, mapped to the wrong earning.
- Lands in: `pay_codes{}.code`

**systems.6** Which employee number does your payroll system use? Is it the same as the HR system's?

- Why: The payroll file must carry the number the payroll system knows.
- Lands in: `roster payroll_id`

## Roles and who is who

A role is a way of being paid. Most small businesses have three to six.

**roles.1** List each role (for example sales associate, key holder, barista, technician, instructor, stylist, massage therapist, front desk, manager).

- Why: Every rule hangs off a role.
- Lands in: `roles[]`

**roles.2** For each role: is it paid hourly on the clock, salary, per hour of service or flagged hour, per service, class or job, or a percent of service revenue?

- Why: The pay basis decides which inputs the role needs and how its hours are counted.
- Lands in: `roles[].pay_basis`

**roles.3** Which service categories does each service role perform (massage, facial, haircut, class, repair, cleaning...)?

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

**roles.7** Does anyone hold two roles (for example a sales associate who also covers the cafe, or a massage therapist who is also an esthetician)? At what rate is each paid?

- Why: Their services are split by category and paid at each role's rate; their incentives follow the role that earned them.
- Lands in: `employee_overrides[].secondary_role, rates`

**roles.8** Does anyone work at more than one location? Which is their home location?

- Why: Their hours are combined for overtime across locations of the same employer, and time off is charged to the home location.
- Lands in: `roster home_location`

**roles.9** Does anyone have a pay deal that differs from the standard plan (a ramp, a guaranteed rate, a special spiff)?

- Why: Special deals are the most common source of missed pay. Each one becomes an override or a rate row with dates.
- Lands in: `employee_overrides[], pay_rates effective_from`
- Follow up: Where is it written down? When does it change next?

**roles.10** Are there contractors, booth renters or 1099 instructors? (They are outside this payroll and should not appear in it.)

- Why: Keeps them out of the employee checks.
- Lands in: `intake_notes`

**roles.11** Do names in your POS, booking or job system differ from legal names (nicknames, 'NICK: Last, First', capitalization)?

- Why: Name aliases stop one person appearing as two.
- Lands in: `employee_overrides[].pos_names`

## Service, job and class pay

_Ask only if someone is paid by per service, job, class or unit._

For anyone paid by the hour of service, the job, the class or a share of revenue, this is most of the paycheck. The most damaging error is paying from the wrong column or the wrong report: scheduled time instead of actual, customer price instead of the pay rate.

**service.1** Which report is the single source of truth for service hours, jobs or classes? Is it actual time or flagged hours, never scheduled or bookable time?

- Why: Scheduled or bookable time includes empty gaps and overstates pay. The engine pays only the service-hours column of the service report.
- Lands in: `systems.pos_reports (services)`

**service.2** Does that report total each person's hours and count? (Those totals are recorded each period and checked.)

- Why: If the mapped rows do not add up to the report's own totals, the run stops.
- Lands in: `period.json sources[].totals`

**service.3** What is each person's service, job or class rate, and where is it kept?

- Why: Rates come from the HR export or a rates file, with an effective date for every change.
- Lands in: `pay_rates.csv`

**service.4** Do upgrades, add-on minutes or extensions count as service time?

- Why: Upgrade codes often carry real service minutes that must be paid to the right role.
- Lands in: `intake_notes; services mapping`

**service.5** How are refunds, comps, no-shows and late cancellations handled for pay?

- Why: Refunded lines are negative rows; a paid no-show fee may or may not pay the person who was booked.
- Lands in: `services refund rows, adjustments`

**service.6** When two people share a service or job (couples massage, a two-person crew), who gets credit?

- Why: The report must credit each person their own time.
- Lands in: `intake_notes`

**service.7** Do rates change by step, tenure or performance during the year? How are you told?

- Why: A missed step increase is an underpayment that compounds. Each change is a dated rate row.
- Lands in: `pay_rates effective_from`

**service.8** If someone paid by the service or job clocks in, is the time between clients or jobs paid separately? (Some states require it for piece-rate pay.)

- Why: California-style rules need non-productive time paid on its own.
- Lands in: `state_rules[].piece_rate_nonproductive_separate`

## Time paid outside the main work

_Ask only if someone is paid by per service, job, class or unit._

Lobby or floor time, training, meetings and drive time between jobs. For staff paid by the service, job or class, this time lives in a different report and is where they are most often underpaid.

**time.1** Which kinds of time outside the main work do you pay: lobby or floor time, training, being trained, training others, meetings, cleaning, drive time between jobs, waiting?

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

## Add-ons, upsells and enhancements

_Ask only if someone is paid by per service, job, class or unit._

Add-on reports usually show the customer price. Paying that price instead of your spiff rate is a classic overpayment, and a code nobody listed silently pays nothing.

**addons.1** List every add-on, upsell or enhancement code your system uses and what you pay for each one. Include the ones that pay nothing.

- Why: Every code gets a rate, even $0. A new code with no rate stops the run until you decide.
- Lands in: `incentives[source=addons].rates[]`

**addons.2** Do codes share a prefix (for example CBD, CBD-SCENTED, CBD-UNSCENTED all pay the same)?

- Why: One prefix rule covers the family.
- Lands in: `rates[].match = code_prefix`

**addons.3** Which roles earn add-on pay? Does it pay differently by role?

- Why: Role gating per incentive.
- Lands in: `incentives[].eligible_roles`

**addons.4** Do any add-ons pay only certain people (a certification, a pilot)?

- Why: Restricted rates pay only the named people; everyone else's units are listed as unpaid.
- Lands in: `rates[].only_employees`

**addons.5** Does the add-on report show a code, a description, or 'CODE: Description'?

- Why: Matching works on the code before the colon.
- Lands in: `addons mapping`

## Sales commissions, memberships, packages and gift cards

_Ask only if someone is paid by commission or spiffs._

Sales incentives are often monthly or seasonal. The question is always: which sales, by whom, over which dates, at what rate.

**sales.1** Do you pay commission on product or retail sales? What percent, on which products or categories, to which roles, and is it paid every period or monthly?

- Why: Monthly incentives are paid only on the month-end run, over the whole month.
- Lands in: `incentives (retail)`

**sales.2** How are membership, subscription, loyalty or service-plan sign-ups paid? Per sale, tiered (first 5 at one rate, then another), or a percent?

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

_Ask only if someone is paid by tips._

**tips.1** Are card tips paid on the paycheck in full to the person who earned them?

- Why: Tips pass through untouched and are reconciled to the tips report total.
- Lands in: `R-TIPS`

**tips.2** Do you pool or share tips (for example with the front desk or the kitchen)? On what formula?

- Why: Pooling needs an explicit rule and is regulated; confirm it with your payroll provider or counsel first.
- Lands in: `intake_notes`

**tips.3** Are cash tips declared through payroll? Only reported, or also paid?

- Why: Declared cash tips are usually reported for taxes, not paid again.
- Lands in: `company.cash_tips`

**tips.4** Do you add a service charge to bills? Is any of it paid to staff?

- Why: A service charge is not a tip; if shared it is wages and belongs in the regular rate.
- Lands in: `intake_notes; adjustments`

**tips.5** Which report gives tips per person per day? Does it include prepaid tips or tips on gift cards?

- Why: The tips report is also proof of who worked; someone with tips and no pay is a red flag.
- Lands in: `systems.pos_reports (tips)`

## Sick time, PTO and holidays

A missing time-off export pays nobody's sick hours, and every other check still passes. The engine will not run without either the rows or a statement that nobody took time off.

**timeoff.1** How is sick time paid for each role? (Piece-rate and commissioned staff are often paid at minimum wage or their regular rate; check your state.)

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

**overtime.2** Does anyone ever work more than 40 hours in a week, counting all their time, including at a second location?

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

## Technology & Software

_Industry pack: ask for Technology & Software._

Sales commission, exempt status and on-call time.

**technology.1** How are sales reps paid: a percent of bookings or revenue, a flat amount per deal, or a rate that rises once they hit quota?

- Why: Per-deal and percent commissions are built in. A rate that changes at quota (an accelerator) is not, so it is entered as an adjustment.
- Lands in: `incentives; adjustments`

**technology.2** Is commission earned when the deal is booked, invoiced, or paid by the customer? Is it paid every period, monthly or quarterly?

- Why: Decides which report and dates count. Quarterly payouts are entered as adjustments or a monthly incentive.
- Lands in: `incentives[].frequency; period.json windows`

**technology.3** Which roles are salaried and exempt, and which are hourly (support, QA, interns)? Has each exempt role been checked against the salary threshold where the person works?

- Why: Misclassified hourly work is the most common wage claim in tech; the engine pays overtime only to non-exempt roles.
- Lands in: `roles[].exempt`

**technology.4** Is on-call or after-hours support paid? A flat amount per shift, or hours when paged?

- Why: A flat on-call amount is a stipend; time spent working when paged is hours worked.
- Lands in: `stipends[]; time_pay[]`

**technology.5** Are bonuses promised in advance (a formula or target) or decided after the fact?

- Why: Promised bonuses raise the overtime rate for non-exempt staff.
- Lands in: `bonus_pools[]; adjustments include_in_regular_rate`

**technology.6** Do people work remotely from several states? Which state is each person's work location?

- Why: Minimum wage, overtime and sick leave follow where the work is done.
- Lands in: `locations[]; roster home_location`

## Entertainment

_Industry pack: ask for Entertainment._

Calls, events, venues and gratuities.

**entertainment.1** Are event or venue crew paid hourly, by the call or shift, or a flat day rate?

- Why: Hourly and salary are built in; a flat day rate works as a per-service rate with one service per day worked.
- Lands in: `roles[].pay_basis`

**entertainment.2** Do you guarantee a minimum number of paid hours per call or shift?

- Why: Minimum-call pay is not computed; short calls are topped up in the time export or entered as adjustments.
- Lands in: `intake_notes; adjustments`

**entertainment.3** Are tips, event gratuities or automatic service charges shared with staff? On what formula?

- Why: The engine pays the tips the export credits to each person; shares and service charges are worked out before mapping.
- Lands in: `tips mapping; adjustments`

**entertainment.4** Are any crew covered by a union agreement with its own scales, fringe or meal penalties?

- Why: Union scales, fringe and penalties are not computed; union payroll is not a fit yet.
- Lands in: `intake_notes`

**entertainment.5** Do staff work at more than one venue? Are the venues under the same legal company?

- Why: Hours at venues of the same employer add up for overtime.
- Lands in: `employers[]; company.ot_aggregation`

**entertainment.6** Do you pay spiffs on tickets, memberships, party packages or concessions?

- Why: Each becomes an incentive on sales.
- Lands in: `incentives (sales)`

## Clinics and practices

_Industry pack: ask for Healthcare & Life Sciences._

Per-visit and production pay, guarantees and call.

**clinics.1** Are providers paid hourly, per visit, or on production (a percent of what they bill or collect)?

- Why: Per visit is per-service pay; production is a percent of service revenue.
- Lands in: `roles[].pay_basis`

**clinics.2** If on production: is it on billed charges or collections? Which report, for which dates?

- Why: Collections arrive later than visits; the report and its window must be fixed in advance.
- Lands in: `services mapping; period.json windows`

**clinics.3** Is there a guaranteed minimum (daily or per period) against production?

- Why: A guarantee against production is not computed; the top-up is entered as an adjustment.
- Lands in: `intake_notes; adjustments`

**clinics.4** Do you pay shift differentials (nights, weekends) or on-call and call-back pay?

- Why: Differentials are not built in yet; a flat on-call amount is a stipend; call-back time is hours worked.
- Lands in: `stipends[]; adjustments; intake_notes`

**clinics.5** For home visits: is drive time between patients paid? Is mileage reimbursed?

- Why: Drive time between visits is usually hours worked; mileage is an adjustment.
- Lands in: `time_pay[category=travel]; adjustments`

**clinics.6** Are any providers contractors or paid through their own professional corporation?

- Why: They stay outside this payroll.
- Lands in: `intake_notes`

## Salons, spas, massage and wellness

_Industry pack: ask for Healthcare & Life Sciences, Retail._

The questions that catch most spa payroll mistakes.

**salon_spa.1** Do service providers clock in for the whole shift, or only for services? Is lobby time recorded in the booking system or the time clock?

- Why: Decides where hours worked come from for overtime and the minimum-wage check, and which report holds lobby time.
- Lands in: `roles[].hours_worked_source; time_entries`

**salon_spa.2** Is there a cap on paid lobby hours per month? Who approves going over it?

- Why: A cap that lives only in someone's head gets paid inconsistently.
- Lands in: `intake_notes`

**salon_spa.3** Do any providers do two kinds of services (massage and skin care, hair and nails)? How does the booking system tell their services apart?

- Why: Dual-role providers are paid at a different rate per role; the service code decides which.
- Lands in: `employee_overrides[].secondary_role; roles[].service_categories`

**salon_spa.4** Are membership commissions paid monthly on the month-end run? Does the membership report include renewals and transfers?

- Why: Renewals and transfers often should not pay; a monthly incentive paid every period doubles it.
- Lands in: `incentives (memberships).frequency, exclude`

**salon_spa.5** Do you run seasonal gift card promotions with commission (holidays, Mother's Day)? On exactly which dates?

- Why: Sales outside the window must not pay; the dates go into each period.
- Lands in: `period.json windows`

**salon_spa.6** Does a franchisor or brand scorecard drive manager bonuses? Which numbers and which dates?

- Why: Bonus metrics must come from the same report every month.
- Lands in: `bonus_pools[].metrics; location_metrics.csv`

## Fitness and yoga studios

_Industry pack: ask for Healthcare & Life Sciences, Entertainment._

Class pay, personal training and cancellations.

**fitness.1** How are instructors paid per class: a flat rate per class, a rate by class length, or a base plus an amount per attendee?

- Why: A flat rate per class is per-service pay; an amount per attendee is mapped as add-on units.
- Lands in: `roles[].pay_basis = piece_per_service; incentives (addons)`

**fitness.2** Is there a minimum per class when few people show up, or pay for a class that is cancelled?

- Why: These are easy to miss in a class report.
- Lands in: `intake_notes; adjustments`

**fitness.3** How are personal trainers paid per session: a flat rate, a percent of the session price, or tiers by sessions per month?

- Why: Decides the pay basis and any tiers.
- Lands in: `roles[].pay_basis; incentives[].tiers`

**fitness.4** What happens to pay for no-shows and late cancellations?

- Why: The class or session report must show them the way you pay them.
- Lands in: `services rows; adjustments`

**fitness.5** Do instructors or trainers earn commission on memberships, packages or personal-training sales?

- Why: Each becomes a sales incentive.
- Lands in: `incentives (sales)`

**fitness.6** Are any instructors contractors (1099)?

- Why: Contractors are outside this payroll and must not appear in it.
- Lands in: `intake_notes`

**fitness.7** Is time for subbing, instructor training or required meetings paid? At what rate?

- Why: Time outside classes still counts for overtime and minimum wage.
- Lands in: `time_pay[]`

## Manufacturing & Industrial

_Industry pack: ask for Manufacturing & Industrial._

Production pay, shifts and pre-shift time.

**manufacturing.1** Is anyone paid per unit or piece produced? Which report counts units per person per day?

- Why: Per-unit pay is per-service pay with units as the quantity; every week must still clear minimum wage.
- Lands in: `roles[].pay_basis = piece_per_service; services`

**manufacturing.2** Do you run more than one shift? Do night or weekend shifts pay more?

- Why: Shift differentials are not built in yet; they are entered as adjustments until they are.
- Lands in: `intake_notes; adjustments`

**manufacturing.3** Do you pay production, safety or attendance bonuses? Are they promised in advance?

- Why: Promised bonuses raise the overtime rate for the weeks they cover.
- Lands in: `bonus_pools[]; adjustments include_in_regular_rate`

**manufacturing.4** Is time for pre-shift meetings, putting on protective gear or cleanup recorded and paid?

- Why: That time is usually hours worked; leaving it out is a common wage claim.
- Lands in: `time_pay[]`

**manufacturing.5** Do you use temp agency workers?

- Why: The agency pays them; they stay out of this payroll.
- Lands in: `intake_notes`

**manufacturing.6** Are any workers covered by a union agreement?

- Why: Union scales and fringe are not computed.
- Lands in: `intake_notes`

## Financial Services

_Industry pack: ask for Financial Services._

Production commission, chargebacks and draws.

**financial_services.1** How are producers, agents or loan officers paid: salary, commission on premium, loans or fees, or salary plus commission?

- Why: Decides each role's pay basis and the commission incentives.
- Lands in: `roles[]; incentives (sales)`

**financial_services.2** Do commissions come back out if a policy cancels or a loan does not fund? Within what time?

- Why: Chargebacks are refund rows; ones older than the window are entered as adjustments.
- Lands in: `sales refund rows; adjustments`

**financial_services.3** Do you pay a draw against commission?

- Why: Draws are not computed; they are entered and repaid as adjustments.
- Lands in: `intake_notes; adjustments`

**financial_services.4** Do seasonal staff (for example in tax season) work overtime? Are they hourly?

- Why: Seasonal overtime is the usual surprise.
- Lands in: `roles[]; overtime`

**financial_services.5** Which roles are exempt? Has each been checked against the salary threshold where the person works?

- Why: The engine pays overtime only to non-exempt roles.
- Lands in: `roles[].exempt`

**financial_services.6** Are bonuses tied to production or referrals and promised in advance?

- Why: Promised bonuses raise the overtime rate.
- Lands in: `incentives; bonus_pools[]`

## Energy & Utilities

_Industry pack: ask for Energy & Utilities._

Field crews, standby pay and travel.

**energy_utilities.1** Are field crews paid hourly? Is travel to and between job sites paid?

- Why: Travel between sites is usually hours worked.
- Lands in: `time_pay[category=travel]`

**energy_utilities.2** Do you pay standby, on-call or call-out pay? How much, and how is it recorded?

- Why: A flat standby amount is a stipend or a fixed-rate time category; call-out time worked is hours worked.
- Lands in: `stipends[]; time_pay[basis=fixed]`

**energy_utilities.3** Do you pay per diem or lodging when crews travel?

- Why: Per diem is entered as an adjustment; your payroll provider decides its tax treatment.
- Lands in: `adjustments`

**energy_utilities.4** Do night, weekend or hazard shifts pay more?

- Why: Differentials are not built in yet; they are entered as adjustments.
- Lands in: `intake_notes; adjustments`

**energy_utilities.5** Is any work on public projects that require prevailing wage or certified payroll?

- Why: Prevailing wage and certified payroll reports are not supported.
- Lands in: `intake_notes`

**energy_utilities.6** Do crews work 10- or 12-hour days, or in states with daily overtime?

- Why: Daily overtime and double time come from the state rules.
- Lands in: `state_rules[].daily_ot`

## Field service and home service trades

_Industry pack: ask for Energy & Utilities._

Drive time and per-job pay are where crews get shorted.

**home_services.1** How are technicians or crew paid: hourly, per job, a percent of the job price, or hourly plus a job bonus?

- Why: Decides each role's pay basis.
- Lands in: `roles[].pay_basis`

**home_services.2** Is drive time between jobs paid? What about the trip to the first job and home from the last?

- Why: Drive time between jobs is usually hours worked; it counts for overtime and minimum wage.
- Lands in: `time_pay[category=travel]`

**home_services.3** For team jobs, how is one job's pay split among the crew?

- Why: The engine pays each job row to one person; a split must arrive as one row per person.
- Lands in: `services mapping`

**home_services.4** Do techs earn spiffs or commission on upsells, service agreements or memberships they sell?

- Why: Each becomes an incentive.
- Lands in: `incentives`

**home_services.5** Are callbacks or rework paid, unpaid, or charged back? (Check your state before docking pay.)

- Why: Unpaid rework must be removed in the export or entered as an adjustment.
- Lands in: `adjustments; intake_notes`

**home_services.6** How are mileage, tools, uniforms and on-call time handled?

- Why: Reimbursements are one-off adjustments; paid on-call time is time pay.
- Lands in: `adjustments; time_pay[]`

**home_services.7** Where does job data come from (a job-management app, a spreadsheet)? Does it total hours and revenue per tech?

- Why: Report totals are checked every period.
- Lands in: `systems.pos_reports; period.json sources`

## Retail stores

_Industry pack: ask for Retail._

Commission base, returns and spiffs are where retail payroll goes wrong.

**retail.1** Is commission figured on gross sales, or net of returns, discounts and employee purchases?

- Why: Decides which sales rows count and which are excluded.
- Lands in: `incentives[].exclude; sales mapping`

**retail.2** When an item is returned, does commission come back out? Within how many days, and from a later paycheck if the sale was already paid?

- Why: Returns are refund rows that reduce commission; a return bigger than the period's sales is flagged, never silently ignored.
- Lands in: `sales refund rows; adjustments`

**retail.3** When two associates help one customer, how is the sale split, and does the POS record the split?

- Why: The engine pays each sales row to one person; a split must arrive as two rows.
- Lands in: `sales mapping`

**retail.4** Which spiffs do you pay (protection plans, store card sign-ups, loyalty sign-ups, featured products)? A flat amount each, or a percent?

- Why: Each spiff is its own incentive with its own rate and eligible roles.
- Lands in: `incentives[kind=per_unit]`

**retail.5** Are store managers bonused on sales against target, shrink, payroll percent or audit scores? Where do those numbers come from each month?

- Why: Bonus pools pay on numbers from a monthly report, checked against a threshold.
- Lands in: `bonus_pools[].metrics; location_metrics.csv`

**retail.6** Do you pay a draw against commission (an advance repaid from later commission)?

- Why: Draws are not computed by the engine; they are entered and repaid as one-off adjustments, so the owner must know that up front.
- Lands in: `intake_notes; adjustments`

**retail.7** Do seasonal or temporary staff have different rates or commission plans?

- Why: A different plan needs its own role or employee override.
- Lands in: `roles[]; employee_overrides[]`

**retail.8** Do associates pick up shifts at other stores? Are those stores under the same legal company?

- Why: Hours at stores of the same employer add up for overtime.
- Lands in: `employers[]; company.ot_aggregation`

## Cafes and counter-service food

_Industry pack: ask for Retail, Entertainment._

Tips and break rules carry most of the risk here.

**food_beverage.1** Do you pay tipped staff below the full minimum wage (a tip credit)?

- Why: This tool does not support a tip credit: every hour is held to the full minimum wage. If you take one, it is not a fit yet.
- Lands in: `intake_notes`

**food_beverage.2** Do you pool tips? Who is in the pool, on what formula (hours, points, a percent of sales), and who figures each share today?

- Why: The engine pays the tips the export credits to each person; pool shares must be worked out before mapping.
- Lands in: `tips mapping; intake_notes`

**food_beverage.3** Do you add an automatic service charge? Is any of it paid to staff, and how?

- Why: Service charges are not tips and are often taxed and paid differently.
- Lands in: `adjustments; intake_notes`

**food_beverage.4** Do your states or cities require meal or rest break premiums, split-shift pay or predictive-scheduling pay? Who tracks them today?

- Why: These are not computed; they must be entered as adjustments so they are not forgotten.
- Lands in: `intake_notes; adjustments`

**food_beverage.5** Do some people work two roles at different rates (barista and baker, counter and kitchen)?

- Why: Each role's hours need their own rate.
- Lands in: `employee_overrides[].secondary_role`

## Auto repair, detailing and tire shops

_Industry pack: ask for Retail, Manufacturing & Industrial._

Flat-rate pay and the minimum-wage floor.

**auto_services.1** Are technicians paid flat rate (per flagged or book hour), hourly, or a mix? Which report shows flagged hours per tech?

- Why: Flagged hours are the service hours for flat-rate techs.
- Lands in: `roles[].pay_basis = piece_service_hour; services`

**auto_services.2** Do flat-rate techs clock in for the whole shift?

- Why: Every clocked hour must earn at least minimum wage each week; the engine checks it.
- Lands in: `roles[].hours_worked_source = clock`

**auto_services.3** How are service advisors paid: commission on labor, parts, or both? A percent or tiers?

- Why: Each becomes an incentive on service revenue or sales.
- Lands in: `incentives (services, sales)`

**auto_services.4** Are comebacks or warranty rework paid? At what rate?

- Why: Unpaid rework must be removed in the export or entered as an adjustment.
- Lands in: `services mapping; adjustments`

**auto_services.5** Do you pay spiffs on add-on services (alignments, fluid services, tires) or on product sales?

- Why: Each spiff code needs a rate, even if it is zero.
- Lands in: `incentives (addons, sales)`

**auto_services.6** Are tool allowances or certification bonuses paid through payroll?

- Why: Allowances are stipends; one-time bonuses are adjustments.
- Lands in: `stipends[]; adjustments`

## Education

_Industry pack: ask for Education._

Sessions, stipends and the school year.

**education.1** Are tutors or instructors paid per session or lesson, hourly, or salary?

- Why: Per-session pay is per-service pay.
- Lands in: `roles[].pay_basis`

**education.2** Are salaried teachers paid over 12 months for a 10-month year?

- Why: Spreading pay over the summer is not computed; the payroll system has to hold that schedule.
- Lands in: `intake_notes`

**education.3** Do you pay stipends for extra duties (coaching, clubs, lead teacher)? From when to when?

- Why: Stipends are paid between their start and end dates.
- Lands in: `stipends[]`

**education.4** Is prep, grading or parent-meeting time paid for hourly or per-session staff?

- Why: That time counts for overtime and minimum wage.
- Lands in: `time_pay[]`

**education.5** Are substitutes paid a daily rate or hourly?

- Why: A daily rate works as a per-service rate.
- Lands in: `roles[].pay_basis`

**education.6** For childcare: do split shifts or ratio coverage create overtime or split-shift pay?

- Why: Split-shift premiums are not computed.
- Lands in: `intake_notes`

## Government & Defense

_Industry pack: ask for Government & Defense._

Know the limits first.

**government.1** Is any work on contracts covered by prevailing wage (Davis-Bacon) or the Service Contract Act?

- Why: Prevailing-wage rates, fringe and certified payroll reports are not supported. If most of the payroll is covered work, this tool is not a fit yet.
- Lands in: `intake_notes`

**government.2** Do you need labor hours by contract or charge code for billing?

- Why: Hours are tracked by location (cost center), not by contract; contract labor reports are not produced.
- Lands in: `locations[].payroll_code; intake_notes`

**government.3** Which roles are exempt? Do non-exempt staff ever work unrecorded hours on contracts?

- Why: The engine pays overtime only on recorded hours of non-exempt roles.
- Lands in: `roles[].exempt`

**government.4** Do people work on government sites or in several states?

- Why: Minimum wage and overtime follow where the work is done.
- Lands in: `locations[]; state_rules[]`

**government.5** Do you pay clearance, hazard or shift premiums?

- Why: These are not built in yet; they are entered as adjustments.
- Lands in: `intake_notes; adjustments`

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

_175 questions in 29 sections._
