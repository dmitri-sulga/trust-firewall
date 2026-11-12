"""Print, as JSON, what the page should display in every state the browser check visits.

Values come from tests/tf_model.py and are rounded the way the page rounds them.
Used by tests/displayed.mjs; run on its own to inspect: python3 tests/expected.py
"""

from fractions import Fraction
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tf_model as m  # noqa: E402
from test_stated_numbers import shown, pct  # noqa: E402

CUT = 2.25
GPS_STATES = [(sc, nz) for sc in m.SCENARIOS for nz in m.NOISE_SLIDER]
RING_STATES = [m.DEFAULTS, (12, 95, 90), (24, 95, 90), (2, 15, 20), (24, 15, 20),
               (12, 0, 20), (12, 15, 90)] + [(12, x, 20) for x in m.PROXY_SLIDER if x != 15]
COST_STATES = [
    m.COST_DEFAULTS,
    {"N": 1000000, "prev_pct": "10", "recall_pct": 100, "fpr_pct": "5", "L": 2000, "C": 5000},
]


def gps():
    out = []
    for sc, nz in GPS_STATES:
        r = m.analyze(m.track(sc, nz))
        out.append({
            "scenario": sc, "noise": nz, "verdict": r["verdict"], "reasons": r["reasons"],
            "sustained": shown(r["sustained"]), "run_len": r["run_len"],
            "band": shown(r["band"], 1), "se": shown(r["se"], 2),
            "max_jump": shown(r["max_jump"]), "jump_limit": shown(r["jump_limit"]),
            "cell_miss": r["cell_miss"], "mock": f'{r["mock"]}/{r["n"]}',
            "sigma": shown(r["sigma"], 1), "sigma_v": shown(r["sigma_v"], 1),
            "raw_peak": shown(r["raw_peak"]), "raw_over": r["raw_over"],
            "raw_count": r["raw_count"],
        })
    return out


def gps_limits():
    L = m.gps_limits()
    return {
        "stretch_s": L["stretch_s"], "window_m": shown(L["window_m"]),
        "noise_min": L["noise_min"], "burst_max": L["burst_max"],
        "hop_limit": shown(L["hop_limit"]), "hop_max": str(L["hop_max"]),
        "hop_kmh": shown(L["hop_kmh"]), "acc_from": shown(L["acc_from_kmh"]),
        "acc_to": shown(L["acc_to_kmh"]), "acc_g": shown(L["acc_g"], 1),
        "raw_err": shown(L["raw_err_kmh"]), "at_min": L["burst_at_min"],
        "first_no_decision": L["first_no_decision"], "all_after": L["no_decision_after"],
    }


def ring():
    M = m.master(m.RING_SEED)
    cut, cal_fp, cal_floor, cal_n = m.calibrate_cut(M)
    out = []
    for st in RING_STATES:
        s = m.ring_state(M, *st, cut=cut)
        h = m.held_out(*st, cut=cut)
        d = m.strip(M, st[0], st[2], cut)
        flagged = s["tp"] + s["fp"]
        if not flagged:
            prec3 = None
        elif s["fp"] == 0:
            bound = min(Fraction(1), Fraction(3, s["N"]))
            prec3 = {"bound": pct(bound), "prec": pct(m.precision_at_rate(s["rec"], bound))}
        else:
            prec3 = {"prec": pct(m.precision_at_rate(s["rec"], s["fpr"]))}
        fw, fc = d["first_warn"], d["first_crit"]
        unit_x = 0 if fc == 0 else (fc if fc is not None else m.PROXY_SLIDER[-1])
        out.append({
            "state": list(st),
            "rec": pct(s["rec"]), "fpr": pct(s["fpr"]),
            "prec": None if s["prec"] is None else pct(s["prec"]),
            "auc": shown(s["auc"], 2), "status": s["state"],
            "over_budget": s["fpr"] > Fraction(3, 100),
            "tp": s["tp"], "fp": s["fp"], "fn": s["fn"], "clusters": s["clusters"],
            "largest": s["largest"], "accounts": s["n"], "links": s["links"],
            "P": s["P"], "N": s["N"], "share": pct(Fraction(s["P"], s["n"])),
            "sizes": " · ".join(map(str, s["ring_sizes"])),
            "links_per": shown(s["links_per_ring_account"], 1),
            "held": [shown(h["auc_min"], 2), shown(h["auc_max"], 2), shown(h["auc_med"], 2),
                     pct(h["rec"]), pct(h["fpr"])],
            "prec3": prec3, "attached": s["attached"],
            "one_account": pct(Fraction(1, s["N"])),
            "strip": {
                "first_warn": fw,
                "warn_kind": None if fw is None else
                ("over FP budget" if d["pts"][fw]["rec"] >= m.RECALL_HOLD else "degrading"),
                "first_crit": fc,
                "unit_x": unit_x,
                "unit_links": shown(d["pts"][unit_x]["links_per_ring_account"], 1),
                "zero_links": shown(d["pts"][0]["links_per_ring_account"], 1),
                "unit_own": pct(d["pts"][unit_x]["own_fingerprint"], 0),
            },
        })
    return {"cut": shown(cut, 2), "cal": [cal_fp, cal_n, cal_floor, cal_n],
            "allowed": int(m.FP_BUDGET * cal_n), "states": out}


def eur(v, signed=False):
    r = m.js_round(v) if v >= 0 else -m.js_round(-v)
    s = ("−" if r < 0 else "") + "€" + f"{abs(r):,}"
    return ("+" + s) if signed and r > 0 else s


def count(v):
    return shown(v, 1) if v < 100 else f"{m.js_round(v):,}"


def cost():
    out = []
    for st in COST_STATES:
        c = m.cost(**st)
        out.append({
            "inputs": st,
            "net": eur(c["net"], True), "prevented": eur(c["prevented"], True),
            "cost": eur(-c["cost"]), "caught": count(c["caught"]),
            "wrongful": count(c["wrongful"]), "prec": pct(c["precision"]),
            "pill": "net saving" if c["net"] > 0 else "net loss" if c["net"] < 0 else "break-even",
            "fraud_loss": eur(c["fraud_loss"]), "missed": eur(c["missed_loss"]),
            "break_even_fpr": pct(c["break_even_fpr"], 2) if c["break_even_fpr"] < 1 else None,
            "break_even_prec": pct(c["break_even_precision"]),
        })
    return out


if __name__ == "__main__":
    json.dump({"gps": gps(), "gps_limits": gps_limits(), "ring": ring(), "cost": cost()},
              sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
