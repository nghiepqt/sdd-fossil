#!/usr/bin/env python3
"""Fast local web UI for human coding of OpenSpec specs (pilot & double coding).

Reads a coder's CSV copy (never *_TEMPLATE.csv) and its sibling `specs/` folder,
displays objective structural facts + full spec text on the left, and provides
keyboard-driven coding controls on the right. Saves directly back to the CSV.
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
COMPLETENESS_VALUES = ("complete", "complete_except_purpose", "skeletal", "near_empty")  # codebook v0 (pilot)
BODY_COMPLETENESS_VALUES = ("complete", "skeletal", "near_empty")  # codebook v1: column body_completeness
PURPOSE_VALUES = ("feat", "fix", "refactor", "style", "perf")
OBJECT_VALUES = ("docs", "test", "ci", "build", "chore")

HEADING_RE = re.compile(r"^(#{1,4})\s+(.*\S)\s*$")
REQ_RE = re.compile(r"^###\s+Requirement:", re.IGNORECASE)
SCENARIO_RE = re.compile(r"^####\s+Scenario:", re.IGNORECASE)
DELTA_RE = re.compile(r"^##\s+(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements\b", re.IGNORECASE)
CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+")
CODE_FENCE_RE = re.compile(r"^\s*```")
FILE_TOKEN_RE = re.compile(
    r"`([^`\s]+(?:/[^`\s]+|\.(?:ts|tsx|js|jsx|py|go|rs|java|kt|cs|rb|php|sql|yaml|yml|json|toml|md|sh|css|scss|html)))`"
)


def extract_objective_summary(text: str) -> dict:
    """Extract purely objective structural facts from a spec markdown file."""
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

    for idx, line in enumerate(lines, start=1):
        if CODE_FENCE_RE.match(line):
            code_fence_lines += 1
            in_code = not in_code
            continue

        if not in_code:
            m = HEADING_RE.match(line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                headings.append({"level": level, "line": idx, "text": title})

                if level == 2 and title.lower() == "purpose":
                    in_purpose = True
                    continue
                elif in_purpose and level <= 2:
                    in_purpose = False

            if REQ_RE.match(line):
                req_count += 1
            if SCENARIO_RE.match(line):
                scenario_count += 1
            if DELTA_RE.match(line):
                delta_count += 1
            if CHECKBOX_RE.match(line):
                checkbox_count += 1

        if in_purpose:
            purpose_lines.append(line)

    purpose_text = "\n".join(purpose_lines).strip()
    if not purpose_text and not any(
        h["level"] == 2 and h["text"].lower() == "purpose" for h in headings
    ):
        purpose_status = "missing_section"
    elif not purpose_text:
        purpose_status = "empty_section"
    else:
        purpose_status = "present"

    file_tokens = sorted(set(FILE_TOKEN_RE.findall(text)))

    return {
        "line_count": len(lines),
        "word_count": len(text.split()),
        "char_count": len(text),
        "purpose_status": purpose_status,
        "purpose_excerpt": purpose_text,
        "headings": headings,
        "counts": {
            "requirements": req_count,
            "scenarios": scenario_count,
            "code_blocks": code_fence_lines // 2,
            "delta_headers": delta_count,
            "checkboxes": checkbox_count,
            "file_tokens": len(file_tokens),
        },
        "file_tokens_sample": file_tokens[:12],
    }


def load_csv(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with csv_path.open("r", encoding="utf-8", newline="") as f:
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


def is_row_coded(row: dict[str, str], has_taxonomy_b: bool) -> bool:
    is_spec = (row.get("is_spec") or "").strip().upper()
    if is_spec == "FALSE":
        return True
    if is_spec != "TRUE":
        return False
    base_ok = all(
        (row.get(col) or "").strip()
        for col in ("requirements_extent", "implementation_extent", "completeness")
    )
    if not base_ok:
        return False
    if has_taxonomy_b:
        return bool((row.get("is_spec_of_work") or "").strip())
    return True


def validate_and_normalize_payload(payload: dict, has_taxonomy_b: bool,
                                   comp_values: tuple[str, ...] = COMPLETENESS_VALUES) -> dict[str, str]:
    is_spec = str(payload.get("is_spec", "")).strip().upper()
    if is_spec not in ("TRUE", "FALSE"):
        raise ValueError("is_spec must be TRUE or FALSE")

    note = str(payload.get("note", "")).replace("\r", " ").replace("\n", " ").strip()

    if is_spec == "FALSE":
        out = {
            "is_spec": "FALSE",
            "requirements_extent": "",
            "implementation_extent": "",
            "completeness": "",
            "note": note,
        }
        if has_taxonomy_b:
            out.update({"is_spec_of_work": "", "purpose": "", "object": ""})
        return out

    req_ext = str(payload.get("requirements_extent", "")).strip()
    impl_ext = str(payload.get("implementation_extent", "")).strip()
    comp = str(payload.get("completeness", "")).strip()

    if req_ext not in EXTENT_VALUES:
        raise ValueError(f"Invalid requirements_extent: {req_ext!r}")
    if impl_ext not in EXTENT_VALUES:
        raise ValueError(f"Invalid implementation_extent: {impl_ext!r}")
    if comp not in comp_values:
        raise ValueError(f"Invalid completeness: {comp!r}")

    out = {
        "is_spec": "TRUE",
        "requirements_extent": req_ext,
        "implementation_extent": impl_ext,
        "completeness": comp,
        "note": note,
    }

    if has_taxonomy_b:
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

        out.update(
            {
                "is_spec_of_work": work,
                "purpose": purpose_str,
                "object": object_str,
            }
        )

    return out


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>OpenSpec Fast Coder</title>
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
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    padding: 8px 14px; background: var(--panel); border-bottom: 1px solid var(--border);
  }
  .title { font-weight: 700; font-size: 15px; color: #f8fafc; }
  .pill-stat {
    background: var(--card); border: 1px solid var(--border); border-radius: 999px;
    padding: 3px 10px; font-size: 12px; color: var(--muted);
  }
  .pill-stat strong { color: var(--green); }
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
    display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(360px, 0.9fr);
    flex: 1; min-height: 0;
  }

  /* Left Pane */
  .left-pane {
    display: flex; flex-direction: column; min-height: 0;
    border-right: 1px solid var(--border); background: var(--bg);
  }
  .digest {
    padding: 10px 14px; background: var(--panel); border-bottom: 1px solid var(--border);
    display: flex; flex-direction: column; gap: 8px; max-height: 38vh; overflow-y: auto;
  }
  .badges { display: flex; flex-wrap: wrap; gap: 6px; }
  .badge {
    font-size: 12px; padding: 2px 8px; border-radius: 6px;
    background: var(--card); border: 1px solid var(--border); color: var(--muted);
  }
  .badge strong { color: var(--text); }
  .badge.warn { border-color: var(--amber); background: var(--amber-bg); color: #fde68a; }
  .badge.info { border-color: var(--accent); background: var(--accent-bg); color: #bae6fd; }
  .purpose-box {
    background: var(--card); border: 1px solid var(--border); border-radius: 6px;
    padding: 7px 10px; font-size: 12.5px; line-height: 1.4;
  }
  .purpose-box .lbl { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); margin-bottom: 3px; }
  .purpose-box pre { margin: 0; white-space: pre-wrap; font-family: var(--mono); font-size: 12px; color: #f1f5f9; }
  .outline { display: flex; flex-wrap: wrap; gap: 4px; }
  .outline-btn {
    font-size: 11.5px; padding: 2px 7px; border-radius: 4px; background: #0f172a;
    border: 1px solid var(--border); color: #cbd5e1; max-width: 280px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .outline-btn:hover { border-color: var(--accent); color: #fff; }
  .outline-btn.h2 { border-left: 3px solid var(--accent); }
  .outline-btn.h3 { border-left: 3px solid #818cf8; }

  .spec-scroll {
    flex: 1; overflow-y: auto; padding: 12px 14px; font-family: var(--mono);
    font-size: 12.5px; line-height: 1.5;
  }
  .spec-line { display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 10px; padding: 1px 4px; border-radius: 3px; }
  .spec-line:hover { background: rgba(148, 163, 184, 0.08); }
  .spec-line.flash { background: rgba(56, 189, 248, 0.25); transition: background 0.8s; }
  .ln { color: #475569; text-align: right; user-select: none; font-size: 11px; padding-top: 1px; }
  .lc { white-space: pre-wrap; word-break: break-word; }
  .lc.h1, .lc.h2 { color: #38bdf8; font-weight: 700; }
  .lc.h3 { color: #a5b4fc; font-weight: 700; }
  .lc.h4 { color: #86efac; font-weight: 600; }
  .lc.code { color: #fcd34d; }
  .lc.kw { color: #f8fafc; }
  .tok-code { background: rgba(245, 158, 11, 0.16); color: #fde68a; padding: 0 3px; border-radius: 3px; }
  .tok-kw { color: #f472b6; font-weight: 700; }

  /* Right Pane */
  .right-pane {
    display: flex; flex-direction: column; min-height: 0; overflow-y: auto;
    padding: 12px 14px; background: var(--panel); gap: 11px;
  }
  .field-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    padding: 9px 11px; display: flex; flex-direction: column; gap: 7px;
  }
  .field-card.missing { border-color: var(--red); box-shadow: 0 0 0 1px var(--red); }
  .field-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .field-title { font-weight: 600; font-size: 13px; color: #f8fafc; }
  .field-hint { font-size: 11px; color: var(--muted); }
  .btn-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
  .btn-row.four { grid-template-columns: repeat(2, minmax(0, 1fr)); }
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

  .save-bar {
    position: sticky; bottom: 0; background: var(--panel); padding-top: 6px;
    display: flex; align-items: center; gap: 8px; border-top: 1px solid var(--border);
  }
  .status-msg { font-size: 12px; color: var(--muted); margin-left: auto; }
  .status-msg.ok { color: var(--green); }
  .status-msg.err { color: var(--red); }

  .cheat {
    font-size: 11.5px; color: var(--muted); line-height: 1.45;
    background: #0f172a; border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px;
  }
  .cheat b { color: #cbd5e1; }
  .hidden { display: none !important; }
</style>
</head>
<body>
<header>
  <span class="title" id="sheetTitle">OpenSpec Coder</span>
  <span class="pill-stat" id="progressStat">0 / 0 coded</span>
  <span class="pill-stat" id="itemBadge">...</span>
  <a class="gh-link" id="ghLink" href="#" target="_blank" rel="noopener">GitHub ↗</a>

  <div class="nav-group">
    <label style="font-size:12px;color:var(--muted);display:flex;align-items:center;gap:4px;">
      <input type="checkbox" id="unlabelledOnly" /> Unlabelled only
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
      <div class="purpose-box">
        <div class="lbl" id="purposeLabel">## Purpose</div>
        <pre id="purposeText">Loading...</pre>
      </div>
      <div class="outline" id="headingOutline"></div>
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
        <button class="opt-btn" data-field="is_spec" data-val="TRUE"><span class="kbd">x</span> TRUE (is a spec)</button>
        <button class="opt-btn" data-field="is_spec" data-val="FALSE"><span class="kbd">x</span> FALSE (not a spec)</button>
      </div>
    </div>

    <div id="specOnlyFields" style="display:flex;flex-direction:column;gap:11px;">
      <div class="field-card" id="card_requirements_extent">
        <div class="field-head">
          <span class="field-title">2. requirements_extent</span>
          <span class="field-hint">Keys: <span class="kbd">1</span> <span class="kbd">2</span> <span class="kbd">3</span> <span class="kbd">4</span></span>
        </div>
        <div class="btn-row four">
          <button class="opt-btn" data-field="requirements_extent" data-val="none"><span class="kbd">1</span> none</button>
          <button class="opt-btn" data-field="requirements_extent" data-val="incidental"><span class="kbd">2</span> incidental</button>
          <button class="opt-btn" data-field="requirements_extent" data-val="substantial"><span class="kbd">3</span> substantial</button>
          <button class="opt-btn" data-field="requirements_extent" data-val="dominant"><span class="kbd">4</span> dominant</button>
        </div>
      </div>

      <div class="field-card" id="card_implementation_extent">
        <div class="field-head">
          <span class="field-title">3. implementation_extent</span>
          <span class="field-hint">Keys: <span class="kbd">q</span> <span class="kbd">w</span> <span class="kbd">e</span> <span class="kbd">r</span></span>
        </div>
        <div class="btn-row four">
          <button class="opt-btn" data-field="implementation_extent" data-val="none"><span class="kbd">q</span> none</button>
          <button class="opt-btn" data-field="implementation_extent" data-val="incidental"><span class="kbd">w</span> incidental</button>
          <button class="opt-btn" data-field="implementation_extent" data-val="substantial"><span class="kbd">e</span> substantial</button>
          <button class="opt-btn" data-field="implementation_extent" data-val="dominant"><span class="kbd">r</span> dominant</button>
        </div>
      </div>

      <div class="field-card" id="card_completeness">
        <div class="field-head">
          <span class="field-title">4. completeness</span>
          <span class="field-hint">Keys: <span class="kbd">a</span> <span class="kbd">s</span> <span class="kbd">d</span> <span class="kbd">f</span></span>
        </div>
        <div class="btn-row four">
          <button class="opt-btn" data-field="completeness" data-val="complete"><span class="kbd">a</span> complete</button>
          <button class="opt-btn" data-field="completeness" data-val="complete_except_purpose"><span class="kbd">s</span> complete_except_purpose</button>
          <button class="opt-btn" data-field="completeness" data-val="skeletal"><span class="kbd">d</span> skeletal</button>
          <button class="opt-btn" data-field="completeness" data-val="near_empty"><span class="kbd">f</span> near_empty</button>
        </div>
      </div>

      <div class="field-card hidden" id="card_is_spec_of_work">
        <div class="field-head">
          <span class="field-title">5. is_spec_of_work (pilot)</span>
          <span class="field-hint">Key: <span class="kbd">t</span> toggle</span>
        </div>
        <div class="btn-row">
          <button class="opt-btn" data-field="is_spec_of_work" data-val="FALSE"><span class="kbd">t</span> FALSE (system as-is)</button>
          <button class="opt-btn" data-field="is_spec_of_work" data-val="TRUE"><span class="kbd">t</span> TRUE (work to do)</button>
        </div>

        <div id="workDetails" class="hidden" style="display:flex;flex-direction:column;gap:8px;margin-top:4px;padding-top:8px;border-top:1px solid var(--border);">
          <div>
            <div class="field-hint" style="margin-bottom:4px;">purpose (multi-select, or none)</div>
            <div class="btn-row flex" id="purposePills"></div>
          </div>
          <div>
            <div class="field-hint" style="margin-bottom:4px;">object (multi-select, or none)</div>
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
        <input type="text" id="noteInput" placeholder="Hesitations, default, opened GitHub URL..." />
        <div class="chip-row">
          <button class="chip" data-note="default">+ default</button>
          <button class="chip" data-note="opened GitHub URL">+ opened GitHub URL</button>
          <button class="chip" data-note="mixed: ">+ mixed:</button>
          <button class="chip" data-note="unsure between ">+ unsure between</button>
        </div>
      </div>
    </div>

    <div class="cheat">
      <b>Quick rules:</b>
      <b>Extent:</b> none=absent | incidental=1–2 lines | substantial=section/several statements | dominant=most of doc. Empty headings &amp; TBD Purpose don't count.<br/>
      <span id="cheatCompleteness"><b>Completeness:</b> <i>complete</i>=all filled + real Purpose | <i>complete_except_purpose</i>=reqs &amp; scenarios filled, Purpose missing/TBD | <i>skeletal</i>=headings/titles only or one-liners / missing scenarios | <i>near_empty</i>=almost nothing.</span><br/>
      <b>Work vs System:</b> SHALL &amp; TBD Purpose are NOT work signals. No clear signal → FALSE + note <code>default</code>.
    </div>

    <div class="save-bar">
      <button class="primary" id="saveNextBtn">Save &amp; Next (<span class="kbd" style="background:#0369a1;border-color:#38bdf8;color:#fff;">Enter</span>)</button>
      <button id="saveOnlyBtn">Save</button>
      <span class="status-msg" id="statusMsg">Ready</span>
    </div>
  </section>
</main>

<script>
const PURPOSE_OPTS = ["feat", "fix", "refactor", "style", "perf", "none"];
const OBJECT_OPTS = ["docs", "test", "ci", "build", "chore", "none"];

let state = {
  csvName: "",
  hasTaxonomyB: false,
  rows: [],
  currentIndex: 0,
  form: {}
};

function escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function isCoded(row) {
  const sp = (row.is_spec || "").trim().toUpperCase();
  if (sp === "FALSE") return true;
  if (sp !== "TRUE") return false;
  if (!row.requirements_extent || !row.implementation_extent || !row.completeness) return false;
  if (state.hasTaxonomyB && !row.is_spec_of_work) return false;
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
  if (val === "none") {
    cur = ["none"];
  } else {
    cur = cur.filter(x => x !== "none");
    if (cur.includes(val)) cur = cur.filter(x => x !== val);
    else cur.push(val);
    if (cur.length === 0) cur = ["none"];
  }
  state.form[field] = cur.join(";");
  syncFormUI();
}

function loadRowIntoForm(row) {
  const coded = isCoded(row);
  state.form = {
    is_spec: (row.is_spec || (coded ? "" : "TRUE")).toUpperCase() || "TRUE",
    requirements_extent: row.requirements_extent || "",
    implementation_extent: row.implementation_extent || "",
    completeness: row.completeness || "",
    is_spec_of_work: (row.is_spec_of_work || (coded ? "" : "FALSE")).toUpperCase() || "FALSE",
    purpose: row.purpose || "none",
    object: row.object || "none",
    note: row.note || ""
  };
  document.getElementById("noteInput").value = state.form.note;
  syncFormUI();
}

function syncFormUI() {
  const isSpec = state.form.is_spec === "TRUE";
  document.getElementById("specOnlyFields").classList.toggle("hidden", !isSpec);
  document.getElementById("card_is_spec_of_work").classList.toggle("hidden", !state.hasTaxonomyB);

  const workTrue = state.hasTaxonomyB && isSpec && state.form.is_spec_of_work === "TRUE";
  document.getElementById("workDetails").classList.toggle("hidden", !workTrue);

  document.querySelectorAll(".opt-btn[data-field]").forEach(btn => {
    const f = btn.dataset.field;
    const v = btn.dataset.val;
    btn.classList.remove("active", "active-green", "active-red");
    if (state.form[f] === v) {
      if (f === "is_spec" && v === "FALSE") btn.classList.add("active-red");
      else if (f === "is_spec" && v === "TRUE") btn.classList.add("active-green");
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

function renderSpecText(rawText) {
  const container = document.getElementById("specContent");
  const lines = rawText.split("\n");
  let inCode = false;
  const htmlParts = lines.map((line, idx) => {
    const ln = idx + 1;
    let cls = "lc";
    if (/^\s*```/.test(line)) {
      inCode = !inCode;
      cls += " code";
    } else if (inCode) {
      cls += " code";
    } else if (/^#\s+/.test(line)) cls += " h1";
    else if (/^##\s+/.test(line)) cls += " h2";
    else if (/^###\s+/.test(line)) cls += " h3";
    else if (/^####\s+/.test(line)) cls += " h4";

    let body = escHtml(line);
    if (!inCode) {
      body = body.replace(/`([^`]+)`/g, '<span class="tok-code">`$1`</span>');
      body = body.replace(/\b(WHEN|THEN|AND|SHALL|MUST|TODO|TBD)\b/g, '<span class="tok-kw">$1</span>');
    }
    return `<div class="spec-line" id="L${ln}"><span class="ln">${ln}</span><span class="${cls}">${body || " "}</span></div>`;
  });
  container.innerHTML = htmlParts.join("");
  container.scrollTop = 0;
}

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
  const row = state.rows[index];
  renderItemSelect();

  const done = isCoded(row);
  document.getElementById("itemBadge").innerHTML =
    `<strong>${row.item_id}</strong> &middot; batch ${row.batch} &middot; ${done ? '<span style="color:var(--green)">coded</span>' : '<span style="color:var(--amber)">todo</span>'}`;
  const gh = document.getElementById("ghLink");
  gh.href = row.file_url;

  loadRowIntoForm(row);
  setStatus("Loading spec...", "");

  const res = await fetch(`/api/spec?id=${encodeURIComponent(row.item_id)}`);
  const data = await res.json();
  if (!res.ok) {
    setStatus(data.error || "Failed to load spec", "err");
    return;
  }

  const s = data.summary;
  const badges = [
    `<span class="badge"><strong>${s.line_count}</strong> lines (${s.word_count} words)</span>`,
    `<span class="badge">Req: <strong>${s.counts.requirements}</strong></span>`,
    `<span class="badge">Scenario: <strong>${s.counts.scenarios}</strong></span>`,
    `<span class="badge">Code blocks: <strong>${s.counts.code_blocks}</strong></span>`,
    `<span class="badge">File refs: <strong>${s.counts.file_tokens}</strong></span>`
  ];
  if (s.counts.delta_headers > 0) {
    badges.push(`<span class="badge warn">Delta headers: <strong>${s.counts.delta_headers}</strong></span>`);
  }
  if (s.counts.checkboxes > 0) {
    badges.push(`<span class="badge warn">Checkboxes: <strong>${s.counts.checkboxes}</strong></span>`);
  }
  document.getElementById("digestBadges").innerHTML = badges.join("");

  const pLabel = document.getElementById("purposeLabel");
  const pText = document.getElementById("purposeText");
  if (s.purpose_status === "missing_section") {
    pLabel.textContent = "## Purpose (no ## Purpose section)";
    pText.textContent = "(none)";
  } else if (s.purpose_status === "empty_section") {
    pLabel.textContent = "## Purpose (empty)";
    pText.textContent = "(empty)";
  } else {
    pLabel.textContent = "## Purpose";
    pText.textContent = s.purpose_excerpt;
  }

  const outline = document.getElementById("headingOutline");
  outline.innerHTML = "";
  s.headings.forEach(h => {
    if (h.level === 4) return;
    const b = document.createElement("button");
    b.type = "button";
    b.className = `outline-btn h${h.level}`;
    b.textContent = `${h.line}: ${h.text}`;
    b.title = h.text;
    b.addEventListener("click", () => jumpToLine(h.line));
    outline.appendChild(b);
  });

  renderSpecText(data.raw_text);
  setStatus(done ? "Loaded existing labels" : "Ready", "");
}

function setStatus(msg, cls) {
  const el = document.getElementById("statusMsg");
  el.textContent = msg;
  el.className = "status-msg" + (cls ? " " + cls : "");
}

function findNextUnlabelled(fromIndex) {
  for (let i = fromIndex + 1; i < state.rows.length; i++) {
    if (!isCoded(state.rows[i])) return i;
  }
  for (let i = 0; i <= fromIndex; i++) {
    if (!isCoded(state.rows[i])) return i;
  }
  return -1;
}

async function saveCurrent(advanceToNextTodo) {
  state.form.note = document.getElementById("noteInput").value.trim();

  if (state.form.is_spec === "TRUE") {
    const missing = [];
    for (const f of ["requirements_extent", "implementation_extent", "completeness"]) {
      if (!state.form[f]) missing.push(f);
    }
    if (missing.length > 0) {
      missing.forEach(f => document.getElementById("card_" + f)?.classList.add("missing"));
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
  if (!res.ok) {
    setStatus(data.error || "Save failed", "err");
    return;
  }

  state.rows[state.currentIndex] = data.row;
  renderItemSelect();
  setStatus(`Saved ${row.item_id}`, "ok");

  if (advanceToNextTodo) {
    const nextIdx = findNextUnlabelled(state.currentIndex);
    if (nextIdx !== -1 && nextIdx !== state.currentIndex) {
      await showItem(nextIdx);
    } else if (nextIdx === -1) {
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
    const f = btn.dataset.field;
    state.form[f] = btn.dataset.val;
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

document.addEventListener("keydown", (e) => {
  const inInput = document.activeElement && (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "SELECT");
  if (e.key === "Escape" && inInput) {
    document.activeElement.blur();
    return;
  }
  if (e.key === "Enter" && (e.ctrlKey || !inInput)) {
    e.preventDefault();
    saveCurrent(true);
    return;
  }
  if (inInput) return;

  const k = e.key.toLowerCase();
  if (k === "/") { e.preventDefault(); document.getElementById("noteInput").focus(); return; }
  if (k === "[") { showItem(state.currentIndex - 1); return; }
  if (k === "]") { showItem(state.currentIndex + 1); return; }
  if (k === "n") {
    const nextIdx = findNextUnlabelled(state.currentIndex);
    if (nextIdx !== -1) showItem(nextIdx);
    return;
  }
  if (k === "x") {
    state.form.is_spec = state.form.is_spec === "TRUE" ? "FALSE" : "TRUE";
    syncFormUI();
    if (state.form.is_spec === "FALSE") document.getElementById("noteInput").focus();
    return;
  }
  if (state.form.is_spec !== "TRUE") return;

  const reqMap = { "1": "none", "2": "incidental", "3": "substantial", "4": "dominant" };
  const implMap = { "q": "none", "w": "incidental", "e": "substantial", "r": "dominant" };
  const compMap = { "a": "complete", "s": "complete_except_purpose", "d": "skeletal", "f": "near_empty" };

  if (reqMap[k]) { state.form.requirements_extent = reqMap[k]; syncFormUI(); }
  else if (implMap[k]) { state.form.implementation_extent = implMap[k]; syncFormUI(); }
  else if (compMap[k] && state.compValues.includes(compMap[k])) { state.form.completeness = compMap[k]; syncFormUI(); }
  else if (k === "t" && state.hasTaxonomyB) {
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
  state.hasTaxonomyB = data.has_taxonomy_b;
  state.compValues = data.comp_values;
  // Codebook v1: hide completeness values the sheet does not allow, relabel the field.
  document.querySelectorAll('.opt-btn[data-field="completeness"]').forEach(b =>
    b.classList.toggle("hidden", !data.comp_values.includes(b.dataset.val)));
  if (data.comp_col === "body_completeness") {
    document.querySelector("#card_completeness .field-title").textContent = "4. body_completeness (ignore Purpose)";
    document.getElementById("cheatCompleteness").innerHTML = "<b>Body completeness (v1, ignore Purpose):</b> <i>complete</i>=every requirement has a body AND &ge;1 scenario | <i>skeletal</i>=some requirement is title-only or has no scenario | <i>near_empty</i>=no requirement has a body.";
  }
  state.rows = data.rows;
  document.getElementById("sheetTitle").textContent = `Coder: ${data.csv_name}`;

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
        self.has_taxonomy_b = "is_spec_of_work" in self.fieldnames
        self.index_by_id = {row["item_id"]: idx for idx, row in enumerate(self.rows)}
        # Codebook v1 sheets use body_completeness (Purpose excluded); the UI keeps calling it "completeness".
        self.comp_col = "body_completeness" if "body_completeness" in self.fieldnames else "completeness"
        self.comp_values = BODY_COMPLETENESS_VALUES if self.comp_col == "body_completeness" else COMPLETENESS_VALUES

    def ui_row(self, row: dict[str, str]) -> dict[str, str]:
        out = dict(row)
        out["completeness"] = row.get(self.comp_col, "")
        return out


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
                        "has_taxonomy_b": ctx.has_taxonomy_b,
                        "fieldnames": ctx.fieldnames,
                        "rows": [ctx.ui_row(r) for r in ctx.rows],
                        "comp_col": ctx.comp_col,
                        "comp_values": list(ctx.comp_values),
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
                updates = validate_and_normalize_payload(payload, ctx.has_taxonomy_b, ctx.comp_values)
                updates[ctx.comp_col] = updates.pop("completeness")
            except (json.JSONDecodeError, ValueError) as exc:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            idx = ctx.index_by_id[item_id]
            ctx.rows[idx].update(updates)
            write_csv_atomic(ctx.csv_path, ctx.fieldnames, ctx.rows)
            self.send_json(HTTPStatus.OK, {"row": ctx.ui_row(ctx.rows[idx])})

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast local web UI for OpenSpec human coding.")
    parser.add_argument(
        "csv_path",
        nargs="?",
        default="labels/pilot/coding_sheet_person1.csv",
        help="Path to the coder CSV file (default: labels/pilot/coding_sheet_person1.csv)",
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
    print(f"Serving {csv_path} ({len(ctx.rows)} items) at {url}")
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
