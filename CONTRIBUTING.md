# Contributing

Thank you for helping make payroll less error-prone.

- **Run the tests** before and after a change: `python3 -m unittest discover -s tests`
  (Python 3.10+ and `pip install openpyxl`).
- **A new check comes with a failing test first.** Reproduce the real mistake with the
  small workspace builder in `tests/helpers.py`, then add the gate or check, then add a
  row to `skills/small-business-payroll-prep/references/lessons.md`.
- **Industry packs** live in `skills/small-business-payroll-prep/assets/intake/questions.json`
  (`industries` and the `pack_*` sections). A good pack asks what trips up payroll in
  that industry and says plainly what the engine does not handle yet.
- **Connector profiles** live in `skills/small-business-payroll-prep/assets/connectors/`. Say which
  account template you compared against and when. Never include real employee data.
- **State presets** live in `skills/small-business-payroll-prep/assets/states/`. Cite the official
  source in `notes`; presets always ship with `confirmed_by_owner: false`.
- **Generated files:** after changing `assets/intake/questions.json` or the input specs,
  run `python3 tools/build_docs.py`. The samples are built on demand by
  `scripts/payprep/sample.py` (spa) and `scripts/payprep/sample_retail.py` (retail); change them there
  when the input format changes.
- **No real people.** Sample data, tests and issues must not contain real names, rates,
  emails or identifiers. Redact exports before attaching them to an issue.
- Write in plain language. The people reading the outputs run businesses, not software.
