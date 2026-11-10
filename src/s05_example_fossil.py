"""Pick one example fossil living spec for the proposal/report figure (seeded, anonymized).

Candidates: OpenSpec living specs in the cohort that are fossils (placeholder at snapshot, zero
revisions), hold the canonical archive placeholder text, are plain ASCII, and are short enough to
show whole (MIN_LINES..MAX_LINES lines after dropping blank lines at both ends). Candidates are
sorted by file_url_sha16 and one is drawn with a fixed seed.

Anonymization (a lightly edited excerpt, not a verbatim one):
  * the repository owner and name are replaced wherever they occur in the text;
  * the change name inside the placeholder becomes <change>;
  * inline code that names a scoped package (`@scope/name`) becomes `<package>`, and inline code
    that names a path (contains "/") becomes `<path>`;
  * URLs and e-mail addresses are masked.
The repository name is never written to disk. The prose of the requirements is kept, so a code
search on a full sentence may still find the source: paraphrase it before any publication.

Reads data/derived/openspec_living.parquet (s00) and data/derived/living_content.parquet (s02).
Writes results/example_fossil_spec.md (the excerpt shown in the figure). Writes nothing to
numbers.json: the excerpt is an illustration, not a result.
"""
import random
import re

import duckdb

from common import DERIVED, RESULTS

SEED = 20261109
MIN_LINES, MAX_LINES = 12, 20
OUT = RESULTS / "example_fossil_spec.md"

RE_URL = re.compile(r"https?://\S+")
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
RE_CHANGE = re.compile(r"(by archiving change )\S+?(\. Update Purpose)")
RE_CODE = re.compile(r"`([^`\n]+)`")


def mask_code(m):
    s = m.group(1)
    if s.startswith("@"):
        return "`<package>`"
    if "/" in s:
        return "`<path>`"
    return m.group(0)


def anonymize(text, repo_name):
    owner, _, name = repo_name.partition("/")
    for token, mask in ((repo_name, "<owner>/<repo>"), (owner, "<owner>"), (name, "<repo>")):
        if len(token) >= 3:
            text = re.sub(re.escape(token), mask, text, flags=re.I)
    text = RE_CHANGE.sub(r"\1<change>\2", text)
    text = RE_CODE.sub(mask_code, text)
    text = RE_URL.sub("<url>", text)
    return RE_EMAIL.sub("<email>", text)


def main():
    con = duckdb.connect()
    rows = con.sql(f"""
        SELECT l.file_url_sha16, l.repo_name, l.file_path, c.content
        FROM read_parquet('{DERIVED / "openspec_living.parquet"}') l
        JOIN read_parquet('{DERIVED / "living_content.parquet"}') c USING (file_url_sha16)
        WHERE l.fossil_class = 'fossil' AND c.re_canonical
        ORDER BY l.file_url_sha16
    """).fetchall()

    candidates = []
    for sha, repo, path, content in rows:
        if content is None or not content.isascii():
            continue
        lines = content.strip("\n").splitlines()
        if MIN_LINES <= len(lines) <= MAX_LINES and any(l.startswith("### Requirement") for l in lines):
            candidates.append((sha, repo, path, lines))

    sha, repo, path, lines = random.Random(SEED).choice(candidates)
    capability = path.split("/")[-2] if path.count("/") >= 2 else "<capability>"
    text = anonymize("\n".join(lines), repo)
    OUT.write_text(f"<!-- openspec/specs/{capability}/spec.md -->\n{text}\n")
    print(f"{len(candidates)} candidates; picked {sha} ({len(lines)} lines) -> {OUT}")


if __name__ == "__main__":
    main()
