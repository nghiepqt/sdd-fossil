"""Representative sample sizes for the coding of fossils (RQ3) and revised living specs (RQ2).

Cochran's formula for a proportion at its most conservative value (p = 0.5), with the
finite-population correction, rounded up:
    n0 = z^2 * p * (1 - p) / e^2,   n = n0 / (1 + (n0 - 1) / N).

Populations come from results/numbers.json (section "headline", written by s00_headline.py):
fossils = headline.fossil.k; revised living specs = living - never_revised.k.
Writes section "sample_size" of results/numbers.json.
"""
import json
import math

from scipy.stats import norm

from common import NUMBERS, update_numbers

CONFIDENCE = 0.95
MARGINS = (0.05, 0.10)


def cochran_fpc(N, e, confidence=CONFIDENCE, p=0.5):
    z = norm.ppf(1 - (1 - confidence) / 2)
    n0 = z * z * p * (1 - p) / (e * e)
    return math.ceil(n0 / (1 + (n0 - 1) / N))


def main():
    h = json.loads(NUMBERS.read_text())["headline"]
    populations = {
        "fossil": h["fossil"]["k"],
        "revised": h["living"] - h["never_revised"]["k"],
    }
    out = {"confidence": CONFIDENCE}
    for group, N in populations.items():
        out[group] = {"population": N}
        for e in MARGINS:
            out[group][f"n_margin_{round(e * 100):02d}"] = cochran_fpc(N, e)
    update_numbers("sample_size", out)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
