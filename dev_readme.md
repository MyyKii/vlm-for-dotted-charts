```markdown
# Developer Quickstart

## 1. Environment Setup

Create and activate your virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install ruff
pip install pytest

```

## 2. Code Quality & Formatting

Linting and formatting are pre-configured in the `Makefile`. Always run Ruff before committing or pushing your changes:

```bash
make ruff

```

## 3. Naming Conventions

Keep branch names and commit messages structured, lowercase, and descriptive. Do **not** use personal or ambiguous names (e.g., avoid `name_test_123` or generic commit messages like `fixed stuff`).

### 3.1 Branch Naming

Use slashes (`/`) to group branches by intent.

**Format:** `<type>/<short-description>`

* `feat/add-login-page` — New user-facing features
* `fix/resolve-auth-bug` — Bug fixes
* `chore/update-dependencies` — Maintenance, tooling, or dependency updates
* `refactor/optimize-queries` — Code restructuring without functional changes

---

### 3.2 Commit Naming (Conventional Commits)

Commit messages follow the [Conventional Commits](https://www.conventionalcommits.org/) specification to ensure automated changelog generation and clear Git history.

**Format:** `<type>(<optional-scope>): <short imperative description>`

#### Standard Types

| Type | Description | Example |
| --- | --- | --- |
| `feat` | A new feature | `feat(auth): add login page UI` |
| `fix` | A bug fix | `fix(api): resolve session timeout bug` |
| `docs` | Documentation changes only | `docs(quickstart): add commit naming guidelines` |
| `refactor` | Code changes that neither fix a bug nor add a feature | `refactor(db): optimize user lookup query` |
| `test` | Adding missing tests or correcting existing tests | `test(auth): add unit test for password hash` |
| `chore` | Maintenance tasks, build processes, or dependency updates | `chore(deps): bump ruff to version 0.3.0` |
| `ci` | Changes to CI/CD pipelines and scripts | `ci(github): add workflow for pull request linting` |

#### Rules

1. Use the **imperative mood** in the subject line (e.g., "add", not "added" or "adds").
2. Keep the first line under **50–72 characters**.
3. Do **not** capitalize the first letter of the description.
4. Do **not** end the description line with a period.

```

```