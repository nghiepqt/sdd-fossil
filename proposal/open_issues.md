# Open issues: proposal v2

These are the points the agent could not settle without the team. Sections A and B need a decision. C, D and E are for information or later work.

---

## A. Decisions needed

### A1. Which groups RQ4 compares

"Revised living specs" and "fossils" do not cover all living specs. The 72,971 living specs split into:

| Group | Definition | Count | Source |
|---|---|---|---|
| Revised | ≥ 1 revision | 27,184 (`\numRevised`) | `numbers.json` |
| Fossil | placeholder at snapshot, 0 revisions | 14,294 | `numbers.json` |
| Never revised, no placeholder | 0 revisions, no placeholder | 31,493 = 45,787 − 14,294 | derived from `numbers.json`; not yet a macro |

The third group is about twice the fossil group. It is neither maintained nor a fossil: these specs were never touched, but they also never had the tool-written TBD, or their Purpose was filled at creation.

- **Default written into v2 (please confirm or change):** revised vs fossil is the main contrast. Never-revised specs without a placeholder are reported as a third group wherever that is cheap (automatic features). They are not coded manually.
- **Alternatives:**
  - (a) a three-way comparison everywhere. This needs a third coded sample (about 380 more specs; Cochran with finite-population correction).
  - (b) revised vs all never-revised specs. This drops the placeholder from the contrast.
- **Related:** the "revised" group mixes specs whose only revisions are archive merges with specs that got other edits. Should RQ4 use "revised by another edit" as the maintained group? That would follow the reasoning of comment 1.2.

### A2. The schedule in Fig. 2

> **Update (2026-11-09): answered by the team.** The team gave the actual plan with dates: numbers frozen on Nov 22, the course presentation on Nov 26, the course report and the MSR 2027 Mining Challenge abstract on Dec 18, and the MSR paper on Dec 23. It is now Fig. 3 of `proposal_v2.pdf`. The text below is kept for the record.

The bars were relabelled to the new RQs, but the dates were **not** changed:

- The caption still says "week 1 starts Sep. 28, 2026; report due Dec. 18", as submitted.
- The team's earlier internal plan gave **December 13, 2026** as the hard end date, with the report and presentation in weeks 9–11 (Nov 23 – Dec 13).

Please give the dates for the report and the presentation, and say whether the plan should show them as separate milestones.

Also note: today (Nov 9) is the start of week 7. The plan shows RQ2/RQ3 and the pilot coding in weeks 5–6, which have passed. Should the bars reflect the actual state?

### A3. Content in the submitted PDF with no source in code

| Item in the submitted PDF | Script found? | What v2 does |
|---|---|---|
| "among specs born with the placeholder (**34%–67%** from snapshot data)" (old RQ2) | **No.** Nothing in `src/` or `results/numbers.json`. | The number is removed. The planned analysis ("among specs born with the placeholder") is kept, without a number. |
| "95% CIs from a **bootstrap over repositories**, as fossils cluster" (old RQ1) | **No.** No bootstrap code exists. | Removed, as the brief instructs. RQ1 now says Wilson 95% CIs, which match Table I. |
| Kaplan–Meier curves of time to first revision | No code yet. | Kept as a planned method (now in RQ2). It is a plan, not a result. |
| Split of revisions into archive merges and other edits | No code yet. | Kept as a planned method (RQ1, RQ2). |

**Likely origin of "34%–67%".** This is a reconstruction, not confirmed. The two ends match bounds on the fossil share among specs born with the placeholder, computed from existing counts:

- **67.0%** = 14,294 / 21,325. Here every spec that holds a placeholder now is treated as born with one; this is the lower bound on the denominator.
- **34.5%** = 14,294 / 41,478. This adds the 20,153 revised specs without a placeholder now (27,184 − 7,031), which could have had one at birth. Never-revised specs without a placeholder cannot have had one.

If the team confirms this was the intended definition, we can add it to a script and a macro, and restore the sentence.

**Bootstrap.** This was a planned method, not a reported value. The team's rule is not to drop a planned analysis without asking, so please decide whether to restore it. Restoring it costs one clause in RQ1 and needs no number. Fig. 1 does show that fossils cluster by repository, which is the reason a cluster bootstrap was proposed. The repository-dominance robustness check (per-repository caps, leave-largest-out) remains in v2.

### A4. Dataset DOI mismatch

| Source | DOI |
|---|---|
| `proposal.bib` (`specmine_dataset`, shown as [12] in v2) | 10.5281/zenodo.**22102780** |
| `data/raw/docs/README.md` (SpecMine citation block) | 10.5281/zenodo.**22102779** |
| The team's earlier internal project plan | 10.5281/zenodo.**22102779** |
| MSR 2027 call for papers (per the brief) | 10.5281/zenodo.**22102779** |

v2 keeps **22102780**, as instructed. Evidence on both sides:

- `src/fetch_data.sh` downloads `specs.jsonl.gz` from Zenodo **record 22102780**.
- A comment in `proposal.bib` says all entries were verified on 2026-10-18 through the Zenodo API.
- A Zenodo record whose number is one below a version's record is often the "concept" DOI (all versions). That would explain the pair, but it has **not** been checked. Please check on zenodo.org which DOI is the concept DOI and which is v1.0, and decide which one to cite.

---

## B. Changes in v2 the team should confirm

1. **(Undone on 2026-11-09: Related Work is again its own section, with the submitted wording.)** **Related Work no longer has its own section.** To fit 2 pages, the first cut in the brief's order folded it into the Problem Statement (Sec. I, ¶3). All citations ([5]–[7], [9], [10]) are kept. The section labels of the proposal (`statement`, `research-idea`, `dataset`, `schedule`) look like the course template's; Related Work looked like our own addition. If the template requires a Related Work section, something else must be cut.
2. **(Undone on 2026-11-09: the 90-day values are back in RQ1.)** **Robustness.** The preliminary 90-day values (58.0% never revised, 16.8% fossils) were dropped from the text. They are still in `numbers.json` and the macros (`\pctNeverRevisedOldNinety`, `\pctFossilOldNinety`).
3. **Data caveats.** These were reworded more tightly. "(recall 100.0%)" was dropped because "catches all … specs" says the same. All other caveat numbers are kept.
4. **New sample of revised specs (about 379).** RQ2 asks for the spec category of revised specs, so a second coded sample is needed. Its size comes from `src/s04_sample_sizes.py` (95% confidence, ±5%, finite-population correction, N = 27,184). This roughly doubles the LLM labelling. Please confirm that double coding (100 specs) should draw from both samples.
5. **Fixed specs moved to RQ2.** In the submitted version, they were the contrast group for fossils. They are a subset of revised specs, so they now sit in RQ2 ("we record who filled the placeholder").
6. **New baselines.** These were added so that every RQ has one. RQ2: counting archive merges as maintenance. RQ4: the naive split into never-revised and revised specs. RQ3 keeps the submitted baselines (no-placeholder control group, inactive repositories). RQ1 now carries the archived/delta comparison (96.7% of archived specs never revised), which was in the old RQ1 and old RQ3.
7. **Placement of the living-spec definition.** It is in Sec. I at the term's first use, not in the definition list at the start of Sec. II where comment 1.3 sits. We chose this so that no term appears before its definition. It can be moved if you prefer.
8. **Removed wording.** The sentence "as the instructor suggested" is gone, since RQ3 now stands on its own.
9. **Layout.** The fossil-rate figure (now Fig. 4) is set at 0.9 column width. The 2-page Gantt chart was later replaced by the dated plan (Fig. 3).

---

## C. Notes on the category taxonomy (comment 1.7)

- **Origin of the kind-of-work labels.** SpecMine takes these labels from **Watanabe et al.** (reference [38] in arXiv:2608.25202v4: M. Watanabe, H. Li, Y. Kashiwa, B. Reid, H. Iida, A. E. Hassan, "On the use of agentic coding: An empirical study of pull requests …"). We cite only the SpecMine paper, because we have not verified the Watanabe reference independently. It should probably be cited in the final report once verified. One author is listed as "H. Li"; it may be worth checking whether this is Prof. Heng Li.
- **Risk that the taxonomy does not fit living specs.** This is the first thing the pilot should check. SpecMine's prompts tell the judge to set `is_spec=false` (spec content, rule 6) or `is_spec_of_work=false` with `["none"]` labels (kind of work, rule 5) for documents that "describe a system as it already stands". Living specs do exactly that, by definition. Yet SpecMine reports purpose and object label shares for "OpenSpec capability" specs (Fig. 4 of the paper), so its judge did label them in practice. The pilot should measure how often the kind-of-work prompt returns "none" on living specs.
- **Completeness levels.** "complete except Purpose / skeletal / near-empty" come from the team's draft codebook and are ours. The pilot should confirm or revise them.
- **SpecMine's own judge.** It used gemini-2.5-pro at temperature 0. Our LLM is not chosen yet.
- **No precomputed labels.** SpecMine does not ship its judge labels in the tables we have (no judge columns in `DATA_DICTIONARY.md`), so we cannot reuse their 1,000 labels directly.

---

## D. For the final report (comment 1.8)

> **Update (2026-11-09):** both figures are now in `proposal_v2.pdf` (Figs. 1 and 2). The example spec is chosen by `src/s05_example_fossil.py` (fixed seed) and written to `results/example_fossil_spec.md`. The repository owner and name, the change name, paths and package names are masked. The requirement sentences are kept verbatim, so a GitHub code search on a full sentence may still find the source: **paraphrase them before any publication** (MSR paper, public report or public repository) and keep calling the excerpt "lightly edited".

1. **An example spec from the dataset.** A suggestion: one fossil living spec showing the tool-written `TBD - created by archiving change <name>. Update Purpose after archive.` Purpose above its requirements and scenarios. Possibly put it next to the same capability's spec in a repository where the Purpose was filled. Source: `data/derived/living_content.parquet`. **Anonymize the repository** (the SpecMine README asks users to avoid deanonymization) and shorten long scenario blocks.
2. **A workflow figure.** Show propose → apply → archive:
   - the `changes/<name>/` folder (proposal, delta specs, design, tasks);
   - the agent reading `openspec/specs/` as context and implementing the tasks;
   - archiving moving the change to `changes/archive/` and merging its delta into `openspec/specs/`.

   Mark the two events our study measures: the **archive merge** (a revision) and the **placeholder** written into a new living spec's Purpose. This answers "how the agents interact with each other" and also explains comment 1.2 visually.

---

## E. Other things found while revising

- **Where the submitted PDF is.** `Thanh_Nghiep_Quan_Final_Proposal.pdf` was not in the project root. It is in the trash: `/mnt/data/.Trash-1000/files/Thanh_Nghiep_Quan_Final_Proposal.pdf`, deleted 2026-11-09 21:26, original path `FinalProject/Thanh_Nghiep_Quan_Final_Proposal.pdf`. It was read from there and **not** restored. The comments PDF (`proposal/instructor_comments.pdf`) contains the same text. You may want to restore the original.
- **Annotations in the comments PDF.** The 11 numbered icons are links to the "Index des commentaires" page. The highlighted phrases with no number (e.g. "whether living specs are actually maintained", "written once and never finished; it is also stale only", "mixes finished specs with forgotten ones", "fossils cluster by repository") are flattened into the page and carry no text. We treated them as emphasis, not as comments.
- **The SpecMine paper changed title in arXiv v4.** Versions v1–v3 were titled "SpecMine: A large-scale corpus of spec-driven development artifacts" with four authors. v4 (15 Oct 2026) is titled "Spec-Driven Development as Prescribed and as Practiced", with authors **Agarwal, Singhal, Macvean, Vasilescu, Breaux**. Cite v4. `proposal.bib` matches v4; this was checked against `data/raw/docs/arxiv_v4.txt`.
- **Dataset version labels.** The SpecMine docs in `data/raw/docs/` (README, `DATA_DICTIONARY.md`) are headed "v1.1". They describe the 500-repository sample, whose Kiro tables were enriched in v1.1. Our tables are the full **v1.0** dataset (the Hugging Face mirror of the Zenodo release), so v2 says "SpecMine v1.0 (July 2026 snapshot)".
- **New code and numbers:**
  - `src/s04_sample_sizes.py` writes section `sample_size` to `results/numbers.json`: fossils N = 14,294 → 375 (±5%) or 96 (±10%); revised N = 27,184 → 379 (±5%) or 96 (±10%).
  - `src/make_macros.py` adds `\numRevised`, `\numSampleFossils`, `\numSampleFossilsTen`, `\numSampleRevised`, `\numSampleRevisedTen` and `\pctConfSample`.
  - `src/run_all.sh` now runs `s04`.
  - Regenerating the macros also rewrote `report/numbers.tex`. All existing macros are unchanged; only the new ones were added.
- **Numbers still typed by hand.** No result is typed by hand. What remains is design parameters and identifiers:
  - design parameters: 30/60/90 days, the 10%/90% thresholds, the 30-spec pilot, 100 double-coded specs, κ ≥ 0.6, temperature 0, ±5%, 95%;
  - dates: July 29, July 11, Sep. 28, Dec. 18;
  - version numbers and PR numbers.

  "July 11" also exists as `cohort.snapshot_end` in `numbers.json` and could become a macro if you want full strictness.
- **Fossil-rate figure colour (now Fig. 4).** It is a single blue series; this is fine in grayscale, but use a neutral palette for the final report (team rule: figures must be readable in grayscale, with no rainbow palettes).

### Differences between `proposal/proposal.tex` and the submitted PDF (step 1)

`proposal_v2.tex` was first rebuilt to match the submitted PDF. A word-level comparison of the compiled rebuild against the submitted PDF showed only hyphenation differences and the "34%–67%" figure. v2 then applies the changes described above. The older `.tex` differed from the submitted PDF as follows:

1. **Abstract:** "calls these specs the source of truth for how the system currently behaves" → "calls it the source of truth".
2. **Sec. I ¶1:** "OpenSpec's documentation states that these specs are the source of truth: they describe how your system currently behaves … read them as context for every later change" → "OpenSpec calls these specs the source of truth for how the system currently behaves … read them before every later change".
3. **Sec. I ¶2:**
   - "was released … (July 11, 2026), so every spec in the snapshot was created by tool versions that could write the placeholder" → "shipped … (July 11), so any spec in the snapshot could have received the placeholder";
   - "written once and forgotten" → "written once and never finished; it is also stale only if its code moved on (RQ2)".
4. **Sec. I ¶3:** "report spec decay in living specs, but commit counts alone cannot show it" → "report spec decay, which commit counts alone cannot show".
5. **Link with the course:** "kept as code next to the system they describe … configuration drift in DevOps … we measure how much such gates are needed" → "kept as code; … configuration drift … we measure how often such a gate would fire on existing specs".
6. **Sec. II opening:** the PDF adds the archive-merge sentence.
7. **RQ1:**
   - the `.tex` compares living specs with archived, delta and Spec Kit specs, uses Wilson CIs and χ², and has Kaplan–Meier "if time permits";
   - the PDF has the archive-merge split, Kaplan–Meier (planned), bootstrap CIs and χ².
8. **RQ2:**
   - the PDF adds "among specs born with the placeholder (34%–67% from snapshot data)", "one fixed spec" per repository, "which separate stale fossils from unfinished ones", "≈375 … (95% confidence, ±5%)";
   - the `.tex` has "After computing the fossil rate of each repository …" and "the remaining sample of about 375 fossils".
9. **Old RQ3:** the `.tex` has "tools label spec files differently … contrast with the pooled comparison"; the PDF has "Spec Kit's per-feature specs resemble OpenSpec's change specs … compare like with like across tools, against the pooled comparison".
10. **Robustness:** "were created less than 30 days before the snapshot" → "are under 30 days old".
11. **Dataset:**
    - "the snapshot text of every spec (`specs.jsonl.gz`, on Zenodo only)" → "snapshot texts (…, Zenodo only)";
    - "lack history (…), content (…), or both (…)" → "lack history (…) or content (…); … of them lack both".
12. **Table I:** caption adds "(Wilson CIs)"; "Repos holding fossils (largest: …)" → "Repos with fossils (largest share: …)".
13. **Data caveats:** same numbers, different wording. "29 of 30" **was already in the `.tex`** through the macros `\numRenamePlainMatch` of `\numRenameChecked`. The PDF adds "among them", "(recall 100.0%)" and "98.7% some TBD Purpose" phrasing.
14. **Related Work:** the `.tex` has longer sentences ("Lethbridge et al. found …", "practitioner interviews and 266 repositories … at scale. We answer their lifecycle question …"); the PDF condenses them.
15. **Fig. 2 and the references** are identical.
