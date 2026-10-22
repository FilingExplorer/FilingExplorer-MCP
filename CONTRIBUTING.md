# Contributing

Thanks for your interest in the FilingExplorer MCP server. Bug reports and pull requests are
welcome.

## Setup

```bash
uv sync --all-groups
sh scripts/install-hooks.sh
```

`install-hooks.sh` points git at the hooks in `.githooks/`:

- **pre-commit** checks the lines you are adding and any new file names.
- **commit-msg** checks the commit message.
- **pre-push** checks every commit you push, and only allows pushes of `main` and tags.

The hooks run `scripts/scrub_check.py`, which looks for content that does not belong in a public
repository: personal file paths, local tool directories, credentials and tokens, email addresses,
issue numbers from other trackers, and commit trailers. Maintainers run additional checks
before merging. To run the built-in checks yourself:

```bash
python3 scripts/scrub_check.py --staged --generic-only
python3 scripts/scrub_check.py --tree --generic-only
```

## Commits

- Commits on `main` use the project identity, `Giant Octopus, LLC <hello@giantoctopus.ink>`.
  A maintainer applies it when merging an outside contribution.
- Do not add trailers to commit messages (co-author, session or tool lines).
- Do not reference issue numbers in commit messages. Describe the change a user would notice.

## Pull requests

- Run `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest` before opening a
  pull request.
- Every pull request needs a maintainer's publication review before it is merged. The reviewer
  checks the diff, the commit messages and the commit identities, and runs the full check.
- Fill in the checklist in the pull request template.

## License

By contributing you agree that your contribution is licensed under the Apache License 2.0.
