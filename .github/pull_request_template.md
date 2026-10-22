## Summary

<!-- What changes for someone using the server? -->

## Checks

- [ ] `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest` pass.
- [ ] `python3 scripts/scrub_check.py --staged` (or `--generic-only`) reported nothing.

## Publication review

- [ ] No personal names, email addresses or file paths from my machine.
- [ ] No credentials, tokens or keys, including in test fixtures.
- [ ] No references to other trackers, internal tools or private documents.
- [ ] Commit messages describe the user-visible change and carry no trailers.
- [ ] Test fixtures contain only public data or made-up values.
- [ ] A maintainer has completed the publication review (maintainers tick this).
