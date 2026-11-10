"""Empirical check: does SpecMine's per-file history follow renames?

For a seeded random sample of OpenSpec living and archived specs (small repos only, one spec per
repo), clone the repo (blobless, no checkout) and compare, up to the snapshot end:
  git log -- <path>            (path-only history, no rename following)
  git log --follow -- <path>   (rename-following history)
against SpecMine's file_total_commits. Clones go to a scratch directory passed as argv[1].

Writes section "renames" of results/numbers.json and data/derived/rename_check.csv.
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd

from common import DERIVED, SNAPSHOT_END, connect, update_numbers

SEED = 20261018
PER_ROLE = 15
MAX_REPO_KB = 20_000


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=600)


def count(cwd, path, follow):
    args = ["log", "--format=%H", f"--until={SNAPSHOT_END}"] + (["--follow"] if follow else []) + ["--", path]
    r = git(*args, cwd=cwd)
    return len([l for l in r.stdout.splitlines() if l.strip()]) if r.returncode == 0 else None


def classify_follow(cwd, path):
    """Classify the oldest rename/copy that --follow crossed for this path."""
    r = git("log", "--follow", f"--until={SNAPSHOT_END}", "--name-status", "--format=", "--", path, cwd=cwd)
    hops = [l.split("\t") for l in r.stdout.splitlines() if l[:1] in ("R", "C")]
    if not hops:
        return None
    _, src, dst = hops[-1][:3]
    in_arch = lambda x: "/changes/archive/" in "/" + x
    in_chg = lambda x: "/changes/" in "/" + x and not in_arch(x)
    in_specs = lambda x: "/specs/" in "/" + x and "/changes/" not in "/" + x
    if in_chg(src) and in_arch(dst):
        return "archive_move"
    if in_chg(src) and in_specs(dst):
        return "delta_to_living"
    if in_specs(src) and in_specs(dst):
        return "living_rename"
    return "other"


def main(scratch):
    scratch = Path(scratch); scratch.mkdir(parents=True, exist_ok=True)
    con = connect()
    sample = con.sql(f"""
        WITH c AS (
          SELECT b.*, sf.repo_size_kb, sf.repo_clone_url,
                 row_number() OVER (PARTITION BY b.spec_role, b.repo_name ORDER BY hash(b.file_url_sha16 || '{SEED}')) rn
          FROM base b JOIN spec_files sf USING (file_url_sha16)
          WHERE b.spec_tool = 'openspec' AND b.spec_role IN ('living', 'archived') AND sf.repo_size_kb < {MAX_REPO_KB})
        SELECT spec_role, repo_name, file_path, file_total_commits, repo_clone_url FROM (
          SELECT *, row_number() OVER (PARTITION BY spec_role ORDER BY hash(repo_name || '{SEED}')) rk FROM c WHERE rn = 1)
        WHERE rk <= {PER_ROLE} ORDER BY spec_role, repo_name""").df()
    rows = []
    for r in sample.itertuples():
        d = scratch / r.repo_name.replace("/", "__")
        if not d.exists():
            cl = git("clone", "-q", "--filter=blob:none", "--no-checkout", r.repo_clone_url, str(d), cwd=scratch)
            if cl.returncode != 0:
                rows.append({**r._asdict(), "status": "clone_failed"}); continue
        plain, follow = count(d, r.file_path, False), count(d, r.file_path, True)
        hop = classify_follow(d, r.file_path) if follow and plain and follow > plain else None
        rows.append({**r._asdict(), "status": "ok", "git_plain": plain, "git_follow": follow, "follow_hop": hop})
        print(r.spec_role, r.repo_name, r.file_total_commits, plain, follow, flush=True)
    res = pd.DataFrame(rows).drop(columns=["Index"])
    res.to_csv(DERIVED / "rename_check.csv", index=False)
    ok = res[(res.status == "ok") & res.git_plain.notna() & (res.git_plain > 0)]
    out = {"seed": SEED, "sampled": len(res), "checked": len(ok)}
    for role, g in ok.groupby("spec_role"):
        out[role] = {
            "checked": len(g),
            "specmine_equals_plain": int((g.file_total_commits == g.git_plain).sum()),
            "follow_gt_plain": int((g.git_follow > g.git_plain).sum()),
            "specmine_lt_follow": int((g.file_total_commits < g.git_follow).sum()),
            "follow_hops": {k: int(v) for k, v in g.follow_hop.value_counts().items()},
        }
    update_numbers("renames", out)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
