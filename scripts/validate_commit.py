#!/usr/bin/env python3
"""Validate conventional commit messages."""
import re
import sys

TYPES = ['feat', 'fix', 'docs', 'style', 'refactor', 'perf', 'test', 'chore', 'build']
PATTERN = r'^(feat|fix|docs|style|refactor|perf|test|chore|build)(\(.+\))?: .+$'


def validate(message: str) -> tuple[bool, str]:
    subject = message.split('\n')[0].strip()
    if len(subject) > 72:
        return False, f"Subject line exceeds 72 characters ({len(subject)})"
    if not re.match(PATTERN, subject):
        return False, f"Invalid format. Use: type(scope): description"
    commit_type = subject.split(':')[0].split('(')[0]
    if commit_type not in TYPES:
        return False, f"Invalid type: {commit_type}. Use: {', '.join(TYPES)}"
    return True, "Valid conventional commit"


if __name__ == '__main__':
    msg = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    valid, result = validate(msg)
    print(result)
    sys.exit(0 if valid else 1)