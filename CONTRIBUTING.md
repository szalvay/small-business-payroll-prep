# Contributing

Thank you for helping make payroll less error-prone.

- **Run the tests** before and after a change: `python3 -m unittest discover -s tests`
  (Python 3.10+ and `pip install openpyxl`).
- **A new check comes with a failing test first.** Reproduce the real mistake with the
  small workspace builder in `tests/helpers.py`, then add the gate or check, then add a
  row to `skills/salon-spa-payroll/references/lessons.md`.
- **Connector profiles** live in `skills/salon-spa-payroll/assets/connectors/`. Say which
  account template you compared against and when. Never include real employee data.
- **State presets** live in `skills/salon-spa-payroll/assets/states/`. Cite the official
  source in `notes`; presets always ship with `confirmed_by_owner: false`.
- **Generated files:** after changing `assets/intake/questions.json` or the input specs,
  run `python3 tools/build_docs.py`. After changing the input format or engine behavior the
  sample relies on, run `python3 tools/make_sample.py`.
- **No real people.** Sample data, tests and issues must not contain real names, rates,
  emails or identifiers. Redact exports before attaching them to an issue.
- Write in plain language. The people reading the outputs run spas, not software.
