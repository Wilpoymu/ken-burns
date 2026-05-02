#!/usr/bin/env python3
"""Minimal verification checks for commit validation and workflow."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from validate_commit import validate


ROOT = Path(__file__).resolve().parents[1]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_valid_commit() -> None:
    ok, message = validate('feat(effect): add zoom parameter to KenBurnsRenderer')
    check(ok, f'expected valid commit, got: {message}')


def test_invalid_commit() -> None:
    ok, message = validate('fixed bug')
    check(not ok, 'expected invalid commit')
    check('Invalid format' in message or 'Invalid type' in message, message)


def test_breaking_change_footer() -> None:
    ok, message = validate(
        'feat(api): change zoom scale\n\n'
        'Update the renderer to use normalized zoom values.\n\n'
        'BREAKING CHANGE: zoom now expects a float between 0 and 1'
    )
    check(ok, f'expected breaking change footer to validate, got: {message}')


def test_template_path_configured() -> None:
    result = subprocess.run(
        ['git', 'config', '--local', '--get', 'commit.template'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    template = result.stdout.strip()
    check(result.returncode == 0, 'commit.template is not configured')
    check(template == '.gitmessage', f'expected .gitmessage, got: {template or "<empty>"}')


def test_optional_body_only() -> None:
    ok, message = validate(
        'docs(readme): clarify workflow\n\n'
        'Explain the branch and commit rules more clearly.'
    )
    check(ok, f'expected optional body to validate, got: {message}')


def test_branch_workflow_evidence() -> None:
    current = subprocess.run(
        ['git', 'branch', '--show-current'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    check(current == 'dev', f'expected to be on dev, got: {current or "<unknown>"}')

    patterns = {
        'main': r'^main$',
        'dev': r'^dev$',
        'feature': r'^feature/[A-Z]+-\d+-[a-z0-9-]+$',
        'hotfix': r'^hotfix/[A-Z]+-\d+-[a-z0-9-]+$',
        'release': r'^release/\d+\.\d+\.\d+$',
    }
    samples = {
        'main': 'main',
        'dev': 'dev',
        'feature': 'feature/PROJ-123-add-ken-burns-effect',
        'hotfix': 'hotfix/PROJ-456-fix-crash-on-load',
        'release': 'release/1.2.3',
    }
    for name, pattern in patterns.items():
        check(re.match(pattern, samples[name]) is not None, f'branch pattern failed: {name}')

    hook = ROOT / '.git' / 'hooks' / 'commit-msg'
    check(hook.exists(), 'commit-msg hook is missing')
    content = hook.read_text(encoding='utf-8')
    check('scripts/validate_commit.py' in content, 'commit-msg hook does not invoke validator')


def main() -> int:
    test_valid_commit()
    test_optional_body_only()
    test_invalid_commit()
    test_breaking_change_footer()
    test_template_path_configured()
    test_branch_workflow_evidence()
    print('commit validation checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
