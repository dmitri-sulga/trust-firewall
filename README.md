# Trust Firewall

Live page: https://dmitri-sulga.github.io/trust-firewall/

A single self-contained page with two fraud detectors and a detector cost calculator. Each one is built on synthetic data and then pushed until its method stops working, so the page shows where it breaks as well as what it catches.

The number the page itself calls worth arguing about is not an AUC. At the defaults the ring graph first breaks at 55% proxy obfuscation, where a ring account keeps 2.6 links inside its ring, against 10.5 with no obfuscation. Past that point no amount of graph work recovers the ring and a behavioural signal has to take over. Like everything here, it describes a synthetic population.

## The three modules

1. **GPS physics.** Four checks on a GPS track: jumps between fixes, sustained speed, the mock-location flag and cell towers. Seven scenarios (Valid, Teleport, Implausible speed, Speed burst, Mock-location, Cell-tower, Smooth spoof) and a noise slider from 4 to 60 m per axis. The page opens on Speed burst at 20 m, where the speed rule cannot decide and answers NO DECISION; lower the noise and it flags the burst. Smooth spoof is a forged track that none of the four checks sees.
2. **Ring graph.** Accounts that share a device, card or address form clusters. A cluster is scored by size times density and flagged above a cut set on the default population to keep false positives within a budget of 3% of legitimate accounts. Sliders for ring sizes, proxy obfuscation and temporal spread change the population; recall, false-positive rate, precision, exact AUC, a ROC curve and a "Where it breaks" chart over the proxy slider update as they move. The exact AUC reads 0.93 at the defaults and 0.53 with all three sliders at maximum.
3. **Cost model.** A calculator, not a measurement: six inputs (accounts scored per year, fraud prevalence, recall, false-positive rate, loss per fraud account, cost of one wrongful block) give the fraud loss prevented, the cost of wrongful blocks, the net effect per year, the derived precision and the break-even false-positive rate. None of the defaults is a measured or published figure.

## Data

All data on the page is synthetic: generated tracks and account populations, no company's data and no production logs. The same seed gives the same numbers on every load. The numbers describe these synthetic populations, not results on real traffic; those can only come from production logs, with the metric and the false-positive budget fixed before the first run.

## Run it locally

Open `index.html` in a modern browser. There is no build step, no server and no network request; everything is computed in the page with JavaScript.

## Related

[trip-physics](https://github.com/dmitri-sulga/trip-physics) is an evaluation harness in Python, built with AI tools I direct.

[refund-decision-eval](https://github.com/dmitri-sulga/refund-decision-eval) is an evaluation of a local language model deciding refunds on disputed card charges, scored against what the companies recorded. Its result is negative: by the study's measure (kappa against the record), no model scored above a simple lookup of each card issuer's past payout rate.

## Licence

MIT, see [LICENSE](LICENSE). Copyright (c) 2026 Dmitri Sulga.
