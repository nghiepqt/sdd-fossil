#!/usr/bin/env python3
"""Fast local web UI for human coding of OpenSpec specs (Codebook v1 & v0).

Reads a coder's CSV copy (never *_TEMPLATE.csv) and its sibling `specs/` folder,
displays objective structural facts + full spec text on the left, and provides
keyboard-driven coding controls + an interactive codebook guide on the right.
Saves directly back to the CSV atomically.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

EXTENT_VALUES = ("none", "incidental", "substantial", "dominant")
V0_COMPLETENESS_VALUES = ("complete", "complete_except_purpose", "skeletal", "near_empty")
V1_COMPLETENESS_VALUES = ("complete", "skeletal", "near_empty")
PURPOSE_VALUES = ("feat", "fix", "refactor", "style", "perf")
OBJECT_VALUES = ("docs", "test", "ci", "build", "chore")

HEADING_RE = re.compile(r"^(#{1,4})\s+(.*\S)\s*$")
REQ_RE = re.compile(r"^###\s+Requirement:\s*(.*)$", re.IGNORECASE)
SCENARIO_RE = re.compile(r"^####\s+Scenario:", re.IGNORECASE)
DELTA_RE = re.compile(r"^##\s+(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements\b", re.IGNORECASE)
CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+")
CODE_FENCE_RE = re.compile(r"^\s*```")
PURPOSE_BLOCK_RE = re.compile(r"^##\s+Purpose\s*$(.*?)(?=^##\s|\Z)", re.M | re.S | re.I)
FILE_TOKEN_RE = re.compile(
    r"`([^`\s]+(?:/[^`\s]+|\.(?:ts|tsx|js|jsx|py|go|rs|java|kt|cs|rb|php|sql|yaml|yml|json|toml|md|sh|css|scss|html)))`"
)


def extract_objective_summary(text: str) -> dict:
    """Extract purely objective structural facts aligned with s09_pilot_codebook.py."""
    lines = text.splitlines()
    headings = []
    req_count = 0
    scenario_count = 0
    delta_count = 0
    checkbox_count = 0
    code_fence_lines = 0
    in_code = False

    purpose_lines: list[str] = []
    in_purpose = False
    purpose_start_line: int | None = None
    purpose_end_line: int | None = None

    # Track non-standard sections (outside Purpose, Requirements, Requirement:, Scenario:)
    # and track each ### Requirement: block for missing #### Scenario:
    non_standard_sections: list[dict] = []
    current_custom_section: dict | None = None
    req_blocks: list[dict] = []
    current_req: dict | None = None

    for idx, line in enumerate(lines, start=1):
        if CODE_FENCE_RE.match(line):
            code_fence_lines += 1
            in_code = not in_code
            if current_custom_section is not None:
                current_custom_section["content_lines"] += 1
            continue

        if not in_code:
            m = HEADING_RE.match(line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                headings.append({"level": level, "line": idx, "text": title})

                if in_purpose and level <= 2:
                    in_purpose = False
                    purpose_end_line = idx - 1

                if level == 2 and title.lower() == "purpose":
                    in_purpose = True
                    purpose_start_line = idx
                    current_custom_section = None
                    current_req = None
                    continue

                if level <= 2:
                    current_req = None
                elif level == 3:
                    req_m = REQ_RE.match(line)
                    if req_m:
                        current_req = {
                            "line": idx,
                            "title": req_m.group(1).strip(),
                            "has_scenario": False,
                            "body_lines": 0,
                        }
                        req_blocks.append(current_req)
                    else:
                        current_req = None

                # Dedicated-section candidate tracking (Rule 3):
                # Exclude #, ## Purpose, ## Requirements, ### Requirement:..., #### Scenario:...
                is_standard = (
                    level == 1
                    or (level == 2 and title.lower() in ("purpose", "requirements"))
                    or bool(REQ_RE.match(line))
                    or bool(SCENARIO_RE.match(line))
                )
                if is_standard:
                    current_custom_section = None
                else:
                    current_custom_section = {"level": level, "line": idx, "text": title, "content_lines": 0}
                    non_standard_sections.append(current_custom_section)

                if REQ_RE.match(line):
                    req_count += 1
                if SCENARIO_RE.match(line):
                    scenario_count += 1
                    if current_req is not None:
                        current_req["has_scenario"] = True
                if DELTA_RE.match(line):
                    delta_count += 1
                continue

            if CHECKBOX_RE.match(line):
                checkbox_count += 1

        if in_purpose:
            purpose_lines.append(line)
        else:
            is_content = bool(line.strip()) and not line.lstrip().startswith("#") and not line.startswith("<!-- item ")
            if is_content:
                if current_custom_section is not None:
                    current_custom_section["content_lines"] += 1
                if current_req is not None:
                    current_req["body_lines"] += 1

    if in_purpose and purpose_end_line is None:
        purpose_end_line = len(lines)

    # Compute n_body_lines exactly like s09_pilot_codebook.py
    text_no_purpose = PURPOSE_BLOCK_RE.sub("", text)
    n_body_lines = sum(
        1
        for ln in text_no_purpose.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#") and not ln.startswith("<!-- item ")
    )

    purpose_text = "\n".join(purpose_lines).strip()
    if purpose_start_line is None:
        purpose_status = "missing_section"
    elif not purpose_text:
        purpose_status = "empty_section"
    else:
        purpose_status = "present"

    reqs_without_scenario = [
        {"line": r["line"], "title": r["title"], "body_lines": r["body_lines"]}
        for r in req_blocks
        if not r["has_scenario"]
    ]
    dedicated_candidates = [s for s in non_standard_sections if s["content_lines"] >= 2]
    file_tokens = sorted(set(FILE_TOKEN_RE.findall(text)))

    return {
        "line_count": len(lines),
        "n_body_lines": n_body_lines,
        "word_count": len(text.split()),
        "purpose_status": purpose_status,
        "purpose_excerpt": purpose_text,
        "purpose_range": [purpose_start_line, purpose_end_line] if purpose_start_line else None,
        "headings": headings,
        "reqs_without_scenario": reqs_without_scenario,
        "dedicated_candidates": dedicated_candidates,
        "counts": {
            "requirements": req_count,
            "scenarios": scenario_count,
            "reqs_without_scenario": len(reqs_without_scenario),
            "code_blocks": code_fence_lines // 2,
            "delta_headers": delta_count,
            "checkboxes": checkbox_count,
            "file_tokens": len(file_tokens),
        },
    }


def load_csv(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"Empty CSV header in {csv_path}")
        fieldnames = list(reader.fieldnames)
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def write_csv_atomic(csv_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    tmp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_path, csv_path)


def detect_schema(fieldnames: list[str]) -> dict:
    if "body_completeness" in fieldnames:
        return {
            "codebook": "v1",
            "completeness_col": "body_completeness",
            "completeness_values": V1_COMPLETENESS_VALUES,
            "has_taxonomy_b": False,
        }
    return {
        "codebook": "v0",
        "completeness_col": "completeness",
        "completeness_values": V0_COMPLETENESS_VALUES,
        "has_taxonomy_b": "is_spec_of_work" in fieldnames,
    }


def is_row_coded(row: dict[str, str], schema: dict) -> bool:
    is_spec = (row.get("is_spec") or "").strip().lower()
    if is_spec == "false":
        return True
    if is_spec != "true":
        return False
    comp_col = schema["completeness_col"]
    base_ok = all(
        (row.get(col) or "").strip()
        for col in ("requirements_extent", "implementation_extent", comp_col)
    )
    if not base_ok:
        return False
    if schema["has_taxonomy_b"]:
        return bool((row.get("is_spec_of_work") or "").strip())
    return True


def validate_and_normalize_payload(payload: dict, schema: dict) -> dict[str, str]:
    is_spec_raw = str(payload.get("is_spec", "")).strip().lower()
    if is_spec_raw not in ("true", "false"):
        raise ValueError("is_spec must be true or false")

    bool_true = "true" if schema["codebook"] == "v1" else "TRUE"
    bool_false = "false" if schema["codebook"] == "v1" else "FALSE"
    comp_col = schema["completeness_col"]
    allowed_comp = schema["completeness_values"]

    note = str(payload.get("note", "")).replace("\r", " ").replace("\n", " ").strip()

    if is_spec_raw == "false":
        out = {
            "is_spec": bool_false,
            "requirements_extent": "",
            "implementation_extent": "",
            comp_col: "",
            "note": note,
        }
        if schema["has_taxonomy_b"]:
            out.update({"is_spec_of_work": "", "purpose": "", "object": ""})
        return out

    req_ext = str(payload.get("requirements_extent", "")).strip()
    impl_ext = str(payload.get("implementation_extent", "")).strip()
    comp = str(payload.get(comp_col, "")).strip()

    if req_ext not in EXTENT_VALUES:
        raise ValueError(f"Invalid requirements_extent: {req_ext!r}")
    if impl_ext not in EXTENT_VALUES:
        raise ValueError(f"Invalid implementation_extent: {impl_ext!r}")
    if comp not in allowed_comp:
        raise ValueError(f"Invalid {comp_col}: {comp!r}")

    out = {
        "is_spec": bool_true,
        "requirements_extent": req_ext,
        "implementation_extent": impl_ext,
        comp_col: comp,
        "note": note,
    }

    if schema["has_taxonomy_b"]:
        work = str(payload.get("is_spec_of_work", "")).strip().upper()
        if work not in ("TRUE", "FALSE"):
            raise ValueError("is_spec_of_work must be TRUE or FALSE")
        if work == "FALSE":
            purpose_str = "none"
            object_str = "none"
        else:
            p_vals = [v.strip() for v in str(payload.get("purpose", "")).split(";") if v.strip()]
            o_vals = [v.strip() for v in str(payload.get("object", "")).split(";") if v.strip()]
            if not p_vals or p_vals == ["none"]:
                purpose_str = "none"
            else:
                for v in p_vals:
                    if v not in PURPOSE_VALUES:
                        raise ValueError(f"Invalid purpose value: {v!r}")
                purpose_str = ";".join(p_vals)

            if not o_vals or o_vals == ["none"]:
                object_str = "none"
            else:
                for v in o_vals:
                    if v not in OBJECT_VALUES:
                        raise ValueError(f"Invalid object value: {v!r}")
                object_str = ";".join(o_vals)

        out.update({"is_spec_of_work": work, "purpose": purpose_str, "object": object_str})

    return out


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>OpenSpec Coder</title>
<style>
  :root {
    --bg: #0f172a;
    --panel: #111827;
    --card: #1e293b;
    --border: #334155;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --accent: #38bdf8;
    --accent-bg: rgba(56, 189, 248, 0.16);
    --green: #22c55e;
    --green-bg: rgba(34, 197, 94, 0.16);
    --amber: #f59e0b;
    --amber-bg: rgba(245, 158, 11, 0.16);
    --red: #ef4444;
    --red-bg: rgba(239, 68, 68, 0.16);
    --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    --sans: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 14px; }
  body { display: flex; flex-direction: column; overflow: hidden; }

  header {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    padding: 8px 14px; background: var(--panel); border-bottom: 1px solid var(--border);
  }
  .title { font-weight: 700; font-size: 14px; color: #f8fafc; }
  .pill-stat {
    background: var(--card); border: 1px solid var(--border); border-radius: 999px;
    padding: 3px 9px; font-size: 12px; color: var(--muted);
  }
  .pill-stat strong { color: var(--green); }
  .pill-v1 { border-color: var(--accent); color: #bae6fd; background: var(--accent-bg); }
  .nav-group { display: flex; align-items: center; gap: 6px; margin-left: auto; flex-wrap: wrap; }
  select, button, input[type="text"] {
    background: var(--card); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 5px 9px; font-size: 13px; font-family: inherit;
  }
  button { cursor: pointer; transition: 0.1s background, 0.1s border-color; }
  button:hover { border-color: var(--accent); }
  button.primary { background: #0284c7; border-color: #0ea5e9; color: #fff; font-weight: 600; }
  button.primary:hover { background: #0369a1; }
  a.gh-link {
    color: var(--accent); text-decoration: none; font-size: 12px; padding: 4px 8px;
    border: 1px solid var(--border); border-radius: 6px; background: var(--card);
  }
  a.gh-link:hover { border-color: var(--accent); }

  main {
    display: grid; grid-template-columns: minmax(0, 1.32fr) minmax(390px, 0.95fr);
    flex: 1; min-height: 0;
  }

  /* Left Pane */
  .left-pane {
    display: flex; flex-direction: column; min-height: 0;
    border-right: 1px solid var(--border); background: var(--bg);
  }
  .digest {
    padding: 10px 14px; background: var(--panel); border-bottom: 1px solid var(--border);
    display: flex; flex-direction: column; gap: 7px; max-height: 40vh; overflow-y: auto;
  }
  .badges { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .badge {
    font-size: 12px; padding: 2px 8px; border-radius: 6px;
    background: var(--card); border: 1px solid var(--border); color: var(--muted);
  }
  .badge strong { color: var(--text); }
  .badge.warn { border-color: var(--amber); background: var(--amber-bg); color: #fde68a; }
  .badge.info { border-color: var(--accent); background: var(--accent-bg); color: #bae6fd; }
  .badge.good { border-color: var(--green); background: var(--green-bg); color: #bbf7d0; }

  .threshold-bar {
    font-size: 12px; color: #cbd5e1; background: #0f172a; border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 9px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  }
  .threshold-bar b { color: var(--accent); }

  .callout-box {
    background: var(--card); border: 1px solid var(--border); border-radius: 6px;
    padding: 6px 9px; font-size: 12px; line-height: 1.45;
  }
  .callout-box .lbl { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); margin-bottom: 3px; }
  .callout-box pre { margin: 0; white-space: pre-wrap; font-family: var(--mono); font-size: 12px; color: #f1f5f9; }
  .jump-list { display: flex; flex-wrap: wrap; gap: 4px; }
  .jump-btn {
    font-size: 11.5px; padding: 2px 7px; border-radius: 4px; background: #0f172a;
    border: 1px solid var(--border); color: #cbd5e1; max-width: 280px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .jump-btn:hover { border-color: var(--accent); color: #fff; }
  .jump-btn.h2 { border-left: 3px solid var(--accent); }
  .jump-btn.h3 { border-left: 3px solid #818cf8; }
  .jump-btn.warn { border-color: var(--amber); color: #fde68a; }
  .jump-btn.info { border-color: var(--accent); color: #bae6fd; }

  .spec-scroll {
    flex: 1; overflow-y: auto; padding: 12px 14px; font-family: var(--mono);
    font-size: 12.5px; line-height: 1.5;
  }
  .spec-line { display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 10px; padding: 1px 4px; border-radius: 3px; }
  .spec-line:hover { background: rgba(148, 163, 184, 0.08); }
  .spec-line.flash { background: rgba(56, 189, 248, 0.25); transition: background 0.8s; }
  .spec-line.purpose-masked { opacity: 0.35; }
  .purpose-banner {
    margin: 4px 0; padding: 6px 10px; border-radius: 6px;
    background: #1e293b; border: 1px dashed #475569; color: var(--muted);
    font-family: var(--sans); font-size: 12px; display: flex; align-items: center; gap: 10px;
  }
  .ln { color: #475569; text-align: right; user-select: none; font-size: 11px; padding-top: 1px; }
  .lc { white-space: pre-wrap; word-break: break-word; }
  .lc.h1, .lc.h2 { color: #38bdf8; font-weight: 700; }
  .lc.h3 { color: #a5b4fc; font-weight: 700; }
  .lc.h4 { color: #86efac; font-weight: 600; }
  .lc.code { color: #fcd34d; }
  .tok-code { background: rgba(245, 158, 11, 0.16); color: #fde68a; padding: 0 3px; border-radius: 3px; }
  .tok-kw { color: #f472b6; font-weight: 700; }

  /* Right Pane */
  .right-pane {
    display: flex; flex-direction: column; min-height: 0; overflow-y: auto;
    padding: 12px 14px; background: var(--panel); gap: 10px;
  }
  .field-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    padding: 9px 11px; display: flex; flex-direction: column; gap: 6px;
  }
  .field-card.missing { border-color: var(--red); box-shadow: 0 0 0 1px var(--red); }
  .field-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .field-title { font-weight: 600; font-size: 13px; color: #f8fafc; }
  .field-hint { font-size: 11px; color: var(--muted); }
  .field-sub { font-size: 11.5px; color: #94a3b8; line-height: 1.35; }
  .btn-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
  .btn-row.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .btn-row.flex { display: flex; flex-wrap: wrap; gap: 6px; }
  .opt-btn {
    display: flex; align-items: center; gap: 6px; text-align: left;
    padding: 6px 8px; border-radius: 6px; background: #0f172a; border: 1px solid var(--border);
    color: #cbd5e1; font-size: 12.5px;
  }
  .opt-btn:hover { border-color: var(--accent); color: #fff; }
  .opt-btn.active { background: var(--accent-bg); border-color: var(--accent); color: #fff; font-weight: 600; }
  .opt-btn.active-green { background: var(--green-bg); border-color: var(--green); color: #bbf7d0; font-weight: 600; }
  .opt-btn.active-red { background: var(--red-bg); border-color: var(--red); color: #fecaca; font-weight: 600; }
  .kbd {
    display: inline-block; min-width: 18px; text-align: center; padding: 1px 4px;
    font-family: var(--mono); font-size: 11px; border-radius: 4px;
    background: #1e293b; border: 1px solid #475569; color: #94a3b8;
  }
  .note-wrap { display: flex; flex-direction: column; gap: 6px; }
  .note-wrap input { width: 100%; background: #0f172a; }
  .chip-row { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip { font-size: 11px; padding: 2px 7px; background: #0f172a; border: 1px solid var(--border); border-radius: 999px; color: var(--muted); }
  .chip:hover { color: #fff; border-color: var(--accent); }

  /* Quick Codebook Card */
  .codebook-card {
    background: #0f172a; border: 1px solid var(--border); border-radius: 8px;
    padding: 9px 11px; font-size: 12px; line-height: 1.45; color: #cbd5e1;
  }
  .codebook-card summary {
    cursor: pointer; font-weight: 600; color: var(--accent); user-select: none;
    display: flex; align-items: center; justify-content: space-between;
  }
  .cb-grid { display: grid; grid-template-columns: 1fr; gap: 8px; margin-top: 8px; }
  .cb-sec { background: #111827; border: 1px solid #1e293b; border-radius: 6px; padding: 7px 9px; }
  .cb-sec h4 { margin: 0 0 4px 0; font-size: 12px; color: #f8fafc; }
  .cb-sec ul { margin: 0; padding-left: 16px; }
  .cb-sec li { margin: 2px 0; }
  .cb-two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .tag-req { color: #86efac; font-weight: 600; }
  .tag-imp { color: #fcd34d; font-weight: 600; }

  .save-bar {
    position: sticky; bottom: 0; background: var(--panel); padding-top: 6px;
    display: flex; align-items: center; gap: 8px; border-top: 1px solid var(--border);
  }
  .status-msg { font-size: 12px; color: var(--muted); margin-left: auto; }
  .status-msg.ok { color: var(--green); }
  .status-msg.err { color: var(--red); }

  /* Modal for full Codebook */
  .modal-backdrop {
    position: fixed; inset: 0; background: rgba(2, 6, 23, 0.78);
    display: flex; align-items: center; justify-content: center; z-index: 50; padding: 20px;
  }
  .modal {
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    max-width: 860px; width: 100%; max-height: 88vh; overflow-y: auto; padding: 16px 20px;
    display: flex; flex-direction: column; gap: 12px;
  }
  .modal-head { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
  .modal-head h2 { margin: 0; font-size: 16px; color: #f8fafc; }
  .hidden { display: none !important; }
</style>
</head>
<body>
<header>
  <span class="title" id="sheetTitle">OpenSpec Coder</span>
  <span class="pill-stat pill-v1" id="codebookBadge">v1</span>
  <span class="pill-stat" id="progressStat">0 / 0 coded</span>
  <span class="pill-stat" id="itemBadge">...</span>
  <a class="gh-link" id="ghLink" href="#" target="_blank" rel="noopener">GitHub ↗</a>

  <div class="nav-group">
    <button id="guideBtn" title="Full Codebook Guide (?)">Guide (?)</button>
    <label style="font-size:12px;color:var(--muted);display:flex;align-items:center;gap:4px;">
      <input type="checkbox" id="unlabelledOnly" /> Todo only
    </label>
    <select id="itemSelect"></select>
    <button id="prevBtn" title="Previous ([)">← [</button>
    <button id="nextBtn" title="Next (])">] →</button>
    <button id="nextUnlabelledBtn" title="Next unlabelled (n)">Next Todo (n)</button>
  </div>
</header>

<main>
  <section class="left-pane">
    <div class="digest">
      <div class="badges" id="digestBadges"></div>
      <div class="threshold-bar" id="thresholdBar"></div>
      <div class="callout-box hidden" id="purposeBox">
        <div class="lbl" id="purposeLabel">## Purpose</div>
        <pre id="purposeText"></pre>
      </div>
      <div class="callout-box hidden" id="missingScenBox">
        <div class="lbl">Requirements missing #### Scenario: (click to jump)</div>
        <div class="jump-list" id="missingScenList"></div>
      </div>
      <div class="callout-box hidden" id="dedicatedBox">
        <div class="lbl">Non-standard sections with ≥2 body lines (Rule 3 dedicated-section candidates)</div>
        <div class="jump-list" id="dedicatedList"></div>
      </div>
      <div class="jump-list" id="headingOutline"></div>
    </div>
    <div class="spec-scroll" id="specContent">Loading...</div>
  </section>

  <section class="right-pane">
    <div class="field-card" id="card_is_spec">
      <div class="field-head">
        <span class="field-title">1. is_spec</span>
        <span class="field-hint">Key: <span class="kbd">x</span> toggle</span>
      </div>
      <div class="btn-row">
        <button class="opt-btn" data-field="is_spec" data-val="true"><span class="kbd">x</span> true (is a spec)</button>
        <button class="opt-btn" data-field="is_spec" data-val="false"><span class="kbd">x</span> false (empty template / unrelated)</button>
      </div>
    </div>

    <div id="specOnlyFields" style="display:flex;flex-direction:column;gap:10px;">
      <div class="field-card" id="card_requirements_extent">
        <div class="field-head">
          <span class="field-title">2. requirements_extent (observable behaviour)</span>
          <span class="field-hint">Keys: <span class="kbd">1</span> <span class="kbd">2</span> <span class="kbd">3</span> <span class="kbd">4</span></span>
        </div>
        <div class="field-sub">SHALL/MUST, WHEN/THEN scenarios, constraints, roles, API endpoints, CLI flags, UI text, sample I/O JSON.</div>
        <div class="btn-row">
          <button class="opt-btn" data-field="requirements_extent" data-val="none"><span class="kbd">1</span> none (0 lines)</button>
          <button class="opt-btn" data-field="requirements_extent" data-val="incidental"><span class="kbd">2</span> incidental (&lt;10%, or 1 line)</button>
          <button class="opt-btn" data-field="requirements_extent" data-val="substantial"><span class="kbd">3</span> substantial (10–50% or ded. sec)</button>
          <button class="opt-btn" data-field="requirements_extent" data-val="dominant"><span class="kbd">4</span> dominant (&gt;50%)</button>
        </div>
      </div>

      <div class="field-card" id="card_implementation_extent">
        <div class="field-head">
          <span class="field-title">3. implementation_extent (internal build)</span>
          <span class="field-hint">Keys: <span class="kbd">q</span> <span class="kbd">w</span> <span class="kbd">e</span> <span class="kbd">r</span></span>
        </div>
        <div class="field-sub">File paths, classes/functions, DB tables/columns, architecture, steps, conventions, tech/libs, code blocks (not sample I/O).</div>
        <div class="btn-row">
          <button class="opt-btn" data-field="implementation_extent" data-val="none"><span class="kbd">q</span> none (0 lines)</button>
          <button class="opt-btn" data-field="implementation_extent" data-val="incidental"><span class="kbd">w</span> incidental (&lt;10%, or 1 line)</button>
          <button class="opt-btn" data-field="implementation_extent" data-val="substantial"><span class="kbd">e</span> substantial (10–50% or ded. sec)</button>
          <button class="opt-btn" data-field="implementation_extent" data-val="dominant"><span class="kbd">r</span> dominant (&gt;50%)</button>
        </div>
      </div>

      <div class="field-card" id="card_body_completeness">
        <div class="field-head">
          <span class="field-title" id="compTitle">4. body_completeness (ignore Purpose!)</span>
          <span class="field-hint" id="compHint">Keys: <span class="kbd">a</span> <span class="kbd">s</span> <span class="kbd">d</span></span>
        </div>
        <div class="field-sub" id="compSub">Every requirement needs a body + ≥1 <code>#### Scenario:</code> (with WHEN/THEN).</div>
        <div class="btn-row three" id="compButtons"></div>
      </div>

      <div class="field-card hidden" id="card_is_spec_of_work">
        <div class="field-head">
          <span class="field-title">5. is_spec_of_work (v0 pilot)</span>
          <span class="field-hint">Key: <span class="kbd">t</span> toggle</span>
        </div>
        <div class="btn-row">
          <button class="opt-btn" data-field="is_spec_of_work" data-val="FALSE"><span class="kbd">t</span> FALSE (system as-is)</button>
          <button class="opt-btn" data-field="is_spec_of_work" data-val="TRUE"><span class="kbd">t</span> TRUE (work to do)</button>
        </div>
        <div id="workDetails" class="hidden" style="display:flex;flex-direction:column;gap:8px;margin-top:4px;padding-top:8px;border-top:1px solid var(--border);">
          <div>
            <div class="field-hint" style="margin-bottom:4px;">purpose</div>
            <div class="btn-row flex" id="purposePills"></div>
          </div>
          <div>
            <div class="field-hint" style="margin-bottom:4px;">object</div>
            <div class="btn-row flex" id="objectPills"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="field-card">
      <div class="field-head">
        <span class="field-title">note</span>
        <span class="field-hint">Key: <span class="kbd">/</span> focus, <span class="kbd">Esc</span> unfocus</span>
      </div>
      <div class="note-wrap">
        <input type="text" id="noteInput" placeholder="Hesitations, alternative structure, opened GitHub URL..." />
        <div class="chip-row">
          <button class="chip" data-note="opened GitHub URL">+ opened GitHub URL</button>
          <button class="chip" data-note="non-standard structure (no ### Requirement:)">+ non-standard structure</button>
          <button class="chip" data-note="dedicated section: ">+ dedicated section:</button>
          <button class="chip" data-note="unsure between ">+ unsure between</button>
        </div>
      </div>
    </div>

    <details class="codebook-card" open id="quickCodebookCard">
      <summary>
        <span>Codebook v1 Quick Cheatsheet</span>
        <span style="font-size:11px;color:var(--muted);font-weight:400;">Press <span class="kbd">?</span> for full rules</span>
      </summary>
      <div class="cb-grid">
        <div class="cb-sec">
          <h4>Rule 1 &amp; 2 — Purpose &amp; Body Completeness</h4>
          <ul>
            <li><b>Ignore <code>## Purpose</code> completely</b> (hidden in text; computed by script).</li>
            <li><b>complete:</b> <u>Every</u> req has a body (SHALL/MUST or text) <b>AND</b> ≥1 scenario (<code>#### Scenario:</code> with WHEN/THEN).</li>
            <li><b>skeletal:</b> ≥1 req has a body, <b>but ≥1</b> req is title-only or has no scenario.</li>
            <li><b>near_empty:</b> No req has a body (headings/titles only).</li>
          </ul>
        </div>
        <div class="cb-sec">
          <h4>Rule 3 — Extent Scale (unit = share of body content lines)</h4>
          <ul>
            <li>Count body lines only (no headings, no blanks, no Purpose, <b>no HTML comments</b> <code>&lt;!-- --&gt;</code> — Rule 4b).</li>
            <li><b>Floor rule:</b> 1 single line is <b>never</b> more than <code>incidental</code>.</li>
            <li><b>Dedicated section:</b> Non-standard heading (not <code>### Requirement:</code>/<code>#### Scenario:</code>) with <b>≥2 content lines</b> mostly in 1 category → at least <code>substantial</code> even if &lt;10%.</li>
          </ul>
        </div>
        <div class="cb-two">
          <div class="cb-sec">
            <h4 class="tag-req">Rule 4 — Requirement (Outside)</h4>
            <ul>
              <li>SHALL/MUST, WHEN/THEN, constraints, roles</li>
              <li>Endpoints, routes, CLI flags, event names, UI text</li>
              <li>Sample I/O JSON or CLI call blocks</li>
              <li>Lib named as host constraint ("MUST use X because host only supports X")</li>
              <li>Prompt content sent to an LLM/agent (output to another system)</li>
              <li><b>4a:</b> a line naming a class/function that a black-box tester can still check (port opened, log line)</li>
            </ul>
          </div>
          <div class="cb-sec">
            <h4 class="tag-imp">Rule 4 — Implementation (Inside)</h4>
            <ul>
              <li>File paths, classes, functions, modules</li>
              <li>DB tables, columns, storage layout</li>
              <li>Architecture, plans, steps, conventions</li>
              <li>Named libs ("uses Redis", "JWT") &amp; code blocks</li>
              <li><b>4a black-box test:</b> line naming a class/function/file that only the code can verify → implementation</li>
              <li>Link/reference lists → neither</li>
            </ul>
          </div>
        </div>
      </div>
    </details>

    <div class="save-bar">
      <button class="primary" id="saveNextBtn">Save &amp; Next (<span class="kbd" style="background:#0369a1;border-color:#38bdf8;color:#fff;">Enter</span>)</button>
      <button id="saveOnlyBtn">Save</button>
      <span class="status-msg" id="statusMsg">Ready</span>
    </div>
  </section>
</main>

<div class="modal-backdrop hidden" id="guideModal">
  <div class="modal">
    <div class="modal-head">
      <h2>Codebook v1 — Complete Decision Guide</h2>
      <button id="closeGuideBtn">Close (Esc)</button>
    </div>
    <div class="cb-sec">
      <h4>Step 1: Skip <code>## Purpose</code> (Rule 1)</h4>
      <p style="margin:4px 0;">Do not count <code>## Purpose</code> in extents or completeness. It is masked in this UI to preserve blinding; <code>s09</code> computes <code>purpose_status</code> automatically.</p>
    </div>
    <div class="cb-sec">
      <h4>Step 2: Check <code>body_completeness</code> (Rule 2)</h4>
      <ul>
        <li><b>complete</b>: Every requirement has a body (at least one SHALL/MUST sentence or description) AND at least one scenario (<code>#### Scenario:</code> + at least one WHEN/THEN or GIVEN/WHEN/THEN line; empty scenario heading does not count).</li>
        <li><b>skeletal</b>: At least one requirement has a body, but at least one requirement is title-only or lacks a scenario.</li>
        <li><b>near_empty</b>: No requirement has a body (only headings, titles, or Purpose).</li>
        <li><i>Alternative structures</i>: If there are no <code>### Requirement:</code> headings, apply the rule to equivalent units (numbered requirements, user stories) and explain in <code>note</code>.</li>
      </ul>
    </div>
    <div class="cb-sec">
      <h4>Step 3: Classify body lines (Rule 4 — Outside vs Inside)</h4>
      <p style="margin:4px 0;"><b>General rule:</b> What users or external systems can observe from outside = <b>requirement</b>. How it is built inside = <b>implementation</b>. A line can belong to one category; some lines (glossary/references) are neither, so extents need not sum to 100%.</p>
      <ul>
        <li><b>Rule 4a (black-box test):</b> for any line naming an internal class, function or file (THEN lines included), ask: could a tester check it without reading the code? Yes → <b>requirement</b> (e.g. "PebbleService SHALL open port 8080 and log WARNING"); No → <b>implementation</b> (e.g. "call <code>plan()</code> then update <code>self._container</code>").</li>
        <li><b>Rule 4b:</b> HTML comments (<code>&lt;!-- @trace … --&gt;</code>) are not body lines; mention long ones in <code>note</code>.</li>
        <li><b>Prompt content</b> sent to an LLM/agent → requirement; the code that builds it → implementation. Link/reference lists → neither.</li>
        <li><b>Code blocks:</b> Implementation, <i>unless</i> they show example input/output (sample JSON, CLI invocation) → requirement.</li>
        <li><b>Technologies/libraries:</b> Implementation ("uses Redis", "JWT"), <i>unless</i> forced by an outside constraint ("MUST use X because host only supports X") → requirement.</li>
      </ul>
    </div>
    <div class="cb-sec">
      <h4>Step 4: Rate each extent independently (Rule 3)</h4>
      <ul>
        <li><b>none</b>: 0 lines</li>
        <li><b>incidental</b>: &gt;0 and &lt;10% of body lines AND no dedicated section. <i>Floor rule: a single line is never more than incidental.</i></li>
        <li><b>substantial</b>: 10–50% of body lines, OR a dedicated section (real author heading outside <code>### Requirement:</code>/<code>#### Scenario:</code> with ≥2 content lines mostly of that category, e.g. <code>## Data Model</code>, <code>## Architecture</code>, <code>## File Structure</code>).</li>
        <li><b>dominant</b>: &gt;50% of body lines.</li>
      </ul>
    </div>
  </div>
</div>

<script>
const PURPOSE_OPTS = ["feat", "fix", "refactor", "style", "perf", "none"];
const OBJECT_OPTS = ["docs", "test", "ci", "build", "chore", "none"];

let state = {
  csvName: "",
  schema: null,
  rows: [],
  currentIndex: 0,
  form: {},
  showPurposeInV1: false,
  lastSpecData: null
};

function escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function isCoded(row) {
  const sp = (row.is_spec || "").trim().toLowerCase();
  if (sp === "false") return true;
  if (sp !== "true") return false;
  const compCol = state.schema.completeness_col;
  if (!row.requirements_extent || !row.implementation_extent || !row[compCol]) return false;
  if (state.schema.has_taxonomy_b && !row.is_spec_of_work) return false;
  return true;
}

function renderItemSelect() {
  const sel = document.getElementById("itemSelect");
  const onlyTodo = document.getElementById("unlabelledOnly").checked;
  sel.innerHTML = "";
  let codedCount = 0;
  state.rows.forEach((r, idx) => {
    const done = isCoded(r);
    if (done) codedCount++;
    if (onlyTodo && done && idx !== state.currentIndex) return;
    const opt = document.createElement("option");
    opt.value = idx;
    opt.textContent = `${done ? "✓" : "○"} ${r.item_id} (b${r.batch})`;
    if (idx === state.currentIndex) opt.selected = true;
    sel.appendChild(opt);
  });
  document.getElementById("progressStat").innerHTML = `<strong>${codedCount}</strong> / ${state.rows.length} coded`;
}

function renderCompletenessButtons() {
  const container = document.getElementById("compButtons");
  const isV1 = state.schema.codebook === "v1";
  const vals = state.schema.completeness_values;
  const keys = ["a", "s", "d", "f"];
  const col = state.schema.completeness_col;

  container.className = isV1 ? "btn-row three" : "btn-row";
  container.innerHTML = "";
  vals.forEach((v, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "opt-btn";
    btn.dataset.field = col;
    btn.dataset.val = v;
    btn.innerHTML = `<span class="kbd">${keys[i]}</span> ${v}`;
    container.appendChild(btn);
  });

  document.getElementById("compTitle").textContent = isV1
    ? "4. body_completeness (ignore Purpose!)"
    : "4. completeness (v0)";
  document.getElementById("compHint").innerHTML = isV1
    ? 'Keys: <span class="kbd">a</span> <span class="kbd">s</span> <span class="kbd">d</span>'
    : 'Keys: <span class="kbd">a</span> <span class="kbd">s</span> <span class="kbd">d</span> <span class="kbd">f</span>';
  document.getElementById("compSub").innerHTML = isV1
    ? '<b>complete</b>: all reqs have body + ≥1 scenario | <b>skeletal</b>: ≥1 req missing body or scenario | <b>near_empty</b>: no req body.'
    : 'Codebook v0 includes Purpose.';
}

function initMultiPills(containerId, opts, field) {
  const el = document.getElementById(containerId);
  el.innerHTML = "";
  opts.forEach(v => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "opt-btn";
    b.dataset.multiField = field;
    b.dataset.val = v;
    b.textContent = v;
    b.addEventListener("click", () => toggleMulti(field, v));
    el.appendChild(b);
  });
}

function toggleMulti(field, val) {
  let cur = (state.form[field] || "none").split(";").filter(Boolean);
  if (val === "none") cur = ["none"];
  else {
    cur = cur.filter(x => x !== "none");
    if (cur.includes(val)) cur = cur.filter(x => x !== val);
    else cur.push(val);
    if (cur.length === 0) cur = ["none"];
  }
  state.form[field] = cur.join(";");
  syncFormUI();
}

function loadRowIntoForm(row) {
  const compCol = state.schema.completeness_col;
  const rawSpec = (row.is_spec || "").trim().toLowerCase();
  state.form = {
    is_spec: rawSpec === "false" ? "false" : "true",
    requirements_extent: row.requirements_extent || "",
    implementation_extent: row.implementation_extent || "",
    [compCol]: row[compCol] || "",
    is_spec_of_work: (row.is_spec_of_work || "FALSE").toUpperCase() || "FALSE",
    purpose: row.purpose || "none",
    object: row.object || "none",
    note: row.note || ""
  };
  document.getElementById("noteInput").value = state.form.note;
  syncFormUI();
}

function syncFormUI() {
  const isSpec = state.form.is_spec === "true";
  document.getElementById("specOnlyFields").classList.toggle("hidden", !isSpec);
  document.getElementById("card_is_spec_of_work").classList.toggle("hidden", !state.schema.has_taxonomy_b);

  const workTrue = state.schema.has_taxonomy_b && isSpec && state.form.is_spec_of_work === "TRUE";
  document.getElementById("workDetails").classList.toggle("hidden", !workTrue);

  document.querySelectorAll(".opt-btn[data-field]").forEach(btn => {
    const f = btn.dataset.field;
    const v = btn.dataset.val;
    btn.classList.remove("active", "active-green", "active-red");
    if (state.form[f] === v) {
      if (f === "is_spec" && v === "false") btn.classList.add("active-red");
      else if (f === "is_spec" && v === "true") btn.classList.add("active-green");
      else btn.classList.add("active");
    }
  });

  document.querySelectorAll(".opt-btn[data-multi-field]").forEach(btn => {
    const f = btn.dataset.multiField;
    const v = btn.dataset.val;
    const vals = (state.form[f] || "none").split(";").filter(Boolean);
    btn.classList.toggle("active", vals.includes(v));
  });

  document.querySelectorAll(".field-card.missing").forEach(el => el.classList.remove("missing"));
}

function renderSpecText(rawText, summary) {
  const container = document.getElementById("specContent");
  const lines = rawText.split("\n");
  const isV1 = state.schema.codebook === "v1";
  const pRange = summary.purpose_range;
  let inCode = false;
  let bannerInserted = false;

  const htmlParts = [];
  lines.forEach((line, idx) => {
    const ln = idx + 1;
    const inPurpose = isV1 && pRange && ln >= pRange[0] && ln <= pRange[1];

    if (inPurpose && !state.showPurposeInV1) {
      if (!bannerInserted) {
        bannerInserted = true;
        htmlParts.push(
          `<div class="purpose-banner">` +
          `<span><b>## Purpose</b> hidden (Rule 1: ignored by coders; computed by s09; preserves blinding)</span>` +
          `<button type="button" onclick="togglePurposePeek()">Show anyway</button>` +
          `</div>`
        );
      }
      return;
    }

    let cls = "lc";
    if (/^\s*```/.test(line)) { inCode = !inCode; cls += " code"; }
    else if (inCode) cls += " code";
    else if (/^#\s+/.test(line)) cls += " h1";
    else if (/^##\s+/.test(line)) cls += " h2";
    else if (/^###\s+/.test(line)) cls += " h3";
    else if (/^####\s+/.test(line)) cls += " h4";

    let body = escHtml(line);
    if (!inCode) {
      body = body.replace(/`([^`]+)`/g, '<span class="tok-code">`$1`</span>');
      body = body.replace(/\b(GIVEN|WHEN|THEN|AND|SHALL|MUST|TODO|TBD)\b/g, '<span class="tok-kw">$1</span>');
    }
    const rowCls = inPurpose ? "spec-line purpose-masked" : "spec-line";
    htmlParts.push(`<div class="${rowCls}" id="L${ln}"><span class="ln">${ln}</span><span class="${cls}">${body || " "}</span></div>`);
  });

  container.innerHTML = htmlParts.join("");
  container.scrollTop = 0;
}

window.togglePurposePeek = function() {
  state.showPurposeInV1 = !state.showPurposeInV1;
  if (state.lastSpecData) renderSpecText(state.lastSpecData.raw_text, state.lastSpecData.summary);
};

function jumpToLine(lineNo) {
  const el = document.getElementById("L" + lineNo);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 900);
}

async function showItem(index) {
  if (index < 0 || index >= state.rows.length) return;
  state.currentIndex = index;
  state.showPurposeInV1 = false;
  const row = state.rows[index];
  renderItemSelect();

  const done = isCoded(row);
  document.getElementById("itemBadge").innerHTML =
    `<strong>${row.item_id}</strong> &middot; batch ${row.batch} &middot; ${done ? '<span style="color:var(--green)">coded</span>' : '<span style="color:var(--amber)">todo</span>'}`;
  document.getElementById("ghLink").href = row.file_url;

  loadRowIntoForm(row);
  setStatus("Loading spec...", "");

  const res = await fetch(`/api/spec?id=${encodeURIComponent(row.item_id)}`);
  const data = await res.json();
  if (!res.ok) { setStatus(data.error || "Failed to load spec", "err"); return; }
  state.lastSpecData = data;

  const s = data.summary;
  const c = s.counts;
  const badges = [
    `<span class="badge info">Body lines: <strong>${s.n_body_lines}</strong></span>`,
    `<span class="badge">Reqs: <strong>${c.requirements}</strong></span>`,
    `<span class="badge">Scenarios: <strong>${c.scenarios}</strong></span>`,
    c.reqs_without_scenario > 0
      ? `<span class="badge warn">Reqs w/o Scenario: <strong>${c.reqs_without_scenario}</strong></span>`
      : (c.requirements > 0 ? `<span class="badge good">All reqs have Scenario</span>` : `<span class="badge">No ### Requirement:</span>`),
    `<span class="badge">Code blocks: <strong>${c.code_blocks}</strong></span>`,
    `<span class="badge">File refs: <strong>${c.file_tokens}</strong></span>`
  ];
  if (c.delta_headers > 0) badges.push(`<span class="badge warn">Delta headers: <strong>${c.delta_headers}</strong></span>`);
  if (c.checkboxes > 0) badges.push(`<span class="badge warn">Checkboxes: <strong>${c.checkboxes}</strong></span>`);
  document.getElementById("digestBadges").innerHTML = badges.join("");

  // Rule 3 threshold helper
  const n = s.n_body_lines;
  const tBar = document.getElementById("thresholdBar");
  if (n === 0) {
    tBar.innerHTML = `<b>Rule 3 guide:</b> 0 body content lines (check if near_empty or not a spec).`;
  } else {
    const incMax = Math.max(0, Math.ceil(n * 0.10) - 1);
    const subMin = Math.max(2, Math.ceil(n * 0.10));
    const subMax = Math.floor(n * 0.50);
    const domMin = subMax + 1;
    tBar.innerHTML =
      `<span><b>Rule 3 thresholds (${n} body lines):</b></span>` +
      `<span>incidental: <code>1–${Math.max(1, incMax)}</code> lines (&lt;10%, or any 1 line)</span>` +
      `<span>substantial: <code>${subMin}–${Math.max(subMin, subMax)}</code> lines (or dedicated ≥2-line section)</span>` +
      `<span>dominant: <code>≥${domMin}</code> lines (&gt;50%)</span>`;
  }

  // Purpose box only for v0
  const pBox = document.getElementById("purposeBox");
  if (state.schema.codebook === "v0") {
    pBox.classList.remove("hidden");
    document.getElementById("purposeText").textContent = s.purpose_excerpt || `(${s.purpose_status})`;
  } else {
    pBox.classList.add("hidden");
  }

  // Missing scenario list
  const msBox = document.getElementById("missingScenBox");
  const msList = document.getElementById("missingScenList");
  msList.innerHTML = "";
  if (s.reqs_without_scenario.length > 0) {
    msBox.classList.remove("hidden");
    s.reqs_without_scenario.forEach(r => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "jump-btn warn";
      b.textContent = `L${r.line}: ${r.title || "(untitled)"} (${r.body_lines} lines)`;
      b.addEventListener("click", () => jumpToLine(r.line));
      msList.appendChild(b);
    });
  } else {
    msBox.classList.add("hidden");
  }

  // Dedicated section candidates
  const dBox = document.getElementById("dedicatedBox");
  const dList = document.getElementById("dedicatedList");
  dList.innerHTML = "";
  if (s.dedicated_candidates.length > 0) {
    dBox.classList.remove("hidden");
    s.dedicated_candidates.forEach(sec => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "jump-btn info";
      b.textContent = `L${sec.line}: ${sec.text} (${sec.content_lines} lines)`;
      b.addEventListener("click", () => jumpToLine(sec.line));
      dList.appendChild(b);
    });
  } else {
    dBox.classList.add("hidden");
  }

  // Heading outline (skip Purpose in v1 for blinding)
  const outline = document.getElementById("headingOutline");
  outline.innerHTML = "";
  s.headings.forEach(h => {
    if (h.level === 4) return;
    if (state.schema.codebook === "v1" && h.level === 2 && h.text.toLowerCase() === "purpose") return;
    const b = document.createElement("button");
    b.type = "button";
    b.className = `jump-btn h${h.level}`;
    b.textContent = `${h.line}: ${h.text}`;
    b.title = h.text;
    b.addEventListener("click", () => jumpToLine(h.line));
    outline.appendChild(b);
  });

  renderSpecText(data.raw_text, s);
  setStatus(done ? "Loaded existing labels" : "Ready", "");
}

function setStatus(msg, cls) {
  const el = document.getElementById("statusMsg");
  el.textContent = msg;
  el.className = "status-msg" + (cls ? " " + cls : "");
}

function findNextUnlabelled(fromIndex) {
  for (let i = fromIndex + 1; i < state.rows.length; i++) if (!isCoded(state.rows[i])) return i;
  for (let i = 0; i <= fromIndex; i++) if (!isCoded(state.rows[i])) return i;
  return -1;
}

async function saveCurrent(advanceToNextTodo) {
  state.form.note = document.getElementById("noteInput").value.trim();
  const compCol = state.schema.completeness_col;

  if (state.form.is_spec === "true") {
    const missing = [];
    for (const f of ["requirements_extent", "implementation_extent", compCol]) {
      if (!state.form[f]) missing.push(f);
    }
    if (missing.length > 0) {
      missing.forEach(f => document.getElementById("card_" + (f === "completeness" ? "body_completeness" : f))?.classList.add("missing"));
      setStatus("Missing: " + missing.join(", "), "err");
      return;
    }
  }

  const row = state.rows[state.currentIndex];
  const res = await fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ item_id: row.item_id, ...state.form })
  });
  const data = await res.json();
  if (!res.ok) { setStatus(data.error || "Save failed", "err"); return; }

  state.rows[state.currentIndex] = data.row;
  renderItemSelect();
  setStatus(`Saved ${row.item_id}`, "ok");

  if (advanceToNextTodo) {
    const nextIdx = findNextUnlabelled(state.currentIndex);
    if (nextIdx !== -1 && nextIdx !== state.currentIndex) await showItem(nextIdx);
    else if (nextIdx === -1) {
      setStatus(`Saved ${row.item_id} — ALL DONE!`, "ok");
      await showItem(state.currentIndex);
    }
  } else {
    await showItem(state.currentIndex);
  }
}

document.addEventListener("click", (e) => {
  const btn = e.target.closest(".opt-btn[data-field]");
  if (btn) {
    state.form[btn.dataset.field] = btn.dataset.val;
    syncFormUI();
    return;
  }
  const chip = e.target.closest(".chip[data-note]");
  if (chip) {
    const inp = document.getElementById("noteInput");
    const add = chip.dataset.note;
    inp.value = inp.value ? `${inp.value}; ${add}` : add;
    inp.focus();
  }
});

document.getElementById("itemSelect").addEventListener("change", (e) => showItem(Number(e.target.value)));
document.getElementById("unlabelledOnly").addEventListener("change", renderItemSelect);
document.getElementById("prevBtn").addEventListener("click", () => showItem(state.currentIndex - 1));
document.getElementById("nextBtn").addEventListener("click", () => showItem(state.currentIndex + 1));
document.getElementById("nextUnlabelledBtn").addEventListener("click", () => {
  const nextIdx = findNextUnlabelled(state.currentIndex);
  if (nextIdx !== -1) showItem(nextIdx);
});
document.getElementById("saveNextBtn").addEventListener("click", () => saveCurrent(true));
document.getElementById("saveOnlyBtn").addEventListener("click", () => saveCurrent(false));
document.getElementById("guideBtn").addEventListener("click", () => document.getElementById("guideModal").classList.remove("hidden"));
document.getElementById("closeGuideBtn").addEventListener("click", () => document.getElementById("guideModal").classList.add("hidden"));
document.getElementById("guideModal").addEventListener("click", (e) => {
  if (e.target.id === "guideModal") document.getElementById("guideModal").classList.add("hidden");
});

document.addEventListener("keydown", (e) => {
  const modalOpen = !document.getElementById("guideModal").classList.contains("hidden");
  if (e.key === "Escape" && modalOpen) {
    document.getElementById("guideModal").classList.add("hidden");
    return;
  }

  const inInput = document.activeElement && (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "SELECT");
  if (e.key === "Escape" && inInput) { document.activeElement.blur(); return; }
  if (e.key === "Enter" && (e.ctrlKey || !inInput) && !modalOpen) { e.preventDefault(); saveCurrent(true); return; }
  if (inInput) return;

  if (e.key === "?") {
    document.getElementById("guideModal").classList.toggle("hidden");
    return;
  }
  if (modalOpen) return;

  const k = e.key.toLowerCase();
  if (k === "/") { e.preventDefault(); document.getElementById("noteInput").focus(); return; }
  if (k === "[") { showItem(state.currentIndex - 1); return; }
  if (k === "]") { showItem(state.currentIndex + 1); return; }
  if (k === "n") { const nextIdx = findNextUnlabelled(state.currentIndex); if (nextIdx !== -1) showItem(nextIdx); return; }
  if (k === "x") {
    state.form.is_spec = state.form.is_spec === "true" ? "false" : "true";
    syncFormUI();
    if (state.form.is_spec === "false") document.getElementById("noteInput").focus();
    return;
  }
  if (state.form.is_spec !== "true") return;

  const reqMap = { "1": "none", "2": "incidental", "3": "substantial", "4": "dominant" };
  const implMap = { "q": "none", "w": "incidental", "e": "substantial", "r": "dominant" };
  const compKeys = ["a", "s", "d", "f"];
  const compIdx = compKeys.indexOf(k);

  if (reqMap[k]) { state.form.requirements_extent = reqMap[k]; syncFormUI(); }
  else if (implMap[k]) { state.form.implementation_extent = implMap[k]; syncFormUI(); }
  else if (compIdx !== -1 && compIdx < state.schema.completeness_values.length) {
    state.form[state.schema.completeness_col] = state.schema.completeness_values[compIdx];
    syncFormUI();
  } else if (k === "t" && state.schema.has_taxonomy_b) {
    state.form.is_spec_of_work = state.form.is_spec_of_work === "TRUE" ? "FALSE" : "TRUE";
    syncFormUI();
  }
});

async function boot() {
  initMultiPills("purposePills", PURPOSE_OPTS, "purpose");
  initMultiPills("objectPills", OBJECT_OPTS, "object");

  const res = await fetch("/api/state");
  const data = await res.json();
  state.csvName = data.csv_name;
  state.schema = data.schema;
  state.rows = data.rows;
  document.getElementById("sheetTitle").textContent = `Coder: ${data.csv_name}`;
  document.getElementById("codebookBadge").textContent = `codebook ${data.schema.codebook}`;
  renderCompletenessButtons();

  const firstTodo = state.rows.findIndex(r => !isCoded(r));
  await showItem(firstTodo !== -1 ? firstTodo : 0);
}
boot();
</script>
</body>
</html>
"""


class LabelAppContext:
    def __init__(self, csv_path: Path, specs_dir: Path) -> None:
        self.csv_path = csv_path
        self.specs_dir = specs_dir
        self.fieldnames, self.rows = load_csv(csv_path)
        self.schema = detect_schema(self.fieldnames)
        self.index_by_id = {row["item_id"]: idx for idx, row in enumerate(self.rows)}


def make_handler(ctx: LabelAppContext):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            pass

        def send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = HTML_PAGE.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/state":
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "csv_name": str(ctx.csv_path),
                        "schema": ctx.schema,
                        "fieldnames": ctx.fieldnames,
                        "rows": ctx.rows,
                    },
                )
                return

            if parsed.path == "/api/spec":
                qs = parse_qs(parsed.query)
                item_id = (qs.get("id") or [""])[0]
                if item_id not in ctx.index_by_id:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown item_id: {item_id}"})
                    return
                spec_path = ctx.specs_dir / f"{item_id}.md"
                if not spec_path.exists():
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": f"Missing file: {spec_path}"})
                    return
                raw_text = spec_path.read_text(encoding="utf-8", errors="replace")
                summary = extract_objective_summary(raw_text)
                self.send_json(HTTPStatus.OK, {"item_id": item_id, "summary": summary, "raw_text": raw_text})
                return

            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/save":
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                item_id = str(payload.get("item_id", "")).strip()
                if item_id not in ctx.index_by_id:
                    raise ValueError(f"Unknown item_id: {item_id}")
                updates = validate_and_normalize_payload(payload, ctx.schema)
            except (json.JSONDecodeError, ValueError) as exc:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            idx = ctx.index_by_id[item_id]
            ctx.rows[idx].update(updates)
            write_csv_atomic(ctx.csv_path, ctx.fieldnames, ctx.rows)
            self.send_json(HTTPStatus.OK, {"row": ctx.rows[idx]})

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast local web UI for OpenSpec human coding.")
    parser.add_argument(
        "csv_path",
        nargs="?",
        default="labels/pilot/recheck/coding_sheet_nghiep.csv",
        help="Path to the coder CSV file (default: labels/pilot/recheck/coding_sheet_nghiep.csv)",
    )
    parser.add_argument("--port", type=int, default=8765, help="Local port (default: 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser")
    args = parser.parse_args()

    csv_path = Path(args.csv_path).resolve()
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}", file=sys.stderr)
        return 1
    if "TEMPLATE" in csv_path.name.upper():
        print(
            f"Refusing to edit template file {csv_path.name}. Copy it to coding_sheet_<name>.csv first.",
            file=sys.stderr,
        )
        return 1

    specs_dir = csv_path.parent / "specs"
    if not specs_dir.is_dir():
        print(f"Error: specs directory not found next to CSV: {specs_dir}", file=sys.stderr)
        return 1

    ctx = LabelAppContext(csv_path, specs_dir)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(ctx))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Serving {csv_path} ({len(ctx.rows)} items, codebook {ctx.schema['codebook']}) at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
