#!/usr/bin/env python3
"""Validate conventional commit messages."""
from __future__ import annotations

from pathlib import Path
import re
import sys

TYPES = ['feat', 'fix', 'docs', 'style', 'refactor', 'perf', 'test', 'chore', 'build']
TYPE_PATTERN = '|'.join(TYPES)
SUBJECT_PATTERN = re.compile(
    rf'^(?P<type>{TYPE_PATTERN})(?:\((?P<scope>[a-z0-9._/-]+)\))?: (?P<subject>.+)$'
)
BREAKING_CHANGE_PATTERN = re.compile(r'^BREAKING CHANGE: .+$')


def _load_message(message_or_path: str) -> str:
    path = Path(message_or_path)
    if path.exists() and path.is_file():
        return path.read_text(encoding='utf-8').strip()
    return message_or_path.strip()


def _split_sections(message: str) -> tuple[str, list[str], list[str]]:
    lines = message.splitlines()
    if not lines:
        return '', [], []

    subject = lines[0].strip()
    remainder = [line.rstrip() for line in lines[1:]]

    while remainder and not remainder[0].strip():
        remainder.pop(0)

    if not remainder:
        return subject, [], []

    sections: list[list[str]] = [[]]
    for line in remainder:
        if not line.strip():
            if sections[-1]:
                sections.append([])
            continue
        sections[-1].append(line)

    sections = [section for section in sections if section]
    if not sections:
        return subject, [], []

    if len(sections) == 1:
        return subject, sections[0], []

    footer_candidate = sections[-1]
    if footer_candidate and footer_candidate[0].startswith('BREAKING CHANGE:'):
        body = [line for section in sections[:-1] for line in section]
        return subject, body, footer_candidate

    body = [line for section in sections for line in section]
    return subject, body, []


def _validate_footer_lines(footer: list[str]) -> tuple[bool, str]:
    for line in footer:
        if line.startswith('BREAKING CHANGE:'):
            if not BREAKING_CHANGE_PATTERN.match(line):
                return False, 'Invalid BREAKING CHANGE footer. Use: BREAKING CHANGE: description'
        elif line.strip() and not re.match(r'^[A-Za-z-]+: .+$', line):
            return False, 'Invalid footer. Use BREAKING CHANGE: description or token: value'
    return True, ''


def validate(message: str) -> tuple[bool, str]:
    message = message.strip()
    if not message:
        return False, 'Commit message is empty'

    subject, _body, footer = _split_sections(message)
    if not subject:
        return False, 'Commit message subject is missing'

    if len(subject) > 72:
        return False, f'Subject line exceeds 72 characters ({len(subject)} > 72)'

    match = SUBJECT_PATTERN.match(subject)
    if not match:
        return False, (
            'Invalid format. Use: type(scope): subject. '
            f'Allowed types: {", ".join(TYPES)}'
        )

    commit_type = match.group('type')
    scope = match.group('scope')
    if commit_type not in TYPES:
        return False, f'Invalid type: {commit_type}. Use: {", ".join(TYPES)}'
    if scope and scope != scope.lower():
        return False, 'Scope must be lowercase'

    ok, error = _validate_footer_lines(footer)
    if not ok:
        return False, error

    return True, 'Valid conventional commit'


def main(argv: list[str]) -> int:
    msg = argv[1] if len(argv) > 1 else sys.stdin.read()
    valid, result = validate(_load_message(msg))
    print(result)
    return 0 if valid else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
