# BOOTSTRAP: one-shot setup and overnight build

You are Claude Code, running unattended in this folder while Vincent sleeps. Vincent has explicitly
authorized everything in this file, including creating a PUBLIC GitHub repo under his account and
pushing the first commit to `main`. Read CLAUDE.md as well; where the two differ, this file wins for
Phases 0-5 and CLAUDE.md wins from Phase 6 on.

Keep a running log in PROGRESS.md (create it). Never print or store tokens. Never claim a step worked
unless you ran it and read the real output.

## Phase 0: Preflight
1. Confirm `git`, `python` (3.10+), and `gh` exist. Run `gh auth status`.
2. Confirm the gh token has the `repo` and `workflow` scopes (pushing `.github/workflows/*` needs `workflow`).
3. If anything is missing, write exactly what is missing and the one command Vincent should run
   (e.g. `gh auth login -s workflow`) to `BOOTSTRAP_BLOCKED.md`, then STOP. Do not try to log in or work around auth.
4. Get his username: `gh api user -q .login`.

## Phase 1: Prepare the code
1. Replace every `YOUR_GITHUB_USERNAME` in src/ingest.py and README.md with that username.
2. Create a virtualenv (`.venv`), `pip install -r requirements.txt dbt-duckdb`, run `pytest -q`. All tests must pass.
   If the system Python is externally managed, the venv solves it. Fix real failures; do not skip tests.

## Phase 2: Create the repo and push main (authorized, one time)
1. `git init -b main`, `git add -A`, commit "Initial commit" (follow any commit-attribution instructions you were given).
   Ensure `.venv/` and `data_repo/` are not committed.
2. `gh repo create valenbisi-inventory-lab --public --source . --remote origin --push`
   (MIT license is already in the repo). If a repo with that name already exists, STOP and log it in
   BOOTSTRAP_BLOCKED.md. Do not overwrite or reuse an existing repo.

## Phase 3: Turn on and verify data collection
1. Make sure Actions is enabled. If workflows are disabled: `gh workflow enable ingest.yml`.
2. `gh workflow run ingest.yml`, wait for it (`gh run list --workflow ingest.yml --limit 1 --json status,conclusion,databaseId`, poll every ~15 s up to 5 min).
3. If it fails: read `gh run view <id> --log-failed`. Known fixes, in order:
   - Push permission error: `gh api -X PUT repos/<owner>/valenbisi-inventory-lab/actions/permissions/workflow -f default_workflow_permissions=write`
   - A genuine code bug in src/ingest.py: fix it, add a test that fails before and passes after, push to main, re-run.
   - Upstream feed unreachable or returning errors: that is NOT a code bug. Record it in PROGRESS.md and continue.
   Max 3 repair attempts, then log the blocker and move on.
4. Success = a `data` branch exists on GitHub and contains new parquet files.
   Check with `gh api repos/<owner>/valenbisi-inventory-lab/branches/data`.
5. Clone it: `git clone --branch data --single-branch https://github.com/<owner>/valenbisi-inventory-lab.git data_repo`,
   run `python src/check_data.py data_repo`, and record the real output summary in PROGRESS.md.
   Pay special attention to feed freshness (`feed_age_s`, `n_stale_1h`); write what the numbers actually show.
6. Scheduled runs happen on GitHub's clock from here on. Do not trigger more than the needed manual runs.

## Phase 4: Lock down future work
1. `git switch -c overnight`.
2. Copy `.claude/settings.overnight.json` to `.claude/settings.json`. Commit on `overnight` only.
3. From now on: never push to `main` or `data`, never force-push, never merge, never delete anything remote,
   never enable GitHub Pages or other publishing. Do not edit `.github/workflows/ingest.yml` or `src/ingest.py`
   unless fixing a proven bug with a failing-then-passing test (and note it in PROGRESS.md).

## Phase 5: Build (follow the roadmap in CLAUDE.md, steps 2 through 10, in order)
- Commit and `git push origin overnight` after every green checkpoint. Update PROGRESS.md each time.
- If a step is blocked, log why and move to the next one.
- Verify your own work by running tests / `dbt build` and reading the output.
- The collected history will be only a few hours old. Build and test everything against synthetic data
  and the small real sample; make NO claims about real forecasting performance.

## Phase 6: Finish
1. Update README so it describes only what actually exists and works now.
2. Open a pull request from `overnight` to `main` with `gh pr create` (do NOT merge). The description lists:
   done, skipped and why, what Vincent should review first, and any questions for him.
3. Final message: short summary: repo URL, whether collection is verified live, what was built, what is blocked.
