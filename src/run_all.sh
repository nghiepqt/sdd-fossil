#!/usr/bin/env bash
# Re-run every analysis end to end from the raw SpecMine tables, then rebuild the LaTeX macros.
# Usage: bash src/run_all.sh [scratch_dir_for_git_clones]
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
SCRATCH=${1:-${TMPDIR:-/tmp}/specmine_clones}
bash src/fetch_data.sh
$PY src/s00_headline.py
$PY src/s01_repo_fossil_dist.py
$PY src/s02_verify_placeholder_flag.py
GIT_TERMINAL_PROMPT=0 $PY src/s03_check_renames.py "$SCRATCH"
$PY src/s04_sample_sizes.py
$PY src/s05_example_fossil.py
$PY src/make_macros.py
