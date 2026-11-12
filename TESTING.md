# How the numbers are checked

The workflow in `.github/workflows/ci.yml` runs two checks on every push to `main`.

**1. Independent re-computation (`tests/tf_model.py`, `tests/test_stated_numbers.py`).**
Plain Python, standard library only, no copy of the page's JavaScript. It shares only the
page's specification with it: the seeds, the named constants and the order in which the
generators draw random numbers. The detectors are re-derived from their definitions,
with its own union-find and an exact Mann-Whitney AUC over every pair (as a fraction,
ties counted one half). Each number the page states at its defaults and each number in
the README is written into the tests as printed, for example recall 87.1%, FPR 2.7%,
precision 96.4%, AUC 950/1023 = 0.928641, the cut 2.25, the 40 held-out seeds, the GPS
noise estimate, band and jump limit, the "too short or too small" limits, NO DECISION
from 18 m, and the cost model's +€258,000. The tests also check states the page shows
once the sliders move, such as AUC 0.475318 and 0.530327 with the attack sliders at
maximum. A number that does not reproduce fails the run.

**2. What the page displays (`tests/displayed.mjs`).** Serves `index.html` locally and
opens it in headless Chromium (Playwright). It reads the numbers off the page at the
defaults, then for all 7 GPS scenarios across the whole noise slider, 26 ring-graph
states (the slider extremes and the full proxy sweep) and two cost-model states. It
compares every one with the Python value, rounded the way the page rounds it. Any
mismatch, page error or console error fails the run.

Run locally: `python3 -m unittest discover -s tests -v`, then `npm ci`,
`npx playwright install chromium` and `node tests/displayed.mjs`.

## What this does not check

- **The data are synthetic.** Both checks confirm that the page computes what it says it
  computes. They say nothing about how any detector would perform on real traffic, and
  the page makes no claim about real fraud.
- The constants and seeds are taken as given. A wrong modelling choice that both
  implementations share would pass.
- Layout, drawing, accessibility and other browsers are not covered here.
- The Python re-computation was built with AI tools I direct, from the page's
  specification. It is an independent implementation, not an independent human review.
