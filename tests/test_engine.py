"""Engine tests: every case here is a way real payroll has gone wrong.

Run: python3 -m unittest discover -s tests -v
"""
import copy
import json
import shutil
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from helpers import (BASE, SKILL, Workspace, clock, codes, roster_row, svc, total)

from payprep.audit import audit
from payprep.calc import allocate, calculate
from payprep.config import Config, validate_config
from payprep.inputs import load_inputs
from payprep.period import History, Period

P1 = ("2026-10-01", "2026-10-15")
P2 = ("2026-10-16", "2026-10-31")
LMT = [roster_row("E1", "Ana", "Reyes", "lmt")]
LMT_RATE = [("E1", "lmt", "25.00", "service_hour", "")]
FD = [roster_row("F1", "Dee", "Gram", "fd")]
FD_RATE = [("F1", "fd", "17.00", "hourly", "")]


class Base(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()

    def tearDown(self):
        self.ws.close()

    def build(self, changes):
        self.ws.close()
        self.ws = Workspace(changes)


class PayBasics(Base):
    def test_piece_rate_and_minimum_wage_time(self):
        pdir = self.ws.period(*P1, LMT, LMT_RATE, files={
            "services": [svc("E1", "2026-10-05", 6), svc("E1", "2026-10-06", 4)],
            "time_entries": [clock("E1", "2026-10-05", 2, category="lobby")],
            "tips": [{"employee_id": "E1", "location": "A", "date": "2026-10-05", "tip_type": "card", "amount": "40"}]})
        out = self.ws.run(pdir)
        self.assertEqual(out["status"], "ALL CLEAR", out["reasons"])
        self.assertEqual(total(out, "E1", "service_wages"), D("250.00"))
        self.assertEqual(total(out, "E1", "lobby"), D("30.00"))
        self.assertEqual(total(out, "E1", "card_tips"), D("40.00"))

    def test_weekly_overtime_is_per_week_not_per_period(self):
        # 45 hours one week and 35 the next is 5 hours of overtime, even though the period totals 80
        days1 = ["2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"]
        days2 = ["2026-10-11", "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15"]
        rows = [clock("F1", d, 9) for d in days1] + [clock("F1", d, 7) for d in days2]
        pdir = self.ws.period(*P1, FD, FD_RATE, files={"time_entries": rows})
        out = self.ws.run(pdir)
        self.assertEqual(total(out, "F1", "overtime", "hours"), D("5.00"))
        self.assertEqual(total(out, "F1", "regular", "hours"), D("75.00"))
        self.assertEqual(total(out, "F1", "overtime"), D("127.50"))
        self.assertEqual(out["audit"]["status"], "PASS")

    def test_boundary_week_overtime_uses_last_period_hours(self):
        # 34.68 hours in the last days of period 1 and 8.85 on the first day of period 2, same workweek
        p1 = [clock("F1", d, "8.67") for d in ("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15")]
        out1 = self.ws.run(self.ws.period(*P1, FD, FD_RATE, files={"time_entries": p1}))
        self.assertEqual(total(out1, "F1", "overtime", "hours"), D("0"))
        out2 = self.ws.run(self.ws.period(*P2, FD, FD_RATE, files={"time_entries": [clock("F1", "2026-10-16", "8.85")]}))
        self.assertEqual(total(out2, "F1", "overtime", "hours"), D("3.53"))
        self.assertEqual(total(out2, "F1", "regular", "hours"), D("5.32"))
        week = next(w for w in out2["result"].weeks if str(w["week_start"]) == "2026-10-11")
        self.assertEqual(week["prior_hours"], D("34.68"))
        self.assertAlmostEqual(float(week["premium_now"]), 30.005, places=3)

    def test_rerunning_a_period_does_not_double_count_history(self):
        p1 = [clock("F1", d, 9) for d in ("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15")]
        pdir1 = self.ws.period(*P1, FD, FD_RATE, files={"time_entries": p1})
        self.ws.run(pdir1)
        self.ws.run(pdir1)  # re-run replaces this period's history instead of adding to it
        out2 = self.ws.run(self.ws.period(*P2, FD, FD_RATE, files={"time_entries": [clock("F1", "2026-10-16", 8)]}))
        self.assertEqual(total(out2, "F1", "overtime", "hours"), D("4.00"))

    def test_multi_location_overtime_same_employer(self):
        rows = [clock("F1", d, 5, loc="A") for d in ("2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08")]
        rows += [clock("F1", d, 4, loc="B") for d in ("2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08")]
        out = self.ws.run(self.ws.period(*P1, FD, FD_RATE, files={"time_entries": rows}))
        self.assertEqual(total(out, "F1", "overtime", "hours"), D("5.00"))

    def test_daily_overtime_and_double_time(self):
        cfg = copy.deepcopy(BASE)
        cfg["locations"][0]["state"] = "CA"
        self.build({"locations": cfg["locations"]})
        out = self.ws.run(self.ws.period(*P1, FD, FD_RATE, files={"time_entries": [clock("F1", "2026-10-05", 13)]}))
        self.assertEqual(total(out, "F1", "overtime", "hours"), D("4.00"))
        self.assertEqual(total(out, "F1", "doubletime", "hours"), D("1.00"))
        self.assertEqual(total(out, "F1", "regular", "hours"), D("8.00"))

    def test_commission_raises_the_overtime_regular_rate(self):
        self.build({"incentives": [{"id": "gc", "source": "sales", "kind": "percent", "pay_code": "gc_commission",
                                    "eligible_roles": ["fd"], "rates": [{"match": "category", "value": "gift_card", "rate": "10"}]}]})
        rows = [clock("F1", d, 9) for d in ("2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08")]
        sales = [{"employee_id": "F1", "location": "A", "date": "2026-10-05", "category": "gift_card", "quantity": "1", "amount": "450"}]
        out = self.ws.run(self.ws.period(*P1, FD, FD_RATE, files={"time_entries": rows, "sales": sales}))
        self.assertEqual(total(out, "F1", "gc_commission"), D("45.00"))
        # $45 over 45 hours lifts the regular rate by $1; 5 OT hours owe an extra 0.5 x $1 x 5 = $2.50
        self.assertEqual(total(out, "F1", "ot_premium"), D("2.50"))
        self.assertEqual(out["audit"]["status"], "PASS")

    def test_mid_period_rate_change(self):
        rates = LMT_RATE + [("E1", "lmt", "27.00", "service_hour", "2026-10-10")]
        out = self.ws.run(self.ws.period(*P1, LMT, rates, files={
            "services": [svc("E1", "2026-10-05", 4), svc("E1", "2026-10-12", 4)]}))
        self.assertEqual(total(out, "E1", "service_wages"), D("208.00"))

    def test_minimum_wage_shortfall_is_flagged_then_made_up(self):
        rates = [("E1", "lmt", "10.00", "service_hour", "")]
        files = {"services": [svc("E1", "2026-10-05", 4)]}
        out = self.ws.run(self.ws.period(*P1, LMT, rates, files=files))
        self.assertIn("CALC_MINWAGE_SHORT", codes(out["findings"], "FAIL"))
        self.assertEqual(out["status"], "NOT CLEAR")
        self.ws.cfg["company"]["min_wage_makeup"] = "auto"
        self.ws.save_config()
        out = self.ws.run(self.ws.period(*P1, LMT, rates, files=files))
        self.assertEqual(total(out, "E1", "min_wage_makeup"), D("20.00"))

    def test_salary_split_adds_back_to_the_cent(self):
        self.assertEqual(sum(allocate(D("58000") / 24, [D("0.5"), D("0.5")])), D("2416.67"))
        self.build({"manager_allocation": [{"employee_id": "M1", "location_id": "A", "share": "0.5"},
                                           {"employee_id": "M1", "location_id": "B", "share": "0.5"}]})
        roster = LMT + [roster_row("M1", "Max", "Quill", "mgr")]
        rates = LMT_RATE + [("M1", "mgr", "58000", "salary_annual", "")]
        out = self.ws.run(self.ws.period(*P1, roster, rates, files={"services": [svc("E1", "2026-10-05", 4)]}))
        self.assertEqual(total(out, "M1", "salary"), D("2416.67"))


class Incentives(Base):
    def test_tiered_membership_commission_excludes_renewals(self):
        self.build({"incentives": [{"id": "mem", "source": "sales", "kind": "per_unit", "frequency": "monthly",
                                    "pay_code": "membership_commission", "eligible_roles": ["fd"],
                                    "rates": [{"match": "category", "value": "membership"}],
                                    "tiers": [{"from": "1", "to": "5", "rate": "10"}, {"from": "6", "rate": "15"}],
                                    "exclude": [{"field": "item_type", "values": ["renewal"]}]}]})
        sales = [{"employee_id": "F1", "location": "A", "date": f"2026-10-{d:02d}", "category": "membership",
                  "item_type": "new", "quantity": "1", "amount": "79"} for d in range(1, 8)]
        sales.append({"employee_id": "F1", "location": "A", "date": "2026-10-20", "category": "membership",
                      "item_type": "renewal", "quantity": "1", "amount": "79"})
        pdir = self.ws.period(*P2, FD, FD_RATE, files={"time_entries": [clock("F1", "2026-10-20", 8)], "sales": sales},
                              include_monthly=True, monthly_window={"start": "2026-10-01", "end": "2026-10-31"})
        out = self.ws.run(pdir)
        self.assertEqual(total(out, "F1", "membership_commission"), D("80.00"))

    def test_monthly_incentive_waits_for_the_month_end_run(self):
        self.build({"incentives": [{"id": "retail", "source": "sales", "kind": "percent", "frequency": "monthly",
                                    "pay_code": "retail_commission", "eligible_roles": ["esty"],
                                    "rates": [{"match": "category", "value": "retail", "rate": "10"}]}]})
        roster = [roster_row("S1", "Nell", "Fox", "esty")]
        rates = [("S1", "esty", "24", "service_hour", "")]
        out = self.ws.run(self.ws.period(*P1, roster, rates, files={"services": [svc("S1", "2026-10-05", 5, cat="facial")]}))
        self.assertEqual(total(out, "S1", "retail_commission"), D("0"))

    def test_addons_pay_the_employer_rate_and_unknown_codes_stop_the_run(self):
        self.build({"incentives": [{"id": "spiff", "source": "addons", "kind": "per_unit", "pay_code": "enhancements",
                                    "eligible_roles": ["lmt"], "rates": [{"match": "code_prefix", "value": "CBD", "rate": "10"}]}]})
        addons = [{"employee_id": "E1", "location": "A", "date": "2026-10-05", "addon_code": "CBDSCNT: CBD scented",
                   "quantity": "2", "customer_price": "30"},
                  {"employee_id": "E1", "location": "A", "date": "2026-10-05", "addon_code": "AROMA",
                   "quantity": "1", "customer_price": "15"}]
        pdir = self.ws.period(*P1, LMT, LMT_RATE, files={"services": [svc("E1", "2026-10-05", 6)], "addons": addons})
        out = self.ws.run(pdir)
        self.assertEqual(total(out, "E1", "enhancements"), D("20.00"))  # 2 x $10, never the $30 customer price
        self.assertIn("INC_ADDON_UNMAPPED", codes(out["findings"], "WARN"))
        self.assertEqual(out["status"], "NOT CLEAR")
        # the owner decides AROMA pays nothing: a rate of 0 clears it
        self.ws.cfg["incentives"][0]["rates"].append({"match": "code", "value": "AROMA", "rate": "0"})
        self.ws.save_config()
        out = self.ws.run(pdir)
        self.assertEqual(out["status"], "ALL CLEAR", out["reasons"])

    def test_role_gating_and_only_employees(self):
        self.build({"incentives": [{"id": "spiff", "source": "addons", "kind": "per_unit", "pay_code": "enhancements",
                                    "eligible_roles": ["lmt"], "rates": [
                                        {"match": "code", "value": "KTAPE", "rate": "2", "only_employees": ["E2"]},
                                        {"match": "code_prefix", "value": "CUP", "rate": "5"}]}]})
        roster = LMT + [roster_row("E2", "Bo", "Kay", "lmt"), roster_row("S1", "Nell", "Fox", "esty")]
        rates = LMT_RATE + [("E2", "lmt", "25", "service_hour", ""), ("S1", "esty", "24", "service_hour", "")]
        add = lambda e, c: {"employee_id": e, "location": "A", "date": "2026-10-05", "addon_code": c, "quantity": "1"}
        out = self.ws.run(self.ws.period(*P1, roster, rates, files={
            "services": [svc("E1", "2026-10-05", 5), svc("E2", "2026-10-05", 5), svc("S1", "2026-10-05", 5, cat="facial")],
            "addons": [add("E1", "KTAPE"), add("E2", "KTAPE"), add("S1", "CUPCUS")]}))
        self.assertEqual(total(out, "E1", "enhancements"), D("0"))
        self.assertEqual(total(out, "E2", "enhancements"), D("2.00"))
        self.assertEqual(total(out, "S1", "enhancements"), D("0"))
        reasons = {n["reason"] for n in out["result"].incentive_notes}
        self.assertTrue(any("pays only E2" in r for r in reasons))
        self.assertTrue(any("not eligible" in r for r in reasons))

    def test_window_drops_are_reported_and_can_be_acknowledged(self):
        self.build({"incentives": [{"id": "gc", "source": "sales", "kind": "percent", "pay_code": "gc_commission",
                                    "eligible_roles": ["fd"], "rates": [{"match": "category", "value": "gift_card", "rate": "3"}]}]})
        sale = lambda d: {"employee_id": "F1", "location": "A", "date": d, "category": "gift_card", "quantity": "1", "amount": "100"}
        files = {"time_entries": [clock("F1", "2026-10-20", 8)], "sales": [sale("2026-10-20"), sale("2026-10-30")]}
        windows = {"gc": {"start": "2026-10-16", "end": "2026-10-29"}}
        out = self.ws.run(self.ws.period(*P2, FD, FD_RATE, files=files, windows=windows))
        self.assertEqual(total(out, "F1", "gc_commission"), D("3.00"))
        self.assertIn("INC_OUTSIDE_WINDOW", codes(out["findings"], "WARN"))
        self.assertEqual(out["status"], "NOT CLEAR")
        acks = [{"code": "GATE_NO_SOURCES", "by": "T"}, {"code": "GATE_HISTORY_GAP", "by": "T"},
                {"code": "INC_OUTSIDE_WINDOW", "match": "gc:", "by": "Owner", "note": "promo"}]
        out = self.ws.run(self.ws.period(*P2, FD, FD_RATE, files=files, windows=windows, acknowledged_warnings=acks))
        self.assertEqual(out["status"], "ALL CLEAR", out["reasons"])

    def test_refunds_reduce_the_base(self):
        self.build({"incentives": [{"id": "gc", "source": "sales", "kind": "percent", "pay_code": "gc_commission",
                                    "eligible_roles": ["fd"], "rates": [{"match": "category", "value": "gift_card", "rate": "10"}]}]})
        sales = [{"employee_id": "F1", "location": "A", "date": "2026-10-05", "category": "gift_card", "quantity": "1", "amount": "200"},
                 {"employee_id": "F1", "location": "A", "date": "2026-10-06", "category": "gift_card", "quantity": "1", "amount": "50", "refund": "Y"}]
        out = self.ws.run(self.ws.period(*P1, FD, FD_RATE, files={"time_entries": [clock("F1", "2026-10-05", 8)], "sales": sales}))
        self.assertEqual(total(out, "F1", "gc_commission"), D("15.00"))

    def test_location_credit_uses_percent_not_whole_amount(self):
        self.build({"incentives": [{"id": "ovr", "source": "sales", "kind": "percent", "credit": "location", "pay_code": "mgr_override",
                                    "include_in_regular_rate": False, "rates": [{"match": "category", "value": "gift_card", "rate": "1"}],
                                    "recipients": [{"location_id": "A", "employee_id": "M1", "share": "1"}]}]})
        roster = FD + [roster_row("M1", "Max", "Quill", "mgr")]
        rates = FD_RATE + [("M1", "mgr", "2000", "salary_period", "")]
        sales = [{"employee_id": "F1", "location": "A", "date": "2026-10-05", "category": "gift_card", "quantity": "1", "amount": "800"}]
        out = self.ws.run(self.ws.period(*P1, roster, rates, files={"time_entries": [clock("F1", "2026-10-05", 8)], "sales": sales}))
        self.assertEqual(total(out, "M1", "mgr_override"), D("8.00"))

    def test_bonus_pool_pass_fail_weights(self):
        self.build({"bonus_pools": [{"id": "pool", "frequency": "monthly", "pool_per_location": "600", "pay_code": "bonus",
                                     "metrics": [{"id": "a", "numerator": "sold", "denominator": "guests", "threshold": "0.14", "weight": "0.5"},
                                                 {"id": "b", "numerator": "rebooked", "denominator": "guests", "threshold": "0.30", "weight": "0.5"}],
                                     "recipients": [{"location_id": "A", "employee_id": "M1", "share": "1"}]}]})
        roster = FD + [roster_row("M1", "Max", "Quill", "mgr")]
        rates = FD_RATE + [("M1", "mgr", "2000", "salary_period", "")]
        metrics = [{"location": "A", "metric": m, "value": v, "window_start": "2026-10-01", "window_end": "2026-10-31"}
                   for m, v in (("sold", "30"), ("guests", "190"), ("rebooked", "40"))]
        out = self.ws.run(self.ws.period(*P2, roster, rates, files={"time_entries": [clock("F1", "2026-10-20", 8)], "location_metrics": metrics},
                                         include_monthly=True, monthly_window={"start": "2026-10-01", "end": "2026-10-31"}))
        self.assertEqual(total(out, "M1", "bonus"), D("300.00"))

    def test_stipend_respects_effective_dates(self):
        self.build({"stipends": [{"id": "s", "employee_id": "M1", "amount": "250", "effective_through": "2026-09-30"}]})
        roster = FD + [roster_row("M1", "Max", "Quill", "mgr")]
        rates = FD_RATE + [("M1", "mgr", "2000", "salary_period", "")]
        out = self.ws.run(self.ws.period(*P1, roster, rates, files={"time_entries": [clock("F1", "2026-10-05", 8)]}))
        self.assertEqual(total(out, "M1", "stipend"), D("0"))


class Gates(Base):
    def test_activity_after_termination_blocks(self):
        roster = [roster_row("E1", "Ana", "Reyes", "lmt", status="terminated", term="2026-10-03")]
        out = self.ws.run(self.ws.period(*P1, roster, LMT_RATE, files={"services": [svc("E1", "2026-10-05", 4)]}))
        self.assertEqual(out["status"], "BLOCKED")
        self.assertIn("GATE_TERMED", codes(out["findings"], "FAIL"))

    def test_missing_time_off_needs_rows_or_an_attestation(self):
        pdir = self.ws.period(*P1, LMT, LMT_RATE, files={"services": [svc("E1", "2026-10-05", 4)]}, keep_time_off_gate=True)
        out = self.ws.run(pdir)
        self.assertEqual(out["status"], "BLOCKED")
        self.assertIn("GATE_TIMEOFF_MISSING", codes(out["findings"], "FAIL"))

    def test_pos_name_spellings_resolve_to_one_person(self):
        roster = [roster_row("E1", "Ana", "Reyes", "lmt", pos_names="Reyes-Lopez, Ana")]
        rows = [dict(svc("", "2026-10-05", 4), employee_name="ANA: Reyes, Ana"),
                dict(svc("", "2026-10-06", 2), employee_name="Reyes-Lopez, Ana"),
                dict(svc("", "2026-10-07", 1), employee_name="ana reyes")]
        out = self.ws.run(self.ws.period(*P1, roster, LMT_RATE, files={"services": rows}))
        self.assertEqual(total(out, "E1", "service_wages", "hours"), D("7.00"))

    def test_report_totals_must_match_the_mapped_rows(self):
        src = [{"file": "raw/a.xlsx", "report": "Service detail", "location_id": "A", "date_from": P1[0], "date_to": P1[1],
                "mapped_to": "services", "totals": {"service_hours": "12"}}]
        out = self.ws.run(self.ws.period(*P1, LMT, LMT_RATE, files={"services": [svc("E1", "2026-10-05", 4)]}, sources=src))
        self.assertIn("GATE_SOURCE_TOTAL", codes(out["findings"], "FAIL"))

    def test_zero_service_hours_means_a_mis_mapped_column(self):
        out = self.ws.run(self.ws.period(*P1, LMT, LMT_RATE, files={"services": [svc("E1", "2026-10-05", 0), svc("E1", "2026-10-06", 0)]}))
        self.assertIn("GATE_ZERO_SVC_HOURS", codes(out["findings"], "FAIL"))

    def test_unsigned_rules_are_never_all_clear(self):
        self.ws.close()
        self.ws = Workspace(approve=False)
        out = self.ws.run(self.ws.period(*P1, LMT, LMT_RATE, files={"services": [svc("E1", "2026-10-05", 4)]}))
        self.assertEqual(out["status"], "NOT CLEAR")

    def test_unused_acknowledgment_is_reported(self):
        acks = [{"code": "GATE_NO_SOURCES", "by": "T"}, {"code": "GATE_HISTORY_GAP", "by": "T"}, {"code": "GATE_DUP_ROW", "by": "T"}]
        out = self.ws.run(self.ws.period(*P1, LMT, LMT_RATE, files={"services": [svc("E1", "2026-10-05", 4)]}, acknowledged_warnings=acks))
        self.assertIn("ACK_UNUSED", codes(out["findings"], "INFO"))


class Reruns(Base):
    def test_blocked_rerun_removes_the_earlier_all_clear_files(self):
        pdir = self.ws.period(*P1, LMT, LMT_RATE, files={"services": [svc("E1", "2026-10-05", 4)]})
        self.assertEqual(self.ws.run(pdir)["status"], "ALL CLEAR")
        (pdir / "inputs" / "services.csv").write_text("employee_id,location,date,category,quantity,service_hours\n"
                                                     "E1,A,2026-10-05,massage,1,0\n")
        out = self.ws.run(pdir)
        self.assertEqual(out["status"], "BLOCKED")
        left = sorted(p.name for p in (pdir / "output").iterdir())
        self.assertEqual(left, ["evidence.json", "run_summary.md"])

    def test_not_clear_upload_files_say_do_not_upload(self):
        self.ws.close()
        self.ws = Workspace(approve=False)
        out = self.ws.run(self.ws.period(*P1, LMT, LMT_RATE, files={"services": [svc("E1", "2026-10-05", 4)]}))
        self.assertEqual(out["status"], "NOT CLEAR")
        self.assertTrue(all(Path(e["file"]).name.startswith("DO_NOT_UPLOAD_") for e in out["exports"]))

    def test_skipping_the_previous_period_is_a_warning(self):
        acks = [{"code": "GATE_NO_SOURCES", "by": "T"}]
        out = self.ws.run(self.ws.period(*P2, FD, FD_RATE, files={"time_entries": [clock("F1", "2026-10-16", 8)]},
                                         acknowledged_warnings=acks))
        self.assertIn("GATE_HISTORY_GAP", codes(out["findings"], "WARN"))
        self.assertEqual(out["status"], "NOT CLEAR")

    def test_month_end_run_needs_a_monthly_window(self):
        self.build({"incentives": [{"id": "retail", "source": "sales", "kind": "percent", "frequency": "monthly",
                                    "pay_code": "retail_commission", "rates": [{"match": "category", "value": "retail", "rate": "10"}]}]})
        out = self.ws.run(self.ws.period(*P2, FD, FD_RATE, files={"time_entries": [clock("F1", "2026-10-20", 8)]},
                                         include_monthly=True))
        self.assertIn("GATE_NO_MONTHLY_WINDOW", codes(out["findings"], "FAIL"))

    def test_new_period_defaults_the_monthly_window(self):
        import contextlib
        import io
        from payprep.cli import main
        with contextlib.redirect_stdout(io.StringIO()):
            main(["new-period", str(self.ws.root), "--start", "2026-11-16", "--end", "2026-11-30", "--monthly"])
        data = json.loads((self.ws.root / "periods" / "2026-11-16_2026-11-30" / "period.json").read_text())
        self.assertEqual(data["monthly_window"], {"start": "2026-11-01", "end": "2026-11-30"})

    def test_source_window_can_be_a_date_range(self):
        src = [{"file": "raw/s.xlsx", "report": "Sales", "location_id": "A", "date_from": "2026-10-01", "date_to": "2026-10-31",
                "mapped_to": "sales", "window": {"start": "2026-10-01", "end": "2026-10-31"}, "totals": {"amount": "0"}}]
        out = self.ws.run(self.ws.period(*P2, FD, FD_RATE, files={"time_entries": [clock("F1", "2026-10-20", 8)]}, sources=src))
        self.assertNotIn("GATE_SOURCE_DATES", codes(out["findings"]))


class ConfigAndOutputs(Base):
    def test_blank_processor_code_fails_validation(self):
        cfg = copy.deepcopy(BASE)
        cfg["pay_codes"]["card_tips"]["code"] = ""
        self.assertIn("CFG_PAYCODE_BLANK", codes(validate_config(Config(cfg)), "FAIL"))

    def test_missing_pay_code_blocks(self):
        cfg = copy.deepcopy(BASE)
        del cfg["pay_codes"]["lobby"]
        self.assertIn("CFG_PAYCODE", codes(validate_config(Config(cfg)), "FAIL"))

    def test_percent_rates_must_be_percents(self):
        cfg = copy.deepcopy(BASE)
        cfg["incentives"] = [{"id": "x", "source": "sales", "kind": "percent", "pay_code": "gc_commission",
                              "rates": [{"match": "any", "rate": "150"}]}]
        self.assertIn("CFG_INC_PCT", codes(validate_config(Config(cfg)), "FAIL"))

    def test_export_files_carry_every_exportable_dollar(self):
        pdir = self.ws.period(*P1, FD + LMT, FD_RATE + LMT_RATE, files={
            "services": [svc("E1", "2026-10-05", 4)], "time_entries": [clock("F1", "2026-10-05", 8)]})
        out = self.ws.run(pdir)
        self.assertEqual(out["status"], "ALL CLEAR", out["reasons"])
        self.assertTrue(all(Path(e["file"]).exists() for e in out["exports"]))
        self.assertEqual(sum(e["grand_total"] for e in out["exports"]), total(out))

    def test_adp_export_needs_a_company_code(self):
        self.ws.cfg["systems"] = {"payroll": "adp_wfn"}
        self.ws.save_config()
        pdir = self.ws.period(*P1, FD, FD_RATE, files={"time_entries": [clock("F1", "2026-10-05", 8)]})
        out = self.ws.run(pdir)
        self.assertIn("EXPORT_SETTING", codes(out["findings"], "FAIL"))
        self.ws.cfg["systems"] = {"payroll": "adp_wfn", "payroll_settings": {"co_code": "ZZ9"}}
        self.ws.save_config()
        out = self.ws.run(pdir)
        self.assertTrue(Path(out["exports"][0]["file"]).name.startswith("EPIZZ9"))

    def test_hours_at_two_rates_warn_when_the_payroll_file_has_no_rate(self):
        self.ws.cfg["systems"] = {"payroll": "bamboohr"}
        self.ws.save_config()
        rates = FD_RATE + [("F1", "fd", "18.00", "hourly", "2026-10-10")]
        out = self.ws.run(self.ws.period(*P1, FD, rates, files={
            "time_entries": [clock("F1", "2026-10-05", 8), clock("F1", "2026-10-12", 8)]}))
        self.assertIn("EXPORT_RATE_ON_FILE", codes(out["findings"], "WARN"))

    def test_audit_catches_an_injected_error(self):
        pdir = self.ws.period(*P1, LMT, LMT_RATE, files={"services": [svc("E1", "2026-10-05", 4)]})
        period = Period(pdir)
        cfg = Config(json.loads((self.ws.root / "payroll_config.json").read_text()))
        inputs, _ = load_inputs(period, cfg)
        result = calculate(cfg, period, inputs, History(self.ws.root))
        self.assertEqual(audit(cfg, period, inputs, result)["status"], "PASS")
        next(l for l in result.lines if l["pay_code"] == "service_wages")["amount"] += D("1.00")
        self.assertEqual(audit(cfg, period, inputs, result)["status"], "FAIL")


class SampleAndIntake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name) / "ws"
        from payprep.sample import build_sample
        build_sample(self.ws)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sample_runs_all_clear_end_to_end(self):
        import contextlib
        import io
        from payprep.cli import main
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["approve", str(self.ws), "--by", "Sample Owner"]), 0)
            for pid in ("2026-10-01_2026-10-15", "2026-10-16_2026-10-31"):
                pdir = self.ws / "periods" / pid
                self.assertEqual(main(["hris-import", str(pdir), "--roster", str(pdir / "raw/bamboohr_roster_export.csv"),
                                       "--time-off", str(pdir / "raw/bamboohr_time_off_used.csv")]), 0)
                self.assertEqual(main(["run", str(pdir)]), 0, pid)
        weeks = json.loads((self.ws / "history" / "weeks.json").read_text())
        self.assertTrue(weeks)

    def test_intake_workbook_round_trip(self):
        from payprep.config import load_config
        from payprep.intake import build_intake_workbook, compile_intake
        cfg = load_config(self.ws / "payroll_config.json")
        path = build_intake_workbook(Path(self.tmp.name) / "intake.xlsx", cfg)
        data, findings = compile_intake(path)
        self.assertFalse(findings.has_fail, [i["message"] for i in findings.of("FAIL")])
        back = Config(data)
        self.assertFalse(validate_config(back).has_fail, [i["message"] for i in validate_config(back).of("FAIL")])
        for key in ("locations", "roles", "incentives", "bonus_pools", "stipends", "pay_codes"):
            self.assertEqual(len(back.data.get(key) or []), len(cfg.data.get(key) or []), key)
        self.assertEqual(sorted(back.locations), sorted(cfg.locations))
        mem = next(i for i in back.incentives if i["id"] == "memberships")
        self.assertEqual(len(mem["tiers"]), 2)
        self.assertEqual(back.data["intake_notes"][0]["id"], "start.4")
        self.assertEqual(back.company.get("industry"), "healthcare")


class RetailSample(unittest.TestCase):
    def test_retail_sample_runs_all_clear_with_daily_and_cross_store_overtime(self):
        import contextlib
        import io
        from openpyxl import load_workbook
        from payprep.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "retail"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["sample", str(ws), "--kind", "retail"]), 0)
                self.assertEqual(main(["approve", str(ws), "--by", "Sample Owner"]), 0)
                for pid in ("2026-10-05_2026-10-18", "2026-10-19_2026-11-01"):
                    pdir = ws / "periods" / pid
                    self.assertEqual(main(["hris-import", str(pdir), "--roster", str(pdir / "raw/adp_worker_export.csv"),
                                           "--time-off", str(pdir / "raw/adp_time_off.csv")]), 0)
                    self.assertEqual(main(["run", str(pdir)]), 0, pid)
            self.assertTrue((ws / "periods" / "2026-10-19_2026-11-01" / "output" / "EPIHPX01.csv").exists())
            ot = {}
            for pid, end in (("2026-10-05_2026-10-18", "2026-10-18"), ("2026-10-19_2026-11-01", "2026-11-01")):
                wb = load_workbook(ws / "periods" / pid / "output" / f"payroll_review_{end}.xlsx", data_only=True)
                rows = list(wb["Overtime"].iter_rows(values_only=True))
                hdr = next(i for i, r in enumerate(rows) if r and r[0] == "Employee")
                for r in rows[hdr + 1:]:
                    if r and r[0]:
                        ot[(r[0], str(r[2])[:10])] = (r[6], r[7])
            self.assertEqual(ot[("Ford, Nina", "2026-10-12")], (4, 0))       # two stores, one employer
            self.assertEqual(ot[("Torres, Ana", "2026-10-05")], (2, 0))      # California daily overtime
            self.assertEqual(ot[("Torres, Ana", "2026-10-26")], (4, 1))      # and double time after 12
            self.assertEqual(ot[("Menon, Ravi", "2026-10-26")][0], 12)       # seven days in a row


class IntakeIndustries(unittest.TestCase):
    def test_every_industry_has_a_pack_and_filtering_works(self):
        from payprep.intake import build_intake_workbook, industries, load_bank, load_questions
        bank = load_bank()
        ids = [i["id"] for i in industries()]
        self.assertEqual(ids, ["technology", "entertainment", "healthcare", "manufacturing", "financial_services",
                               "energy_utilities", "retail", "education", "government", "other"])
        qids = [q["id"] for s in bank["sections"] for q in s["questions"]]
        self.assertEqual(len(qids), len(set(qids)), "question ids must be unique")
        for sec in bank["sections"]:
            for ind in sec.get("industries", []):
                self.assertIn(ind, ids, sec["id"])
        for ind in ids[:-1]:
            self.assertTrue(any(ind in s.get("industries", []) for s in bank["sections"]), ind)
        retail = {q[1] for q in load_questions("retail")}
        self.assertIn("retail.1", retail)
        self.assertIn("salon_spa.1", retail)
        self.assertNotIn("technology.1", retail)
        self.assertIn("company.1", retail)
        self.assertGreater(len(load_questions()), len(retail))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                build_intake_workbook(Path(tmp) / "x.xlsx", None, "nope")


if __name__ == "__main__":
    unittest.main()
