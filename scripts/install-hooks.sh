#!/bin/sh
# Point git at the repository's hooks.
set -e
cd "$(git rev-parse --show-toplevel)"
chmod +x .githooks/* scripts/scrub_check.py
git config core.hooksPath .githooks
echo "Hooks installed (core.hooksPath=.githooks)."
