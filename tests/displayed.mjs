// Headless check: what the page actually displays, compared with the independent
// Python re-computation (tests/expected.py).
//
// Serves index.html over HTTP as GitHub Pages does, opens it in headless Chromium with
// reduced motion, reads the numbers off the DOM at the defaults, then walks every GPS
// scenario across the whole noise slider, a set of ring-graph slider states (extremes
// and the full proxy sweep) and two cost-model states. Every displayed number is
// compared as a string with the Python value rounded the way the page rounds it.
//
// Usage: node tests/displayed.mjs        (PYTHON=python3.12 to choose the interpreter)
// Exit code 1 on any mismatch, page error or console error.
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const EXP = JSON.parse(
  execFileSync(
    process.env.PYTHON || "python3",
    [join(ROOT, "tests", "expected.py")],
    {
      encoding: "utf8",
      maxBuffer: 64 << 20,
    }
  )
);

// ---------- static server ----------
const FILES = {
  "/": ["index.html", "text/html; charset=utf-8"],
  "/index.html": ["index.html", "text/html; charset=utf-8"],
  "/og.png": ["og.png", "image/png"],
};
const server = createServer((req, res) => {
  const f = FILES[req.url.split("?")[0]];
  if (!f) {
    res.writeHead(404);
    res.end();
    return;
  }
  res.writeHead(200, { "content-type": f[1] });
  res.end(readFileSync(join(ROOT, f[0])));
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const URL0 = `http://127.0.0.1:${server.address().port}/`;

// ---------- comparison ----------
const bad = [];
let checks = 0;
function eq(ctx, field, got, want) {
  checks++;
  if (String(got) !== String(want))
    bad.push(
      `${ctx} ${field}: page shows ${JSON.stringify(
        got
      )}, expected ${JSON.stringify(want)}`
    );
}
function grab(ctx, field, text, re, group = 1) {
  const m = re.exec(text || "");
  if (!m) {
    checks++;
    bad.push(
      `${ctx} ${field}: pattern ${re} not found in ${JSON.stringify(text)}`
    );
    return undefined;
  }
  return m[group];
}
const lead = (s) => (/^\s*([−-]?[\d.,]+)/.exec(s) || [])[1];

// ---------- browser ----------
const browser = await chromium.launch();
const ctxB = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  reducedMotion: "reduce",
});
const page = await ctxB.newPage();
page.on("pageerror", (e) => bad.push(`page error: ${e.message}`));
page.on("console", (m) => {
  if (m.type() === "error") bad.push(`console error: ${m.text()}`);
});
await page.goto(URL0, { waitUntil: "load" });
const frames = () =>
  page.evaluate(
    () =>
      new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))
  );
await frames();
const tab = async (id) => {
  await page.click(`#tf-tab-${id}`);
  await frames();
};

// ===================== Module 1: GPS =====================
const readGps = () =>
  page.evaluate(() => {
    const root = document.getElementById("tf_gps-root");
    const v = root.querySelector("#tf_gps-verdict");
    const t = (el, s) =>
      (el.querySelector(s) || { textContent: "" }).textContent;
    return {
      pill: t(v, ".tf_gps-pill").trim(),
      reasons: [...v.querySelectorAll(".tf_gps-reasons li b")].map((b) =>
        b.textContent.trim()
      ),
      reasonText: t(v, ".tf_gps-reasons"),
      abstText: t(v, ".tf_gps-abstmsg"),
      tiles: [...root.querySelectorAll("#tf_gps-metrics .tf_gps-tile")].map(
        (x) => ({
          sub: t(x, ".tf_gps-tsub"),
          thr: t(x, ".tf_gps-tthr"),
          val: t(x, ".tf_gps-tval"),
        })
      ),
      note: t(root, "#tf_gps-fpnote"),
    };
  });
function checkGps(e, d) {
  const c = `GPS ${e.scenario} @${e.noise}m`;
  eq(c, "verdict", d.pill, e.verdict);
  eq(c, "reasons", d.reasons.join(","), e.reasons.join(","));
  const [sp, jp, cell, mock, noise, raw] = d.tiles;
  eq(c, "sustained speed", lead(sp.val), e.sustained);
  eq(
    c,
    "readings in stretch",
    grab(c, "readings", sp.sub, /(\d+) readings/),
    e.run_len
  );
  eq(c, "band", grab(c, "band", sp.thr, /± ([\d.]+) km\/h/), e.band);
  eq(c, "largest jump", lead(jp.val), e.max_jump);
  eq(c, "jump limit", grab(c, "limit", jp.thr, /limit (\d+) m/), e.jump_limit);
  eq(c, "cell mismatch", cell.val.trim(), e.cell_miss);
  eq(c, "mock flag", mock.val.replace(/\s/g, ""), e.mock);
  eq(c, "sigma", lead(noise.val), e.sigma);
  eq(
    c,
    "sigma_v",
    grab(c, "sigma_v", noise.thr, /σv ([\d.]+) km\/h/),
    e.sigma_v
  );
  eq(c, "raw peak", lead(raw.val), e.raw_peak);
  eq(c, "raw over", grab(c, "raw over", raw.thr, /^(\d+) of/), e.raw_over);
  eq(
    c,
    "raw count",
    grab(c, "raw count", raw.thr, /of (\d+) readings/),
    e.raw_count
  );
  eq(
    c,
    "standard error",
    grab(c, "se", d.note, /= ([\d.]+) km\/h and the band/),
    e.se
  );
  // The NO DECISION sentence names both the noise estimated from the fixes and the noise
  // the track was drawn with (the slider value), so it cannot disagree with the slider.
  eq(c, "abstain sentence present", d.abstText !== "", e.verdict === "NO DECISION");
  if (e.verdict === "NO DECISION") {
    eq(
      c,
      "abstain: estimated noise",
      grab(c, "abst sigma", d.abstText, /With noise estimated from the fixes at about (\d+) m/),
      e.sigma0
    );
    eq(
      c,
      "abstain: drawn noise",
      grab(c, "abst drawn", d.abstText, / m \(drawn with (\d+) m\), that average/),
      String(e.noise)
    );
    eq(
      c,
      "abstain: band",
      grab(c, "abst band", d.abstText, /only good to ± ([\d.]+) km\/h/),
      e.band
    );
    eq(
      c,
      "abstain: stretch",
      grab(c, "abst stretch", d.abstText, /hardest reads (\d+) km\/h/),
      e.sustained
    );
  }
  if (e.reasons.includes("TELEPORT")) {
    eq(
      c,
      "reason jump",
      grab(c, "reason jump", d.reasonText, /Jump of (\d+) m/),
      e.max_jump
    );
    eq(
      c,
      "reason limit",
      grab(c, "reason limit", d.reasonText, /noise is (\d+) m\./),
      e.jump_limit
    );
  }
}
const gpsAt = (sc, nz) =>
  page.evaluate(
    ([sc, nz]) => {
      const r = document.getElementById("tf_gps-root");
      const b = r.querySelector(`[data-tf-gps-scn="${sc}"]`);
      if (b.getAttribute("aria-pressed") !== "true") b.click();
      const sl = r.querySelector("#tf_gps-noise");
      if (sl.value !== String(nz)) {
        sl.value = String(nz);
        sl.dispatchEvent(new Event("input", { bubbles: true }));
      }
    },
    [sc, nz]
  );

// Defaults first, untouched: the page opens on Speed burst at 20 m of noise.
const opened = await page.evaluate(() => {
  const r = document.getElementById("tf_gps-root");
  return {
    pressed: [...r.querySelectorAll("[data-tf-gps-scn][aria-pressed=true]")].map(
      (b) => b.getAttribute("data-tf-gps-scn")
    ),
    slider: r.querySelector("#tf_gps-noise").value,
    label: r.querySelector("#tf_gps-noiseval").textContent.replace(/\s/g, ""),
  };
});
eq("GPS opening state", "scenario pressed", opened.pressed.join(","), "burst");
eq("GPS opening state", "noise slider", opened.slider, "20");
eq("GPS opening state", "noise label", opened.label, "20m");
const gpsDefault = EXP.gps.find(
  (e) => e.scenario === "burst" && e.noise === 20
);
checkGps(gpsDefault, await readGps());

// The link preview quotes the ring graph's "Where it breaks" line at the defaults.
{
  const s = EXP.ring.states[0].strip;
  const metas = await page.evaluate(() =>
    ["meta[property='og:description']", "meta[name='twitter:description']"].map(
      (q) => document.querySelector(q).content
    )
  );
  for (const [i, t] of metas.entries()) {
    const c = i ? "twitter:description" : "og:description";
    const mt =
      /ring graph first breaks at (\d+)% proxy obfuscation, where a ring account keeps ([\d.]+) links inside its ring, against ([\d.]+) with none\./.exec(
        t
      ) || [];
    eq(c, "first break % / links at the break / with no obfuscation", mt.slice(1).join(" "),
      [s.first_crit, s.unit_links, s.zero_links].join(" "));
  }
}

const lim = await page.evaluate(() => ({
  bz: document.getElementById("tf_gps-blindzone").textContent,
  ab: document.getElementById("tf_gps-abstain").textContent,
}));
{
  const L = EXP.gps_limits,
    c = "GPS limits";
  eq(
    c,
    "stretch s",
    grab(c, "stretch", lim.bz, /\((\d+) s of track\)/),
    L.stretch_s
  );
  eq(
    c,
    "window m",
    grab(c, "window", lim.bz, /more than (\d+) m \(/),
    L.window_m
  );
  eq(
    c,
    "lowest noise",
    grab(c, "noise", lim.bz, /lowest noise, (\d+) m,/),
    L.noise_min
  );
  eq(
    c,
    "burst s",
    grab(c, "burst", lim.bz, /lasts (?:up to (\d+) s|(1) second)/),
    L.burst_max
  );
  eq(
    c,
    "hop limit",
    grab(c, "hop limit", lim.bz, /jump limit \((\d+) m at that noise\)/),
    L.hop_limit
  );
  eq(
    c,
    "hop m",
    grab(c, "hop", lim.bz, /a hop of (\d+) m in one second/),
    L.hop_max
  );
  eq(
    c,
    "hop km/h",
    grab(c, "hop kmh", lim.bz, /in one second, (\d+) km\/h/),
    L.hop_kmh
  );
  eq(c, "acc from", grab(c, "from", lim.bz, /goes from (\d+) to/), L.acc_from);
  eq(
    c,
    "acc to",
    grab(c, "to", lim.bz, /to (\d+) km\/h between two fixes/),
    L.acc_to
  );
  eq(
    c,
    "acc g",
    grab(c, "g", lim.bz, /between two fixes, ([\d.]+) g/),
    L.acc_g
  );
  eq(
    c,
    "raw error",
    grab(c, "raw", lim.bz, /good to about ± (\d+) km\/h/),
    L.raw_err
  );
  const atMin = grab(
    c,
    "at min",
    lim.ab,
    /Speed burst track is (FLAGGED|OK|NO DECISION) at (\d+) m/
  );
  eq(c, "burst at lowest noise", atMin, L.at_min);
  eq(
    c,
    "NO DECISION from",
    grab(c, "abst", lim.ab, /gets NO DECISION (from|at) (\d+) m/, 2),
    L.first_no_decision
  );
  eq(
    c,
    "NO DECISION all after",
    /gets NO DECISION from/.test(lim.ab),
    L.all_after
  );
}

// Every scenario across the whole noise slider.
for (const e of EXP.gps) {
  await gpsAt(e.scenario, e.noise);
  checkGps(e, await readGps());
}

// ===================== Module 2: ring graph =====================
await tab("m2");
const readRing = () =>
  page.evaluate(() => {
    const q = (id) => {
      const el = document.getElementById(id);
      return el ? el.textContent : null;
    };
    return {
      rec: q("tf_graph-m-rec"),
      fpr: q("tf_graph-m-fpr"),
      prec: q("tf_graph-m-prec"),
      auc: q("tf_graph-m-auc"),
      tp: q("tf_graph-m-tp"),
      fp: q("tf_graph-m-fp"),
      fn: q("tf_graph-m-fn"),
      comps: q("tf_graph-m-comps"),
      big: q("tf_graph-m-big"),
      nodes: q("tf_graph-m-nodes"),
      edges: q("tf_graph-m-edges"),
      cut: q("tf_graph-cut"),
      sizes: q("tf_graph-l-acc"),
      proxy: q("tf_graph-l-proxy"),
      pill: q("tf_graph-health"),
      sentence: q("tf_graph-strip-verdict"),
      unit: q("tf_graph-strip-unit"),
      pop: q("tf_graph-note-pop"),
      budget: q("tf_graph-note-budget"),
    };
  });
const ringAt = async ([acc, proxy, temp]) => {
  await page.evaluate(
    ([acc, proxy, temp]) => {
      for (const [id, v] of [
        ["acc", acc],
        ["proxy", proxy],
        ["temp", temp],
      ]) {
        const el = document.getElementById("tf_graph-s-" + id);
        if (el.value !== String(v)) {
          el.value = String(v);
          el.dispatchEvent(new Event("input", { bubbles: true }));
        }
      }
    },
    [acc, proxy, temp]
  );
  await frames();
};
function checkRing(e, d) {
  const R = EXP.ring,
    c = `Ring ${e.state.join("/")}`;
  eq(c, "recall", d.rec, e.rec + "%");
  eq(c, "FPR", d.fpr, e.fpr + "%");
  eq(c, "precision", d.prec, e.prec === null ? "n/a" : e.prec + "%");
  eq(c, "AUC", d.auc, e.auc);
  eq(c, "TP", d.tp, e.tp);
  eq(c, "FP", d.fp, e.fp);
  eq(c, "FN", d.fn, e.fn);
  eq(c, "clusters", d.comps, e.clusters);
  eq(c, "largest", d.big, e.largest);
  eq(c, "accounts", d.nodes, e.accounts);
  eq(c, "links", d.edges, e.links);
  eq(c, "cut", d.cut, R.cut);
  eq(c, "ring sizes", d.sizes, e.sizes);
  eq(c, "proxy %", grab(c, "proxy", d.proxy, /^(\d+)%/), e.state[1]);
  eq(
    c,
    "links per ring account",
    grab(c, "links", d.proxy, /· ([\d.]+) links per ring account/),
    e.links_per
  );
  const word =
    e.status === "crit"
      ? "detector blind"
      : e.status === "ok"
      ? "detector holding"
      : e.over_budget
      ? "over false-positive budget"
      : "degrading";
  eq(c, "status pill", d.pill, `${word} · recall ${e.rec}% · FPR ${e.fpr}%`);
  // population and held-out line
  const pm =
    /This population: (\d+) ring accounts among (\d+) \(([\d.]+)%\)/.exec(
      d.pop
    ) || [];
  eq(c, "ring accounts", pm[1], e.P);
  eq(c, "population", pm[2], e.accounts);
  eq(c, "fraud share", pm[3], e.share);
  const hm =
    /AUC ([\d.]+)–([\d.]+) \(median ([\d.]+)\), recall ([\d.]+)% and FPR ([\d.]+)% pooled/.exec(
      d.pop
    ) || [];
  eq(c, "held-out", hm.slice(1).join(" "), e.held.join(" "));
  if (e.prec3 === null)
    eq(c, "nothing flagged", /Nothing is flagged/.test(d.pop), true);
  else if (e.prec3.bound) {
    eq(
      c,
      "FPR bound",
      grab(c, "bound", d.pop, /below about ([\d.]+)%/),
      e.prec3.bound
    );
    eq(
      c,
      "precision bound",
      grab(c, "pb", d.pop, /precision as low as ([\d.]+)%/),
      e.prec3.prec
    );
  } else
    eq(
      c,
      "precision at 3%",
      grab(c, "p3", d.pop, /would give ([\d.]+)% precision/),
      e.prec3.prec
    );
  // false-positive budget note
  const bm =
    /at most (\d+) of (\d+)\. Now: (\d+) of (\d+) \(([\d.]+)%\), (within|over) budget/.exec(
      d.budget
    ) || [];
  eq(
    c,
    "budget",
    bm.slice(1).join(" "),
    [
      R.allowed,
      R.cal[1],
      e.fp,
      e.N,
      e.fpr,
      e.over_budget ? "over" : "within",
    ].join(" ")
  );
  if (e.fp)
    eq(
      c,
      "attached",
      grab(c, "attached", d.budget, /; (\d+) of the \d+ sit/),
      e.attached
    );
  const cm =
    /The cut, ([\d.]+), .*\((\d+) of (\d+) flagged; at the floor itself, (\d+) of (\d+)\)/.exec(
      d.budget
    ) || [];
  eq(c, "calibration", cm.slice(1).join(" "), [R.cut, ...R.cal].join(" "));
  eq(
    c,
    "one account",
    grab(c, "one", d.budget, /already ([\d.]+)% of the legitimate/),
    e.one_account
  );
  // "Where it breaks"
  const s = e.strip;
  if (s.first_crit === 0) {
    eq(c, "strip sentence", d.sentence, "blind with no obfuscation");
    const um =
      /With no obfuscation a ring account keeps ([\d.]+) links inside its ring, and (\d+)% of ring/.exec(
        d.unit
      ) || [];
    eq(
      c,
      "strip unit",
      um.slice(1).join(" "),
      [s.unit_links, s.unit_own].join(" ")
    );
  } else {
    const showWarn =
      s.first_warn !== null &&
      (s.first_crit === null || s.first_warn < s.first_crit);
    const wm = /^(over FP budget|degrading) at (\d+)%, /.exec(d.sentence);
    eq(
      c,
      "strip warn",
      wm ? `${wm[1]} ${wm[2]}` : null,
      showWarn ? `${s.warn_kind} ${s.first_warn}` : null
    );
    eq(
      c,
      "strip breaks",
      grab(
        c,
        "breaks",
        d.sentence,
        /(first breaks at|does not break by|holds to) (\d+)%/,
        2
      ),
      s.unit_x
    );
    eq(
      c,
      "strip breaks kind",
      /first breaks at/.test(d.sentence),
      s.first_crit !== null
    );
    const um =
      /^At (\d+)%(?:, where it first breaks,)? a ring account keeps ([\d.]+) links inside its ring \(([\d.]+) with no obfuscation\), and (\d+)% of ring/.exec(
        d.unit
      ) || [];
    eq(
      c,
      "strip unit",
      um.slice(1).join(" "),
      [s.unit_x, s.unit_links, s.zero_links, s.unit_own].join(" ")
    );
  }
}
checkRing(EXP.ring.states[0], await readRing()); // defaults, untouched
for (const e of EXP.ring.states.slice(1)) {
  await ringAt(e.state);
  checkRing(e, await readRing());
}
await ringAt(EXP.ring.states[0].state);
checkRing(EXP.ring.states[0], await readRing()); // back to defaults

// ===================== Module 3: cost model =====================
await tab("m3");
const readCost = () =>
  page.evaluate(() => {
    const q = (id) => document.getElementById(id).textContent;
    return {
      net: q("tf_pnl-net"),
      prevented: q("tf_pnl-savings"),
      cost: q("tf_pnl-fpcost"),
      caught: q("tf_pnl-caught"),
      wrongful: q("tf_pnl-fpevents"),
      prec: q("tf_pnl-prec"),
      pill: document.querySelector("#tf_pnl-netpill .tf_pnl-pill-txt")
        .textContent,
      formula: q("tf_pnl-formula"),
      be: q("tf_pnl-breakeven"),
      bar: q("tf_pnl-barcap"),
    };
  });
const costAt = (i) =>
  page.evaluate((i) => {
    for (const [id, v] of [
      ["pop", i.N],
      ["prev", i.prev_pct],
      ["recall", i.recall_pct],
      ["fpr", i.fpr_pct],
      ["loss", i.L],
      ["fcost", i.C],
    ]) {
      const el = document.getElementById("tf_pnl-s-" + id);
      el.value = String(v);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }, i);
function checkCost(e, d, k) {
  const c = `Cost state ${k}`;
  eq(c, "net", d.net, e.net);
  eq(c, "prevented", d.prevented, e.prevented);
  eq(c, "wrongful cost", d.cost, e.cost);
  eq(c, "caught", d.caught, e.caught);
  eq(c, "wrongful blocks", d.wrongful, e.wrongful);
  eq(c, "precision", d.prec, e.prec + "%");
  eq(c, "pill", d.pill, e.pill);
  eq(
    c,
    "formula prevented",
    grab(c, "f1", d.formula, /= (€[\d,]+) − €/),
    e.prevented.replace("+", "")
  );
  eq(c, "formula net", grab(c, "f2", d.formula, /= ([+−]?€[\d,]+)$/), e.net);
  if (e.break_even_fpr !== null)
    eq(
      c,
      "break-even FPR",
      grab(c, "be", d.be, /at these inputs: ([\d.]+)%/),
      e.break_even_fpr
    );
  eq(
    c,
    "break-even precision",
    grab(c, "bp", d.be, /C ÷ \(C \+ L\) = ([\d.]+)%/),
    e.break_even_prec
  );
  const bm =
    /no detector, (€[\d,]+)\. Right bar: fraud the detector misses, (€[\d,]+), plus the cost of its wrongful blocks, (€[\d,]+)\. The gap between the bars is the net effect, ([+−]?€[\d,]+)\./.exec(
      d.bar
    ) || [];
  eq(
    c,
    "bar caption",
    bm.slice(1).join(" "),
    [e.fraud_loss, e.missed, e.cost.replace("−", ""), e.net].join(" ")
  );
}
checkCost(EXP.cost[0], await readCost(), 0); // defaults, untouched
for (let k = 1; k < EXP.cost.length; k++) {
  await costAt(EXP.cost[k].inputs);
  checkCost(EXP.cost[k], await readCost(), k);
}
await costAt(EXP.cost[0].inputs);
checkCost(EXP.cost[0], await readCost(), 0);

await browser.close();
server.close();
console.log(
  JSON.stringify({
    checks,
    mismatches: bad.length,
    gpsStates: EXP.gps.length,
    ringStates: EXP.ring.states.length,
    costStates: EXP.cost.length,
  })
);
for (const b of bad.slice(0, 50)) console.log("MISMATCH " + b);
process.exit(bad.length ? 1 : 0);
