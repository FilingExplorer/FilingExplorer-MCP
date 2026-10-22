#!/usr/bin/env python3
"""Check commits, messages and files for content that should not be published.

Two layers of patterns:

* Generic patterns, kept in this file: namespaced class paths, issue references,
  absolute home-directory paths, session links, email addresses outside an
  allowlist, private key or token shapes, and a trailer block at the end of a
  commit message.
* Additional patterns, loaded from the file named by ``FE_SCRUB_TERMS``, else
  ``~/.config/filingexplorer/scrub_terms.txt``.
  One entry per line; blank lines and lines starting with ``#`` are ignored.
  A plain entry is matched case-insensitively as a whole word. An entry that
  contains regex syntax, or starts with ``re:``, is used as a case-insensitive regex.

If no pattern file is found the check fails, unless ``--generic-only`` is passed.
In CI (``CI=true``) and with ``--release`` it always fails without the list.

Modes (combine as needed):

  --staged        added lines and new file names in the index
  --message FILE  a commit message file
  --range A..B    each commit in the range: message, author/committer, added lines.
                  A single revision means its whole ancestry.
  --tree          every tracked file at HEAD
  --history       every commit message, identity and blob reachable from all refs,
                  or from ``--ref REF`` only

Output: ``file:line category snippet``. Matches of additional patterns are
never printed in full: only the first two characters and the length.
Exit status: 0 clean, 1 findings, 2 configuration error.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TERMS_PATH = Path("~/.config/filingexplorer/scrub_terms.txt").expanduser()

ALLOWED_IDENTITY = ("Giant Octopus, LLC", "hello@giantoctopus.ink")

# Several patterns use a one-character class (e.g. ``[s]``) so that this file
# does not match its own patterns when the tree is scanned.
GENERIC: list[tuple[str, re.Pattern[str]]] = [
    ("class-path", re.compile(r"\b[A-Za-z_]\w*::[A-Za-z_]\w*")),
    ("issue-ref", re.compile(r"(?<![&\w/])#\d{2,5}\b")),
    ("issue-ref", re.compile(r"\bGH-\d+\b", re.IGNORECASE)),
    ("home-path", re.compile(r"/User[s]/|/hom[e]/|~/rep[o]s\b")),
    ("session-link", re.compile(r"claude\.ai/code/sessio[n]", re.IGNORECASE)),
    ("private-key", re.compile(r"-----BEGI[N] (?:[A-Z0-9]+ )*PRIVATE KEY-----")),
    ("token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_\w{22,}")),
    ("token", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("token", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{32,}")),
    ("token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    (
        "token",
        re.compile(
            r"(?:api[_-]?key|secret|token|passwor[d])['\"]?\s*[:=]\s*['\"][A-Za-z0-9_\-/+=.]{24,}['\"]",
            re.IGNORECASE,
        ),
    ),
]

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
ALLOWED_EMAIL = re.compile(
    r"^(?:hello@giantoctopus\.ink|noreply@github\.com|[A-Za-z0-9._+-]+@users\.noreply\.github\.com)$",
    re.IGNORECASE,
)
TRAILER_LINE = re.compile(r"^[A-Za-z][\w-]*: \S")
REGEX_SYNTAX = re.compile(r"[\\()\[\]|?*+^${}]")
ZERO_SHA = re.compile(r"^0+$")


@dataclass
class Finding:
    where: str
    line: int
    category: str
    snippet: str

    def __str__(self) -> str:
        return f"{self.where}:{self.line} {self.category} {self.snippet}"


class Scanner:
    def __init__(self, terms: list[re.Pattern[str]]):
        self.terms = terms
        self.findings: list[Finding] = []

    # -- helpers ---------------------------------------------------------
    def _redact(self, text: str) -> str:
        for term in self.terms:
            text = term.sub(lambda m: _mask(m.group(0)), text)
        return text

    def scan_line(self, where: str, lineno: int, line: str) -> None:
        for term in self.terms:
            for m in term.finditer(line):
                self.findings.append(Finding(where, lineno, "private-term", _mask(m.group(0))))
        for category, regex in GENERIC:
            m = regex.search(line)
            if m:
                self.findings.append(Finding(where, lineno, category, self._snippet(line, m)))
        for m in EMAIL.finditer(line):
            if not ALLOWED_EMAIL.match(m.group(0)):
                self.findings.append(Finding(where, lineno, "email", self._snippet(line, m)))

    def _snippet(self, line: str, m: re.Match[str]) -> str:
        start = max(0, m.start() - 20)
        text = line[start : m.end() + 40].strip()
        return self._redact(text)[:80]

    def scan_text(self, where: str, text: str, linenos: list[int] | None = None) -> None:
        for i, line in enumerate(text.splitlines()):
            self.scan_line(where, linenos[i] if linenos else i + 1, line)

    def scan_path(self, where: str, path: str) -> None:
        self.scan_line(where, 0, path)

    def scan_identity(self, where: str, role: str, name: str, email: str) -> None:
        if (name, email) != ALLOWED_IDENTITY:
            shown = self._redact(f"{role} {name} <{email}>")
            self.findings.append(Finding(where, 0, "identity", shown))

    def scan_message(self, where: str, text: str) -> None:
        lines: list[tuple[int, str]] = []
        for i, line in enumerate(text.splitlines(), start=1):
            if line.startswith("# ------------------------ >8"):
                break
            if line == "#" or line.startswith("# "):
                continue
            lines.append((i, line))
            self.scan_line(where, i, line)
        # A final paragraph made only of "Key: value" lines is a trailer block.
        while lines and not lines[-1][1].strip():
            lines.pop()
        block: list[tuple[int, str]] = []
        for i, line in reversed(lines):
            if not line.strip():
                break
            block.insert(0, (i, line))
        if len(block) < len(lines) and block and all(TRAILER_LINE.match(x) for _, x in block):
            for i, line in block:
                self.findings.append(Finding(where, i, "trailer", self._redact(line)[:80]))


def _mask(term: str) -> str:
    return f"{term[:2]}...(len {len(term)})"


# -- pattern file -----------------------------------------------------------------
def load_terms(path: Path) -> list[re.Pattern[str]]:
    terms = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("re:"):
            pattern = entry[3:]
        elif REGEX_SYNTAX.search(entry):
            pattern = entry
        else:
            pattern = r"(?<!\w)" + re.escape(entry) + r"(?!\w)"
        terms.append(re.compile(pattern, re.IGNORECASE))
    return terms


def find_terms_file() -> Path | None:
    env = os.environ.get("FE_SCRUB_TERMS")
    if env:
        path = Path(env).expanduser()
        return path if path.is_file() else None
    return DEFAULT_TERMS_PATH if DEFAULT_TERMS_PATH.is_file() else None


# -- git -------------------------------------------------------------------
def git(*args: str, binary: bool = False):
    out = subprocess.run(["git", *args], check=True, capture_output=True).stdout
    return out if binary else out.decode("utf-8", errors="replace")


def _parse_diff(scanner: Scanner, diff: str, label: str = "") -> None:
    path, lineno = "?", 0
    hunk = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            path = target[2:] if target.startswith("b/") else target
            continue
        if line.startswith("--- ") or line.startswith("diff --git"):
            continue
        m = hunk.match(line)
        if m:
            lineno = int(m.group(1))
            continue
        if line.startswith("+"):
            scanner.scan_line(f"{label}{path}", lineno, line[1:])
            lineno += 1


def scan_staged(scanner: Scanner) -> None:
    for path in git("diff", "--cached", "--name-only", "--diff-filter=AR").splitlines():
        scanner.scan_path(path, path)
    diff = git("diff", "--cached", "-U0", "--text", "--no-color", "--no-ext-diff")
    _parse_diff(scanner, diff)


def _commits(rev_args: list[str]) -> list[str]:
    return git("rev-list", *rev_args).split()


def scan_commit(scanner: Scanner, sha: str, with_diff: bool) -> None:
    short = sha[:10]
    fields = git("show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%P", sha).rstrip("\n")
    an, ae, cn, ce, parents = fields.split("\x00")
    scanner.scan_identity(f"commit {short}", "author", an, ae)
    scanner.scan_identity(f"commit {short}", "committer", cn, ce)
    scanner.scan_message(f"commit {short} message", git("show", "-s", "--format=%B", sha))
    if not with_diff:
        return
    parent = parents.split()[0] if parents else None
    if parent:
        diff = git("diff", "-U0", "--text", "--no-color", "--no-ext-diff", parent, sha)
        names = git("diff", "--name-only", "--diff-filter=AR", parent, sha)
    else:
        diff = git("show", "--format=", "-U0", "--text", "--no-color", "--no-ext-diff", sha)
        names = git("show", "--format=", "--name-only", sha)
    for path in names.splitlines():
        if path:
            scanner.scan_path(f"commit {short} {path}", path)
    _parse_diff(scanner, diff, label=f"commit {short} ")


def scan_range(scanner: Scanner, spec: str) -> None:
    if ".." in spec:
        base, head = spec.split("..", 1)
        rev_args = [head] if ZERO_SHA.match(base or "0") else [f"{base}..{head}"]
    else:
        rev_args = [spec]
    for sha in _commits(rev_args):
        scan_commit(scanner, sha, with_diff=True)


def _scan_blobs(scanner: Scanner, objects: list[tuple[str, str]], label: str) -> None:
    if not objects:
        return
    batch = "".join(f"{sha}\n" for sha, _ in objects).encode()
    out = subprocess.run(
        ["git", "cat-file", "--batch"], input=batch, check=True, capture_output=True
    ).stdout
    pos = 0
    for _sha, path in objects:
        header_end = out.index(b"\n", pos)
        header = out[pos:header_end].split()
        size = int(header[2])
        body = out[header_end + 1 : header_end + 1 + size]
        pos = header_end + 1 + size + 1
        scanner.scan_path(f"{label}{path}", path)
        scanner.scan_text(f"{label}{path}", body.decode("utf-8", errors="replace"))


def scan_tree(scanner: Scanner) -> None:
    objects = []
    for line in git("ls-tree", "-r", "-z", "HEAD").split("\x00"):
        if not line:
            continue
        meta, path = line.split("\t", 1)
        _mode, kind, sha = meta.split()
        if kind == "blob":
            objects.append((sha, path))
    _scan_blobs(scanner, objects, "")


def scan_history(scanner: Scanner, ref: str | None) -> None:
    rev_args = [ref] if ref else ["--all"]
    for sha in _commits(rev_args):
        scan_commit(scanner, sha, with_diff=False)
    objects = []
    seen = set()
    for line in git("rev-list", "--objects", *rev_args).splitlines():
        sha, _, path = line.partition(" ")
        if sha in seen:
            continue
        seen.add(sha)
        objects.append((sha, path))
    if not objects:
        return
    check = subprocess.run(
        ["git", "cat-file", "--batch-check=%(objectname) %(objecttype)"],
        input="".join(f"{s}\n" for s, _ in objects).encode(),
        check=True,
        capture_output=True,
    ).stdout.decode()
    types = dict(line.split() for line in check.splitlines())
    blobs = [(s, p or s[:10]) for s, p in objects if types.get(s) == "blob"]
    _scan_blobs(scanner, blobs, "blob ")
    for s, _ in objects:
        if types.get(s) == "tag":
            scanner.scan_message(f"tag {s[:10]}", git("cat-file", "tag", s))


# -- entry point -------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--staged", action="store_true")
    p.add_argument("--message", metavar="FILE")
    p.add_argument("--range", dest="ranges", action="append", default=[], metavar="A..B")
    p.add_argument("--tree", action="store_true")
    p.add_argument("--history", action="store_true")
    p.add_argument("--ref", help="limit --history to this ref")
    p.add_argument("--release", action="store_true", help="require the pattern file")
    p.add_argument("--generic-only", action="store_true", help="run without the pattern file")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (args.staged or args.message or args.ranges or args.tree or args.history):
        print("scrub_check: choose at least one mode", file=sys.stderr)
        return 2

    strict = args.release or os.environ.get("CI", "").lower() == "true"
    terms_file = find_terms_file()
    if terms_file is None:
        if strict:
            print("scrub_check: pattern file not found; failing closed", file=sys.stderr)
            return 2
        if not args.generic_only:
            print(
                "scrub_check: pattern file not found (set FE_SCRUB_TERMS or install "
                f"{DEFAULT_TERMS_PATH}); pass --generic-only to run generic checks only",
                file=sys.stderr,
            )
            return 2
        terms: list[re.Pattern[str]] = []
        print("scrub_check: running generic checks only", file=sys.stderr)
    elif args.generic_only and not strict:
        terms = []
    else:
        try:
            terms = load_terms(terms_file)
        except re.error as exc:
            print(f"scrub_check: bad entry in pattern file: {exc}", file=sys.stderr)
            return 2

    scanner = Scanner(terms)
    if args.staged:
        scan_staged(scanner)
    if args.message:
        scanner.scan_message("message", Path(args.message).read_text(encoding="utf-8"))
    for spec in args.ranges:
        scan_range(scanner, spec)
    if args.tree:
        scan_tree(scanner)
    if args.history:
        scan_history(scanner, args.ref)

    for finding in scanner.findings:
        print(finding)
    if scanner.findings:
        print(f"scrub_check: {len(scanner.findings)} finding(s)", file=sys.stderr)
        return 1
    print("scrub_check: clean", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
