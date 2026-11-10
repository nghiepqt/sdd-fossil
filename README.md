# The Myth of the "Living" Document

LOG6309E (Intelligent DevOps of Large-Scale Software Systems), Polytechnique Montréal, Fall 2026.
An empirical study on the MSR 2027 Mining Challenge dataset (SpecMine), planned to become a
4-page challenge paper.

## What this project is

In spec-driven development (SDD), developers write a Markdown *spec* that says what to build, and an
AI coding agent implements it. OpenSpec, the SDD tool with the most spec files in SpecMine, keeps one
*living spec* per capability under `openspec/specs/`. OpenSpec calls these specs the source of truth for
how the system currently behaves, and agents read them before every later change. When an archived
change created a new capability, OpenSpec (before v1.7.0) wrote a *placeholder* ("TBD - created by
archiving change … Update Purpose after archive.") into the spec's Purpose section. We call a living spec
that still holds this placeholder and was never revised a *fossil*. Our question: are living specs actually
maintained, or written once and forgotten? The full plan is in
[`proposal/proposal_v2.pdf`](proposal/proposal_v2.pdf).

## Where we are

**Done (as of November 9, 2026).** All numbers below come from [`results/numbers.json`](results/numbers.json).

- The data pipeline is reproducible from the raw SpecMine tables.
  - SpecMine v1.0 has 470,795 spec files in 73,030 repositories.
  - Our cohort keeps the 468,163 specs that have both a commit history and content (735,667 commits). The 2,632 dropped files lack one or both.
  - OpenSpec accounts for 274,955 files (58.4%) in 8,926 repositories.
- Headline result: of the 72,971 OpenSpec living specs,
  - 62.7% (95% CI [62.4, 63.1]) were never revised after creation;
  - 29.2% hold an unfilled placeholder;
  - **19.6% (14,294 specs, CI [19.3, 19.9]) are fossils**;
  - 9.6% kept the placeholder through at least one revision.
- Baseline from OpenSpec's other roles: 96.7% of archived specs and 89.7% of delta specs were never revised.
- Fossils sit in 2,488 repositories, and the largest single repository holds 0.94% of them.
- Fossils cluster by repository. Among the 4,618 repositories with at least 3 living specs, 70% have a fossil rate at or below 10% or at or above 90%: 56% have none, 7% have only fossils.
- File-age robustness: among specs at least 90 days old, 58.0% were never revised and 16.8% are fossils.
- Checks on the data:
  - The placeholder flag catches all 19,651 specs that hold the archive text (recall 100.0%), and 92.2% of flagged specs hold that text.
  - SpecMine histories do not follow renames (29 of 30 sampled specs match a path-only `git log`), so revision counts are lower bounds.
- Sample sizes for manual coding (95% confidence, ±5%): 375 fossils and 379 revised specs.
- The proposal was revised after the instructor's 11 comments: four RQs, and a category taxonomy taken from the SpecMine paper. See [`proposal/response_to_comments.md`](proposal/response_to_comments.md).

**Not done yet.**
- RQ1:
  - the split of revisions into archive merges and other edits;
  - the robustness runs (file age, repository caps).
- Drawing the samples and the 30-spec taxonomy pilot.
- Double coding (Cohen's κ) and the LLM labelling pipeline.
- Cloning repositories to find *fixed* specs and later code changes.
- RQ2–RQ4 (Kaplan–Meier, χ² / Cramér's V).
- The course report and the MSR paper.

The dated plan is Fig. 3 of the proposal: numbers are frozen on Nov 22, the presentation is on Nov 26, the report and the MSR abstract are due on Dec 18, and the MSR paper on Dec 23.

**Open decisions.** See [`proposal/open_issues.md`](proposal/open_issues.md), section A:
- which groups RQ4 compares (A1);
- the bootstrap CIs and the unsourced "34%–67%" figure from the submitted proposal (A3);
- the dataset DOI (A4).

Text in the proposal marked "(to be decided)" depends on these decisions.

## Setup

You need:
- Python 3.12;
- `bash`, `curl` and `git` (`git` for the rename check);
- optionally, a TeX Live installation to compile the proposal (IEEEtran is included in `proposal/`; you also need the `pgfgantt`, `tikz`, `listings`, `cleveref`, `microtype` and `booktabs` packages, which are all in a full TeX Live).

Run all commands from the repository root.

With [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Without uv:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` pins every package that the scripts import:
- duckdb, pandas, numpy, matplotlib, scipy, statsmodels;
- pyarrow, which pandas uses for Parquet;
- lifelines, which the planned Kaplan–Meier analysis will use.

## Getting the data

`bash src/fetch_data.sh` downloads the raw data into `data/raw/`. It skips any file that is already there. **It needs network access.**

| File | Source | Size |
|---|---|---|
| `spec_files.parquet` | Hugging Face mirror of SpecMine v1.0 (`ShyAgarwal/specmine`) | 676 MB |
| `spec_file_commits.parquet` | same | 423 MB |
| `spec_content_features.parquet` | same | 11 MB |
| `repo_trees.parquet` | same | 1.5 MB |
| `zenodo/specs.jsonl.gz` (snapshot text of every spec) | Zenodo record 22102780. HTTP range requests fetch only this member of the 5.4 GB zip. | 998 MB |

Disk use:
- raw data: about **2.1 GB**;
- derived data (`data/derived/`, written by the pipeline): about **0.2 GB**;
- the rename check's clones: about 15 MB.

Plan for about **2.5 GB** in total, plus about 0.6 GB for the virtual environment.

The SpecMine documentation in `data/raw/docs/` is not fetched by the script. It is optional, and is only needed to read the data dictionary and the paper:

```bash
mkdir -p data/raw/docs
for f in README.md DATA_DICTIONARY.md schema.sql; do
  curl -fsSL -o data/raw/docs/$f https://raw.githubusercontent.com/shyamagarwal13/specmine-official/main/$f
done
curl -fsSL -o data/raw/docs/arxiv_v4.pdf https://arxiv.org/pdf/2608.25202v4
```

## Running everything

```bash
source .venv/bin/activate
bash src/run_all.sh ~/specmine_clones     # the argument is where s03 clones repositories
```

`run_all.sh` runs these steps in order:

| Step | What it does | Writes |
|---|---|---|
| `fetch_data.sh` | Downloads the raw data if missing (network). | `data/raw/` |
| `s00_headline.py` | Builds the cohort and computes the headline numbers per tool and role, with Wilson CIs and file-age filters. | `numbers.json`: `cohort`, `headline`, `age_filtered`; `data/derived/openspec_living.parquet` |
| `s01_repo_fossil_dist.py` | Computes the fossil rate per repository and draws Fig. 4 of the proposal. | `repo_fossil`; `results/figures/repo_fossil_rate.pdf` |
| `s02_verify_placeholder_flag.py` | Checks SpecMine's placeholder flag against the OpenSpec placeholder text over all living specs (reads `specs.jsonl.gz`). | `placeholder_flag`; `data/derived/living_content.parquet` |
| `s03_check_renames.py` | Checks whether SpecMine's per-file history follows renames. It **clones about 30 small GitHub repositories** (blobless, network) into the folder given as argument (default `$TMPDIR/specmine_clones`, or `/tmp/specmine_clones`). | `renames`; `data/derived/rename_check.csv` |
| `s04_sample_sizes.py` | Computes the sample sizes for coding (Cochran's formula with finite-population correction). | `sample_size` |
| `s05_example_fossil.py` | Picks one example fossil with a fixed seed and anonymizes it (Fig. 2). | `results/example_fossil_spec.md` |
| `make_macros.py` | Turns `numbers.json` into LaTeX macros. | `proposal/numbers.tex`, `report/numbers.tex` |

A full run took **73 seconds** on the machine it was measured on (20 cores, 16 GB RAM, Linux, data already downloaded). Downloading the data adds the transfer time for about 2.1 GB.

After the run, `git diff results/numbers.json` should show only the known differences below. Anything else: tell the team before using any number.

Known differences between runs (none of them reaches a paper or `numbers.tex`):
- `placeholder_flag.flag_only_examples`: the list shows the 15 most frequent flagged Purpose texts. Texts with the same count (the last ones have 6) can swap in or out from one run to the next.
- `repo_fossil.k3.mean` and `repo_fossil.k5.mean` can differ in the 16th to 17th digit (floating-point summation order).
- `results/figures/repo_fossil_rate.pdf` differs only in its creation date.

If a new experiment adds numbers that must be exactly reproducible, make the script deterministic (add a tie-breaker to every sort, round stored values) and update this list.

To compile the proposal:

```bash
cd proposal
pdflatex proposal_v2 && bibtex proposal_v2 && pdflatex proposal_v2 && pdflatex proposal_v2
```

## Repository map

| Path | Content |
|---|---|
| `src/` | The pipeline: `run_all.sh`, `fetch_data.sh`, `s00`–`s05`, `make_macros.py`, shared helpers in `common.py`. |
| `data/raw/` | SpecMine tables and the spec text. Not in git; fetched; read-only. |
| `data/derived/` | Tables derived by the pipeline. The `.parquet` files are not in git (regenerate them with `run_all.sh`); small text outputs are. |
| `results/` | `numbers.json` (every number we use), `figures/` and the example spec excerpt. |
| `proposal/` | `proposal_v2.tex/.pdf` (the current direction document), `response_to_comments.md`, `open_issues.md`, `instructor_comments.pdf` (the submitted proposal with the instructor's comments), and the older `proposal.tex`. |
| `report/` | The course report (IEEE template, not started). |
| `labels/` | Sample IDs, codebook, human labels and LLM outputs (empty until sampling). |

## Rules of the repo

- **No hand-typed numbers.** Every number in a paper comes from `results/numbers.json`, through `src/make_macros.py` and the generated `numbers.tex` (e.g. `\pctFossil`). A new number needs a script that writes it to `numbers.json`.
- **`data/raw/` is read-only.** Write everything derived to `data/derived/` or `results/`.
- **Fixed random seeds** for every sample (e.g. `SEED` in `s03` and `s05`), and pinned package versions.
- **Dataset version.** The dataset is **SpecMine v1.0 (July 2026 snapshot)**. There is no v1.1 of the full dataset. The docs in `data/raw/docs/` say "v1.1" because they describe the 500-repository sample.
- **Human labels belong to the students.** Scripts may prepare coding sheets and compute agreement, but never fill in human labels.
- **Claims.** This is a characterization study: we report associations, not causes.

## Key definitions

Same wording as `proposal/proposal_v2.tex`.

- **Spec:** a Markdown file, written before or alongside the code, that describes what a system should do.
- **Living spec:** a spec in `openspec/specs/`. Each one describes how one capability of the system currently behaves and is meant to be updated whenever an archived change affects that capability.
- **Revision:** a commit that touches the file after its creation commit.
- **Archive merge:** a revision written by OpenSpec's archive step (a commit that also creates a file under `changes/archive/`). It follows automatically from archiving a change, so it says little about whether anyone chose to maintain the spec; other edits are deliberate.
- **Placeholder:** the text `TBD - created by archiving change <name>. Update Purpose after archive.` Before v1.7.0, OpenSpec wrote it into the Purpose section of a new capability's spec. In the data, this is SpecMine's `has_unfilled_placeholder` flag at the snapshot.
- **Fossil:** a living spec whose snapshot content holds an unfilled placeholder and that has zero revisions.
