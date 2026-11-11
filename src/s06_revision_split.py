"""RQ1: split the revisions of OpenSpec living specs into archive merges and other edits.

Definitions (proposal_v2.tex, README):
- Revision: a commit that touches a living spec after its creation commit (seq_from_oldest > 1).
- Archive merge: a revision written by OpenSpec's archive step, i.e. a commit that also creates a
  file under changes/archive/.
- Other edit: any revision that is not an archive merge.

Rule. SpecMine histories do not follow renames (s03), and OpenSpec archives a change with `git mv`,
so the creation commit of an archived spec file (file_first_commit_sha) is the archive commit of its
change. A revision is an archive merge when its commit SHA, in the same repository, is the creation
commit of at least one archived OpenSpec spec file with a commit history (cohort or not).

Revision type per living spec: none (0 revisions), merge_only (>= 1 revision, all archive merges),
edited (>= 1 other edit).

Writes section "revision_split" of results/numbers.json,
data/derived/living_revisions.parquet (one row per revision) and
data/derived/revision_split_samples.csv (20 revisions for a manual check; repo and message only).
"""
import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportion_confint

from common import DERIVED, SNAPSHOT_END, connect, update_numbers

SEED = 20261110
N_SAMPLE = 10
MSG_ARCHIVE = r"(?i)archive"
TYPES = ("none", "merge_only", "edited")
SIZE_CLASSES = ("1", "2-4", "5+")


def wilson(k, n):
    lo, hi = proportion_confint(k, n, alpha=0.05, method="wilson")
    return {"k": int(k), "n": int(n), "p": k / n, "ci_lo": lo, "ci_hi": hi}


def crosstab(con, where, n_total):
    """Revision type x placeholder status, as counts and shares of n_total with Wilson CIs."""
    rows = con.sql(f"""SELECT rev_type, placeholder = 1, count(*) FROM spec_types
        WHERE {where} GROUP BY ALL""").fetchall()
    counts = {(t, bool(p)): k for t, p, k in rows}
    table = {}
    for t in TYPES:
        ph, no = counts.get((t, True), 0), counts.get((t, False), 0)
        table[t] = {"placeholder": wilson(ph, n_total), "no_placeholder": wilson(no, n_total),
                    "total": wilson(ph + no, n_total)}
    table["all"] = {s: wilson(sum(counts.get((t, s == "placeholder"), 0) for t in TYPES), n_total)
                    for s in ("placeholder", "no_placeholder")}
    table["n"] = n_total
    return table


def main():
    con = connect()
    one = lambda q: con.sql(q).fetchone()

    # ---- Archive commits: creation commits of archived OpenSpec spec files -----------------
    con.sql("""CREATE TABLE archive_commits AS
        SELECT DISTINCT repo_name, file_first_commit_sha AS commit_sha FROM spec_files
        WHERE spec_tool = 'openspec' AND spec_role = 'archived' AND commit_history_status = 'done'""")
    # Sensitivity: creation commits of ANY spec file under changes/archive/ (incl. nested OpenSpec roots).
    con.sql("""CREATE TABLE archive_commits_any AS
        SELECT DISTINCT repo_name, file_first_commit_sha AS commit_sha FROM spec_files
        WHERE file_path LIKE '%changes/archive/%' AND commit_history_status = 'done'""")
    arch_files, arch_hist, arch_repos, arch_repos_nohist = one("""
        SELECT count(*), count(*) FILTER (WHERE commit_history_status = 'done'), count(DISTINCT repo_name),
               count(DISTINCT repo_name) FILTER (WHERE commit_history_status <> 'done')
        FROM spec_files WHERE spec_tool = 'openspec' AND spec_role = 'archived'""")
    n_arch_commits, n_arch_commits_no_living = one("""
        SELECT count(*), count(*) FILTER (WHERE repo_name NOT IN (SELECT repo_name FROM living))
        FROM archive_commits""")

    # ---- One row per revision of a living spec ---------------------------------------------
    con.sql(f"""CREATE TABLE revisions AS
        SELECT l.file_url_sha16, l.repo_name, l.placeholder, c.seq_from_oldest, c.commit_sha, c.message,
               a.commit_sha IS NOT NULL AS is_merge,
               b.commit_sha IS NOT NULL AS is_merge_any,
               regexp_matches(c.message, '{MSG_ARCHIVE}') AS msg_archive
        FROM living l
        JOIN spec_file_commits c USING (file_url_sha16)
        LEFT JOIN archive_commits a ON a.repo_name = l.repo_name AND a.commit_sha = c.commit_sha
        LEFT JOIN archive_commits_any b ON b.repo_name = l.repo_name AND b.commit_sha = c.commit_sha
        WHERE c.seq_from_oldest > 1""")
    n_rev_check = one("SELECT sum(revisions) FROM living")[0]
    n_rev, n_merge, n_merge_any = one(
        "SELECT count(*), count(*) FILTER (WHERE is_merge), count(*) FILTER (WHERE is_merge_any) FROM revisions")
    assert n_rev == n_rev_check, "revision rows do not match file_total_commits - 1"

    # ---- Revision type per living spec ------------------------------------------------------
    con.sql("""CREATE TABLE spec_types AS
        SELECT l.file_url_sha16, l.repo_name, l.placeholder, l.revisions, l.file_first_commit_at,
               coalesce(r.merges, 0) AS merges, coalesce(r.other_edits, 0) AS other_edits,
               CASE WHEN l.revisions = 0 THEN 'none'
                    WHEN coalesce(r.other_edits, 0) = 0 THEN 'merge_only' ELSE 'edited' END AS rev_type
        FROM living l LEFT JOIN (
            SELECT file_url_sha16, count(*) FILTER (WHERE is_merge) AS merges,
                   count(*) FILTER (WHERE NOT is_merge) AS other_edits
            FROM revisions GROUP BY 1) r USING (file_url_sha16)""")
    n_living = one("SELECT count(*) FROM spec_types")[0]
    table = crosstab(con, "TRUE", n_living)

    old_cut = f"CAST(file_first_commit_at AS TIMESTAMP) <= TIMESTAMP '{SNAPSHOT_END}' - INTERVAL 90 DAY"
    n_old = one(f"SELECT count(*) FROM spec_types WHERE {old_cut}")[0]
    table_old = crosstab(con, old_cut, n_old)

    # Other edits per spec among `edited` specs (quantile_disc: an observed value, no interpolation).
    med, p90, mean = one("""SELECT quantile_disc(other_edits, 0.5), quantile_disc(other_edits, 0.9),
        avg(other_edits) FROM spec_types WHERE rev_type = 'edited'""")

    # ---- Share of revisions that are archive merges, by repository size class --------------
    by_size = {}
    con.sql("""CREATE TABLE repo_size AS
        SELECT repo_name, count(*) AS n_living, CASE WHEN count(*) = 1 THEN '1'
               WHEN count(*) <= 4 THEN '2-4' ELSE '5+' END AS size_class
        FROM living GROUP BY 1""")
    rev_by_size = {c: (k, n) for c, k, n in con.sql("""SELECT size_class, count(*) FILTER (WHERE is_merge),
        count(*) FROM revisions JOIN repo_size USING (repo_name) GROUP BY 1""").fetchall()}
    for cls, repos, specs in con.sql(
            "SELECT size_class, count(*), sum(n_living) FROM repo_size GROUP BY 1 ORDER BY 1").fetchall():
        k, n = rev_by_size.get(cls, (0, 0))
        by_size[cls] = {"repos": repos, "living": int(specs), "revisions": n,
                        "merge_share": wilson(k, n) if n else None}

    # ---- Validation --------------------------------------------------------------------------
    msg = {("merge" if m else "other"): wilson(k, n) for m, k, n in con.sql(
        "SELECT is_merge, count(*) FILTER (WHERE msg_archive), count(*) FROM revisions GROUP BY 1").fetchall()}
    # Does the archived change carry a delta spec for the same capability as the living spec?
    cap_match = one("""
        WITH arch AS (SELECT DISTINCT repo_name, file_first_commit_sha AS commit_sha,
                             regexp_extract(file_path, 'changes/archive/[^/]+/specs/(.+)/spec\\.md$', 1) AS cap
                      FROM spec_files WHERE spec_tool = 'openspec' AND spec_role = 'archived'
                        AND commit_history_status = 'done')
        SELECT count(*) FILTER (WHERE EXISTS (SELECT 1 FROM arch a WHERE a.repo_name = r.repo_name
                 AND a.commit_sha = r.commit_sha AND a.cap = regexp_extract(l.file_path, 'specs/(.+)/spec\\.md$', 1)))
        FROM revisions r JOIN living l USING (file_url_sha16) WHERE r.is_merge""")[0]
    created_at_archive = one("""SELECT count(*) FROM living l JOIN archive_commits a
        ON a.repo_name = l.repo_name AND a.commit_sha = l.file_first_commit_sha""")[0]
    # Revisions in repos where the archive rule cannot fire or may miss: no archived spec at all in
    # the data, or some archived spec without a history.
    cover = {g: {"repos": rp, "revisions": n, "merges": int(m), "other_edits_msg_archive": int(oa)}
             for g, rp, n, m, oa in con.sql("""
        WITH ra AS (SELECT repo_name, count(*) AS n_arch,
                           count(*) FILTER (WHERE commit_history_status = 'done') AS n_hist
                    FROM spec_files WHERE spec_tool = 'openspec' AND spec_role = 'archived' GROUP BY 1)
        SELECT CASE WHEN ra.repo_name IS NULL THEN 'repo_without_archived_specs'
                    WHEN ra.n_hist < ra.n_arch THEN 'repo_with_archived_specs_without_history'
                    ELSE 'repo_with_all_archived_specs_with_history' END,
               count(DISTINCT r.repo_name), count(*), count(*) FILTER (WHERE is_merge),
               count(*) FILTER (WHERE NOT is_merge AND msg_archive)
        FROM revisions r LEFT JOIN ra USING (repo_name) GROUP BY 1""").fetchall()}
    # Bound, not a rule: if every other edit whose message mentions "archive" were a missed archive
    # merge, how many `edited` specs would remain?
    edited_if_msg_merges = one("""SELECT count(*) FROM (SELECT file_url_sha16 FROM revisions
        WHERE NOT is_merge AND NOT msg_archive GROUP BY 1)""")[0]
    edited_any_rule = one("""SELECT count(*) FROM (SELECT file_url_sha16 FROM revisions
        WHERE NOT is_merge_any GROUP BY 1)""")[0]

    # Random revisions for a manual check (repo and first line of the message; no author fields).
    samples = []
    for kind in ("archive_merge", "other_edit"):
        cand = con.sql(f"""SELECT repo_name, commit_sha, file_url_sha16,
                split_part(replace(message, chr(13), ''), chr(10), 1) AS message_first_line
            FROM revisions WHERE is_merge = {kind == 'archive_merge'}
            ORDER BY file_url_sha16, commit_sha""").df()
        idx = np.sort(np.random.default_rng(SEED).choice(len(cand), N_SAMPLE, replace=False))
        samples.append(cand.iloc[idx].assign(kind=kind))
    samples = pd.concat(samples)[["kind", "repo_name", "commit_sha", "message_first_line"]]
    samples.to_csv(DERIVED / "revision_split_samples.csv", index=False)

    update_numbers("revision_split", {
        "rule": "revision commit (same repo) = creation commit of >= 1 archived OpenSpec spec file with history",
        "archived_files": arch_files, "archived_files_with_history": arch_hist,
        "archived_files_without_history": arch_files - arch_hist,
        "archived_repos": arch_repos, "archived_repos_with_file_without_history": arch_repos_nohist,
        "archive_commits": n_arch_commits, "archive_commits_in_repos_without_cohort_living": n_arch_commits_no_living,
        "living": n_living, "revisions": n_rev, "archive_merges": n_merge, "other_edits": n_rev - n_merge,
        "merge_share": wilson(n_merge, n_rev), "merge_share_by_repo_size": by_size,
        "type_by_placeholder": table, "type_by_placeholder_min_age_90d": table_old,
        "other_edits_per_edited_spec": {"median": int(med), "p90": int(p90), "mean": mean},
        "validation": {
            "msg_archive_regex": MSG_ARCHIVE, "msg_archive": msg,
            "merges_same_capability": wilson(cap_match, n_merge),
            "living_created_in_archive_commit": wilson(created_at_archive, n_living),
            "coverage": cover,
            "other_edits_msg_archive": msg["other"]["k"],
            "edited_if_all_msg_archive_other_edits_were_merges": edited_if_msg_merges,
            "sensitivity_any_file_under_changes_archive": {
                "archive_merges": n_merge_any, "edited": edited_any_rule},
            "sample_seed": SEED, "sample_per_kind": N_SAMPLE,
        },
    })

    # ---- Console report ----------------------------------------------------------------------
    con.sql(f"COPY revisions TO '{DERIVED / 'living_revisions.parquet'}' (FORMAT parquet)")
    for name, t in (("all living specs", table), ("living specs >= 90 days old", table_old)):
        print(f"\nRevision type x placeholder, {name} (n = {t['n']:,}; share of n, Wilson 95% CI)")
        print(f"{'type':<11}{'placeholder':>36}{'no placeholder':>36}{'total':>12}")
        for ty in TYPES:
            cells = [t[ty][s] for s in ("placeholder", "no_placeholder")]
            print(f"{ty:<11}" + "".join(f"{c['k']:>8,} {100*c['p']:5.1f}% [{100*c['ci_lo']:4.1f}, {100*c['ci_hi']:4.1f}]"
                                        .rjust(36) for c in cells) + f"{t[ty]['total']['k']:>12,}")
    print(f"\nrevisions {n_rev:,}: archive merges {n_merge:,} ({n_merge/n_rev:.1%}), other edits {n_rev-n_merge:,}")
    print("merge share by repo size:", {k: (v["revisions"], round(v["merge_share"]["p"], 3)) for k, v in by_size.items()})
    print(f"other edits per edited spec: median {med}, p90 {p90}, mean {mean:.2f}")
    print(f"'archive' in message: merges {msg['merge']['p']:.1%}, other edits {msg['other']['p']:.1%}")
    print(f"merges with same-capability archived delta: {cap_match/n_merge:.1%}; "
          f"living specs created in an archive commit: {created_at_archive/n_living:.1%}")
    print("coverage:", cover)
    print(f"edited: {table['edited']['total']['k']:,}; if all msg-archive other edits were merges: "
          f"{edited_if_msg_merges:,}; with any changes/archive file: {edited_any_rule:,}")
    print(samples.to_string(index=False, max_colwidth=90))


if __name__ == "__main__":
    main()
