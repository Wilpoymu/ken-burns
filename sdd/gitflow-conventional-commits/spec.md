# Spec: gitflow-conventional-commits

## Overview

This specification defines the Gitflow branching model with conventional commits for the ken-burns project, using `dev` as the integration branch name.

---

## ADDED Requirements

### Requirement: Branch Naming Convention

The project MUST use the following branch naming strategy:

| Branch Type | Pattern | Base Branch | Merges To |
|-------------|---------|--------------|-----------|
| main | `main` | - | - |
| dev | `dev` | main | main |
| feature | `feature/<ticket>-<description>` | dev | dev |
| hotfix | `hotfix/<ticket>-<description>` | main | main & dev |
| release | `release/<version>` | dev | main & dev |

#### Scenario: Create feature branch

- GIVEN developer is on `dev` branch with clean working tree
- WHEN developer creates `feature/PROJ-123-add-ken-burns-effect`
- THEN branch is created off `dev`
- AND developer can commit with conventional format

#### Scenario: Emergency hotfix

- GIVEN production issue requires immediate fix
- WHEN developer creates `hotfix/PROJ-456-fix-crash-on-load` from `main`
- THEN fix is applied and merged to both `main` and `dev`

---

### Requirement: Conventional Commits Format

All commit messages MUST follow this format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Subject Line Rules:**
- Maximum 72 characters
- Use imperative mood (add, not added/adding)
- Lowercase for type and scope

**Types:**
| Type | Description |
|------|-------------|
| feat | New feature |
| fix | Bug fix |
| docs | Documentation only |
| style | Code style (formatting, semicolons) |
| refactor | Code restructuring without behavior change |
| perf | Performance improvement |
| test | Adding/updating tests |
| chore | Maintenance, dependencies, build |
| build | Build system or dependencies |

**Scope:** Optional. Module/component affected (e.g., `feat(video):`, `fix(export):`)

#### Scenario: Valid feature commit

- GIVEN developer adds Ken Burns zoom effect
- WHEN committing with `feat(effect): add zoom parameter to KenBurnsRenderer`
- THEN commit is accepted by validation

#### Scenario: Breaking change footer

- GIVEN developer changes API that breaks backward compatibility
- WHEN commit includes `BREAKING CHANGE: zoom param now expects float instead of int`
- THEN validation recognizes breaking change

---

### Requirement: Commit Message Validation

The system MUST validate commit messages locally before acceptance.

**Implementation Options:**
1. Git hook at `.git/hooks/commit-msg`
2. Python script `scripts/validate_commit.py`

**Validation Rules:**
1. Subject line matches pattern: `^(feat|fix|docs|style|refactor|perf|test|chore|build)(\(.+\))?: .+$`
2. Subject line length <= 72 characters
3. Type is from allowed list
4. Breaking changes properly formatted in footer

#### Scenario: Reject invalid commit

- GIVEN developer attempts commit with "fixed bug" (no type)
- WHEN validation runs
- THEN commit is rejected
- AND error message shows correct format

---

### Requirement: Commit Template

The project SHOULD provide a `.gitmessage` template to assist developers.

**Template Content:**
```
# <type>(<scope>): <subject>
#
# Body: Describe what and why (not how)
#
# Types: feat, fix, docs, style, refactor, perf, test, chore, build
# Footer: BREAKING CHANGE: or Closes #<issue>
```

#### Scenario: Use commit template

- GIVEN developer runs `git commit`
- THEN template appears in editor
- AND developer fills in type, scope, description

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `.gitmessage` | Create | Commit message template |
| `.git/hooks/commit-msg` | Create | Validation hook |
| `scripts/validate_commit.py` | Create | Python validation script |
| `.github/CONTRIBUTING.md` | Create (optional) | Contribution guidelines |

---

## Workflow Summary

1. **Start work**: `git checkout dev && git pull && git checkout -b feature/PROJ-123-description`
2. **Commit**: Use conventional format with type/scope/description
3. **Push**: `git push -u origin feature/PROJ-123-description`
4. **PR/MR**: Create merge request to `dev`
5. **Release**: Merge `dev` to `main` with version tag
