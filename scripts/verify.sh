#!/usr/bin/env bash
# Every local check for this repo, in one command. The commit hook (.claude/hooks/guard_git.py)
# runs it before each commit and CI runs it on every PR, so keep it under about a minute.
# Exits non-zero on any failure.
set -u
cd "$(dirname "$0")/.."
status=0

echo "== Unit tests =="
python3 -m unittest discover -s tests -p 'test_*.py' || status=1

exit $status
