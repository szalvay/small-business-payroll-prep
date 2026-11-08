# State rules

Overtime, minimum wage, sick pay, rest breaks, tip rules and final-pay deadlines are set
by states and sometimes cities. This skill ships a few starting presets in
`assets/states/` and computes what they say. It does not give legal advice, and it does
not keep laws up to date. The owner confirms every state's rules with their payroll
provider or employment counsel and records that by setting `confirmed_by_owner: true`.
Until then, every run carries a warning.

## Presets

| File | What it sets |
|---|---|
| `federal.json` | Overtime after 40 hours in a workweek; regular rate includes commissions and non-discretionary bonuses. Use for states with no stricter rule, then confirm |
| `OR.json` | Weekly overtime after 40. Minimum wage has regional tiers that change every July 1; each location carries its own rate |
| `WA.json` | Weekly overtime after 40. Several cities set higher minimum wages; ask about paid rest breaks for piece-rate staff |
| `CA.json` | Daily overtime after 8 and double time after 12; seventh consecutive day rules; piece-rate staff paid separately for rest, recovery and other non-productive time |

To use one, copy its fields (without `state`) into `state_rules["<STATE>"]` in the config,
show the owner the rule in the Pay Rules Book, and ask them to confirm it.

For a state with no preset, start from `federal.json`, tell the owner plainly that no
state-specific rules are loaded, and ask what their payroll provider says about daily
overtime, minimum wage, sick pay and paid rest breaks.

## What the engine does with them

- **Weekly overtime** per workweek (`company.workweek_start`), adding hours across
  locations of the same employer. A week that straddles two pay periods uses the
  earlier period's hours from `history/weeks.json`; only what was not already paid is
  paid now.
- **Daily overtime and double time** per day when `daily_ot` is set, and the seventh
  consecutive day when `seventh_day_ot` is true. Hours already paid as daily overtime do
  not count again toward weekly overtime.
- **Regular rate.** Overtime premium is half the regular rate (all straight-time
  earnings for the week divided by hours worked) for each overtime hour, and the full
  regular rate for double time. Incentives with `include_in_regular_rate` raise it.
  Monthly incentives are spread back over the weeks of the month and any extra premium
  owed for weeks with overtime is paid as a true-up line.
- **Minimum wage floor** per workweek: straight-time pay must cover hours worked times
  the minimum wage where they were worked.
- **Non-productive time** for piece-rate staff where `piece_rate_nonproductive_separate`
  is true: clocked time that is not service time and not otherwise paid is paid at
  minimum wage. Paid rest and recovery periods use `time_pay` with `basis: regular_rate`.
- A week worked in two states uses the rules of the state where most hours were worked,
  and warns.

## What it does not do

- It does not decide whether someone is exempt, whether a tip pool is lawful, or how
  much sick time someone has accrued. It pays what the rules and inputs say.
- It does not check final-pay deadlines; it reminds the owner whenever someone left
  during the period.
- It does not track minimum wage changes by itself. Add each new rate to the location's
  `min_wage` list with its `effective_from` date as soon as it is announced.
