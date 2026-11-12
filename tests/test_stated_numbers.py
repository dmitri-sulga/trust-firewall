"""Every number the page and the README state, re-computed by tests/tf_model.py.

Each stated value is written here as the page prints it (for example "87.1" for
"87.1%"), and the re-computed value is rounded the way the page rounds it before the
two are compared. A number that does not reproduce fails the run; the test is never
adjusted to fit the page.

Run: python3 -m unittest discover -s tests -v
"""

from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
import os
import re
import unittest

import tf_model as m

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def shown(x, d=0, scale=1):
    """x * scale rounded to d decimals, halves up (what Number.toFixed does for x >= 0)."""
    if isinstance(x, Fraction):
        v = Decimal(x.numerator) * scale / Decimal(x.denominator)
    else:
        v = Decimal(x) * scale  # the exact value of the float
    return str(v.quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP))


def pct(x, d=1):
    return shown(x, d, 100)


CUT = 2.25
_MASTER = m.master(m.RING_SEED)


class GpsDefault(unittest.TestCase):
    """Module 1 as it opens: Teleport at 8 m of noise per axis."""

    @classmethod
    def setUpClass(cls):
        cls.r = m.analyze(m.track("teleport", 8))

    def test_verdict(self):
        self.assertEqual(self.r["verdict"], "FLAGGED")
        self.assertEqual(self.r["reasons"], ["TELEPORT"])

    def test_jump(self):  # "Jump of 4312 m ...; the limit at this noise is 431 m."
        self.assertEqual(shown(self.r["max_jump"]), "4312")
        self.assertEqual(shown(self.r["jump_limit"]), "431")

    def test_noise_estimate(self):  # "σ ≈ 7.2 m (drawn with 8 m; this track reads 10% low)"
        self.assertEqual(shown(self.r["sigma"], 1), "7.2")
        self.assertEqual(m.js_round((self.r["sigma"] / 8 - 1) * 100), -10)
        self.assertEqual(shown(self.r["sigma_v"], 1), "3.7")  # σv ≈ 3.7 km/h

    def test_speed_band(self):  # "5 readings ... σv·√5 / 5 = 1.64 km/h ... 180 ± 6.6 km/h"
        self.assertEqual(self.r["run_len"], 5)
        self.assertEqual(shown(self.r["se"], 2), "1.64")
        self.assertEqual(shown(self.r["band"], 1), "6.6")
        self.assertEqual(shown(self.r["sustained"]), "45")  # "It reads 45 km/h"
        self.assertEqual(self.r["speed_state"], "under")  # "below the band"

    def test_tiles(self):
        self.assertEqual(self.r["cell_miss"], 0)  # Cell mismatch 0
        self.assertEqual((self.r["mock"], self.r["n"]), (0, 70))  # Mock flag 0/70
        self.assertEqual(shown(self.r["raw_peak"]), "140")  # raw peak 140 km/h
        self.assertEqual((self.r["raw_over"], self.r["raw_count"]), (0, 68))  # 0 of 68


class GpsScenarios(unittest.TestCase):
    """'The rule-breaking tracks are ... built past each threshold to show which rule
    fires'; 'Smooth spoof is the attack none of them sees'; the noise slider runs from
    4 to 60 m."""

    def test_slider(self):
        self.assertEqual((m.NOISE_SLIDER[0], m.NOISE_SLIDER[-1]), (4, 60))

    def test_each_rule_fires_at_default_noise(self):
        expect = {"valid": [], "teleport": ["TELEPORT"], "speed": ["SPEED"],
                  "burst": ["SPEED"], "mock": ["MOCK"], "cell": ["CELL"], "smooth": []}
        for sc, reasons in expect.items():
            with self.subTest(scenario=sc):
                self.assertEqual(m.analyze(m.track(sc, 8))["reasons"], reasons)

    def test_smooth_spoof_never_seen(self):
        for nz in m.NOISE_SLIDER:
            with self.subTest(noise=nz):
                self.assertEqual(m.analyze(m.track("smooth", nz))["reasons"], [])

    def test_long_stretch_stays_decidable(self):
        # "a long stretch stays decidable where a short one does not: that is the
        # difference between Implausible speed and Speed burst as you raise the noise"
        for nz in m.NOISE_SLIDER:
            with self.subTest(noise=nz):
                self.assertEqual(m.analyze(m.track("speed", nz))["speed_state"], "over")


class GpsLimits(unittest.TestCase):
    """The 'What is too short or too small' and 'NO DECISION is not a pass' notes."""

    @classmethod
    def setUpClass(cls):
        cls.L = m.gps_limits()

    def test_stretch_and_window(self):  # "(14 s of track)", "more than 500 m"
        self.assertEqual(self.L["stretch_s"], 14)
        self.assertEqual(shown(self.L["window_m"]), "500")

    def test_burst(self):  # "a burst at 300 km/h is called OK if it lasts up to 5 s"
        self.assertEqual(self.L["noise_min"], 4)
        self.assertEqual(self.L["burst_max"], 5)

    def test_hop(self):  # "(420 m at that noise)", "a hop of 410 m ..., 1476 km/h"
        self.assertEqual(shown(self.L["hop_limit"]), "420")
        self.assertEqual(self.L["hop_max"], 410)
        self.assertEqual(shown(self.L["hop_kmh"]), "1476")

    def test_acceleration(self):  # "from 26 to 200 km/h between two fixes, 4.9 g"
        self.assertEqual(shown(self.L["acc_from_kmh"]), "26")
        self.assertEqual(shown(self.L["acc_to_kmh"]), "200")
        self.assertEqual(shown(self.L["acc_g"], 1), "4.9")

    def test_raw_error(self):  # "At 4 m one raw 1-s reading is good to about ± 20 km/h"
        self.assertEqual(shown(self.L["raw_err_kmh"]), "20")

    def test_no_decision(self):  # "FLAGGED at 4 m and gets NO DECISION from 18 m"
        self.assertEqual(self.L["burst_at_min"], "FLAGGED")
        self.assertEqual(self.L["first_no_decision"], 18)
        self.assertTrue(self.L["no_decision_after"])


class RingDefault(unittest.TestCase):
    """Module 2 as it opens: ring sizes 12, proxy 15%, temporal 20%."""

    @classmethod
    def setUpClass(cls):
        cls.s = m.ring_state(_MASTER, *m.DEFAULTS, cut=CUT)

    def test_cut(self):  # "The cut, 2.25, ... (3 of 110 flagged; at the floor itself, 22 of 110)"
        cut, fp_cut, fp_floor, N = m.calibrate_cut(_MASTER)
        self.assertEqual((cut, fp_cut, fp_floor, N), (2.25, 3, 22, 110))
        self.assertEqual(int(m.FP_BUDGET * N), 3)  # "at most 3 of 110"

    def test_population(self):  # "93 ring accounts among 203 (45.8%)", "406 links"
        s = self.s
        self.assertEqual((s["P"], s["n"], s["links"]), (93, 203, 406))
        self.assertEqual(pct(Fraction(s["P"], s["n"])), "45.8")
        self.assertEqual((s["clusters"], s["largest"]), (111, 33))
        self.assertEqual(s["ring_sizes"], [34, 19, 18, 10, 7, 5])

    def test_confusion(self):  # TP 81, FP 3, FN 12
        self.assertEqual((self.s["tp"], self.s["fp"], self.s["fn"]), (81, 3, 12))

    def test_rates(self):  # recall 87.1%, FPR 2.7%, precision 96.4%, "detector holding"
        self.assertEqual(pct(self.s["rec"]), "87.1")
        self.assertEqual(pct(self.s["fpr"]), "2.7")
        self.assertEqual(pct(self.s["prec"]), "96.4")
        self.assertEqual(self.s["state"], "ok")

    def test_auc(self):  # tile 0.93; exact value 950/1023
        self.assertEqual(self.s["auc"], Fraction(950, 1023))
        self.assertEqual(shown(self.s["auc"], 6), "0.928641")
        self.assertEqual(shown(self.s["auc"], 2), "0.93")

    def test_links_per_ring_account(self):  # "15% · 8.4 links per ring account"
        self.assertEqual(shown(self.s["links_per_ring_account"], 1), "8.4")

    def test_budget_sentence(self):  # "3 of the 3 sit in a cluster together with ring accounts"
        self.assertEqual(self.s["attached"], 3)
        self.assertEqual(pct(Fraction(1, self.s["N"])), "0.9")  # one account = 0.9%

    def test_precision_at_three_percent(self):  # "49.7% precision"
        self.assertEqual(pct(m.precision_at_rate(self.s["rec"], self.s["fpr"])), "49.7")

    def test_legit_links_are_pairs_and_chains(self):
        # "legitimate accounts here link only in pairs and chains, which sit on the floor"
        fraud, _, _, links = m.population(_MASTER, *m.DEFAULTS)
        score, comp, _, _ = m.cluster_scores(len(fraud), links)
        ring_comps = {comp[i] for i in range(len(fraud)) if fraud[i]}
        legit_scores = {score[i] for i in range(len(fraud))
                        if comp[i] not in ring_comps and score[i] > 0}
        self.assertEqual(legit_scores, {2.0})

    def test_held_out(self):  # "AUC 0.90–0.98 (median 0.93), recall 87.2% and FPR 1.9% pooled"
        h = m.held_out(*m.DEFAULTS, cut=CUT)
        self.assertEqual(shown(h["auc_min"], 2), "0.90")
        self.assertEqual(shown(h["auc_max"], 2), "0.98")
        self.assertEqual(shown(h["auc_med"], 2), "0.93")
        self.assertEqual(pct(h["rec"]), "87.2")
        self.assertEqual(pct(h["fpr"]), "1.9")

    def test_where_it_breaks(self):
        # "degrading at 20%, first breaks at 55%"; "At 55% ... 2.6 links inside its ring
        # (10.5 with no obfuscation), and 60% of ring accounts show their own fingerprint."
        d = m.strip(_MASTER, m.DEFAULTS[0], m.DEFAULTS[2], CUT)
        self.assertEqual((d["first_warn"], d["first_crit"]), (20, 55))
        self.assertLess(d["pts"][20]["rec"], m.RECALL_HOLD)  # "degrading", not "over FP budget"
        self.assertEqual(shown(d["pts"][55]["links_per_ring_account"], 1), "2.6")
        self.assertEqual(shown(d["pts"][0]["links_per_ring_account"], 1), "10.5")
        self.assertEqual(pct(d["pts"][55]["own_fingerprint"], 0), "60")


class RingScoreClaims(unittest.TestCase):
    def test_floor_pairs_chains_triangles(self):
        # "pairs and chains sit exactly on it [2.0]"; "triangles, which this score puts at 3.0"
        self.assertEqual(m.cluster_scores(2, {(0, 1)})[0], [2.0, 2.0])
        self.assertEqual(set(m.cluster_scores(4, {(0, 1), (1, 2), (2, 3)})[0]), {2.0})
        self.assertEqual(set(m.cluster_scores(3, {(0, 1), (1, 2), (0, 2)})[0]), {3.0})

    def test_temporal_ten_percent_is_one_cohort(self):
        # "The scale starts at 10%: up to there every ring is still a single cohort."
        for share in m.RING_SHARE:
            self.assertEqual(
                m.js_round(0.10 * min(m.COHORT_CAP, share / m.COHORT_MIN_SIZE)), 0)


class RingReadme(unittest.TestCase):
    """README: 'The exact AUC reads 0.93 at the defaults and 0.53 with all three sliders
    at maximum.' The maxima are ring sizes 24, proxy 95%, temporal 90%."""

    def test_auc_defaults_and_max(self):
        self.assertEqual(shown(m.ring_state(_MASTER, *m.DEFAULTS, cut=CUT)["auc"], 2), "0.93")
        s = m.ring_state(_MASTER, 24, 95, 90, cut=CUT)
        self.assertEqual(s["auc"], Fraction(21701, 40920))
        self.assertEqual(shown(s["auc"], 6), "0.530327")
        self.assertEqual(shown(s["auc"], 2), "0.53")


class ReadmeText(unittest.TestCase):
    """The numbers above are written into this file; these tests tie them to the
    README as published, so an edit to either side shows up here."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            cls.text = f.read()

    def test_auc_sentence(self):
        mt = re.search(r"exact AUC reads ([\d.]+) at the defaults and ([\d.]+) with all "
                       r"three sliders at maximum", self.text)
        self.assertIsNotNone(mt)
        self.assertEqual(mt.group(1), shown(m.ring_state(_MASTER, *m.DEFAULTS, cut=CUT)["auc"], 2))
        self.assertEqual(mt.group(2), shown(m.ring_state(_MASTER, 24, 95, 90, cut=CUT)["auc"], 2))

    def test_gps_sentence(self):
        mt = re.search(r"Seven scenarios \(([^)]*)\) and a noise slider from (\d+) to (\d+) m",
                       self.text)
        self.assertIsNotNone(mt)
        self.assertEqual(len(mt.group(1).split(", ")), len(m.SCENARIOS))
        self.assertEqual((int(mt.group(2)), int(mt.group(3))),
                         (m.NOISE_SLIDER[0], m.NOISE_SLIDER[-1]))

    def test_budget_sentence(self):
        self.assertIn("within a budget of 3% of legitimate accounts", self.text)
        self.assertEqual(m.FP_BUDGET, 0.03)


class RingRecordedStates(unittest.TestCase):
    """States the page shows after the sliders move, with the values recorded when the
    page was last reviewed. The browser check reads the same states off the page."""

    def check(self, state, rec, auc2):
        s = m.ring_state(_MASTER, *state, cut=CUT)
        self.assertEqual(pct(s["rec"]), rec)
        self.assertEqual(shown(s["auc"], 2), auc2)
        return s

    def test_proxy_and_temporal_max(self):  # 12/95/90: recall 0.0%, FPR 0.0%, n/a, 0.48
        s = self.check((12, 95, 90), "0.0", "0.48")
        self.assertEqual(s["auc"], Fraction(1945, 4092))
        self.assertEqual(shown(s["auc"], 6), "0.475318")
        self.assertEqual((s["tp"], s["fp"], s["prec"]), (0, 0, None))
        self.assertEqual((s["links"], s["clusters"], s["largest"]), (37, 166, 7))
        h = m.held_out(12, 95, 90, cut=CUT)
        self.assertEqual([shown(h[k], 2) for k in ("auc_min", "auc_max", "auc_med")],
                         ["0.43", "0.53", "0.48"])
        d = m.strip(_MASTER, 12, 90, CUT)
        self.assertEqual((d["first_warn"], d["first_crit"]), (10, 30))
        self.assertEqual(shown(d["pts"][30]["links_per_ring_account"], 1), "2.5")
        self.assertEqual(shown(d["pts"][0]["links_per_ring_account"], 1), "4.9")
        self.assertEqual(pct(d["pts"][30]["own_fingerprint"], 0), "45")

    def test_all_max(self):  # 24/95/90: sizes 68·38·36·20·14·10, 406 accounts, 96 links
        s = self.check((24, 95, 90), "0.0", "0.53")
        self.assertEqual(s["ring_sizes"], [68, 38, 36, 20, 14, 10])
        self.assertEqual((s["n"], s["links"]), (406, 96))
        h = m.held_out(24, 95, 90, cut=CUT)
        self.assertEqual([shown(h[k], 2) for k in ("auc_min", "auc_max", "auc_med")],
                         ["0.46", "0.56", "0.52"])
        self.assertEqual(pct(h["rec"]), "0.1")

    def test_other_extremes(self):
        self.check((2, 15, 20), "27.8", "0.72")
        s = self.check((24, 15, 20), "95.2", "0.96")
        self.assertEqual(pct(s["fpr"]), "2.7")
        self.check((12, 0, 20), "95.7", "0.98")
        self.check((12, 15, 90), "74.2", "0.87")


class CostDefaults(unittest.TestCase):
    """Module 3 at its defaults: N 100,000, π 3.0%, r 70%, f 0.50%, L €400, C €1,200."""

    @classmethod
    def setUpClass(cls):
        cls.c = m.cost(**m.COST_DEFAULTS)

    def test_money(self):
        c = self.c
        self.assertEqual(c["prevented"], 840000)  # +€840,000
        self.assertEqual(c["cost"], 582000)  # −€582,000
        self.assertEqual(c["net"], 258000)  # +€258,000
        self.assertEqual(c["fraud_loss"], 1200000)  # left bar €1,200,000
        self.assertEqual(c["missed_loss"], 360000)  # €360,000 missed
        self.assertEqual(c["missed_loss"] + c["cost"], 942000)  # right bar

    def test_counts(self):  # 2,100 caught; 485 wrongful; precision 81.2%
        self.assertEqual(self.c["caught"], 2100)
        self.assertEqual(self.c["wrongful"], 485)
        self.assertEqual(pct(self.c["precision"]), "81.2")

    def test_break_even(self):  # "0.72% (π·r·L ÷ (1−π)·C)", "C ÷ (C + L) = 75.0%"
        self.assertEqual(pct(self.c["break_even_fpr"], 2), "0.72")
        self.assertGreater(self.c["break_even_fpr"], Fraction(5, 1000))  # slider "below it"
        self.assertEqual(pct(self.c["break_even_precision"]), "75.0")

    def test_formula_terms(self):  # "100,000 × 3.0% × 70% × €400 − 100,000 × 97.0% × 0.50% × €1,200"
        self.assertEqual(pct(1 - Fraction("3.0") / 100), "97.0")


if __name__ == "__main__":
    unittest.main()
