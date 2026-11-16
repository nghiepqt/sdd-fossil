"""Draw the coding samples for RQ2-RQ4: fossils vs edited living specs (decision brief 2026-11-12).

Populations (both are OpenSpec living specs of the cohort):
- fossil: SpecMine flag fossil (placeholder, 0 revisions) AND the snapshot text holds the OpenSpec archive
  placeholder (s02, RE_ARCHIVE_ANY). Every coded fossil therefore holds the tool-written TBD (item 2).
- edited: >= 1 other edit, i.e. a revision that is not an archive merge (s06); "maintained" in RQ4 (item 5).

Design:
- At most CAP specs per repository and group, so that a few repositories cannot drive the categories.
- Each spec gets a uniform random key (numpy default_rng(SEED), specs sorted by file_url_sha16). Within a
  repository, the CAP specs with the smallest keys are eligible; eligible specs are then ranked by key.
  The rank defines nested samples: any prefix of the ranking is a random sample of the capped population.
- Per group, by rank: 1..N_PILOT = pilot (dev set, codebook v1); next N_DOUBLE = double coding (human test
  set, Cohen's kappa); the rest up to the Cochran size (s04, 95%, +-5%) = LLM-only items.
  The first N_FALLBACK double-coding items per group form batch 1 (the 50+50 fallback, item 4).
- Coding sheets are blind to the group: items from both groups are shuffled together and get neutral IDs.
  The key lives in labels/sample_frame.csv. (Fossils still show the TBD, so blinding is partial.)

Writes labels/sample_frame.csv, labels/{pilot,double}/coding_sheet_TEMPLATE.csv, one Markdown file per
coded spec in labels/{pilot,double}/specs/, and section "samples" of results/numbers.json.
Human labels are filled in by the students only.
"""
import json
import shutil

import numpy as np
import pandas as pd

from common import DERIVED, NUMBERS, ROOT, SNAPSHOT_END, connect, update_numbers

SEED = 20261114
CAP = 3
N_PILOT = 15        # per group -> 30 specs
N_DOUBLE = 100      # per group -> 200 specs
N_FALLBACK = 50     # per group, batch 1 of the double-coding set
LABELS = ROOT / "labels"
GROUPS = ("fossil", "edited")
SHEET_FIELDS = {
    "pilot": ["is_spec", "requirements_extent", "implementation_extent", "completeness",
              "is_spec_of_work", "purpose", "object", "note"],
    "double": ["is_spec", "requirements_extent", "implementation_extent", "completeness", "note"],
}


def frame(con):
    rev = DERIVED / "living_revisions.parquet"
    content = DERIVED / "living_content.parquet"
    return con.sql(f"""
        WITH r AS (SELECT file_url_sha16, count(*) FILTER (WHERE is_merge) AS merges,
                          count(*) FILTER (WHERE NOT is_merge) AS other_edits
                   FROM read_parquet('{rev}') GROUP BY 1)
        SELECT l.file_url_sha16, l.repo_name, l.file_path, sf.file_url, l.file_first_commit_at,
               date_diff('day', CAST(l.file_first_commit_at AS TIMESTAMP), TIMESTAMP '{SNAPSHOT_END}') AS age_days,
               l.revisions, coalesce(r.merges, 0) AS merges, coalesce(r.other_edits, 0) AS other_edits,
               l.placeholder, c.re_archive_any, l.n_bytes, l.n_scenario_blocks,
               CASE WHEN l.fossil_class = 'fossil' AND c.re_archive_any THEN 'fossil'
                    WHEN coalesce(r.other_edits, 0) > 0 THEN 'edited' END AS grp
        FROM living l
        JOIN spec_files sf USING (file_url_sha16)
        JOIN read_parquet('{content}') c USING (file_url_sha16)
        LEFT JOIN r USING (file_url_sha16)""").df()


def draw(df, n_target, rng):
    df = df.sort_values("file_url_sha16").reset_index(drop=True)
    df["key"] = rng.random(len(df))
    df["rank_in_repo"] = df.groupby("repo_name")["key"].rank(method="first").astype(int)
    elig = df[df.rank_in_repo <= CAP].sort_values("key").reset_index(drop=True)
    elig["rank_in_group"] = np.arange(1, len(elig) + 1)
    s = elig.head(n_target).copy()
    s["split"] = np.select([s.rank_in_group <= N_PILOT, s.rank_in_group <= N_PILOT + N_DOUBLE],
                           ["pilot", "double"], "llm_only")
    s["batch"] = np.where(s.split != "double", 0,
                          np.where(s.rank_in_group <= N_PILOT + N_FALLBACK, 1, 2))
    return s, len(elig)


def write_split(split, items, content, rng):
    """Shuffle both groups together, assign neutral IDs, write the spec files and an empty sheet."""
    out = LABELS / split
    if (out / "specs").exists():
        shutil.rmtree(out / "specs")
    (out / "specs").mkdir(parents=True)
    prefix, width = ("P", 2) if split == "pilot" else ("D", 3)
    # Batch 1 first (the 50+50 fallback), then batch 2; random order within a batch.
    items = items.assign(u=rng.random(len(items))).sort_values(["batch", "u"]).reset_index(drop=True)
    items["item_id"] = [f"{prefix}{i:0{width}d}" for i in range(1, len(items) + 1)]
    for row in items.itertuples():
        text = content[row.file_url_sha16]
        (out / "specs" / f"{row.item_id}.md").write_text(
            f"<!-- item {row.item_id} | {row.file_url} -->\n\n{text}", encoding="utf-8")
    sheet = items[["item_id", "batch", "file_url"]].copy()
    for f in SHEET_FIELDS[split]:
        sheet[f] = ""
    sheet.to_csv(out / "coding_sheet_TEMPLATE.csv", index=False)
    return items


def main():
    con = connect()
    n = json.loads(NUMBERS.read_text())
    df = frame(con)
    pops = {g: df[df.grp == g] for g in GROUPS}
    # Consistency with s02 / s06.
    assert len(pops["fossil"]) == n["placeholder_flag"]["fossils_by_archive_text"]
    assert len(pops["edited"]) == n["revision_split"]["type_by_placeholder"]["edited"]["total"]["k"]

    rng = np.random.default_rng(SEED)
    target = {"fossil": n["sample_size"]["fossil_archive_text"]["n_margin_05"],
              "edited": n["sample_size"]["edited"]["n_margin_05"]}
    samples, stats = [], {}
    for g in GROUPS:
        s, n_elig = draw(pops[g].copy(), target[g], rng)
        s["group"] = g
        samples.append(s)
        top = s.repo_name.value_counts()
        stats[g] = {"population": len(pops[g]), "population_repos": int(pops[g].repo_name.nunique()),
                    "eligible_after_cap": n_elig, "drawn": len(s), "target_cochran_05": target[g],
                    "repos_in_sample": int(s.repo_name.nunique()), "max_specs_per_repo": int(top.max()),
                    "splits": {k: int(v) for k, v in s.split.value_counts().items()},
                    "median_age_days": float(s.age_days.median()),
                    "under_30d_in_coded": int(((s.split != "llm_only") & (s.age_days < 30)).sum())}
    sample = pd.concat(samples, ignore_index=True)

    ids = set(sample.file_url_sha16[sample.split != "llm_only"])
    content = dict(con.sql(f"""SELECT file_url_sha16, content FROM read_parquet('{DERIVED / "living_content.parquet"}')
        WHERE file_url_sha16 IN (SELECT unnest(?::VARCHAR[]))""", params=[sorted(ids)]).fetchall())
    id_map = []
    for split in ("pilot", "double"):
        id_map.append(write_split(split, sample[sample.split == split], content, rng)[["file_url_sha16", "item_id"]])
    sample = sample.merge(pd.concat(id_map), on="file_url_sha16", how="left")
    llm = sample.split == "llm_only"
    sample.loc[llm, "item_id"] = [f"L{i:03d}" for i in range(1, llm.sum() + 1)]
    cols = ["item_id", "group", "split", "batch", "rank_in_group", "file_url_sha16", "repo_name", "file_path",
            "file_url", "file_first_commit_at", "age_days", "revisions", "merges", "other_edits", "placeholder",
            "re_archive_any", "n_bytes", "n_scenario_blocks"]
    sample[cols].sort_values(["split", "item_id"]).to_csv(LABELS / "sample_frame.csv", index=False)

    update_numbers("samples", {"seed": SEED, "cap_per_repo": CAP, "pilot_per_group": N_PILOT,
                               "double_per_group": N_DOUBLE, "fallback_per_group": N_FALLBACK, "groups": stats})
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
