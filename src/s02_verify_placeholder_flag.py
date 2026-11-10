"""Validate SpecMine's has_unfilled_placeholder flag against the OpenSpec archive placeholder text.

Runs over the full population of OpenSpec living specs in the cohort (not a sample), using the
snapshot content in specs.jsonl.gz. Placeholder variants, from the OpenSpec source history:
  * canonical (2025-08-19 .. ): "TBD - created by archiving change <name>. Update Purpose after archive."
  * original  (2025-08-19, first commit only): "TBD — created by archiving change. Update Purpose after archive."
  * agent-written: the /opsx:sync skill (2026-01-06 .. v1.7.0) told the agent to
    "Add Purpose section (can be brief, mark as TBD)", so free-form TBD Purposes also occur.

Writes section "placeholder_flag" of results/numbers.json and
data/derived/living_content.parquet (living-spec content + derived flags; used by RQ2b sampling).
"""
import gzip
import json
import re

import pandas as pd

from common import DERIVED, SPECS_JSONL, connect, update_numbers

RE_CANON = re.compile(r"TBD - created by archiving change \S.*?\. Update Purpose after archive\.")
RE_ARCHIVE_ANY = re.compile(r"TBD\s*[-—–]\s*created by archiving change.*?Update Purpose after archive",
                            re.I | re.S)
RE_PURPOSE = re.compile(r"^##\s+Purpose\s*$(.*?)(?=^##\s|\Z)", re.M | re.S)
RE_TBD = re.compile(r"\bTBD\b")


def purpose_body(text):
    m = RE_PURPOSE.search(text)
    return m.group(1).strip() if m else None


def main():
    con = connect()
    living = con.sql("SELECT file_url_sha16, repo_name, placeholder, revisions, fossil_class FROM living").df()
    keep = set(living.file_url_sha16)
    rows = []
    with gzip.open(SPECS_JSONL, "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d["file_url_sha16"] not in keep:
                continue
            text = d.get("content") or ""
            pb = purpose_body(text)
            rows.append({
                "file_url_sha16": d["file_url_sha16"], "content": text,
                "purpose": pb,
                "re_canonical": bool(RE_CANON.search(text)),
                "re_archive_any": bool(RE_ARCHIVE_ANY.search(text)),
                "purpose_has_tbd": bool(pb is not None and RE_TBD.search(pb)),
                "any_tbd": bool(RE_TBD.search(text)),
            })
    content = pd.DataFrame(rows)
    df = living.merge(content, on="file_url_sha16", how="left", indicator=True)
    n = len(df)
    matched = int((df._merge == "both").sum())
    df = df[df._merge == "both"].drop(columns="_merge")
    flag = df.placeholder == 1

    def cm(col):
        pred, true = flag, df[col]
        tp = int((pred & true).sum()); fp = int((pred & ~true).sum()); fn = int((~pred & true).sum())
        return {"tp": tp, "fp": fp, "fn": fn, "tn": int((~pred & ~true).sum()),
                "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / (tp + fn) if tp + fn else None}

    # What does the flag catch beyond the archive placeholder?
    extra = df[flag & ~df.re_archive_any]
    extra_examples = extra.purpose.fillna("<no Purpose section>").str.slice(0, 120).value_counts().head(15)
    missed = df[~flag & df.re_archive_any]

    out = {
        "living": n, "living_with_content": matched,
        "flag_vs_canonical": cm("re_canonical"),
        "flag_vs_archive_any": cm("re_archive_any"),
        "flag_vs_purpose_tbd": cm("purpose_has_tbd"),
        "n_canonical": int(df.re_canonical.sum()), "n_archive_any": int(df.re_archive_any.sum()),
        "n_purpose_tbd": int(df.purpose_has_tbd.sum()), "n_any_tbd": int(df.any_tbd.sum()),
        "n_no_purpose_section": int(df.purpose.isna().sum()),
        "fossils_by_archive_text": int((df.re_archive_any & (df.revisions == 0)).sum()),
        "flag_only_examples": {k: int(v) for k, v in extra_examples.items()},
        "missed_examples": missed.purpose.fillna("").str.slice(0, 160).head(5).tolist(),
    }
    update_numbers("placeholder_flag", out)
    df.drop(columns=["placeholder", "revisions", "fossil_class", "repo_name"]).to_parquet(
        DERIVED / "living_content.parquet", index=False)
    print(json.dumps({k: v for k, v in out.items() if k not in ("flag_only_examples", "missed_examples")}, indent=1))
    print("flag-only Purpose bodies:")
    for k, v in out["flag_only_examples"].items():
        print(f"  {v:6d}  {k!r}")
    print("missed:", out["missed_examples"])


if __name__ == "__main__":
    main()
