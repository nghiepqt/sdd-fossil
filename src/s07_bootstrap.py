"""Repository cluster bootstrap CIs for the RQ1 shares (decision brief 2026-11-12, item 6; open issue A3).

Specs in one repository are not independent (fossils cluster by repository, s01), so Wilson CIs, which
treat every spec as an independent draw, can be too narrow. We resample repositories with replacement
(B = 1,000, fixed seed) and recompute each share as a ratio of sums over the resampled repositories:
    p_b = sum_r w_rb * k_r / sum_r w_rb * n_r,   (w_1b..w_Rb) ~ Multinomial(R, 1/R).
CIs are the 2.5th and 97.5th percentiles of p_b (percentile bootstrap). Point estimates are the
spec-level shares, identical to s00/s06.

Needs data/derived/living_revisions.parquet (s06) for the archive-merge split.
Writes section "bootstrap" of results/numbers.json.
"""
import numpy as np
from statsmodels.stats.proportion import proportion_confint

from common import DERIVED, SNAPSHOT_END, connect, update_numbers

SEED = 20261115
B = 1000

# metric -> (numerator column, denominator column) of the per-repository table
METRICS = {
    "never_revised": ("never_revised", "living"),
    "placeholder": ("placeholder", "living"),
    "fossil": ("fossil", "living"),
    "placeholder_revised": ("placeholder_revised", "living"),
    "edited": ("edited", "living"),
    "merge_only": ("merge_only", "living"),
    "archive_merge_share_of_revisions": ("merges", "revisions"),
    "fossil_min_age_90d": ("fossil_old90", "living_old90"),
    "never_revised_min_age_90d": ("never_revised_old90", "living_old90"),
}


def main():
    con = connect()
    rev = DERIVED / "living_revisions.parquet"
    old = f"CAST(l.file_first_commit_at AS TIMESTAMP) <= TIMESTAMP '{SNAPSHOT_END}' - INTERVAL 90 DAY"
    per_repo = con.sql(f"""
        WITH r AS (SELECT file_url_sha16, count(*) FILTER (WHERE is_merge) AS merges,
                          count(*) FILTER (WHERE NOT is_merge) AS other_edits
                   FROM read_parquet('{rev}') GROUP BY 1)
        SELECT l.repo_name,
               count(*) AS living,
               count(*) FILTER (WHERE l.revisions = 0) AS never_revised,
               count(*) FILTER (WHERE l.placeholder = 1) AS placeholder,
               count(*) FILTER (WHERE l.fossil_class = 'fossil') AS fossil,
               count(*) FILTER (WHERE l.fossil_class = 'placeholder_revised') AS placeholder_revised,
               count(*) FILTER (WHERE coalesce(r.other_edits, 0) > 0) AS edited,
               count(*) FILTER (WHERE l.revisions > 0 AND coalesce(r.other_edits, 0) = 0) AS merge_only,
               sum(l.revisions) AS revisions,
               sum(coalesce(r.merges, 0)) AS merges,
               count(*) FILTER (WHERE {old}) AS living_old90,
               count(*) FILTER (WHERE {old} AND l.fossil_class = 'fossil') AS fossil_old90,
               count(*) FILTER (WHERE {old} AND l.revisions = 0) AS never_revised_old90
        FROM living l LEFT JOIN r USING (file_url_sha16)
        GROUP BY 1 ORDER BY 1""").df()
    R = len(per_repo)
    W = np.random.default_rng(SEED).multinomial(R, np.full(R, 1.0 / R), size=B).astype(np.float64)

    out = {"B": B, "seed": SEED, "repos": R, "method": "percentile bootstrap over repositories",
           "metrics": {}}
    for name, (num, den) in METRICS.items():
        k_r = per_repo[num].to_numpy(np.float64)
        n_r = per_repo[den].to_numpy(np.float64)
        k, n = int(k_r.sum()), int(n_r.sum())
        p_b = (W @ k_r) / (W @ n_r)
        lo, hi = np.percentile(p_b, [2.5, 97.5])
        w_lo, w_hi = proportion_confint(k, n, alpha=0.05, method="wilson")
        out["metrics"][name] = {
            "k": k, "n": n, "p": k / n,
            "ci_lo": float(lo), "ci_hi": float(hi), "se": float(p_b.std(ddof=1)),
            "wilson_lo": w_lo, "wilson_hi": w_hi,
            "width_ratio_boot_over_wilson": float((hi - lo) / (w_hi - w_lo)),
        }
    update_numbers("bootstrap", out)

    print(f"repository cluster bootstrap: R = {R:,} repos, B = {B}, seed {SEED}")
    print(f"{'metric':<34}{'k / n':>18}{'p':>8}{'bootstrap 95% CI':>20}{'Wilson 95% CI':>20}{'ratio':>7}")
    for name, m in out["metrics"].items():
        print(f"{name:<34}{m['k']:>8,} / {m['n']:<8,}{100*m['p']:7.1f}%"
              f"{f'[{100*m['ci_lo']:.1f}, {100*m['ci_hi']:.1f}]':>20}"
              f"{f'[{100*m['wilson_lo']:.1f}, {100*m['wilson_hi']:.1f}]':>20}"
              f"{m['width_ratio_boot_over_wilson']:7.1f}")


if __name__ == "__main__":
    main()
