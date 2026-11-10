"""Reproduce the preliminary headline numbers and explain the 470,795 vs 468,163 gap.

Writes section "headline" and "cohort" of results/numbers.json and
data/derived/openspec_living.parquet (one row per OpenSpec living spec in the cohort).
"""
from statsmodels.stats.proportion import proportion_confint

from common import DERIVED, SNAPSHOT_END, connect, update_numbers


def wilson(k, n):
    lo, hi = proportion_confint(k, n, alpha=0.05, method="wilson")
    return {"k": int(k), "n": int(n), "p": k / n, "ci_lo": lo, "ci_hi": hi}


def main():
    con = connect()
    one = lambda q: con.sql(q).fetchone()

    # ---- Cohort accounting (470,795 -> 468,163) ---------------------------------------
    n_all, n_repos, n_repos_ci = one(
        "SELECT count(*), count(DISTINCT repo_name), count(DISTINCT lower(repo_name)) FROM spec_files")
    no_hist, no_content, both_missing = one("""
        SELECT count(*) FILTER (WHERE commit_history_status <> 'done'),
               count(*) FILTER (WHERE content_fetch_status <> 'done'),
               count(*) FILTER (WHERE commit_history_status <> 'done' AND content_fetch_status <> 'done')
        FROM spec_files""")
    n_feat = one("SELECT count(*) FROM spec_content_features")[0]
    n_base = one("SELECT count(*) FROM base")[0]
    n_commits_table, n_files_in_commits = one(
        "SELECT count(*), count(DISTINCT file_url_sha16) FROM spec_file_commits")
    n_commits_orphan = one("""SELECT count(*) FROM spec_file_commits
        WHERE file_url_sha16 NOT IN (SELECT file_url_sha16 FROM spec_files)""")[0]
    n_commits_base = one("""SELECT count(*) FROM spec_file_commits
        WHERE file_url_sha16 IN (SELECT file_url_sha16 FROM base)""")[0]
    sum_total_commits_base = one("SELECT sum(file_total_commits) FROM base")[0]
    first_min, first_max = one("SELECT min(file_first_commit_at), max(file_first_commit_at) FROM base")
    update_numbers("cohort", {
        "spec_files_rows": n_all, "spec_files_repos_distinct_name": n_repos,
        "spec_files_repos_case_insensitive": n_repos_ci,
        "no_commit_history": no_hist, "no_content": no_content, "no_history_and_no_content": both_missing,
        "content_feature_rows": n_feat, "cohort_specs": n_base, "dropped_specs": n_all - n_base,
        "commit_table_rows": n_commits_table, "commit_table_distinct_files": n_files_in_commits,
        "commit_rows_for_files_not_in_spec_files": n_commits_orphan,
        "commit_rows_in_cohort": n_commits_base, "sum_file_total_commits_in_cohort": int(sum_total_commits_base),
        "first_commit_min": first_min, "first_commit_max": first_max, "snapshot_end": SNAPSHOT_END,
    })

    # ---- OpenSpec scale --------------------------------------------------------------
    os_files, os_repos = one(
        "SELECT count(*), count(DISTINCT repo_name) FROM spec_files WHERE spec_tool = 'openspec'")
    roles_all = dict(con.sql("""SELECT spec_role, count(*) FROM spec_files
        WHERE spec_tool = 'openspec' GROUP BY 1""").fetchall())
    roles_base = dict(con.sql("""SELECT spec_role, count(*) FROM base
        WHERE spec_tool = 'openspec' GROUP BY 1""").fetchall())

    # ---- Living specs ------------------------------------------------------------------
    n, never, ph, fossil, ph_rev, repos_living, repos_fossil = one("""
        SELECT count(*), count(*) FILTER (WHERE revisions = 0), count(*) FILTER (WHERE placeholder = 1),
               count(*) FILTER (WHERE fossil_class = 'fossil'),
               count(*) FILTER (WHERE fossil_class = 'placeholder_revised'),
               count(DISTINCT repo_name), count(DISTINCT repo_name) FILTER (WHERE fossil_class = 'fossil')
        FROM living""")
    top_repo, top_n = one("""SELECT repo_name, count(*) FROM living WHERE fossil_class = 'fossil'
        GROUP BY 1 ORDER BY 2 DESC LIMIT 1""")
    # Living specs created within 30/60/90 days of the snapshot end.
    young = {f"living_younger_than_{d}d": one(f"""SELECT count(*) FROM living
        WHERE CAST(file_first_commit_at AS TIMESTAMP) > TIMESTAMP '{SNAPSHOT_END}' - INTERVAL {d} DAY""")[0]
        for d in (30, 60, 90)}

    # Never-revised share per OpenSpec role (data check: archived histories restart at the git mv).
    role_never = {r: wilson(k, m) for r, k, m in con.sql("""SELECT spec_role, count(*) FILTER (WHERE revisions = 0),
        count(*) FROM base WHERE spec_tool = 'openspec' GROUP BY 1""").fetchall()}
    # Headline rates after excluding living specs younger than d days at the snapshot end.
    age_filtered = {}
    for d in (30, 60, 90):
        m, nv, fs = one(f"""SELECT count(*), count(*) FILTER (WHERE revisions = 0),
            count(*) FILTER (WHERE fossil_class = 'fossil') FROM living
            WHERE CAST(file_first_commit_at AS TIMESTAMP) <= TIMESTAMP '{SNAPSHOT_END}' - INTERVAL {d} DAY""")
        age_filtered[f"min_age_{d}d"] = {"living": m, "never_revised": wilson(nv, m), "fossil": wilson(fs, m)}
    update_numbers("age_filtered", age_filtered)

    update_numbers("headline", {
        "openspec_role_never_revised": role_never,
        "spec_files": n_all, "repos": n_repos_ci, "cohort_specs": n_base, "cohort_commits": n_commits_base,
        "openspec_files": os_files, "openspec_repos": os_repos, "openspec_share_of_files": os_files / n_all,
        "openspec_roles_all": roles_all, "openspec_roles_cohort": roles_base,
        "living": n, "living_repos": repos_living,
        "never_revised": wilson(never, n), "placeholder": wilson(ph, n),
        "fossil": wilson(fossil, n), "placeholder_revised": wilson(ph_rev, n),
        "no_placeholder": wilson(n - ph, n),
        "fossil_repos": repos_fossil, "top_fossil_repo": top_repo, "top_fossil_repo_n": top_n,
        "top_fossil_repo_share": top_n / fossil, **young,
    })

    con.sql(f"COPY (SELECT * FROM living) TO '{DERIVED / 'openspec_living.parquet'}' (FORMAT parquet)")
    print(f"cohort {n_base:,} of {n_all:,}; living {n:,}; never {never/n:.1%}; placeholder {ph/n:.1%}; "
          f"fossil {fossil:,} ({fossil/n:.1%}) in {repos_fossil:,} repos; top repo {top_n/fossil:.2%}")


if __name__ == "__main__":
    main()
