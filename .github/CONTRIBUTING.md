# Contributing

## Branches

- `main`: production-ready branch
- `dev`: integration branch for completed work
- `feature/*`: new work branched from `dev`
- `hotfix/*`: urgent fixes branched from `main`

Recommended flow:

1. Start from `dev` for features.
2. Start from `main` for hotfixes.
3. Merge feature work back into `dev`.
4. Merge hotfixes into `main` and back into `dev`.

## Commit messages

Use conventional commits:

```text
<type>(<scope>): <subject>

<body>

<footer>
```

Allowed types:

- `feat`
- `fix`
- `docs`
- `style`
- `refactor`
- `perf`
- `test`
- `chore`
- `build`

Rules:

- Subject line must be 72 characters or less.
- Type and scope must be lowercase.
- Body and footer are optional.
- Use `BREAKING CHANGE:` in the footer when a change is not backward compatible.

## Commit template

The repository ships with `.gitmessage`.

Enable it locally with:

```bash
git config --local commit.template .gitmessage
```

Check the current setting with:

```bash
git config --local --get commit.template
```

## Manual validation

Run the validator directly:

```bash
python scripts/validate_commit.py "feat(effect): add zoom parameter"
```

Or validate a commit message file the same way the hook does:

```bash
python scripts/validate_commit.py .git/COMMIT_EDITMSG
```

To run the minimal workflow checks:

```bash
python scripts/validate_commit_checks.py
```
