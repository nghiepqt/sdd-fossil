"""Turn results/numbers.json into LaTeX macros (proposal/numbers.tex and report/numbers.tex).

The LaTeX sources use these macros only; no number is typed by hand.
"""
import json

from common import NUMBERS, ROOT


def i(x):   # integer with LaTeX thousands separator
    return f"{int(x):,}".replace(",", "{,}")


def pct(x, d=1):
    return f"{100 * x:.{d}f}\\%"


def ci(w, d=1):
    return f"[{100 * w['ci_lo']:.{d}f}, {100 * w['ci_hi']:.{d}f}]\\%"


def build(n):
    h, c, r, a = n["headline"], n["cohort"], n["repo_fossil"], n["age_filtered"]
    k = r[f"k{r['k_main']}"]
    m = {
        # dataset and cohort
        "numSpecFiles": i(h["spec_files"]), "numRepos": i(h["repos"]),
        "numCohortSpecs": i(c["cohort_specs"]), "numDroppedSpecs": i(c["dropped_specs"]),
        "numNoHistory": i(c["no_commit_history"]), "numNoContent": i(c["no_content"]),
        "numNoBoth": i(c["no_history_and_no_content"]),
        "numCommitTable": i(c["commit_table_rows"]), "numCohortCommits": i(c["commit_rows_in_cohort"]),
        "numOrphanCommits": i(c["commit_rows_for_files_not_in_spec_files"]),
        "numOpenSpecFiles": i(h["openspec_files"]), "numOpenSpecRepos": i(h["openspec_repos"]),
        "pctOpenSpecFiles": pct(h["openspec_share_of_files"]),
        "numLiving": i(h["living"]), "numLivingRepos": i(h["living_repos"]),
        "numDelta": i(h["openspec_roles_cohort"]["change_proposal"]),
        "numArchived": i(h["openspec_roles_cohort"]["archived"]),
        # living-spec headline
        "pctNeverRevised": pct(h["never_revised"]["p"]), "ciNeverRevised": ci(h["never_revised"]),
        "pctPlaceholder": pct(h["placeholder"]["p"]), "ciPlaceholder": ci(h["placeholder"]),
        "numFossils": i(h["fossil"]["k"]), "pctFossil": pct(h["fossil"]["p"]), "ciFossil": ci(h["fossil"]),
        "numPlaceholderRevised": i(h["placeholder_revised"]["k"]),
        "pctPlaceholderRevised": pct(h["placeholder_revised"]["p"]),
        "pctNoPlaceholder": pct(h["no_placeholder"]["p"]),
        "numFossilRepos": i(h["fossil_repos"]), "pctTopFossilRepo": pct(h["top_fossil_repo_share"], 2),
        "pctArchivedNeverRevised": pct(h["openspec_role_never_revised"]["archived"]["p"]),
        "pctDeltaNeverRevised": pct(h["openspec_role_never_revised"]["change_proposal"]["p"]),
        # file age
        "numLivingYoungThirty": i(h["living_younger_than_30d"]),
        "pctLivingYoungThirty": pct(h["living_younger_than_30d"] / h["living"], 0),
        "pctLivingYoungNinety": pct(h["living_younger_than_90d"] / h["living"], 0),
        "numLivingOldNinety": i(a["min_age_90d"]["living"]),
        "pctNeverRevisedOldNinety": pct(a["min_age_90d"]["never_revised"]["p"]),
        "pctFossilOldNinety": pct(a["min_age_90d"]["fossil"]["p"]),
        # repo-level distribution (RQ2b step 1)
        "numRepoK": str(r["k_main"]), "numReposK": i(k["repos"]),
        "pctReposZeroFossil": pct(k["share_zero"], 0), "pctReposAllFossil": pct(k["share_one"], 0),
        "pctReposExtreme": pct(k["share_extreme"], 0),
    }
    if "sample_size" in n:   # s04_sample_sizes.py
        s = n["sample_size"]
        m |= {"numRevised": i(s["revised"]["population"]),
              "pctConfSample": pct(s["confidence"], 0),
              "numSampleFossils": i(s["fossil"]["n_margin_05"]),
              "numSampleFossilsTen": i(s["fossil"]["n_margin_10"]),
              "numSampleRevised": i(s["revised"]["n_margin_05"]),
              "numSampleRevisedTen": i(s["revised"]["n_margin_10"])}
    if "sample_size" in n and "edited" in n["sample_size"]:
        s = n["sample_size"]
        m |= {"numFossilsCodedPop": i(s["fossil_archive_text"]["population"]),
              "numSampleFossilsCoded": i(s["fossil_archive_text"]["n_margin_05"]),
              "numSampleEdited": i(s["edited"]["n_margin_05"])}
    if "bootstrap" in n:   # s07_bootstrap.py
        b = n["bootstrap"]
        bm = b["metrics"]
        m |= {"numBootB": i(b["B"]), "numBootRepos": i(b["repos"]),
              "bciNeverRevised": ci(bm["never_revised"]), "bciPlaceholder": ci(bm["placeholder"]),
              "bciFossil": ci(bm["fossil"]), "bciPlaceholderRevised": ci(bm["placeholder_revised"]),
              "bciTypeEdited": ci(bm["edited"]), "bciTypeMergeOnly": ci(bm["merge_only"]),
              "bciArchiveMerges": ci(bm["archive_merge_share_of_revisions"]),
              "bciFossilOldNinety": ci(bm["fossil_min_age_90d"])}
    if "samples" in n:   # s08_draw_samples.py
        sp = n["samples"]
        g = sp["groups"]
        m |= {"numSampleCap": i(sp["cap_per_repo"]),
              "numPilot": i(2 * sp["pilot_per_group"]), "numDoubleCode": i(2 * sp["double_per_group"]),
              "numDoublePerGroup": i(sp["double_per_group"]), "numFallbackPerGroup": i(sp["fallback_per_group"]),
              "numSampleFossilRepos": i(g["fossil"]["repos_in_sample"]),
              "numSampleEditedRepos": i(g["edited"]["repos_in_sample"])}
    if "pilot" in n and "fields" in n["pilot"]:   # s09_pilot_codebook.py (codebook v0)
        pf = n["pilot"]["fields"]
        st = n["pilot"]["taxonomy_b_stop_rule"]
        kap = lambda x: r"\textbf{n/a}" if x is None else f"{x:.2f}"
        m |= {"kappaPilotReq": kap(pf["requirements_extent"]["kappa"]),
              "kappaPilotImpl": kap(pf["implementation_extent"]["kappa"]),
              "kappaPilotCompleteness": kap(pf["completeness"]["kappa"]),
              "pctPilotAgreeImpl": pct(pf["implementation_extent"]["agreement"], 0),
              "pctPilotSpecOfWorkMax": pct(max(st[c]["share_spec_of_work"] for c in ("coder1", "coder2")), 0),
              "numRecheck": i(n["pilot"]["recheck"]["n"])}
        if "recheck_v1" in n["pilot"]:
            rf = n["pilot"]["recheck_v1"]["fields"]
            m |= {"kappaRecheckReq": kap(rf["requirements_extent"]["kappa"]),
                  "kappaRecheckReqLin": kap(rf["requirements_extent"]["kappa_linear"]),
                  "kappaRecheckImpl": kap(rf["implementation_extent"]["kappa"]),
                  "kappaRecheckImplLin": kap(rf["implementation_extent"]["kappa_linear"]),
                  "pctRecheckAgreeCompleteness": pct(rf["body_completeness"]["agreement"], 0)}
    if "renames" in n:
        rn = n["renames"]
        m |= {"numRenameChecked": i(rn["checked"]),
              "numRenamePlainMatch": i(rn["archived"]["specmine_equals_plain"] + rn["living"]["specmine_equals_plain"]),
              "numRenameLivingChecked": i(rn["living"]["checked"]),
              "numRenameLivingTrue": i(rn["living"]["follow_hops"].get("living_rename", 0))}
    if "revision_split" in n:   # s06_revision_split.py
        rs = n["revision_split"]
        t, t90, v = rs["type_by_placeholder"], rs["type_by_placeholder_min_age_90d"], rs["validation"]
        m |= {"numRevisions": i(rs["revisions"]), "numArchiveMerges": i(rs["archive_merges"]),
              "numOtherEdits": i(rs["other_edits"]),
              "pctArchiveMerges": pct(rs["merge_share"]["p"]), "ciArchiveMerges": ci(rs["merge_share"]),
              "numTypeMergeOnly": i(t["merge_only"]["total"]["k"]),
              "pctTypeMergeOnly": pct(t["merge_only"]["total"]["p"]),
              "numTypeEdited": i(t["edited"]["total"]["k"]),
              "pctTypeEdited": pct(t["edited"]["total"]["p"]), "ciTypeEdited": ci(t["edited"]["total"]),
              "numPhMergeOnly": i(t["merge_only"]["placeholder"]["k"]),
              "pctPhMergeOnly": pct(t["merge_only"]["placeholder"]["p"]),
              "ciPhMergeOnly": ci(t["merge_only"]["placeholder"]),
              "numPhEdited": i(t["edited"]["placeholder"]["k"]),
              "pctPhEdited": pct(t["edited"]["placeholder"]["p"]),
              "pctTypeEditedOldNinety": pct(t90["edited"]["total"]["p"]),
              "pctPhMergeOnlyOldNinety": pct(t90["merge_only"]["placeholder"]["p"]),
              "numMedianOtherEdits": i(rs["other_edits_per_edited_spec"]["median"]),
              "numPNinetyOtherEdits": i(rs["other_edits_per_edited_spec"]["p90"]),
              "pctMsgArchiveMerge": pct(v["msg_archive"]["merge"]["p"]),
              "pctMsgArchiveOther": pct(v["msg_archive"]["other"]["p"])}
    if "placeholder_flag" in n:
        p = n["placeholder_flag"]
        m |= {"pctFlagPrecision": pct(p["flag_vs_archive_any"]["precision"]),
              "pctFlagRecall": pct(p["flag_vs_archive_any"]["recall"]),
              "numArchivePlaceholder": i(p["n_archive_any"]),
              "numFlagOnly": i(p["flag_vs_archive_any"]["fp"]),
              "numFossilsArchiveText": i(p["fossils_by_archive_text"]),
              "pctFlagPurposeTbd": pct(p["flag_vs_purpose_tbd"]["precision"])}
    else:   # not computed yet: render a visible marker instead of a number
        m |= {k: r"\textbf{??}" for k in ("pctFlagPrecision", "pctFlagRecall", "numArchivePlaceholder",
                                            "numFlagOnly", "numFossilsArchiveText", "pctFlagPurposeTbd")}
    return m


def main():
    macros = build(json.loads(NUMBERS.read_text()))
    body = "% Generated by src/make_macros.py from results/numbers.json. Do not edit by hand.\n"
    body += "".join(f"\\newcommand{{\\{k}}}{{{v}\\xspace}}\n" for k, v in sorted(macros.items()))
    for d in ("proposal", "report"):
        (ROOT / d / "numbers.tex").write_text(body)
    print(f"wrote {len(macros)} macros")


if __name__ == "__main__":
    main()
