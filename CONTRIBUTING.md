# Contributing to AgriPredict

This repository is developed by a four-member team. These rules exist so that
four people can work in parallel without overwriting each other.

---

## 1. Roles and ownership

| Role | Owns | Branch |
| --- | --- | --- |
| Member 1 — Frontend | `frontend/` | `feature/frontend` |
| Member 2 — Backend | `backend/` | `feature/backend` |
| Member 3 — ML | `ml/` | `feature/ml-model` |
| Member 4 — Database | `database/` | `feature/database` |

**Ownership rule:** you may only modify another member's folder after that
member has agreed in the PR/issue thread. Shared files (root `README.md`,
`.env.example`, `.github/`, `tests/`, `docs/`) are changed via PR and reviewed by
the member whose module is affected.

No personal names, student IDs, or contact details are committed to this
repository. Use the generic role labels above.

## 2. First-time setup

```bash
git clone https://github.com/Rajputbrothers8184/AgriPredict.git
cd AgriPredict
git config user.name  "Your Name"
git config user.email "you@example.com"
git switch develop                 # never start work on main
cp .env.example .env               # fill in your own values; .env is ignored
```

Tool installation (Node, Python, JDK 17, Android Studio) is documented in
[`docs/installation/`](docs/installation/).

## 3. Branch model

```
main      ── stable, tested, release-tagged only
  └── develop ── integration branch, all features land here first
        ├── feature/frontend
        ├── feature/backend
        ├── feature/ml-model
        ├── feature/database
        ├── feature/<topic>      e.g. feature/weather-integration
        ├── bugfix/<topic>
        └── hotfix/<topic>       branches from main, merged to main + develop
```

Rules:

1. `main` is protected: no direct pushes, PRs only, CI must pass.
2. Branch from `develop`, not from `main` (except `hotfix/`).
3. Keep branches short-lived; rebase or merge `develop` in at least weekly.
4. Never delete or force-push someone else's branch.
5. One logical change per pull request.

## 4. Commits — Conventional Commits

```
<type>(<scope>): <subject>

[optional body — why, not what]

[optional footer: Refs #12]
```

Allowed types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`,
`build`, `ci`, `style`.

Scopes: `frontend`, `backend`, `ml`, `database`, `docs`, `ci`, `deps`, `repo`.

Good:

```
feat(backend): implement JWT refresh endpoint
fix(frontend): keep forecast chart labels on small screens
test(ml): assert 30-day forecast length and monotonic dates
docs: add PostgreSQL migration walkthrough
```

Rejected: `update`, `changes`, `final`, `testing`, `new files`, `complete
project`, or a message that does not describe the actual change.

## 5. Pull request checklist

Before opening a PR:

- [ ] Branch is up to date with `develop`
- [ ] `git status` shows only intended files
- [ ] No secrets, no `.env`, no keys, no personal data
- [ ] Relevant tests pass locally
- [ ] Docs updated if behaviour or setup changed
- [ ] PR description states **what** changed and **how it was verified**

Reviewers must approve; the author merges with squash or merge commit. Delete
the branch after merge.

## 6. Definition of done

A task is done when: code is committed in logical increments, tests exist and
pass, documentation reflects reality, CI is green, and any limitation is
recorded in `DEVELOPMENT_PROGRESS.md` rather than hidden.

## 7. Secrets hygiene

- `.env` is ignored — only `.env.example` is committed.
- Never paste tokens in issues, PRs, or chat.
- If a secret is committed: revoke/rotate it immediately, then tell the team
  lead; removing the file in a later commit is **not** sufficient (history
  retains it).

## 8. Staying in sync

```bash
git switch develop
git pull --ff-only origin develop
git switch feature/backend
git merge develop              # or: git rebase develop
# resolve conflicts, run tests, then push
git push origin feature/backend
```

Conflict guidance: never resolve a conflict by deleting the other member's
work; if unsure, ask in the PR thread.

## 9. Reporting issues

Use the templates in `.github/ISSUE_TEMPLATE/`. Include steps to reproduce,
expected vs actual behaviour, and environment (OS, Node/Python version, device).

## 10. Code style

- JavaScript/JSX: ESLint + Prettier (`npm run lint`, `npm run format`) — 2-space
  indent, single quotes, semicolons.
- Python: `ruff` + `black`-compatible 88-column formatting; type hints on
  public functions.
- SQL: lowercase keywords, one clause per line, explicit column lists.
- Tests live next to the module they cover, never in another member's folder.
