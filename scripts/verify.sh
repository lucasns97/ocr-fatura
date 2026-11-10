#!/usr/bin/env bash
# Every local check for this repo, in one command. The commit hook (.claude/hooks/guard_git.py)
# runs it before each commit and CI runs it on every PR, so keep it under about a minute.
# Exits non-zero on any failure.
set -u
cd "$(dirname "$0")/.."
status=0

# The app's tests need its dependencies, which uv installs into .venv (uv sync).
if command -v uv >/dev/null 2>&1; then
  py=(uv run --frozen python)
else
  echo "warning: uv not found; running with python3 (app tests fail without the dependencies)" >&2
  py=(python3)
fi

echo "== Unit tests (git guard, parser, pipeline, CSV, server, real OCR on synthetic screenshots) =="
"${py[@]}" -W ignore::DeprecationWarning -m unittest discover -s tests -p 'test_*.py' || status=1

echo "== Front-end syntax =="
if command -v node >/dev/null 2>&1; then
  node --check src/fatura_ocr/static/app.js || status=1
  node tests/js/money.test.js || status=1
  node tests/js/stream.test.js || status=1
else
  echo "skipped: node not installed"
fi

echo "== Windows scripts: ASCII only, CRLF line endings =="
for f in *.ps1 *.cmd; do
  if LC_ALL=C grep -q '[^[:print:][:space:]]' "$f"; then echo "$f: non-ASCII character (PowerShell 5 would garble it)"; status=1; fi
  if [ "$(grep -c $'\r$' "$f")" != "$(wc -l < "$f")" ]; then echo "$f: not CRLF"; status=1; fi
done

exit $status
