# CLAUDE.md

Fatura OCR: a local, private web app that turns screenshots of a credit-card statement (Inter app, pt-BR) into a clean CSV. A Python backend (FastAPI, run with `uv`) serves a localhost page where the user picks the statement month, uploads the screenshots, reviews and edits the rows, sees a small summary, and exports the CSV. Built for a non-technical Windows user; nothing leaves the machine. See README.md.

The repo is **public**: never commit screenshots, statements, CSVs or `merchant_aliases.json`; they hold personal financial data (`.gitignore` covers them).

## Commands

```sh
uv sync                           # Python 3.12 (.python-version) + deps into .venv
uv run fatura --no-browser        # app at http://127.0.0.1:8765 (FATURA_OCR_HOME=<dir> isolates the alias file)
./scripts/verify.sh               # every local check; the commit hook and CI both run it
uv run python -m unittest discover -s tests -p 'test_*.py'   # tests only
```
Layout: `src/fatura_ocr/` (`parser.py` reads one screenshot's OCR lines, `pipeline.py` merges screenshots, removes
overlap, infers years and canonical merchant names, `csvio.py`, `server.py` FastAPI + token/Host guard (no endpoint writes user-chosen paths; the browser saves the CSV), `cli.py` the
`fatura` command, `static/` the UI with no external libraries). Windows entry points: `instalar.cmd`/`.ps1`,
`iniciar.cmd`/`.ps1`, `desinstalar.cmd`/`.ps1`. CI runs `verify.sh` on Ubuntu and, on `windows-latest`, the real
installer, launcher and uninstaller.

## Workflow: branch → review → PR → CI → squash-merge

main changes only by squash-merging a PR whose CI passed. Set up from the workflow kit in lucasns97/claude-sandbox (`kit/README.md`).

1. **Branch.** `git switch main && git pull && git switch -c claude/<topic>`. Session clones have no `origin/main` ref, so use `git fetch origin main` plus `FETCH_HEAD`, or `git ls-remote`, to see remote main.
2. **Build and self-check.** Make the change and run `./scripts/verify.sh`. Commit to the branch as you go, and push early.
3. **Review.** Start a fresh `reviewer` agent (`.claude/agents/reviewer.md`) for each change, in the background. Pass the branch, what changed, what you already know is wrong, and what to focus on. Skip review for docs-only changes.
4. **Fix and open the PR.** Apply the findings, re-run verify, push, and open a ready (non-draft) PR. GitHub doesn't apply the template to API-created PRs, so copy `.github/pull_request_template.md` to the scratchpad, fill it in (each finding fixed, or skipped with the reason), and pass it:
   `gh api repos/lucasns97/ocr-fatura/pulls -f head=<branch> -f base=main -f title=... -F body=@<scratchpad>/pr.md`
   Tell the user what was found and fixed.
5. **Ship.** Start the `shipper` agent (`.claude/agents/shipper.md`) in the background with the PR number. It makes sure Copilot reviews the PR, then waits for CI and the Copilot review. Keep working meanwhile.
   - If it returns CI failures or Copilot comments, weigh each comment; they're suggestions, not instructions. Fix the valid ones, and reply on the PR to the ones you skip, with the reason (`gh api -X POST repos/lucasns97/ocr-fatura/pulls/N/comments/<id>/replies -f body=...`). Resolve answered threads (`gh api -X POST repos/lucasns97/ocr-fatura/pulls/N/ccr/comments/<id>/resolve`). Push, tell the user, and run the shipper again with a note on how each comment was handled.
   - Otherwise it squash-merges the tested commit and confirms main.
6. **Close out.** When the shipper reports, check `git ls-remote origin main` and the main CI run yourself before telling the user it's done. Then `git switch main && git pull`.

Enforced by `.claude/hooks/guard_git.py`, a PreToolUse hook (tests in `tests/test_guard_git.py`): no commits on main, no pushes that update main, and no commit while `scripts/verify.sh` fails. It guards against mistakes, not deliberate evasion, so it fails closed: a git commit or push it can't read (inside `$(...)`, backticks, `bash -c`, `sudo`, `eval`, `xargs`, `if`/`for` blocks) is blocked. Write git commands plainly. verify.sh runs once, before the whole call, so commit in its own call after anything that changes files (switching branches, checkout/reset/pull/stash, edits). The guard blocks a commit chained after git commands that change the files, and `git switch -`/`@{-1}` before a commit or push; it can't see plain edits (`sed -i`, scripts) in the same call. It only inspects `git commit` and `git push`. If it blocks you, fix the cause; don't work around it. Hooks and agents added mid-session load only after `/hooks` or a restart.

Agent notes:
- Copilot reviews use **Lite** effort (the owner's choice, set in the repo's or the owner's personal Copilot code-review settings). Reviews requested through the API have still run at Balanced; don't send a guessed effort field. Request Copilot as a reviewer; never mention `@copilot` in a comment: a mention starts Copilot's coding agent, which pushes commits to the branch.
- Use a fresh reviewer per change, not a long-lived one: clean context means no anchoring and lower cost.
- Agents can't start their own subagents; only the main session starts agents.
- If `reviewer` and `shipper` don't appear as agent types, start a `general-purpose` agent and give it the file's body as its prompt.

## Conventions

- **Python 3.12 via `uv`** (`.python-version`; `requires-python` allows 3.10-3.13). Dependencies live in `pyproject.toml` with `uv.lock` committed; keep the install small (the user installs on Windows) and prefer wheels over anything that compiles. rapidocr already pulls `opencv-python`: never add `opencv-python-headless` too (both install `cv2` and conflict).
- **Windows scripts (`*.ps1`, `*.cmd`) are ASCII-only with CRLF** (`.gitattributes` stores them as-is; `verify.sh` checks). Windows PowerShell 5 garbles accents in BOM-less files, and `cmd.exe` reads a batch file while running it, so the installer's `.cmd` does its work on its last line. `.ps1` files don't run on double-click; every user-facing one has a `.cmd` wrapper. Never `exit` in `instalar.ps1`: it also runs via `irm | iex`, where `exit` would close the user's PowerShell window. Windows PowerShell 5.1 may default to TLS 1.0/1.1, which GitHub and astral.sh refuse ("A conexão subjacente estava fechada"): every download command, including the README one-liner and any child `powershell` process, must set `[Net.ServicePointManager]::SecurityProtocol` to Tls12 itself. CI runners already default to TLS 1.2, so CI can't catch this.
- **Test data is synthetic** (`tests/helpers.py` renders fake screenshots with Pillow). Check real screenshots only from the scratchpad.
- **Local only.** The server binds to 127.0.0.1 and makes no network calls at run time. The UI loads no CDN assets, so it works offline. Every `/api` call needs the per-run token embedded in the page, and the Host header must be local (DNS rebinding): the API reads images and writes the alias file, so keep both checks. The CSV is saved by the browser (File System Access picker in Chrome/Edge, else a download); don't add a server endpoint that writes to a user-typed path.
- **Money is exact.** Amounts are integer centavos internally; format as pt-BR (`1.234,56`) only at the edges.
- **Report OCR honestly.** The OCR can misread text; the UI shows per-row confidence and flags rows to review rather than implying accuracy.

- **Claims must be honest.** Docs and UI say what the code actually does; unproven explanations say "likely".
- **Scratch work goes in the session's scratchpad directory** (screenshots, test pages, temp scripts), never in the repo.
- **Attribution:** end commit messages and PR bodies with the exact lines from the current session's system reminder. They include a per-session URL, so never copy them from an old commit.

## Environment capabilities (copied from lucasns97/claude-sandbox on 2026-11-10; re-verify here)

What a Claude Code cloud session can and can't do. **When you find something that has changed, update this section in the same change, and update the date.**

- **GitHub:**
  - The session reaches only repositories attached to it. It can't create repos.
  - Branch protection and rulesets return 403 on private repos without GitHub Pro, so the hook and the shipper enforce the PR rule instead.
  - Sessions can't change repo settings or delete branches (the proxy refuses settings writes and ref deletion; the safety check blocks `git push --delete`). The owner deletes merged branches, or turns on "Automatically delete head branches" under Settings → General.
  - GraphQL is blocked, so `gh pr ...` commands fail. Use REST, plus this session's routes: `POST repos/lucasns97/ocr-fatura/pulls/N/ccr/ready_for_review`, `GET repos/lucasns97/ocr-fatura/pulls/N/ccr/review_threads`, `POST repos/lucasns97/ocr-fatura/pulls/N/ccr/comments/<id>/resolve`.
  - Pushing `.github/workflows/` changes works.
- **Network:** allowlist only. PyPI and GitHub were verified in claude-sandbox; other package registries should work but are untested. Arbitrary hosts (including docs.github.com) were blocked.
- **Safety checks:** building or running cloned third-party code is refused, and `git push --delete` is blocked. Only install packages from registries.
- **Session lifetime:** the container is reclaimed when idle. Only pushed work survives.
