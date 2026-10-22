import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "scrub_check.py"
_spec = importlib.util.spec_from_file_location("scrub_check", SCRIPT)
scrub = importlib.util.module_from_spec(_spec)
sys.modules["scrub_check"] = scrub
_spec.loader.exec_module(scrub)

# Planted strings are split so this file does not trip the checker itself.
PLANTED_GENERIC = [
    ("class-path", "Mailer:" + ":Digest"),
    ("issue-ref", "fixed in #" + "1234"),
    ("issue-ref", "see GH" + "-42"),
    ("home-path", "/Us" + "ers/someone/project"),
    ("home-path", "/ho" + "me/someone/project"),
    ("home-path", "~/re" + "pos/project"),
    ("session-link", "https://claude.ai/code/sess" + "ion_abc"),
    ("email", "write to some" + "one" + "@example.com"),
    ("private-key", "-----BEG" + "IN RSA PRIVATE KEY-----"),
    ("token", "gh" + "p_" + "a" * 36),
    ("token", "AK" + "IA" + "B" * 16),
]

ORDINARY = [
    "Form 13-F holdings",
    "S&P 500",
    "Q3 #1 holder",
    "10-K Item 1A",
    "Programming Language :: Python :: 3",
    "User-Agent: something",
    "contact hello@giantoctopus.ink",
    "12345+someone@users.noreply.github.com",
    "color &#1234; entity",
]


def _compile(terms):
    path = Path(os.environ["SCRUB_TEST_TMP"]) / "terms.txt"
    path.write_text("\n".join(terms) + "\n")
    return scrub.load_terms(path)


@pytest.fixture(autouse=True)
def _tmp_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRUB_TEST_TMP", str(tmp_path))


def _scan_line(line, terms=()):
    s = scrub.Scanner(_compile(terms))
    s.scan_line("x", 1, line)
    return s.findings


@pytest.mark.parametrize(("category", "line"), PLANTED_GENERIC)
def test_generic_patterns_catch_planted_text(category, line):
    assert category in {f.category for f in _scan_line(line)}, line


@pytest.mark.parametrize("line", ORDINARY)
def test_generic_patterns_allow_ordinary_text(line):
    assert _scan_line(line) == []


def test_private_terms_match_words_and_regexes_and_are_masked():
    terms = ["# comment", "zebra-widget", "re:quux\\d+", "foo(bar|baz)"]
    findings = _scan_line("Zebra-Widget and QUUX42 and foobaz", terms)
    assert [f.category for f in findings] == ["private-term"] * 3
    assert findings[0].snippet == "Ze...(len 12)"
    assert all("widget" not in str(f).lower() for f in findings)


def test_plain_terms_respect_word_boundaries():
    assert _scan_line("zebra-widgets are fine", ["zebra-widget"]) == []
    assert _scan_line("xzebra-widget", ["zebra-widget"]) == []


def test_generic_snippet_masks_private_terms():
    findings = _scan_line("see /Us" + "ers/zebra-widget/x", ["zebra-widget"])
    assert {f.category for f in findings} == {"private-term", "home-path"}
    assert all("widget" not in f.snippet for f in findings)


@pytest.mark.parametrize(
    "message",
    [
        "Fix a thing\n\nMore detail.\n\nReviewed-by: Someone\n",
        "Fix a thing\n\nSigned-off-by: A\nX-Tool: y\n\n",
    ],
)
def test_message_trailer_block_is_flagged(message):
    s = scrub.Scanner([])
    s.scan_message("m", message)
    assert "trailer" in {f.category for f in s.findings}


@pytest.mark.parametrize(
    "message",
    ["Fix: a thing\n", "Fix a thing\n\nNote: this changes output.\nIt is clearer.\n"],
)
def test_message_without_trailer_block_passes(message):
    s = scrub.Scanner([])
    s.scan_message("m", message)
    assert s.findings == []


def test_message_skips_git_comments():
    s = scrub.Scanner([])
    s.scan_message("m", "Fix a thing\n\n# fixed in #" + "1234\n")
    assert s.findings == []


# -- end-to-end against a throwaway repository ---------------------------------
def _git(repo, *args, env=None):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


def _run(repo, *args, terms=None, extra_env=None):
    env = {k: v for k, v in os.environ.items() if k not in {"CI", "FE_SCRUB_TERMS"}}
    env["HOME"] = str(repo)  # keep the developer's own list out of the test
    if terms is not None:
        env["FE_SCRUB_TERMS"] = str(terms)
    env.update(extra_env or {})
    return subprocess.run(
        ["python3", str(SCRIPT), *args], cwd=repo, capture_output=True, text=True, env=env
    )


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Giant Octopus, LLC")
    _git(repo, "config", "user.email", "hello@giantoctopus.ink")
    (repo / "a.txt").write_text("hello\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "Initial")
    terms = tmp_path / "terms.txt"
    terms.write_text("zebra-widget\n")
    return repo, terms


def test_missing_list_fails_unless_generic_only(repo):
    path, _ = repo
    assert _run(path, "--tree").returncode == 2
    assert _run(path, "--tree", "--generic-only").returncode == 0


def test_missing_list_fails_closed_in_ci_and_release(repo):
    path, _ = repo
    assert _run(path, "--tree", "--generic-only", extra_env={"CI": "true"}).returncode == 2
    assert _run(path, "--tree", "--generic-only", "--release").returncode == 2


def test_tree_and_staged_find_private_terms(repo):
    path, terms = repo
    assert _run(path, "--tree", terms=terms).returncode == 0
    (path / "b.txt").write_text("a zebra-widget here\n")
    _git(path, "add", "b.txt")
    staged = _run(path, "--staged", terms=terms)
    assert staged.returncode == 1
    assert "b.txt:1 private-term ze...(len 12)" in staged.stdout
    assert "widget" not in staged.stdout


def test_range_and_history_check_identity_and_messages(repo):
    path, terms = repo
    env = dict(os.environ, GIT_AUTHOR_NAME="Someone", GIT_AUTHOR_EMAIL="someone" + "@example.org")
    (path / "c.txt").write_text("ok\n")
    _git(path, "add", "c.txt")
    _git(path, "commit", "-q", "-m", "Second\n\nTool: x", env=env)
    rng = _run(path, "--range", "HEAD~1..HEAD", terms=terms)
    assert rng.returncode == 1
    assert "identity" in rng.stdout and "trailer" in rng.stdout
    _git(path, "branch", "side")
    _git(path, "reset", "-q", "--hard", "HEAD~1")
    assert _run(path, "--history", "--ref", "main", terms=terms).returncode == 0
    assert _run(path, "--history", terms=terms).returncode == 1


def test_history_scans_unreachable_blob_versions(repo):
    path, terms = repo
    (path / "a.txt").write_text("zebra-widget\n")
    _git(path, "commit", "-q", "-am", "Change")
    (path / "a.txt").write_text("hello\n")
    _git(path, "commit", "-q", "-am", "Revert")
    assert _run(path, "--tree", terms=terms).returncode == 0
    assert _run(path, "--history", terms=terms).returncode == 1
