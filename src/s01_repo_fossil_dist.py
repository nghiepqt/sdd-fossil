"""RQ2b Step 1: repo-level fossil-rate distribution among OpenSpec living specs.

For repos with >= k living specs, fossil rate = fossils / living specs in that repo.
Writes section "repo_fossil" of results/numbers.json, data/derived/repo_fossil_rate.parquet,
and results/figures/repo_fossil_rate.pdf.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common import DERIVED, FIGURES, connect, update_numbers

K_MAIN = 3
K_SENS = (1, 3, 5, 10)
COLOR = "#2a78d6"     # single series; prints as a mid gray
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def summarize(rates):
    r = np.asarray(rates)
    return {
        "repos": int(r.size), "mean": float(r.mean()), "median": float(np.median(r)),
        "share_zero": float((r == 0).mean()), "share_one": float((r == 1).mean()),
        "share_le_10pct": float((r <= 0.10).mean()), "share_ge_90pct": float((r >= 0.90).mean()),
        "share_extreme": float(((r <= 0.10) | (r >= 0.90)).mean()),
    }


def main():
    con = connect()
    repo = con.sql("""
        SELECT repo_name, count(*) AS n_living,
               count(*) FILTER (WHERE fossil_class = 'fossil') AS n_fossil,
               count(*) FILTER (WHERE placeholder = 1) AS n_placeholder
        FROM living GROUP BY 1""").df()
    repo["fossil_rate"] = repo.n_fossil / repo.n_living
    con.register("repo_df", repo)
    con.sql(f"COPY repo_df TO '{DERIVED / 'repo_fossil_rate.parquet'}' (FORMAT parquet)")

    out = {"k_main": K_MAIN}
    for k in K_SENS:
        sub = repo[repo.n_living >= k]
        out[f"k{k}"] = summarize(sub.fossil_rate)
        out[f"k{k}"]["living_specs_covered"] = int(sub.n_living.sum())
    update_numbers("repo_fossil", out)

    rates = repo.loc[repo.n_living >= K_MAIN, "fossil_rate"].to_numpy()
    s = out[f"k{K_MAIN}"]

    plt.rcParams.update({"font.family": "serif", "font.size": 8, "axes.edgecolor": INK2,
                         "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
                         "pdf.fonttype": 42})
    fig, ax = plt.subplots(figsize=(3.4, 1.45))   # one IEEE column
    bins = np.linspace(0, 1, 21)
    counts, _ = np.histogram(rates, bins=bins)
    ax.bar(bins[:-1], counts, width=0.05 * 0.85, align="edge", color=COLOR, linewidth=0, zorder=2)
    ax.set_xlim(-0.01, 1.01)
    ax.set_xlabel("Fossil rate of the repository's living specs")
    ax.set_ylabel("Repositories")
    ax.yaxis.grid(True, color=GRID, linewidth=0.5, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.annotate(f"{s['share_zero']:.0%} at 0", (0.025, counts[0]), xytext=(8, -2),
                textcoords="offset points", fontsize=7, color=INK, va="top")
    ax.annotate(f"{s['share_one']:.0%} at 1", (0.975, counts[-1]), xytext=(-4, 4),
                textcoords="offset points", fontsize=7, color=INK, ha="right")
    fig.tight_layout(pad=0.3)
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / "repo_fossil_rate.pdf")
    fig.savefig(FIGURES / "repo_fossil_rate.png", dpi=200)
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()})


if __name__ == "__main__":
    main()
