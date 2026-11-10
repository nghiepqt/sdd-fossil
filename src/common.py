"""Shared paths, DuckDB views, and the numbers.json writer.

Raw data (read-only) lives in data/raw/ and is fetched by src/fetch_data.sh.
"""
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DERIVED = ROOT / "data" / "derived"
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
NUMBERS = RESULTS / "numbers.json"
SPECS_JSONL = RAW / "zenodo" / "specs.jsonl.gz"

# Crawl end of SpecMine v1.0 (README of specmine-official; max file_first_commit_at is 2026-07-10).
SNAPSHOT_END = "2026-07-11"

# OpenSpec archive placeholder written into a new main spec's Purpose section
# (quoted verbatim in Fission-AI/OpenSpec PR #1431; shipped fix in v1.7.0, 2026-07-29).
PLACEHOLDER_REGEX = r"TBD - created by archiving change .*?\. Update Purpose after archive\."
# Looser variant: tolerant to dash/whitespace differences and changed change names.
PLACEHOLDER_LOOSE_REGEX = r"(?i)TBD.{0,200}?Update Purpose after archive"


def connect() -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB with one view per raw table and the analysis cohort.

    Cohort `base`: spec files with a fetched commit history (commit_history_status = 'done')
    AND a content-features row (i.e. content was fetched). This is the 468,163-spec set.
    """
    con = duckdb.connect()
    for t in ("spec_files", "spec_file_commits", "spec_content_features", "repo_trees"):
        con.sql(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{RAW / (t + '.parquet')}')")
    con.sql(
        """
        CREATE TABLE base AS
        SELECT sf.file_url_sha16, sf.repo_name, sf.file_path, sf.spec_tool, sf.spec_role,
               sf.file_total_commits, sf.file_total_commits - 1 AS revisions,
               sf.file_first_commit_at, sf.file_last_commit_at, sf.file_first_commit_sha,
               sf.repo_pushed_at, sf.repo_created_at, sf.repo_stars, sf.repo_fork,
               cf.has_unfilled_placeholder AS placeholder, cf.has_purpose, cf.n_bytes,
               cf.n_scenario_blocks, cf.is_tiny
        FROM spec_files sf
        JOIN spec_content_features cf USING (file_url_sha16)
        WHERE sf.commit_history_status = 'done'
        """
    )
    con.sql(
        """
        CREATE VIEW living AS
        SELECT *,
               CASE WHEN placeholder = 1 AND revisions = 0 THEN 'fossil'
                    WHEN placeholder = 1 THEN 'placeholder_revised'
                    ELSE 'no_placeholder' END AS fossil_class
        FROM base WHERE spec_tool = 'openspec' AND spec_role = 'living'
        """
    )
    return con


def update_numbers(section: str, values: dict) -> None:
    """Merge `values` under `section` in results/numbers.json (creates the file if needed)."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    data = json.loads(NUMBERS.read_text()) if NUMBERS.exists() else {}
    data[section] = values
    NUMBERS.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
