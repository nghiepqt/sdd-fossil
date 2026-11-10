#!/usr/bin/env bash
# Fetch the SpecMine v1.0 tables used by this project into data/raw/ (read-only afterwards).
# Parquet: Hugging Face per-table mirror of SpecMine v1.0 (identical byte sizes to the Zenodo copy).
# Spec text: specs.jsonl.gz, extracted from the Zenodo archive with HTTP range requests
# (the 5.4 GB zip stores members uncompressed, so only the ~1 GB member is downloaded).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw/zenodo
HF=https://huggingface.co/datasets/ShyAgarwal/specmine/resolve/main/data
for t in spec_files spec_file_commits spec_content_features repo_trees; do
  [ -f "data/raw/$t.parquet" ] || curl -fsSL -o "data/raw/$t.parquet" "$HF/$t.parquet"
done
ZIP=https://zenodo.org/api/records/22102780/files/specmine.zip/content
[ -f data/raw/zenodo/specs.jsonl.gz ] || \
  python -I src/zip_range_extract.py "$ZIP" specmine-zenodo/specs.jsonl.gz data/raw/zenodo/specs.jsonl.gz
chmod a-w data/raw/*.parquet data/raw/zenodo/specs.jsonl.gz
