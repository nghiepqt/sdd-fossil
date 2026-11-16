"""Representative sample sizes for the coding of fossils (RQ3) and revised living specs (RQ2).

Cochran's formula for a proportion at its most conservative value (p = 0.5), with the
finite-population correction, rounded up:
    n0 = z^2 * p * (1 - p) / e^2,   n = n0 / (1 + (n0 - 1) / N).

Populations come from results/numbers.json:
- fossil = headline.fossil.k (s00); revised = living - never_revised.k (s00);
- fossil_archive_text = placeholder_flag.fossils_by_archive_text (s02): fossils whose snapshot text holds the
  OpenSpec archive placeholder. The flag contains every such spec (recall 1.0), so this is the intersection of
  the flag and the archive text, the population the coded fossil sample is drawn from (decision 2026-11-12, item 2);
- edited = revision_split.type_by_placeholder.edited.total.k (s06): living specs with >= 1 other edit, the
  "maintained" group of RQ4 (decision 2026-11-12, item 5).
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
    n = json.loads(NUMBERS.read_text())
    h = n["headline"]
    populations = {
        "fossil": h["fossil"]["k"],
        "revised": h["living"] - h["never_revised"]["k"],
        "fossil_archive_text": n["placeholder_flag"]["fossils_by_archive_text"],
        "edited": n["revision_split"]["type_by_placeholder"]["edited"]["total"]["k"],
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
