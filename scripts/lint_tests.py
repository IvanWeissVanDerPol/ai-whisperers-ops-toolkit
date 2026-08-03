#!/usr/bin/env python3
"""
test-doc-standard linter — checks Python pytest and TypeScript Jest tests
for compliance with the AAA + Verifies-that pattern.

Usage:
    python3 lint_tests.py --path <file_or_dir>           # lint one
    python3 lint_tests.py --path <dir> --recursive       # lint all
    python3 lint_tests.py --path <dir> --json            # json output

Exit codes:
    0  clean
    1  violations found
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

PY_TEST_RE = re.compile(r'^(class\s+Test\w+|def\s+test_\w+)', re.MULTILINE)
TS_TEST_RE = re.compile(r'^\s*(describe\(|it\(|test\()', re.MULTILINE)
PY_DOCSTRING_RE = re.compile(r'"""([^"]+)"""', re.MULTILINE)

def lint_python(path: Path) -> list[dict]:
    text = path.read_text(encoding='utf-8', errors='replace')
    violations = []
    # find every class Test* and def test_*
    for m in re.finditer(r'(class\s+(Test\w+)\s*:|def\s+(test_\w+)\s*\()', text):
        kind, name = (m.group(2), m.group(2)) if 'class' in m.group(0) else ('def', m.group(3))
        # find docstring (next """ block) — for classes, docstring is right after `:`;
        # for methods, docstring is right after `(self)` or params.
        start = m.end()
        snippet = text[start:start + 500]
        doc_match = PY_DOCSTRING_RE.search(snippet)
        if not doc_match:
            violations.append({
                'file': str(path), 'line': text[:m.start()].count('\n') + 1,
                'kind': kind, 'name': name,
                'rule': 'missing-docstring',
                'fix': f'Add a one-line docstring starting with "Verifies that".',
            })
            continue
        doc = doc_match.group(1).strip()
        if not doc.lower().startswith('verifies that'):
            violations.append({
                'file': str(path), 'line': text[:m.start()].count('\n') + 1,
                'kind': kind, 'name': name,
                'rule': 'docstring-not-verifies',
                'fix': f'Docstring must start with "Verifies that". Currently: "{doc[:60]}..."',
            })
    return violations

def lint_typescript(path: Path) -> list[dict]:
    text = path.read_text(encoding='utf-8', errors='replace')
    violations = []
    # very lightweight — look for describe() with a string arg that's not a 'Verifies that' pattern
    for m in re.finditer(r'(describe|it|test)\(\s*[\'"`]([^\'"`]+)[\'"`]', text):
        verb, label = m.group(1), m.group(2)
        # it's OK for `describe` to be a feature/section name; check `it`/`test`
        if verb in ('it', 'test') and not label.lower().startswith('verifies that'):
            violations.append({
                'file': str(path), 'line': text[:m.start()].count('\n') + 1,
                'kind': verb, 'name': label[:60],
                'rule': 'test-label-not-verifies',
                'fix': f'{verb}() label should start with "Verifies that". Currently: "{label[:60]}".',
            })
    return violations

def lint(path: Path, recursive: bool) -> list[dict]:
    if path.is_file():
        files = [path]
    else:
        pattern = '**/*.py' if recursive else '*.py'
        files = [p for p in path.glob(pattern) if 'test' in p.name.lower() or p.name.startswith('test_')]
        files += [p for p in path.glob('**/*.test.ts' if recursive else '*.test.ts')]
        files += [p for p in path.glob('**/*.spec.ts' if recursive else '*.spec.ts')]
    all_v = []
    for f in files:
        if f.suffix == '.py':
            all_v += lint_python(f)
        elif f.suffix == '.ts':
            all_v += lint_typescript(f)
    return all_v

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--path', required=True)
    ap.add_argument('--recursive', action='store_true')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    p = Path(args.path).expanduser()
    if not p.exists():
        print(f'ERROR: {p} not found', file=sys.stderr)
        return 1
    violations = lint(p, args.recursive)
    if args.json:
        print(json.dumps(violations, indent=2))
    elif violations:
        print(f'{len(violations)} violation(s):')
        for v in violations:
            print(f"  {v['file']}:{v['line']}  [{v['rule']}]  {v['kind']} {v['name']}")
            print(f"    fix: {v['fix']}")
    else:
        print('OK — no violations')
    return 1 if violations else 0

if __name__ == '__main__':
    sys.exit(main())
