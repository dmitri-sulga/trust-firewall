"""Independent Python re-computation of the numbers on the Trust Firewall page.

Nothing here imports, evaluates or translates the page's JavaScript at run time.
What is shared with the page is its specification: the seeds, the named constants
and the order in which the generators draw random numbers (stated in the page text
and in the comments next to each constant in index.html). The detectors and the
metrics are re-derived from their definitions, in places by a different route:

* jumps: the largest fix-to-fix distance, checked against 400 m + 3 * sqrt(2) * sigma;
* sustained speed: the average of k windowed readings is computed through the
  identity stated on the page (displacement between the averaged fixes at the two
  ends of the stretch), not by summing reading vectors;
* clusters: a plain union-find of our own;
* AUC: a pairwise Mann-Whitney count over every (ring, legitimate) pair, kept as an
  exact fraction with ties counted one half, not a trapezoid over a ROC curve;
* cost model: exact rational arithmetic.

All data is synthetic. These checks say the page computes what it says it computes;
they say nothing about fraud on real traffic.
"""

from fractions import Fraction
import math

M32 = 0xFFFFFFFF


def js_round(x):
    """Math.round for the non-negative values used here (halves go up)."""
    return math.floor(x + 0.5)


def mulberry32(seed):
    """mulberry32, written on unsigned 32-bit integers; returns a draw in [0, 1)."""
    state = [seed & M32]

    def draw():
        a = (state[0] + 0x6D2B79F5) & M32
        state[0] = a
        t = ((a ^ (a >> 15)) * (a | 1)) & M32
        t = ((t + ((t ^ (t >> 7)) * (t | 61))) & M32) ^ t
        return ((t ^ (t >> 14)) & M32) / 4294967296.0

    return draw


# =====================================================================
# Module 1: GPS physics
# =====================================================================
GPS_SEED = 45079
CITY_W, CITY_H = 6000.0, 4000.0
SPEED_KMH = 180  # limit
WINDOW_S = 10  # speed is displacement over 10 s
SUSTAIN = 5  # stretches of 5 or more consecutive readings
DECIDE_SE = 4  # decide only beyond 4 standard errors
TELEPORT_M = 400
TELEPORT_SIGMAS = 3
TELEPORT_MAX_DT_S = 2
CELL_M = 1500.0  # synthetic square cells of 1.5 km
CELL_TOL = 1.6  # a fix is "far" beyond 1.6 cell sizes from the cell centre
CELL_MIN = 6
MOCK_MIN = 3
N_FIXES = 70
BURST = (28, 14, 200)  # start index, seconds, km/h
NOISE_SLIDER = list(range(4, 61, 2))  # 4..60 m per axis, step 2
G = 9.81


def _gauss(rng):
    u = 0.0
    while u == 0.0:
        u = rng()
    v = 0.0
    while v == 0.0:
        v = rng()
    return math.sqrt(-2.0 * math.log(u)) * math.cos(2.0 * math.pi * v)


def _cell(x, y):
    return (math.floor(x / CELL_M), math.floor(y / CELL_M))


class Fix:
    __slots__ = ("t", "x", "y", "speed", "mock", "cell")

    def __init__(self, t, x, y, speed, mock=False, cell=None):
        self.t, self.x, self.y, self.speed, self.mock = t, x, y, speed, mock
        self.cell = cell if cell is not None else _cell(x, y)


def drive(seed, noise, burst=None):
    """A city drive at 3-16 m/s, one fix per second, Gaussian noise per axis."""
    rng = mulberry32(seed)
    x, y, heading, v = 800.0, 3200.0, -0.5, 9.0
    out = []
    for i in range(N_FIXES):
        fast = burst is not None and burst[0] <= i < burst[0] + burst[1]
        heading += (rng() - 0.5) * (0.03 if fast else 0.18)
        v = min(16.0, max(3.0, v + (rng() - 0.5) * 1.4))
        step = burst[2] / 3.6 if fast else v
        x += math.cos(heading) * step
        y += math.sin(heading) * step
        if x < 300:
            x, heading = 300.0, 0.0
        if x > CITY_W - 300:
            x, heading = CITY_W - 300, math.pi
        if y < 300:
            y, heading = 300.0, math.pi / 2
        if y > CITY_H - 300:
            y, heading = CITY_H - 300, -math.pi / 2
        nx = x + _gauss(rng) * noise
        ny = y + _gauss(rng) * noise
        _gauss(rng)  # the reported accuracy, not used by any rule
        out.append(Fix(float(i), nx, ny, step))
    return out


def track(scenario, noise, seed=GPS_SEED):
    if scenario == "valid":
        return drive(seed, noise)
    if scenario == "teleport":
        fx = drive(seed ^ 0x9E37, noise)
        for f in fx[34:]:
            f.x = min(CITY_W - 200, f.x + 4200)
            f.y = max(200.0, f.y - 900)
            f.cell = _cell(f.x, f.y)
        return fx
    if scenario == "speed":  # held at 62 m/s, turning back at the map edge
        rng = mulberry32(seed ^ 0x5151)
        x, y, heading, v = 500.0, 500.0, 0.4, 62.0
        out = []
        for i in range(N_FIXES):
            heading += (rng() - 0.5) * 0.05
            x += math.cos(heading) * v
            y += math.sin(heading) * v
            if x > CITY_W - 300 or x < 300 or y > CITY_H - 300 or y < 300:
                heading += math.pi * 0.68
                x = max(300.0, min(CITY_W - 300, x))
                y = max(300.0, min(CITY_H - 300, y))
            nx = x + _gauss(rng) * noise
            ny = y + _gauss(rng) * noise
            _gauss(rng)
            out.append(Fix(float(i), nx, ny, v))
        return out
    if scenario == "burst":
        return drive(seed ^ 0x2B2B, noise, BURST)
    if scenario == "mock":
        fx = drive(seed ^ 0x1234, noise)
        for f in fx:
            f.mock = True
        return fx
    if scenario == "cell":
        fx = drive(seed ^ 0xABCD, noise)
        for f in fx[20:50]:
            f.cell = _cell(min(CITY_W - 100, f.x + 3800), min(CITY_H - 100, f.y + 2200))
        return fx
    if scenario == "smooth":
        return drive(seed ^ 0x77A1, noise)
    raise ValueError(scenario)


SCENARIOS = ["valid", "teleport", "speed", "burst", "mock", "cell", "smooth"]


def _median(v):
    s = sorted(v)
    h = len(s) // 2
    return s[h] if len(s) % 2 else (s[h - 1] + s[h]) / 2


def analyze(fx):
    """The four rules as the page describes them. Returns a dict of readouts."""
    n = len(fx)
    # Noise from the track: |second difference|^2 ~ Exp(mean 12 sigma^2).
    sq = [
        (fx[i - 1].x - 2 * fx[i].x + fx[i + 1].x) ** 2
        + (fx[i - 1].y - 2 * fx[i].y + fx[i + 1].y) ** 2
        for i in range(1, n - 1)
    ]
    sigma = math.sqrt(_median(sq) / (12 * math.log(2)))
    sigma_v = math.sqrt(2) * sigma / WINDOW_S * 3.6
    jump_limit = TELEPORT_M + TELEPORT_SIGMAS * math.sqrt(2) * sigma

    steps = [math.hypot(fx[i].x - fx[i - 1].x, fx[i].y - fx[i - 1].y) for i in range(1, n)]
    dts = [fx[i].t - fx[i - 1].t for i in range(1, n)]
    jump = [False] + [s > jump_limit and dt <= TELEPORT_MAX_DT_S for s, dt in zip(steps, dts)]
    raw = [s / dt * 3.6 for s, dt, j in zip(steps, dts, jump[1:]) if not j]

    mock = sum(f.mock for f in fx)
    far = [
        math.hypot(f.x - (f.cell[0] + 0.5) * CELL_M, f.y - (f.cell[1] + 0.5) * CELL_M)
        > CELL_M * CELL_TOL
        for f in fx
    ]
    cell_miss = sum(far)

    # A reading at fix i covers fixes i-10..i; it exists when no jump falls inside.
    has = [i >= WINDOW_S and not any(jump[i - WINDOW_S + 1 : i + 1]) for i in range(n)]
    # Average of readings a..b = (sum of fixes a..b - sum of fixes a-W..b-W) / (k W).
    px = [0.0]
    py = [0.0]
    for f in fx:
        px.append(px[-1] + f.x)
        py.append(py[-1] + f.y)
    best = None
    for a in range(n):
        if not has[a]:
            continue
        b = a
        while b < n and has[b]:
            k = b - a + 1
            if k >= SUSTAIN:
                dx = (px[b + 1] - px[a]) - (px[b + 1 - WINDOW_S] - px[a - WINDOW_S])
                dy = (py[b + 1] - py[a]) - (py[b + 1 - WINDOW_S] - py[a - WINDOW_S])
                speed = math.hypot(dx, dy) / (k * WINDOW_S) * 3.6
                se = max(1e-9, sigma_v * math.sqrt(min(k, WINDOW_S)) / k)
                z = (speed - SPEED_KMH) / se
                if best is None or z > best[0]:
                    best = (z, speed, se, k)
            b += 1
    if best is None:
        state = "band"
        z = speed = se = 0.0
        k = 0
    else:
        z, speed, se, k = best
        state = "over" if z > DECIDE_SE else "under" if z < -DECIDE_SE else "band"

    reasons = []
    if mock >= MOCK_MIN:
        reasons.append("MOCK")
    if any(jump):
        reasons.append("TELEPORT")
    if state == "over":
        reasons.append("SPEED")
    if cell_miss >= CELL_MIN:
        reasons.append("CELL")
    verdict = "FLAGGED" if reasons else ("NO DECISION" if state == "band" else "OK")
    return {
        "verdict": verdict,
        "reasons": reasons,
        "speed_state": state,
        "sigma": sigma,
        "sigma_v": sigma_v,
        "se": se,
        "band": DECIDE_SE * se,
        "run_len": k,
        "sustained": speed,
        "jump_limit": jump_limit,
        "max_jump": max(steps),
        "raw_peak": max(raw, default=0.0),
        "raw_over": sum(r > SPEED_KMH for r in raw),
        "raw_count": len(raw),
        "cell_miss": cell_miss,
        "mock": mock,
        "n": n,
    }


def gps_limits():
    """The 'too short or too small' and 'NO DECISION is not a pass' paragraphs."""
    lo = NOISE_SLIDER[0]
    seed = GPS_SEED ^ 0x2B2B
    burst_max = 0
    for d in range(1, BURST[1] + 1):
        if analyze(drive(seed, lo, (BURST[0], d, 300)))["verdict"] != "OK":
            break
        burst_max = d
    base = drive(seed, lo)
    at = BURST[0]
    ax, ay = base[at + 3].x - base[at - 3].x, base[at + 3].y - base[at - 3].y
    al = math.hypot(ax, ay) or 1.0
    hop_limit = analyze(base)["jump_limit"]
    hop_max = 0
    for h in range(10, 4 * TELEPORT_M + 1, 10):
        moved = [
            f if i < at else Fix(f.t, f.x + ax / al * h, f.y + ay / al * h, f.speed)
            for i, f in enumerate(base)
        ]
        r = analyze(moved)
        if r["verdict"] != "OK":
            break
        hop_max = js_round(r["max_jump"])
    bp = track("burst", lo)
    dv, v_from, v_to = 0.0, 0.0, 0.0
    for i in range(1, len(bp)):
        d = (bp[i].speed - bp[i - 1].speed) / (bp[i].t - bp[i - 1].t)
        if d > dv:
            dv, v_from, v_to = d, bp[i - 1].speed, bp[i].speed
    verdicts = {nz: analyze(track("burst", nz))["verdict"] for nz in NOISE_SLIDER}
    first_abst = next((nz for nz in NOISE_SLIDER if verdicts[nz] == "NO DECISION"), None)
    after = [verdicts[nz] for nz in NOISE_SLIDER if first_abst is not None and nz >= first_abst]
    return {
        "noise_min": lo,
        "stretch_s": WINDOW_S + SUSTAIN - 1,
        "window_m": SPEED_KMH / 3.6 * WINDOW_S,
        "burst_max": burst_max,
        "hop_limit": hop_limit,
        "hop_max": hop_max,
        "hop_kmh": hop_max * 3.6,
        "acc_from_kmh": v_from * 3.6,
        "acc_to_kmh": v_to * 3.6,
        "acc_g": dv / G,
        "raw_err_kmh": math.sqrt(2) * lo * 3.6,
        "burst_at_min": verdicts[lo],
        "first_no_decision": first_abst,
        "no_decision_after": all(v == "NO DECISION" for v in after),
        "burst_verdicts": verdicts,
    }


# =====================================================================
# Module 2: fraud-ring graph
# =====================================================================
RING_SEED = 2954361361
RING_SHARE = [34, 19, 18, 10, 7, 5]
REF_SCALE, MAX_SCALE, RING_REF_TOTAL, LEGIT_REF = 12, 24, 93, 110
BASE_INTRA, PROXY_THIN = 0.96, 0.93
BASE_STEALTH, STEALTH_GAIN, STEALTH_MAX, STEALTH_KEEP = 0.33, 0.55, 0.85, 0.11
TEMP_THIN, COHORT_CAP, COHORT_MIN_SIZE = 0.85, 4, 3
FAKE_MUL, NOISE_FRAC = 0.13, 0.09
CUT_FLOOR, CUT_STEP, FP_BUDGET = 2.0, 0.25, 0.03
RECALL_HOLD, RECALL_BLIND = 0.8, 0.5
RARE_RATE = Fraction(3, 100)
HELD_OUT_SEEDS = 40
DEFAULTS = (12, 15, 20)  # ring-size slider, proxy %, temporal %
PROXY_SLIDER = list(range(0, 96, 5))


def ring_size(r, scale):
    return max(2, js_round(scale * RING_SHARE[r] / REF_SCALE))


def master(seed):
    """Every random number of one population, drawn once for the largest scale."""
    core = mulberry32(seed)
    ext = mulberry32((seed ^ 0x5EEDCA11) & M32)
    rings, ring_max = [], 0
    for r, ref in enumerate(RING_SHARE):
        mx = ring_size(r, MAX_SCALE)
        ring_max += mx
        core()  # drawn by the page for the picture; no metric uses it
        u_st, u_co, pair = [0.0] * mx, [0.0] * mx, {}
        for i in range(ref):
            u_st[i], u_co[i] = core(), core()
            core()  # drawn by the page for the picture; no metric uses it
        for a in range(ref):
            for b in range(a + 1, ref):
                pair[(a, b)] = core()
        for b in range(ref, mx):
            u_st[b], u_co[b] = ext(), ext()
            for a in range(b):
                pair[(a, b)] = ext()
        rings.append((u_st, u_co, pair))
    legit_max = js_round(ring_max * LEGIT_REF / RING_REF_TOTAL)
    for _ in range(LEGIT_REF):
        core()  # drawn by the page for the picture; no metric uses it
    n_ref = js_round(LEGIT_REF * NOISE_FRAC)
    n_max = js_round(legit_max * NOISE_FRAC)
    f_max = js_round((ring_max + legit_max) * FAKE_MUL)
    noise = [(core(), core()) for _ in range(n_ref)] + [(ext(), ext()) for _ in range(n_ref, n_max)]
    fake = [(core(), core()) for _ in range(f_max)]
    return rings, noise, fake


def population(M, scale, proxy_pct, temporal_pct):
    """Returns (is_fraud list, ring index list, stealth list, set of links)."""
    rings, noise, fake = M
    proxy, temporal = proxy_pct / 100, temporal_pct / 100
    fraud, ring_of, stealth, links = [], [], [], set()

    def link(x, y):
        if x != y:
            links.add((min(x, y), max(x, y)))

    stealth_p = min(STEALTH_MAX, BASE_STEALTH + proxy * STEALTH_GAIN)
    for r, (u_st, u_co, pair) in enumerate(rings):
        size, base = ring_size(r, scale), len(fraud)
        cohorts = 1 + js_round(temporal * min(COHORT_CAP, RING_SHARE[r] / COHORT_MIN_SIZE))
        st = [u_st[i] < stealth_p for i in range(size)]
        co = [math.floor(u_co[i] * cohorts) for i in range(size)]
        fraud += [True] * size
        ring_of += [r] * size
        stealth += st
        for b in range(1, size):
            for a in range(b):
                p = BASE_INTRA * (1 - proxy * PROXY_THIN)
                if co[a] != co[b]:
                    p *= 1 - temporal * TEMP_THIN
                if st[a] or st[b]:
                    p *= STEALTH_KEEP
                if pair[(a, b)] < p:
                    link(base + a, base + b)
    first_legit = len(fraud)
    n_legit = js_round(first_legit * LEGIT_REF / RING_REF_TOTAL)
    fraud += [False] * n_legit
    ring_of += [-1] * n_legit
    stealth += [False] * n_legit
    for q in range(js_round(n_legit * NOISE_FRAC)):
        link(first_legit + math.floor(noise[q][0] * n_legit),
             first_legit + math.floor(noise[q][1] * n_legit))
    n = len(fraud)
    for q in range(js_round(proxy * n * FAKE_MUL)):
        link(math.floor(fake[q][0] * n), math.floor(fake[q][1] * n))
    return fraud, ring_of, stealth, links


def cluster_scores(n, links):
    """Connected components; score of every account = 2E / (m - 1) of its cluster."""
    parent = list(range(n))

    def root(x):
        while parent[x] != x:
            x = parent[x]
        return x

    for a, b in links:
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[ra] = rb
    comp = [root(i) for i in range(n)]
    size, edges = {}, {}
    for c in comp:
        size[c] = size.get(c, 0) + 1
    for a, _ in links:
        edges[comp[a]] = edges.get(comp[a], 0) + 1
    score = [0.0 if size[c] < 2 else 2 * edges.get(c, 0) / (size[c] - 1) for c in comp]
    return score, comp, len(size), max(size.values())


def auc_exact(fraud, score):
    """Mann-Whitney: P(ring score > legit score) + 1/2 P(tie), as an exact fraction."""
    pos = [s for s, f in zip(score, fraud) if f]
    neg = [s for s, f in zip(score, fraud) if not f]
    twice = sum(2 if p > q else 1 if p == q else 0 for p in pos for q in neg)
    return Fraction(twice, 2 * len(pos) * len(neg))


def state_of(rec, fpr):
    if rec < RECALL_BLIND:
        return "crit"
    if fpr > FP_BUDGET or rec < RECALL_HOLD:
        return "warn"
    return "ok"


def ring_state(M, scale, proxy_pct, temporal_pct, cut):
    fraud, ring_of, stealth, links = population(M, scale, proxy_pct, temporal_pct)
    score, comp, n_comp, largest = cluster_scores(len(fraud), links)
    P = sum(fraud)
    N = len(fraud) - P
    tp = sum(1 for s, f in zip(score, fraud) if f and s >= cut)
    fp = sum(1 for s, f in zip(score, fraud) if not f and s >= cut)
    ring_comps = {comp[i] for i in range(len(fraud)) if fraud[i]}
    attached = sum(1 for i in range(len(fraud))
                   if not fraud[i] and score[i] >= cut and comp[i] in ring_comps)
    inner = sum(2 for a, b in links if fraud[a] and fraud[b] and ring_of[a] == ring_of[b])
    return {
        "P": P, "N": N, "n": len(fraud), "links": len(links),
        "clusters": n_comp, "largest": largest,
        "tp": tp, "fp": fp, "fn": P - tp, "attached": attached,
        "rec": Fraction(tp, P), "fpr": Fraction(fp, N),
        "prec": Fraction(tp, tp + fp) if tp + fp else None,
        "auc": auc_exact(fraud, score), "state": state_of(tp / P, fp / N),
        "links_per_ring_account": Fraction(inner, P),
        "own_fingerprint": Fraction(sum(stealth[:P]), P),
        "ring_sizes": [ring_size(r, scale) for r in range(6)],
        "scores": score, "fraud": fraud,
    }


def calibrate_cut(M):
    """Lowest step of 0.25 from the floor 2.0 with FP <= 3% on the default population.

    Returns (cut, false positives at the cut, false positives at the floor, N)."""
    st = ring_state(M, *DEFAULTS, cut=CUT_FLOOR)
    k = 0
    while True:
        cut = CUT_FLOOR + k * CUT_STEP
        fp = sum(1 for s, f in zip(st["scores"], st["fraud"]) if not f and s >= cut)
        if Fraction(fp, st["N"]) <= Fraction(3, 100):
            return cut, fp, st["fp"], st["N"]
        k += 1


def held_out(scale, proxy_pct, temporal_pct, cut):
    aucs, tp, fp, P, N = [], 0, 0, 0, 0
    for h in range(1, HELD_OUT_SEEDS + 1):
        s = ring_state(master((RING_SEED + h) & M32), scale, proxy_pct, temporal_pct, cut)
        aucs.append(s["auc"])
        tp, fp, P, N = tp + s["tp"], fp + s["fp"], P + s["P"], N + s["N"]
    aucs.sort()
    mid = len(aucs) // 2
    med = aucs[mid] if len(aucs) % 2 else (aucs[mid - 1] + aucs[mid]) / 2
    return {"auc_min": aucs[0], "auc_max": aucs[-1], "auc_med": med,
            "rec": Fraction(tp, P), "fpr": Fraction(fp, N)}


def strip(M, scale, temporal_pct, cut):
    """'Where it breaks': one state per step of the proxy slider."""
    pts = {x: ring_state(M, scale, x, temporal_pct, cut) for x in PROXY_SLIDER}
    first_warn = next((x for x in PROXY_SLIDER if pts[x]["state"] != "ok"), None)
    first_crit = next((x for x in PROXY_SLIDER if pts[x]["state"] == "crit"), None)
    return {"pts": pts, "first_warn": first_warn, "first_crit": first_crit}


def precision_at_rate(rec, fpr, rate=RARE_RATE):
    return rate * rec / (rate * rec + (1 - rate) * fpr)


# =====================================================================
# Module 3: cost model (exact)
# =====================================================================
COST_DEFAULTS = {"N": 100000, "prev_pct": "3.0", "recall_pct": 70, "fpr_pct": "0.5",
                 "L": 400, "C": 1200}


def cost(N, prev_pct, recall_pct, fpr_pct, L, C):
    pi, r, f = Fraction(prev_pct) / 100, Fraction(recall_pct) / 100, Fraction(fpr_pct) / 100
    fraud, legit = N * pi, N * (1 - pi)
    caught, wrongful = fraud * r, legit * f
    prevented, cost_ = caught * L, wrongful * C
    return {
        "caught": caught, "wrongful": wrongful,
        "prevented": prevented, "cost": cost_, "net": prevented - cost_,
        "precision": caught / (caught + wrongful),
        "fraud_loss": fraud * L, "missed_loss": fraud * L - prevented,
        "break_even_fpr": fraud * r * L / (legit * C),
        "break_even_precision": Fraction(C, C + L),
    }
