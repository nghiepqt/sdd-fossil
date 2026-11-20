"""Pilot agreement (codebook v0), automatic Purpose status, and the codebook-v1 recheck sheet.

Codebook v1 (team decision 2026-11-19, labels/README.md):
- Taxonomy B is dropped by its stop rule (decision brief 2026-11-12, item 1). This script checks the rule
  on the pilot sheets and records the result.
- Completeness is split in two. `purpose_status` is computed here from the spec text, never coded by hand.
  `body_completeness` (Purpose ignored) is coded by the students.

Steps:
1. purpose_status and structural counts for every sampled spec (pilot, double, llm_only)
   -> labels/auto_features.csv. The file reveals the group (fossils are tbd_archive), so coders must not
   open it while coding.
2. Agreement of the two pilot coders under codebook v0 (raw agreement, Cohen's kappa; linear-weighted
   kappa for the ordinal extents) and the stop rule for taxonomy B -> section "pilot" of numbers.json.
   Coder 2's sheet has no item_id column; row n is item Pnn (confirmed by coder 2 on 2026-11-19).
3. Recheck 1: the N_RECHECK pilot items on which the coders disagreed most, as an empty v1 sheet in
   labels/pilot/recheck/ (with a copy of their spec files, so that src/label_ui.py can open it).
   Recheck 2 (after Rules 4a/4b, 2026-11-20): N_RECHECK of the other 20 pilot items, drawn at random, in
   labels/pilot/recheck2/. The v1 agreement of both rechecks goes to numbers.json when both sheets are coded.

Human labels are filled in by the students only. This script never writes a label into a coder sheet.
"""
import json
import re
import shutil

import numpy as np
import pandas as pd

from common import DERIVED, ROOT, connect, update_numbers

LABELS = ROOT / "labels"
PILOT = LABELS / "pilot"
CODER_SHEETS = {"coder1": PILOT / "coding_sheet_person1.csv", "coder2": PILOT / "coding_sheet_person2.csv"}
ROW_ORDER_FROM_POSITION = {"coder2": "row n = item Pnn, confirmed by coder 2 on 2026-11-19"}
SEED = 20261119
N_RECHECK = 10
SEED_RECHECK2 = 20261120  # recheck 2: random draw from the pilot items not in recheck 1
EXTENT = ["none", "incidental", "substantial", "dominant"]
V0_FIELDS = ["is_spec", "requirements_extent", "implementation_extent", "completeness",
             "is_spec_of_work", "purpose", "object"]
V1_FIELDS = ["is_spec", "requirements_extent", "implementation_extent", "body_completeness", "note"]
B_MIN_SHARE = 0.15   # stop rule: >= 2 labels each in >= 15% of the pilot specs ...
B_MIN_LABELS = 2     # ... AND most pilot specs have is_spec_of_work = true

# Same pattern as s02 (RE_ARCHIVE_ANY): the OpenSpec archive placeholder, tolerant to dash variants.
RE_ARCHIVE_ANY = re.compile(r"TBD\s*[-—–]\s*created by archiving change.*?Update Purpose after archive", re.I | re.S)
RE_PURPOSE = re.compile(r"^##\s+Purpose\s*$(.*?)(?=^##\s|\Z)", re.M | re.S | re.I)
RE_OTHER_TBD = re.compile(r"\b(TBD|TODO|FIXME)\b|to be (defined|determined|written|filled)", re.I)
RE_REQ = re.compile(r"^###\s+Requirement:", re.M | re.I)
RE_SCEN = re.compile(r"^####\s+Scenario:", re.M | re.I)
RE_DELTA = re.compile(r"^##\s+(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements\b", re.M | re.I)
RE_FENCE = re.compile(r"^\s*```", re.M)
RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)  # Rule 4b: not body lines


def purpose_status(text):
    """filled / tbd_archive / tbd_other / empty / missing, from the ## Purpose section of the spec text."""
    m = RE_PURPOSE.search(text)
    if not m:
        return "missing"
    body = m.group(1).strip()
    if not body:
        return "empty"
    if RE_ARCHIVE_ANY.search(body):
        return "tbd_archive"
    if RE_OTHER_TBD.search(body):
        return "tbd_other"
    return "filled"


def body_lines(text):
    """Lines with content in the body: no headings, no blank lines, no Purpose section, no HTML comments
    (Rule 4b; this also drops the item header that s08 writes as an HTML comment)."""
    text = RE_HTML_COMMENT.sub("", RE_PURPOSE.sub("", text))
    return sum(1 for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#"))


def html_comment_lines(text):
    """Lines inside HTML comments, without the item header of line 1."""
    text = text.split("\n", 1)[1] if text.startswith("<!-- item ") else text
    return sum(m.group(0).count("\n") + 1 for m in RE_HTML_COMMENT.finditer(text))


def structure(text):
    """Requirement and scenario counts; requirements without a scenario before the next requirement/section."""
    blocks = re.split(r"(?=^###\s+Requirement:)", text, flags=re.M | re.I)[1:]
    no_scen = sum(1 for b in blocks if not RE_SCEN.search(re.split(r"^##\s", b, maxsplit=1, flags=re.M)[0]))
    return {"n_body_lines": body_lines(text), "n_html_comment_lines": html_comment_lines(text), "n_requirements": len(RE_REQ.findall(text)), "n_scenarios": len(RE_SCEN.findall(text)),
            "n_requirements_without_scenario": no_scen, "n_delta_headers": len(RE_DELTA.findall(text)),
            "n_code_blocks": len(RE_FENCE.findall(text)) // 2}


def auto_features(con):
    frame = pd.read_csv(LABELS / "sample_frame.csv")
    content = dict(con.sql(f"""SELECT file_url_sha16, content FROM read_parquet('{DERIVED / "living_content.parquet"}')
        WHERE file_url_sha16 IN (SELECT unnest(?::VARCHAR[]))""", params=[sorted(frame.file_url_sha16)]).fetchall())
    rows = [{"item_id": r.item_id, "purpose_status": purpose_status(content[r.file_url_sha16]),
             **structure(content[r.file_url_sha16])} for r in frame.itertuples()]
    out = pd.DataFrame(rows).sort_values("item_id")
    out.to_csv(LABELS / "auto_features.csv", index=False)
    by = frame[["item_id", "group"]].merge(out, on="item_id")
    status = {g: {k: int(v) for k, v in d.purpose_status.value_counts().items()} for g, d in by.groupby("group")}
    lines = {g: {q: float(d.n_body_lines.quantile(x)) for q, x in (("p25", .25), ("median", .5), ("p75", .75))}
             for g, d in by.groupby("group")}
    return out, status, lines


def read_sheet(name, path):
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    if "item_id" not in df.columns:
        if not ROW_ORDER_FROM_POSITION.get(name):
            raise ValueError(f"{path} has no item_id column")
        idcol = df.columns[0]
        df["item_id"] = [f"P{int(x):02d}" for x in df[idcol]]
    df = df.set_index("item_id")
    for c in V0_FIELDS:
        df[c] = (df[c].str.strip().str.lower().replace({"yes": "true", "no": "false"})
                 .str.split(";").map(lambda v: ";".join(sorted(x.strip() for x in v if x.strip()))))
    return df


def cohen_kappa(x, y, order=None, weights=None):
    cats = order or sorted(set(x) | set(y))
    idx = {c: i for i, c in enumerate(cats)}
    m = np.zeros((len(cats), len(cats)))
    for u, v in zip(x, y):
        m[idx[u], idx[v]] += 1
    m /= m.sum()
    expected = np.outer(m.sum(1), m.sum(0))
    i, j = np.indices(m.shape)
    w = (i != j).astype(float) if weights is None else np.abs(i - j) / (len(cats) - 1)
    denom = (w * expected).sum()
    return None if denom == 0 else float(1 - (w * m).sum() / denom)


def pilot_agreement(sheets):
    a, b = sheets["coder1"], sheets["coder2"]
    items = sorted(a.index)
    assert sorted(b.index) == items and len(items) == 30, "both pilot sheets must cover P01..P30"
    a, b = a.loc[items], b.loc[items]
    out = {}
    for f in V0_FIELDS:
        rec = {"agreement": float((a[f] == b[f]).mean()), "kappa": cohen_kappa(a[f], b[f]),
               "coder1": {k: int(v) for k, v in a[f].value_counts().items()},
               "coder2": {k: int(v) for k, v in b[f].value_counts().items()}}
        if f.endswith("_extent"):
            rec["kappa_linear"] = cohen_kappa(a[f], b[f], EXTENT, "linear")
        out[f] = rec
    stop = {}
    for name, s in sheets.items():
        work = float((s.is_spec_of_work == "true").mean())
        labels = pd.Series([v for col in ("purpose", "object") for cell in s[col] for v in cell.split(";")
                            if v and v != "none"])
        frequent = sorted(k for k, v in labels.value_counts().items() if v / len(s) >= B_MIN_SHARE)
        stop[name] = {"share_spec_of_work": work, "labels_at_15pct": frequent,
                      "passes": bool(len(frequent) >= B_MIN_LABELS and work > 0.5)}
    stop["taxonomy_b_kept"] = all(v["passes"] for k, v in stop.items() if k.startswith("coder"))
    return out, stop, a, b


def recheck_set(a, b, rng):
    """Items with the largest disagreement on the v1 fields (extent distance + completeness mismatch)."""
    r = {c: i for i, c in enumerate(EXTENT)}
    score = (abs(a.requirements_extent.map(r) - b.requirements_extent.map(r))
             + abs(a.implementation_extent.map(r) - b.implementation_extent.map(r))
             + (a.completeness != b.completeness).astype(int))
    d = pd.DataFrame({"score": score, "tie": rng.random(len(score))}, index=a.index)
    chosen = d.sort_values(["score", "tie"], ascending=[False, True]).head(N_RECHECK)
    ids = sorted(chosen.index)
    write_v1_sheet(PILOT / "recheck", ids)
    return ids, {i: int(chosen.score[i]) for i in ids}


def write_v1_sheet(out, ids):
    """Empty v1 sheet for the given pilot items, with a copy of their spec files (for label_ui.py)."""
    if (out / "specs").exists():
        shutil.rmtree(out / "specs")
    (out / "specs").mkdir(parents=True)
    template = pd.read_csv(PILOT / "coding_sheet_TEMPLATE.csv", dtype=str).set_index("item_id").loc[ids]
    sheet = template[["batch", "file_url"]].reset_index()
    for f in V1_FIELDS:
        sheet[f] = ""
    sheet.to_csv(out / "coding_sheet_TEMPLATE.csv", index=False)
    for i in ids:
        shutil.copy(PILOT / "specs" / f"{i}.md", out / "specs" / f"{i}.md")


def recheck2_set(recheck1_ids):
    """Recheck 2 (after Rules 4a/4b): N_RECHECK of the other pilot items, drawn at random."""
    rest = sorted(set(f"P{i:02d}" for i in range(1, 31)) - set(recheck1_ids))
    ids = sorted(np.random.default_rng(SEED_RECHECK2).choice(rest, size=N_RECHECK, replace=False).tolist())
    write_v1_sheet(PILOT / "recheck2", ids)
    return ids


def recheck_agreement(folder="recheck"):
    """v1 agreement of the two coders on a recheck set (their own copies of its template)."""
    sheets = sorted(p for p in (PILOT / folder).glob("coding_sheet_*.csv") if "TEMPLATE" not in p.name)
    if len(sheets) != 2:
        print(f"{folder}: expected 2 coder sheets, found {len(sheets)}; skipped")
        return None
    a, b = (pd.read_csv(p, dtype=str).fillna("").set_index("item_id") for p in sheets)
    fields = ["is_spec", "requirements_extent", "implementation_extent", "body_completeness"]
    if any((d[f].str.strip() == "").any() for d in (a, b) for f in fields) or sorted(a.index) != sorted(b.index):
        print(f"{folder}: a coder sheet is incomplete or covers other items; skipped")
        return None
    b = b.loc[a.index]
    out = {"codebook": "v1", "items": len(a), "coders": [p.stem.replace("coding_sheet_", "") for p in sheets], "fields": {}}
    for f in fields:
        x, y = a[f].str.strip().str.lower(), b[f].str.strip().str.lower()
        rec = {"agreement": float((x == y).mean()), "kappa": cohen_kappa(x, y),
               "coder_a": {k: int(v) for k, v in x.value_counts().items()},
               "coder_b": {k: int(v) for k, v in y.value_counts().items()}}
        if f.endswith("_extent"):
            rec["kappa_linear"] = cohen_kappa(x, y, EXTENT, "linear")
            r = {c: i for i, c in enumerate(EXTENT)}
            rec["b_higher"] = int((y.map(r) > x.map(r)).sum())
            rec["b_lower"] = int((y.map(r) < x.map(r)).sum())
        out["fields"][f] = rec
    return out


def main():
    con = connect()
    feats, status_by_group, lines_by_group = auto_features(con)
    result = {"codebook": "v0 (pilot)", "purpose_status_by_group": status_by_group,
              "body_lines_by_group": lines_by_group}
    if all(p.exists() for p in CODER_SHEETS.values()):
        sheets = {k: read_sheet(k, p) for k, p in CODER_SHEETS.items()}
        agree, stop, a, b = pilot_agreement(sheets)
        ids, scores = recheck_set(a, b, np.random.default_rng(SEED))
        result.update({"items": 30, "row_order_from_position": ROW_ORDER_FROM_POSITION, "fields": agree,
                       "taxonomy_b_stop_rule": stop,
                       "recheck": {"seed": SEED, "n": len(ids), "items": ids, "disagreement_score": scores}})
        ids2 = recheck2_set(ids)
        result["recheck2"] = {"seed": SEED_RECHECK2, "n": len(ids2), "items": ids2,
                              "rules_added": "4a black-box test, 4b HTML comments excluded, prompt content, link lists"}
    else:
        print("pilot sheets missing: agreement and recheck sets skipped")
    for folder, key in (("recheck", "recheck_v1"), ("recheck2", "recheck2_v1")):
        rc = recheck_agreement(folder)
        if rc:
            result[key] = rc
    update_numbers("pilot", result)
    print(json.dumps(result, indent=1, default=str))


if __name__ == "__main__":
    main()
