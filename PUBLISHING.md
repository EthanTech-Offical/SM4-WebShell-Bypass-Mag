# Publishing to GitHub

This repository is ready to publish. Before pushing, do these three things.

## 1. Replace the placeholders

- `pyproject.toml` has no repository URL yet; add `[project.urls]` if you want PyPI links:

  ```toml
  [project.urls]
  Homepage = "https://github.com/<you>/webshell-mag"
  Repository = "https://github.com/<you>/webshell-mag"
  Issues = "https://github.com/<you>/webshell-mag/issues"
  ```

## 2. Initialize and push

```bash
git init -b main
git add .
git commit -m "initial commit"
git remote add origin git@github.com:<you>/webshell-mag.git
git push -u origin main
```

## 3. Check what is committed

```bash
git status --short
git ls-files | grep -E 'shell\.php|\.env|credentials|dist/' && echo "remove secrets/artifacts!"
```

The `.gitignore` already excludes:

- `.venv/`, `__pycache__/`, build/dist
- generated payloads (`shell.php`, `*.webshell.php`)
- local credentials, `.env*`, logs
- archives and local docs artifacts

## GitHub Actions scope

If `git push` is rejected with:

```
refusing to allow a Personal Access Token to create or update workflow
.github/workflows/ci.yml without `workflow` scope
```

the token used for HTTPS push lacks the `workflow` scope. Either:

- create a fine-grained/classic PAT with **workflow** permission and update the
  keychain entry, or
- add the workflow file through the GitHub web UI (Actions → New workflow).

After fixing the credential:

```bash
git add -f .github/workflows/ci.yml
git commit -m "ci: add workflow"
git push
```

## Optional

- Enable **Private vulnerability reporting** in Settings → Security.
- Add a repository description/topics: `webshell`, `security`, `sm4`, `qt6`, `php`.
- Enable Dependabot alerts.
